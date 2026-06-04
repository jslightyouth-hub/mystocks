import argparse
import time
from datetime import datetime, timedelta

import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN
from sync_daily_quotes import (
    REQUEST_INTERVAL_SECONDS,
    create_daily_quotes_table,
    fetch_daily_quotes,
    save_daily_quotes,
)


STOCK_FIELDS = ["ts_code", "symbol", "name", "area", "industry"]

engine = create_engine(DATABASE_URL)
pro = ts.pro_api(TUSHARE_TOKEN)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Update the stocks table with latest listed stock basic information."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check new or changed stocks without writing to the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N stocks from Tushare. Useful for testing.",
    )
    parser.add_argument(
        "--ts-code",
        default=None,
        help="Only check one stock code, for example 000001.SZ.",
    )
    parser.add_argument(
        "--quote-days",
        type=int,
        default=5000,
        help="Calendar days of daily quotes to backfill for newly listed stocks. Default: 5000.",
    )
    parser.add_argument(
        "--skip-quotes",
        action="store_true",
        help="Only update stocks table; do not backfill daily_quotes for new stocks.",
    )
    return parser.parse_args()


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def normalize_row(row):
    return {field: clean_value(row.get(field)) for field in STOCK_FIELDS}


def table_exists(table_name):
    with engine.connect() as conn:
        return conn.execute(
            text("SHOW TABLES LIKE :table_name"),
            {"table_name": table_name},
        ).first() is not None


def get_table_columns(table_name):
    with engine.connect() as conn:
        rows = conn.execute(text(f"SHOW COLUMNS FROM {table_name}")).mappings().all()
    return {row["Field"] for row in rows}


def ensure_stocks_table():
    create_sql = text("""
        CREATE TABLE IF NOT EXISTS stocks (
            id BIGINT NOT NULL AUTO_INCREMENT,
            ts_code VARCHAR(20) NOT NULL,
            symbol VARCHAR(20) NULL,
            name VARCHAR(100) NULL,
            area VARCHAR(100) NULL,
            industry VARCHAR(100) NULL,
            created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_stocks_ts_code (ts_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with engine.begin() as conn:
        conn.execute(create_sql)

    columns = get_table_columns("stocks")
    if "updated_at" not in columns:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE stocks
                ADD COLUMN updated_at TIMESTAMP NULL
                    DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
            """))


def get_database_status():
    if not table_exists("stocks"):
        return {
            "row_count": 0,
            "latest_created_at": None,
            "latest_updated_at": None,
            "has_updated_at": False,
        }

    columns = get_table_columns("stocks")
    updated_expr = "MAX(updated_at)" if "updated_at" in columns else "NULL"
    with engine.connect() as conn:
        row = conn.execute(
            text(f"""
                SELECT
                    COUNT(*) AS row_count,
                    MAX(created_at) AS latest_created_at,
                    {updated_expr} AS latest_updated_at
                FROM stocks
            """)
        ).mappings().one()

    status = dict(row)
    status["has_updated_at"] = "updated_at" in columns
    return status


def fetch_latest_stocks(ts_code=None, limit=None):
    df = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry",
    )

    if ts_code:
        df = df[df["ts_code"] == ts_code]

    if limit:
        df = df.head(limit)

    return [normalize_row(row) for _, row in df.iterrows()]


