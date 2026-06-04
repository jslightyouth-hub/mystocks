import argparse
import time
from datetime import datetime, timedelta

from sqlalchemy import text

from settings import DATABASE_URL, TUSHARE_TOKEN
from sync_daily_quotes import create_daily_quotes_table, engine, pro, save_daily_quotes


DEFAULT_LOOKBACK_OPEN_DAYS = 5
REQUEST_INTERVAL_SECONDS = 0.13


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check the latest daily quote date in MySQL and backfill missing records."
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Override the first trade date to check, in YYYYMMDD format.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Override the last trade date to check, in YYYYMMDD format. Default: today.",
    )
    parser.add_argument(
        "--lookback-open-days",
        type=int,
        default=DEFAULT_LOOKBACK_OPEN_DAYS,
        help=(
            "When daily_quotes already has data, also re-check this many recent open "
            "trading days to catch partial or failed syncs. Default: 5."
        ),
    )
    parser.add_argument(
        "--init-days",
        type=int,
        default=30,
        help="If daily_quotes is empty and --start-date is not provided, look back this many calendar days.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the dates that need syncing without writing quote rows.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh target trade dates even when row counts already match Tushare.",
    )
    return parser.parse_args()


def today():
    return datetime.now().strftime("%Y%m%d")


def yyyymmdd_to_date(value):
    return datetime.strptime(value, "%Y%m%d").date()


def date_to_yyyymmdd(value):
    return value.strftime("%Y%m%d")


def get_database_status():
    create_daily_quotes_table()
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


def get_open_trade_dates(start_date, end_date):
    df = pro.trade_cal(
        exchange="",
        start_date=start_date,
        end_date=end_date,
        is_open="1",
        fields="cal_date,is_open",
    )
    if df.empty:
        return []
    return sorted(df["cal_date"].astype(str).tolist())


def choose_start_date(args, latest_trade_date, end_date):
    if args.start_date:
        return args.start_date

    if latest_trade_date:
        start = yyyymmdd_to_date(latest_trade_date) - timedelta(
            days=max(args.lookback_open_days * 2, 1)
        )
        return date_to_yyyymmdd(start)

    start = yyyymmdd_to_date(end_date) - timedelta(days=args.init_days)
    return date_to_yyyymmdd(start)


def keep_recent_window(open_dates, latest_trade_date, lookback_open_days):
    if not latest_trade_date:
        return open_dates

    newer_dates = [trade_date for trade_date in open_dates if trade_date > latest_trade_date]
    recent_existing = [
        trade_date for trade_date in open_dates if trade_date <= latest_trade_date
    ][-lookback_open_days:]
    return sorted(set(recent_existing + newer_dates))


def get_existing_counts(trade_dates):
    if not trade_dates:
        return {}

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT trade_date, COUNT(*) AS row_count
                FROM daily_quotes
                WHERE trade_date IN :trade_dates
                GROUP BY trade_date
            """).bindparams(trade_dates=tuple(trade_dates))
        ).mappings().all()

    return {row["trade_date"]: row["row_count"] for row in rows}


def fetch_daily_by_trade_date(trade_date, retries=3):
    for attempt in range(1, retries + 1):
        try:
            return pro.daily(trade_date=trade_date)
        except Exception:
            if attempt == retries:
                raise
            time.sleep(attempt * 2)


def find_updates_needed(target_dates, existing_counts, force_refresh=False):
    updates_needed = []
    skipped_dates = []

    for index, trade_date in enumerate(target_dates, start=1):
        existing_count = existing_counts.get(trade_date, 0)
        df = fetch_daily_by_trade_date(trade_date)
        fetched_count = len(df)

        if fetched_count == 0:
            skipped_dates.append({
                "trade_date": trade_date,
                "existing_count": existing_count,
                "fetched_count": fetched_count,
                "reason": "tushare returned 0 rows",
            })
            print(
                f"[{index}/{len(target_dates)}] {trade_date}: "
                f"已有 {existing_count} 条，Tushare 返回 0 条，跳过"
            )
        elif force_refresh or existing_count < fetched_count:
            updates_needed.append({
                "trade_date": trade_date,
                "existing_count": existing_count,
                "fetched_count": fetched_count,
                "df": df,
            })
            print(
                f"[{index}/{len(target_dates)}] {trade_date}: "
                f"需要更新，已有 {existing_count} 条，Tushare 有 {fetched_count} 条"
            )
        else:
            print(
                f"[{index}/{len(target_dates)}] {trade_date}: "
                f"已完整，已有 {existing_count} 条，Tushare 有 {fetched_count} 条"
            )

        time.sleep(REQUEST_INTERVAL_SECONDS)

    return updates_needed, skipped_dates


def print_status(status):
    print("Database status:")
    print(f"  DATABASE_URL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    print(f"  TUSHARE_TOKEN: {'configured' if TUSHARE_TOKEN else 'missing'}")
    print(f"  rows: {status['row_count']}")
    print(f"  latest trade_date: {status['latest_trade_date'] or 'none'}")
    print(f"  latest updated_at: {status['latest_updated_at'] or 'none'}")


def main():
    args = parse_args()
    end_date = args.end_date or today()
    status = get_database_status()
    print_status(status)

    start_date = choose_start_date(args, status["latest_trade_date"], end_date)
    open_dates = get_open_trade_dates(start_date, end_date)
    target_dates = keep_recent_window(
        open_dates,
        status["latest_trade_date"],
        max(args.lookback_open_days, 0),
    )

    if not target_dates:
        print(f"No open trading days found from {start_date} to {end_date}.")
        return

    existing_counts = get_existing_counts(target_dates)
    print(f"Checking {len(target_dates)} open trading day(s): {target_dates[0]} to {target_dates[-1]}")

    updates_needed, skipped_dates = find_updates_needed(
        target_dates,
        existing_counts,
        args.force_refresh,
    )

    if not updates_needed:
        print("已经是最新的数据，不用更新")
        if skipped_dates:
            skipped_text = ",".join(item["trade_date"] for item in skipped_dates)
            print(f"跳过无可用行情数据的交易日: {skipped_text}")
        return

    update_dates = [item["trade_date"] for item in updates_needed]
    print(f"需要更新的交易日: {','.join(update_dates)}")

    if args.dry_run:
        print(f"Dry run finished. Would update trade dates: {','.join(update_dates)}")
        return

    total_saved = 0
    failed_dates = []
    updated_dates = []
    for index, item in enumerate(updates_needed, start=1):
        trade_date = item["trade_date"]
        try:
            saved_count = save_daily_quotes(item["df"])
            total_saved += saved_count
            updated_dates.append(trade_date)
            print(
                f"[{index}/{len(updates_needed)}] {trade_date}: "
                f"更新完成，原有 {item['existing_count']} 条，写入 {saved_count} 条"
            )
        except Exception as exc:
            failed_dates.append(trade_date)
            print(f"[{index}/{len(updates_needed)}] {trade_date}: failed: {exc}")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    if updated_dates:
        print(f"已更新交易日: {','.join(updated_dates)}")
    print(f"Done. Saved or updated {total_saved} daily quote row(s).")

    if failed_dates:
        print("Failed trade dates:", ",".join(failed_dates))


if __name__ == "__main__":
    main()
