import argparse
import time
from datetime import datetime, timedelta

import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


engine = create_engine(DATABASE_URL)
pro = ts.pro_api(TUSHARE_TOKEN)

DEFAULT_DAYS = 5000
REQUEST_INTERVAL_SECONDS = 0.13


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def parse_args():
    parser = argparse.ArgumentParser(description="Sync daily quote history for every stock.")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="Calendar days to look back from today. Default: 5000.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only sync the first N stocks. Useful for testing before a full run.",
    )
    parser.add_argument(
        "--ts-code",
        default=None,
        help="Only sync one stock code, for example 000001.SZ.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip stock codes that already have rows in the target date range.",
    )
    return parser.parse_args()


def get_date_range(days):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def create_daily_quotes_table():
    sql = text("""
        CREATE TABLE IF NOT EXISTS daily_quotes (
            id BIGINT NOT NULL AUTO_INCREMENT,
            ts_code VARCHAR(20) NOT NULL,
            trade_date CHAR(8) NOT NULL,
            open DECIMAL(12, 4) NULL,
            high DECIMAL(12, 4) NULL,
            low DECIMAL(12, 4) NULL,
            close DECIMAL(12, 4) NULL,
            pre_close DECIMAL(12, 4) NULL,
            `change` DECIMAL(12, 4) NULL,
            pct_chg DECIMAL(12, 4) NULL,
            vol DECIMAL(20, 2) NULL,
            amount DECIMAL(20, 3) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_daily_quotes_ts_code_trade_date (ts_code, trade_date),
            KEY idx_daily_quotes_trade_date (trade_date),
            KEY idx_daily_quotes_ts_code (ts_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def get_stock_codes(limit=None, ts_code=None, start_date=None, end_date=None, skip_existing=False):
    if ts_code:
        return [ts_code]

    if skip_existing:
        sql = "SELECT ts_code FROM stocks ORDER BY ts_code"
        params = {}
    else:
        sql = "SELECT ts_code FROM stocks ORDER BY ts_code"
        params = {}

    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).scalars().all()

        if skip_existing:
            existing_rows = conn.execute(
                text("""
                    SELECT DISTINCT ts_code
                    FROM daily_quotes
                    WHERE trade_date BETWEEN :start_date AND :end_date
                """),
                {
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).scalars().all()
            existing_codes = set(existing_rows)
            rows = [row for row in rows if row not in existing_codes]

    return list(rows)


def fetch_daily_quotes(ts_code, start_date, end_date, retries=3):
    # Match the Tushare example: query one stock's daily data over a date range.
    for attempt in range(1, retries + 1):
        try:
            return pro.query(
                "daily",
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception:
            if attempt == retries:
                raise
            time.sleep(attempt * 2)


def save_daily_quotes(df):
    if df.empty:
        return 0

    sql = text("""
        INSERT INTO daily_quotes (
            ts_code,
            trade_date,
            open,
            high,
            low,
            close,
            pre_close,
            `change`,
            pct_chg,
            vol,
            amount
        )
        VALUES (
            :ts_code,
            :trade_date,
            :open,
            :high,
            :low,
            :close,
            :pre_close,
            :change,
            :pct_chg,
            :vol,
            :amount
        )
        ON DUPLICATE KEY UPDATE
            open = VALUES(open),
            high = VALUES(high),
            low = VALUES(low),
            close = VALUES(close),
            pre_close = VALUES(pre_close),
            `change` = VALUES(`change`),
            pct_chg = VALUES(pct_chg),
            vol = VALUES(vol),
            amount = VALUES(amount)
    """)

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "ts_code": clean_value(row["ts_code"]),
            "trade_date": clean_value(row["trade_date"]),
            "open": clean_value(row["open"]),
            "high": clean_value(row["high"]),
            "low": clean_value(row["low"]),
            "close": clean_value(row["close"]),
            "pre_close": clean_value(row["pre_close"]),
            "change": clean_value(row["change"]),
            "pct_chg": clean_value(row["pct_chg"]),
            "vol": clean_value(row["vol"]),
            "amount": clean_value(row["amount"]),
        })

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def main():
    args = parse_args()
    start_date, end_date = get_date_range(args.days)

    create_daily_quotes_table()
    stock_codes = get_stock_codes(
        limit=args.limit,
        ts_code=args.ts_code,
        start_date=start_date,
        end_date=end_date,
        skip_existing=args.skip_existing,
    )
    if not stock_codes:
        print("No stock codes found. Please sync the stocks table first.")
        return

    total_saved = 0
    failed_codes = []
    total_stocks = len(stock_codes)
    print(f"Syncing {total_stocks} stock(s), date range {start_date} to {end_date}")

    for index, ts_code in enumerate(stock_codes, start=1):
        try:
            df = fetch_daily_quotes(ts_code, start_date, end_date)
            saved_count = save_daily_quotes(df)
            total_saved += saved_count
            print(f"[{index}/{total_stocks}] {ts_code}: saved {saved_count} row(s)")
        except Exception as exc:
            failed_codes.append(ts_code)
            print(f"[{index}/{total_stocks}] {ts_code}: failed: {exc}")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    print(f"Done. Saved {total_saved} daily quote row(s).")
    if failed_codes:
        print("Failed stock codes:", ",".join(failed_codes))


if __name__ == "__main__":
    main()
