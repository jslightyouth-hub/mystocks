import argparse
import time
from datetime import datetime, timedelta

import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


engine = create_engine(DATABASE_URL)
pro = ts.pro_api(TUSHARE_TOKEN)

DEFAULT_DAYS = 1095
REQUEST_INTERVAL_SECONDS = 0.25
MARGIN_DETAIL_FIELDS = (
    "trade_date,ts_code,name,rzye,rqye,rzmre,rzche,rqyl,rqchl,rqmcl,rzrqye"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync Tushare margin_detail financing and securities lending data."
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="First trade date in YYYYMMDD. Default: end date minus --days calendar days.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Last trade date in YYYYMMDD. Default: latest trade_date in daily_quotes, or today.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="Calendar days to look back when --start-date is omitted. Default: 1095.",
    )
    parser.add_argument(
        "--limit-dates",
        type=int,
        default=None,
        help="Only sync the first N open trade dates. Useful for testing.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Rewrite dates even when local row count already matches or exceeds Tushare.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and compare counts without writing rows.",
    )
    return parser.parse_args()


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def validate_yyyymmdd(value, name):
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise SystemExit(f"{name} must be YYYYMMDD, got {value!r}") from exc


def date_to_yyyymmdd(value):
    return value.strftime("%Y%m%d")


def yyyymmdd_to_datetime(value):
    return datetime.strptime(value, "%Y%m%d")


def today():
    return datetime.now().strftime("%Y%m%d")


def table_exists(table_name):
    with engine.connect() as conn:
        return conn.execute(
            text("SHOW TABLES LIKE :table_name"),
            {"table_name": table_name},
        ).first() is not None


def get_latest_daily_quote_trade_date():
    if not table_exists("daily_quotes"):
        return None

    with engine.connect() as conn:
        return conn.execute(text("SELECT MAX(trade_date) FROM daily_quotes")).scalar_one_or_none()


def choose_end_date(end_date):
    return end_date or get_latest_daily_quote_trade_date() or today()


def choose_start_date(start_date, end_date, days):
    if start_date:
        return start_date

    start = yyyymmdd_to_datetime(end_date) - timedelta(days=days)
    return date_to_yyyymmdd(start)


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


def create_stock_margin_detail_table():
    sql = text("""
        CREATE TABLE IF NOT EXISTS stock_margin_detail (
            id BIGINT NOT NULL AUTO_INCREMENT,
            trade_date CHAR(8) NOT NULL,
            ts_code VARCHAR(20) NOT NULL,
            name VARCHAR(80) NULL,
            rzye DECIMAL(24, 4) NULL,
            rqye DECIMAL(24, 4) NULL,
            rzmre DECIMAL(24, 4) NULL,
            rzche DECIMAL(24, 4) NULL,
            rqyl DECIMAL(24, 4) NULL,
            rqchl DECIMAL(24, 4) NULL,
            rqmcl DECIMAL(24, 4) NULL,
            rzrqye DECIMAL(24, 4) NULL,
            created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_stock_margin_detail_ts_code_trade_date (ts_code, trade_date),
            KEY idx_stock_margin_detail_trade_date (trade_date),
            KEY idx_stock_margin_detail_ts_code (ts_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def get_existing_counts(trade_dates):
    if not trade_dates or not table_exists("stock_margin_detail"):
        return {}

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT trade_date, COUNT(*) AS row_count
                FROM stock_margin_detail
                WHERE trade_date IN :trade_dates
                GROUP BY trade_date
            """).bindparams(trade_dates=tuple(trade_dates))
        ).mappings().all()

    return {row["trade_date"]: row["row_count"] for row in rows}


def fetch_margin_detail(trade_date, retries=3):
    for attempt in range(1, retries + 1):
        try:
            return pro.margin_detail(
                trade_date=trade_date,
                fields=MARGIN_DETAIL_FIELDS,
            )
        except Exception:
            if attempt == retries:
                raise
            time.sleep(attempt * 2)


