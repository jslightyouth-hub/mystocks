import argparse
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import text

import backfill_missing_daily_quotes as daily_backfill
import sync_stock_company_profile
import sync_stock_industries
import sync_stock_margin_detail
import sync_stock_premarket
import sync_daily_quote_metrics
import update_stocks
from settings import DATABASE_URL, TUSHARE_TOKEN
from sync_daily_quotes import REQUEST_INTERVAL_SECONDS, create_daily_quotes_table, engine, save_daily_quotes


DEFAULT_LOOKBACK_OPEN_DAYS = 5
SAMPLE_LIMIT = 5


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run the daily incremental market data update: stocks, company profiles, "
            "industries, daily quotes, stock_premarket, margin_detail, daily_quote_metrics, "
            "and final data-quality checks."
        )
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Last date to check in YYYYMMDD format. Default: today.",
    )
    parser.add_argument(
        "--lookback-open-days",
        type=int,
        default=DEFAULT_LOOKBACK_OPEN_DAYS,
        help="Recent open trading days to re-check. Default: 5.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch/check data and print planned writes without changing the database.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh daily quote dates even when row counts already match Tushare.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit stock and industry rows for development testing.",
    )
    parser.add_argument("--skip-stocks", action="store_true", help="Skip stocks table update.")
    parser.add_argument(
        "--skip-company-profiles",
        action="store_true",
        help="Skip stock_company company profile update.",
    )
    parser.add_argument("--skip-industries", action="store_true", help="Skip Shenwan industry update.")
    parser.add_argument("--skip-quotes", action="store_true", help="Skip daily quote update.")
    parser.add_argument("--skip-premarket", action="store_true", help="Skip stock_premarket update.")
    parser.add_argument("--skip-margin-detail", action="store_true", help="Skip stock_margin_detail update.")
    parser.add_argument("--skip-quote-metrics", action="store_true", help="Skip daily_quote_metrics calculation.")
    return parser.parse_args()


def today():
    return datetime.now().strftime("%Y%m%d")


def validate_yyyymmdd(value, name):
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise SystemExit(f"{name} must be YYYYMMDD, got {value!r}") from exc


def table_exists(table_name):
    with engine.connect() as conn:
        return conn.execute(
            text("SHOW TABLES LIKE :table_name"),
            {"table_name": table_name},
        ).first() is not None


def get_daily_quote_status(create_if_missing=False):
    if create_if_missing:
        create_daily_quotes_table()
    elif not table_exists("daily_quotes"):
        return {
            "latest_trade_date": None,
            "latest_updated_at": None,
            "row_count": 0,
        }

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    MAX(trade_date) AS latest_trade_date,
                    MAX(updated_at) AS latest_updated_at,
                    COUNT(*) AS row_count
                FROM daily_quotes
            """)
        ).mappings().one()
    return dict(row)


def get_premarket_status():
    if not table_exists("stock_premarket"):
        return {
            "latest_trade_date": None,
            "latest_updated_at": None,
            "row_count": 0,
        }

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    MAX(trade_date) AS latest_trade_date,
                    MAX(updated_at) AS latest_updated_at,
                    COUNT(*) AS row_count
                FROM stock_premarket
            """)
        ).mappings().one()
    return dict(row)