def get_existing_stocks():
    if not table_exists("stocks"):
        return {}

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT ts_code, symbol, name, area, industry
                FROM stocks
            """)
        ).mappings().all()

    return {
        row["ts_code"]: {field: row[field] for field in STOCK_FIELDS}
        for row in rows
    }


def diff_stocks(latest_rows, existing_rows):
    new_rows = []
    changed_rows = []

    for row in latest_rows:
        ts_code = row["ts_code"]
        existing = existing_rows.get(ts_code)

        if not existing:
            new_rows.append(row)
            continue

        changed_fields = [
            field
            for field in STOCK_FIELDS
            if (existing.get(field) or None) != (row.get(field) or None)
        ]
        if changed_fields:
            changed = dict(row)
            changed["changed_fields"] = changed_fields
            changed_rows.append(changed)

    return new_rows, changed_rows


def save_stocks(rows):
    if not rows:
        return 0

    sql = text("""
        INSERT INTO stocks (
            ts_code,
            symbol,
            name,
            area,
            industry
        )
        VALUES (
            :ts_code,
            :symbol,
            :name,
            :area,
            :industry
        )
        ON DUPLICATE KEY UPDATE
            symbol = VALUES(symbol),
            name = VALUES(name),
            area = VALUES(area),
            industry = VALUES(industry)
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def get_quote_date_range(days):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def backfill_daily_quotes_for_new_stocks(new_rows, quote_days):
    if not new_rows:
        return []

    create_daily_quotes_table()
    start_date, end_date = get_quote_date_range(quote_days)
    results = []
    total_stocks = len(new_rows)

    print(
        f"Backfilling daily quotes for {total_stocks} new stock(s), "
        f"date range {start_date} to {end_date}"
    )

    for index, row in enumerate(new_rows, start=1):
        ts_code = row["ts_code"]
        try:
            df = fetch_daily_quotes(ts_code, start_date, end_date)
            saved_count = save_daily_quotes(df)
            results.append({
                "ts_code": ts_code,
                "name": row.get("name"),
                "saved_count": saved_count,
                "failed": False,
            })
            print(
                f"[{index}/{total_stocks}] {ts_code} {row.get('name') or ''}: "
                f"saved {saved_count} daily quote row(s)"
            )
        except Exception as exc:
            results.append({
                "ts_code": ts_code,
                "name": row.get("name"),
                "saved_count": 0,
                "failed": True,
                "error": str(exc),
            })
            print(f"[{index}/{total_stocks}] {ts_code}: daily quote backfill failed: {exc}")

        time.sleep(REQUEST_INTERVAL_SECONDS)

    return results


def print_status(status):
    print("Database status:")
    print(f"  rows: {status['row_count']}")
    print(f"  latest created_at: {status['latest_created_at'] or 'none'}")
    print(f"  latest updated_at: {status['latest_updated_at'] or 'none'}")
    print(f"  has updated_at: {status['has_updated_at']}")


def print_stock_list(title, rows, include_changed_fields=False):
    if not rows:
        return

    print(title)
    for row in rows:
        suffix = ""
        if include_changed_fields:
            suffix = f" changed_fields={','.join(row['changed_fields'])}"
        print(f"  {row['ts_code']} {row.get('name') or ''}{suffix}")


def main():
    args = parse_args()
    status = get_database_status()
    print_status(status)

    latest_rows = fetch_latest_stocks(args.ts_code, args.limit)
    existing_rows = get_existing_stocks()
    new_rows, changed_rows = diff_stocks(latest_rows, existing_rows)

    print(f"Tushare listed stocks: {len(latest_rows)}")
    print(f"New stocks: {len(new_rows)}")
    print(f"Changed stocks: {len(changed_rows)}")

    if not new_rows and not changed_rows:
        print("股票基础信息已经是最新的数据，不用更新")
        return

    print_stock_list("新增股票:", new_rows)
    print_stock_list("信息变化股票:", changed_rows, include_changed_fields=True)

    if args.dry_run:
        print("Dry run finished. No rows were written.")
        if new_rows and not args.skip_quotes:
            print(
                "Dry run finished. Would backfill daily quotes for new stocks: "
                + ",".join(row["ts_code"] for row in new_rows)
            )
        return

    ensure_stocks_table()
    saved_count = save_stocks(new_rows + changed_rows)
    print(f"Done. Saved or updated {saved_count} stock row(s).")

    if new_rows and not args.skip_quotes:
        quote_results = backfill_daily_quotes_for_new_stocks(new_rows, args.quote_days)
        updated_quote_codes = [
            item["ts_code"]
            for item in quote_results
            if not item["failed"] and item["saved_count"] > 0
        ]
        failed_quote_codes = [
            item["ts_code"]
            for item in quote_results
            if item["failed"]
        ]

        if updated_quote_codes:
            print("已补齐日线数据的新股票:", ",".join(updated_quote_codes))
        if failed_quote_codes:
            print("日线数据补齐失败的新股票:", ",".join(failed_quote_codes))
    elif new_rows and args.skip_quotes:
        print("Skipped daily quote backfill for new stocks because --skip-quotes was set.")


if __name__ == "__main__":
    main()