def save_margin_detail(df):
    if df.empty:
        return 0

    sql = text("""
        INSERT INTO stock_margin_detail (
            trade_date,
            ts_code,
            name,
            rzye,
            rqye,
            rzmre,
            rzche,
            rqyl,
            rqchl,
            rqmcl,
            rzrqye
        )
        VALUES (
            :trade_date,
            :ts_code,
            :name,
            :rzye,
            :rqye,
            :rzmre,
            :rzche,
            :rqyl,
            :rqchl,
            :rqmcl,
            :rzrqye
        )
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            rzye = VALUES(rzye),
            rqye = VALUES(rqye),
            rzmre = VALUES(rzmre),
            rzche = VALUES(rzche),
            rqyl = VALUES(rqyl),
            rqchl = VALUES(rqchl),
            rqmcl = VALUES(rqmcl),
            rzrqye = VALUES(rzrqye)
    """)

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "trade_date": clean_value(row["trade_date"]),
            "ts_code": clean_value(row["ts_code"]),
            "name": clean_value(row["name"]),
            "rzye": clean_value(row["rzye"]),
            "rqye": clean_value(row["rqye"]),
            "rzmre": clean_value(row["rzmre"]),
            "rzche": clean_value(row["rzche"]),
            "rqyl": clean_value(row["rqyl"]),
            "rqchl": clean_value(row["rqchl"]),
            "rqmcl": clean_value(row["rqmcl"]),
            "rzrqye": clean_value(row["rzrqye"]),
        })

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def get_margin_detail_status():
    if not table_exists("stock_margin_detail"):
        return {
            "row_count": 0,
            "earliest_trade_date": None,
            "latest_trade_date": None,
            "latest_updated_at": None,
        }

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    COUNT(*) AS row_count,
                    MIN(trade_date) AS earliest_trade_date,
                    MAX(trade_date) AS latest_trade_date,
                    MAX(updated_at) AS latest_updated_at
                FROM stock_margin_detail
            """)
        ).mappings().one()

    return dict(row)


def main():
    args = parse_args()
    end_date = choose_end_date(args.end_date)
    start_date = choose_start_date(args.start_date, end_date, args.days)
    validate_yyyymmdd(start_date, "--start-date")
    validate_yyyymmdd(end_date, "--end-date")
    if start_date > end_date:
        raise SystemExit(f"--start-date cannot be after --end-date: {start_date} > {end_date}")

    if not args.dry_run:
        create_stock_margin_detail_table()

    open_dates = get_open_trade_dates(start_date, end_date)
    if args.limit_dates:
        open_dates = open_dates[:args.limit_dates]

    if not open_dates:
        print(f"No open trading days found from {start_date} to {end_date}.")
        return

    existing_counts = get_existing_counts(open_dates)
    print("Syncing stock_margin_detail from Tushare margin_detail")
    print(f"Date range: {open_dates[0]} to {open_dates[-1]} ({len(open_dates)} open day(s))")
    print(f"Dry run: {args.dry_run}")

    total_saved = 0
    updated_dates = []
    skipped_dates = []
    empty_dates = []
    failed_dates = []

    for index, trade_date in enumerate(open_dates, start=1):
        existing_count = existing_counts.get(trade_date, 0)
        try:
            df = fetch_margin_detail(trade_date)
            fetched_count = len(df)
            if fetched_count == 0:
                empty_dates.append(trade_date)
                print(
                    f"[{index}/{len(open_dates)}] {trade_date}: "
                    f"existing {existing_count}, Tushare returned 0 rows"
                )
                continue

            if not args.force_refresh and existing_count >= fetched_count:
                skipped_dates.append(trade_date)
                print(
                    f"[{index}/{len(open_dates)}] {trade_date}: "
                    f"already complete, existing {existing_count}, Tushare {fetched_count}"
                )
                continue

            if args.dry_run:
                updated_dates.append(trade_date)
                print(
                    f"[{index}/{len(open_dates)}] {trade_date}: "
                    f"would update, existing {existing_count}, Tushare {fetched_count}"
                )
                continue

            saved_count = save_margin_detail(df)
            total_saved += saved_count
            updated_dates.append(trade_date)
            print(
                f"[{index}/{len(open_dates)}] {trade_date}: "
                f"saved or updated {saved_count} row(s), existing {existing_count}"
            )
        except Exception as exc:
            failed_dates.append(trade_date)
            print(f"[{index}/{len(open_dates)}] {trade_date}: failed: {exc}")

        time.sleep(REQUEST_INTERVAL_SECONDS)

    status = get_margin_detail_status()
    print("")
    print("Done.")
    print(f"Saved or updated rows this run: {total_saved}")
    print(f"Updated dates: {len(updated_dates)}")
    print(f"Skipped complete dates: {len(skipped_dates)}")
    print(f"Empty dates: {len(empty_dates)}")
    print(f"Failed dates: {len(failed_dates)}")
    print(f"stock_margin_detail rows: {status['row_count']}")
    print(f"stock_margin_detail range: {status['earliest_trade_date'] or 'none'} to {status['latest_trade_date'] or 'none'}")
    if failed_dates:
        print("Failed trade dates: " + ",".join(failed_dates))


if __name__ == "__main__":
    main()