def get_margin_detail_status():
    if not table_exists("stock_margin_detail"):
        return {
            "latest_trade_date": None,
            "latest_updated_at": None,
            "row_count": 0,
        }

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    MAX(trade_date) AS latest_trade_date,
                    MAX(updated_at) AS latest_updated_at,
                    COUNT(*) AS row_count
                FROM stock_margin_detail
            """)
        ).mappings().one()
    return dict(row)


def quote_count(trade_date):
    if not table_exists("daily_quotes"):
        return 0
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM daily_quotes WHERE trade_date = :trade_date"),
            {"trade_date": trade_date},
        ).scalar_one()


def premarket_count(trade_date):
    if not table_exists("stock_premarket"):
        return 0
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM stock_premarket WHERE trade_date = :trade_date"),
            {"trade_date": trade_date},
        ).scalar_one()


def margin_detail_count(trade_date):
    if not table_exists("stock_margin_detail"):
        return 0
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM stock_margin_detail WHERE trade_date = :trade_date"),
            {"trade_date": trade_date},
        ).scalar_one()


def quote_metrics_count(trade_date):
    if not table_exists("daily_quote_metrics"):
        return 0
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM daily_quote_metrics WHERE trade_date = :trade_date"),
            {"trade_date": trade_date},
        ).scalar_one()


def print_section(title):
    print("")
    print("=" * 78)
    print(title)
    print("=" * 78)


def run_stock_update(args):
    print_section("1. Update stocks")
    status = update_stocks.get_database_status()
    print(f"Existing stocks: {status['row_count']}")

    latest_rows = update_stocks.fetch_latest_stocks(limit=args.limit)
    existing_rows = update_stocks.get_existing_stocks()
    new_rows, changed_rows = update_stocks.diff_stocks(latest_rows, existing_rows)

    print(f"Tushare listed stocks checked: {len(latest_rows)}")
    print(f"New stocks: {len(new_rows)}")
    print(f"Changed stocks: {len(changed_rows)}")

    if args.dry_run:
        print("Dry run: would save new/changed stocks; new-stock history backfill is intentionally skipped.")
        return {
            "new": len(new_rows),
            "changed": len(changed_rows),
            "saved": 0,
        }

    update_stocks.ensure_stocks_table()
    saved_count = update_stocks.save_stocks(new_rows + changed_rows)
    print(f"Saved or updated stock rows: {saved_count}")
    print("Skipped per-stock historical quote backfill; daily quotes are handled by trade date below.")
    return {
        "new": len(new_rows),
        "changed": len(changed_rows),
        "saved": saved_count,
    }


def run_company_profile_update(args):
    print_section("2. Update stock company profiles")

    latest_rows = sync_stock_company_profile.dedupe_company_profiles(
        sync_stock_company_profile.fetch_company_profiles(limit=args.limit)
    )
    existing_rows = sync_stock_company_profile.get_existing_company_profiles()
    new_rows, changed_rows = sync_stock_company_profile.diff_company_profiles(
        latest_rows,
        existing_rows,
    )

    print(f"Tushare company profiles checked: {len(latest_rows)}")
    print(f"New company profiles: {len(new_rows)}")
    print(f"Changed company profiles: {len(changed_rows)}")

    if args.dry_run:
        print("Dry run: would save new/changed company profiles.")
        return {
            "checked": len(latest_rows),
            "new": len(new_rows),
            "changed": len(changed_rows),
            "saved": 0,
        }

    sync_stock_company_profile.create_stock_company_profile_table()
    saved_count = sync_stock_company_profile.save_company_profiles(new_rows + changed_rows)
    print(f"Saved or updated company profile rows: {saved_count}")
    return {
        "checked": len(latest_rows),
        "new": len(new_rows),
        "changed": len(changed_rows),
        "saved": saved_count,
    }


def run_industry_update(args):
    print_section("3. Update Shenwan industries")

    if args.dry_run:
        rows = sync_stock_industries.dedupe_industries(
            sync_stock_industries.fetch_current_industries(limit=args.limit)
        )
        print(f"Dry run: fetched {len(rows)} industry rows; no stock rows were updated.")
        return {"fetched": len(rows), "updated": 0}

    added_columns = sync_stock_industries.ensure_industry_columns()
    if added_columns:
        print("Added industry columns: " + ", ".join(added_columns))
    else:
        print("Industry columns already exist.")

    rows = sync_stock_industries.dedupe_industries(
        sync_stock_industries.fetch_current_industries(limit=args.limit)
    )
    updated_count = sync_stock_industries.save_industries(rows)
    print(f"Fetched industry rows: {len(rows)}")
    print(f"Updated stock rows: {updated_count}")
    return {"fetched": len(rows), "updated": updated_count}


def get_quote_target_dates(args, status, end_date):
    helper_args = SimpleNamespace(
        start_date=None,
        end_date=end_date,
        lookback_open_days=max(args.lookback_open_days, 0),
        init_days=30,
        dry_run=args.dry_run,
        force_refresh=args.force_refresh,
    )
    start_date = daily_backfill.choose_start_date(
        helper_args,
        status["latest_trade_date"],
        end_date,
    )
    open_dates = daily_backfill.get_open_trade_dates(start_date, end_date)
    target_dates = daily_backfill.keep_recent_window(
        open_dates,
        status["latest_trade_date"],
        max(args.lookback_open_days, 0),
    )
    return start_date, open_dates, target_dates


def run_daily_quote_update(args, end_date):
    print_section("4. Backfill daily quotes")
    status = get_daily_quote_status(create_if_missing=not args.dry_run)
    print(f"Existing daily quote rows: {status['row_count']}")
    print(f"Latest daily quote trade_date: {status['latest_trade_date'] or 'none'}")

    start_date, open_dates, target_dates = get_quote_target_dates(args, status, end_date)
    if not open_dates:
        print(f"No open trading days found from {start_date} to {end_date}.")
        return {
            "target_dates": [],
            "updated_dates": [],
            "skipped_dates": [],
            "failed_dates": [],
            "total_saved": 0,
        }

    if not target_dates:
        print(f"No target trading days found from {start_date} to {end_date}.")
        return {
            "target_dates": [],
            "updated_dates": [],
            "skipped_dates": [],
            "failed_dates": [],
            "total_saved": 0,
        }

    print(f"Checking open trading days: {target_dates[0]} to {target_dates[-1]} ({len(target_dates)} day(s))")
    existing_counts = daily_backfill.get_existing_counts(target_dates)
    updates_needed, skipped_dates = daily_backfill.find_updates_needed(
        target_dates,
        existing_counts,
        args.force_refresh,
    )

    if args.dry_run:
        update_dates = [item["trade_date"] for item in updates_needed]
        print("Dry run: would update daily quotes for: " + (", ".join(update_dates) or "none"))
        return {
            "target_dates": target_dates,
            "updated_dates": [],
            "skipped_dates": skipped_dates,
            "failed_dates": [],
            "total_saved": 0,
        }

    total_saved = 0
    updated_dates = []
    failed_dates = []
    for index, item in enumerate(updates_needed, start=1):
        trade_date = item["trade_date"]
        try:
            saved_count = save_daily_quotes(item["df"])
            total_saved += saved_count
            updated_dates.append(trade_date)
            print(
                f"[{index}/{len(updates_needed)}] {trade_date}: "
                f"saved or updated {saved_count} daily quote row(s)"
            )
        except Exception as exc:
            failed_dates.append(trade_date)
            print(f"[{index}/{len(updates_needed)}] {trade_date}: failed: {exc}")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    print(f"Daily quote update finished. Saved or updated {total_saved} row(s).")
    if failed_dates:
        print("Failed daily quote dates: " + ", ".join(failed_dates))

    return {
        "target_dates": target_dates,
        "updated_dates": updated_dates,
        "skipped_dates": skipped_dates,
        "failed_dates": failed_dates,
        "total_saved": total_saved,
    }


def choose_premarket_dates(args, quote_result):
    target_dates = list(quote_result.get("target_dates") or [])
    if target_dates:
        return target_dates

    latest_trade_date = get_daily_quote_status(create_if_missing=False)["latest_trade_date"]
    return [latest_trade_date] if latest_trade_date else []


def run_premarket_update(args, quote_result):
    print_section("5. Sync stock_premarket")
    trade_dates = choose_premarket_dates(args, quote_result)
    if not trade_dates:
        print("No daily quote trade dates available; stock_premarket sync skipped.")
        return {"updated_dates": [], "empty_dates": [], "failed_dates": [], "total_saved": 0}

    print("Premarket target dates: " + ", ".join(trade_dates))

    if not args.dry_run:
        sync_stock_premarket.create_stock_premarket_table()

    total_saved = 0
    updated_dates = []
    empty_dates = []
    failed_dates = []

    for index, trade_date in enumerate(trade_dates, start=1):
        try:
            df = sync_stock_premarket.fetch_stock_premarket(trade_date)
            fetched_count = len(df)
            source = getattr(df, "attrs", {}).get("source", "daily_basic")
            print(
                f"[{index}/{len(trade_dates)}] {trade_date}: "
                f"fetched {fetched_count} stock_premarket row(s) from {source}"
            )
            if fetched_count == 0:
                empty_dates.append(trade_date)
                print(f"{trade_date}: Tushare returned 0 share rows; data may not be published yet.")
                continue
            if args.dry_run:
                continue
            saved_count = sync_stock_premarket.save_stock_premarket(df)
            total_saved += saved_count
            updated_dates.append(trade_date)
            print(f"{trade_date}: saved or updated {saved_count} stock_premarket row(s)")
        except Exception as exc:
            failed_dates.append(trade_date)
            print(f"{trade_date}: stock_premarket sync failed: {exc}")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    if args.dry_run:
        print("Dry run: no stock_premarket rows were written.")
    else:
        print(f"Premarket sync finished. Saved or updated {total_saved} row(s).")

    return {
        "updated_dates": updated_dates,
        "empty_dates": empty_dates,
        "failed_dates": failed_dates,
        "total_saved": total_saved,
    }


def run_margin_detail_update(args, quote_result):
    print_section("6. Sync stock_margin_detail")
    trade_dates = choose_premarket_dates(args, quote_result)
    if not trade_dates:
        print("No daily quote trade dates available; stock_margin_detail sync skipped.")
        return {"updated_dates": [], "empty_dates": [], "failed_dates": [], "total_saved": 0}

    print("Margin detail target dates: " + ", ".join(trade_dates))
    existing_counts = sync_stock_margin_detail.get_existing_counts(trade_dates)

    if not args.dry_run:
        sync_stock_margin_detail.create_stock_margin_detail_table()

    total_saved = 0
    updated_dates = []
    empty_dates = []
    failed_dates = []

    for index, trade_date in enumerate(trade_dates, start=1):
        existing_count = existing_counts.get(trade_date, 0)
        try:
            df = sync_stock_margin_detail.fetch_margin_detail(trade_date)
            fetched_count = len(df)
            print(
                f"[{index}/{len(trade_dates)}] {trade_date}: "
                f"fetched {fetched_count} stock_margin_detail row(s), existing {existing_count}"
            )
            if fetched_count == 0:
                empty_dates.append(trade_date)
                print(f"{trade_date}: Tushare returned 0 margin_detail rows; data may not be published yet.")
                continue
            if not args.force_refresh and existing_count >= fetched_count:
                print(f"{trade_date}: stock_margin_detail already complete.")
                continue
            if args.dry_run:
                continue
            saved_count = sync_stock_margin_detail.save_margin_detail(df)
            total_saved += saved_count
            updated_dates.append(trade_date)
            print(f"{trade_date}: saved or updated {saved_count} stock_margin_detail row(s)")
        except Exception as exc:
            failed_dates.append(trade_date)
            print(f"{trade_date}: stock_margin_detail sync failed: {exc}")
        time.sleep(sync_stock_margin_detail.REQUEST_INTERVAL_SECONDS)

    if args.dry_run:
        print("Dry run: no stock_margin_detail rows were written.")
    else:
        print(f"Margin detail sync finished. Saved or updated {total_saved} row(s).")

    return {
        "updated_dates": updated_dates,
        "empty_dates": empty_dates,
        "failed_dates": failed_dates,
        "total_saved": total_saved,
    }


def run_quote_metrics_update(args):
    print_section("7. Calculate daily_quote_metrics")
    latest_trade_date = get_daily_quote_status(create_if_missing=False)["latest_trade_date"]
    if not latest_trade_date:
        print("No daily quote trade date available; daily_quote_metrics calculation skipped.")
        return {"trade_date": None, "calculated": 0, "saved": 0}

    result = sync_daily_quote_metrics.sync_daily_quote_metrics(latest_trade_date, dry_run=args.dry_run)
    print(f"daily_quote_metrics trade_date: {result['trade_date']}")
    print(f"daily_quote_metrics calculated rows: {result['calculated']}")
    if args.dry_run:
        print("Dry run: no daily_quote_metrics rows were written.")
    else:
        print(f"daily_quote_metrics saved rows: {result['saved']}")
    return result


def get_latest_verification():
    if not table_exists("daily_quotes"):
        return {
            "latest_trade_date": None,
            "quote_count": 0,
            "premarket_count": 0,
            "margin_detail_count": 0,
            "quote_metrics_count": 0,
            "missing_float_share_count": 0,
            "samples": [],
        }

    latest_trade_date = get_daily_quote_status(create_if_missing=False)["latest_trade_date"]
    if not latest_trade_date:
        return {
            "latest_trade_date": None,
            "quote_count": 0,
            "premarket_count": 0,
            "margin_detail_count": 0,
            "quote_metrics_count": 0,
            "missing_float_share_count": 0,
            "samples": [],
        }

    premarket_exists = table_exists("stock_premarket")
    if premarket_exists:
        missing_sql = text("""
            SELECT COUNT(*)
            FROM daily_quotes q
            LEFT JOIN stock_premarket p
                ON p.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
                AND p.trade_date = q.trade_date COLLATE utf8mb4_unicode_ci
            WHERE q.trade_date = :trade_date
                AND (p.float_share IS NULL OR p.float_share = 0)
        """)
        sample_sql = text("""
            SELECT
                q.ts_code,
                s.name,
                q.close,
                q.vol,
                p.float_share,
                CASE
                    WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                    ELSE q.vol / p.float_share
                END AS turnover_rate,
                p.total_share,
                CASE
                    WHEN p.total_share IS NULL OR p.total_share = 0 THEN NULL
                    ELSE q.close * p.total_share
                END AS market_value
            FROM daily_quotes q
            LEFT JOIN stocks s ON s.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
            LEFT JOIN stock_premarket p
                ON p.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
                AND p.trade_date = q.trade_date COLLATE utf8mb4_unicode_ci
            WHERE q.trade_date = :trade_date
            ORDER BY q.amount DESC
            LIMIT :limit
        """)
    else:
        missing_sql = text("""
            SELECT COUNT(*)
            FROM daily_quotes q
            WHERE q.trade_date = :trade_date
        """)
        sample_sql = text("""
            SELECT
                q.ts_code,
                s.name,
                q.close,
                q.vol,
                NULL AS float_share,
                NULL AS turnover_rate,
                NULL AS total_share,
                NULL AS market_value
            FROM daily_quotes q
            LEFT JOIN stocks s ON s.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
            WHERE q.trade_date = :trade_date
            ORDER BY q.amount DESC
            LIMIT :limit
        """)

    with engine.connect() as conn:
        missing_count = conn.execute(missing_sql, {"trade_date": latest_trade_date}).scalar_one()
        samples = conn.execute(
            sample_sql,
            {"trade_date": latest_trade_date, "limit": SAMPLE_LIMIT},
        ).mappings().all()

    return {
        "latest_trade_date": latest_trade_date,
        "quote_count": quote_count(latest_trade_date),
        "premarket_count": premarket_count(latest_trade_date),
        "margin_detail_count": margin_detail_count(latest_trade_date),
        "quote_metrics_count": quote_metrics_count(latest_trade_date),
        "missing_float_share_count": missing_count,
        "samples": [dict(row) for row in samples],
    }


def fmt_number(value, digits=4):
    if value is None:
        return "--"
    return f"{float(value):.{digits}f}"


def print_final_verification():
    print_section("8. Final verification")
    daily_status = get_daily_quote_status(create_if_missing=False)
    premarket_status = get_premarket_status()
    margin_detail_status = get_margin_detail_status()
    verification = get_latest_verification()

    print(f"DATABASE_URL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    print(f"TUSHARE_TOKEN: {'configured' if TUSHARE_TOKEN else 'missing'}")
    print(f"daily_quotes rows: {daily_status['row_count']}")
    print(f"daily_quotes latest trade_date: {daily_status['latest_trade_date'] or 'none'}")
    print(f"stock_premarket rows: {premarket_status['row_count']}")
    print(f"stock_premarket latest trade_date: {premarket_status['latest_trade_date'] or 'none'}")
    print(f"stock_margin_detail rows: {margin_detail_status['row_count']}")
    print(f"stock_margin_detail latest trade_date: {margin_detail_status['latest_trade_date'] or 'none'}")

    latest_trade_date = verification["latest_trade_date"]
    if not latest_trade_date:
        print("No daily quote data found; cannot verify turnover-rate readiness.")
        return False

    print(f"Latest quote date checked: {latest_trade_date}")
    print(f"Quote rows on latest date: {verification['quote_count']}")
    print(f"Premarket rows on latest date: {verification['premarket_count']}")
    print(f"Margin detail rows on latest date: {verification['margin_detail_count']}")
    print(f"Quote metric rows on latest date: {verification['quote_metrics_count']}")
    print(f"Rows missing usable float_share on latest date: {verification['missing_float_share_count']}")

    if verification["samples"]:
        print("Sample rows:")
        for row in verification["samples"]:
            print(
                "  "
                f"{row['ts_code']} {row.get('name') or ''} | "
                f"close={fmt_number(row['close'], 2)} | "
                f"vol={fmt_number(row['vol'], 2)} | "
                f"float_share={fmt_number(row['float_share'], 4)} | "
                f"turnover_rate={fmt_number(row['turnover_rate'], 4)} | "
                f"total_share={fmt_number(row['total_share'], 4)} | "
                f"market_value={fmt_number(row['market_value'], 4)}"
            )

    if verification["quote_count"] > 0 and verification["premarket_count"] == 0:
        print("WARNING: latest daily quotes exist, but stock_premarket has no rows for that date.")
        print("This usually means Tushare has not published daily_basic share fields for the latest trade date yet.")
        return False

    if verification["missing_float_share_count"] > 0:
        print("WARNING: some latest-date stocks still lack usable float_share; turnover_rate may show --.")
        return False

    print("Verification passed: latest quote date has usable stock_premarket data.")
    return True


def main():
    args = parse_args()
    end_date = args.end_date or today()
    validate_yyyymmdd(end_date, "--end-date")

    print("Daily market data update")
    print(f"End date: {end_date}")
    print(f"Lookback open days: {args.lookback_open_days}")
    print(f"Dry run: {args.dry_run}")

    if args.skip_stocks:
        print_section("1. Update stocks")
        print("Skipped by --skip-stocks")
    else:
        run_stock_update(args)

    if args.skip_company_profiles:
        print_section("2. Update stock company profiles")
        print("Skipped by --skip-company-profiles")
    else:
        run_company_profile_update(args)

    if args.skip_industries:
        print_section("3. Update Shenwan industries")
        print("Skipped by --skip-industries")
    else:
        run_industry_update(args)

    if args.skip_quotes:
        print_section("4. Backfill daily quotes")
        print("Skipped by --skip-quotes")
        quote_result = {"target_dates": [], "updated_dates": [], "skipped_dates": [], "failed_dates": []}
    else:
        quote_result = run_daily_quote_update(args, end_date)

    if args.skip_premarket:
        print_section("5. Sync stock_premarket")
        print("Skipped by --skip-premarket")
    else:
        run_premarket_update(args, quote_result)

    if args.skip_margin_detail:
        print_section("6. Sync stock_margin_detail")
        print("Skipped by --skip-margin-detail")
    else:
        run_margin_detail_update(args, quote_result)

    if getattr(args, "skip_quote_metrics", False):
        print_section("7. Calculate daily_quote_metrics")
        print("Skipped by --skip-quote-metrics")
    else:
        run_quote_metrics_update(args)

    passed = print_final_verification()
    if not passed:
        if args.dry_run:
            print("Dry run finished with verification warnings because no rows were written.")
            return
        raise SystemExit(2)


if __name__ == "__main__":
    main()
