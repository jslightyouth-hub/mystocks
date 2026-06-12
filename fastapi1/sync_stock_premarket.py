import argparse
from datetime import datetime

import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


engine = create_engine(DATABASE_URL)
pro = ts.pro_api(TUSHARE_TOKEN)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync daily share data from Tushare daily_basic."
    )
    parser.add_argument(
        "--trade-date",
        default=None,
        help="Trade date in YYYYMMDD format. Default: latest trade_date in daily_quotes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print row count without writing to the database.",
    )
    return parser.parse_args()


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def create_stock_premarket_table():
    sql = text("""
        CREATE TABLE IF NOT EXISTS stock_premarket (
            id BIGINT NOT NULL AUTO_INCREMENT,
            trade_date CHAR(8) NOT NULL,
            ts_code VARCHAR(20) NOT NULL,
            total_share DECIMAL(20, 4) NULL,
            float_share DECIMAL(20, 4) NULL,
            created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_stock_premarket_ts_code_trade_date (ts_code, trade_date),
            KEY idx_stock_premarket_trade_date (trade_date),
            KEY idx_stock_premarket_ts_code (ts_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def get_latest_quote_trade_date():
    with engine.connect() as conn:
        return conn.execute(text("SELECT MAX(trade_date) FROM daily_quotes")).scalar_one_or_none()


def fetch_daily_basic_shares(trade_date):
    df = pro.daily_basic(
        trade_date=trade_date,
        fields="trade_date,ts_code,total_share,float_share",
    )
    df.attrs["source"] = "daily_basic"
    return df


def fetch_stock_premarket(trade_date):
    return fetch_daily_basic_shares(trade_date)


def save_stock_premarket(df):
    if df.empty:
        return 0

    sql = text("""
        INSERT INTO stock_premarket (
            trade_date,
            ts_code,
            total_share,
            float_share
        )
        VALUES (
            :trade_date,
            :ts_code,
            :total_share,
            :float_share
        )
        ON DUPLICATE KEY UPDATE
            total_share = VALUES(total_share),
            float_share = VALUES(float_share)
    """)

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "trade_date": clean_value(row["trade_date"]),
            "ts_code": clean_value(row["ts_code"]),
            "total_share": clean_value(row["total_share"]),
            "float_share": clean_value(row["float_share"]),
        })

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def main():
    args = parse_args()
    trade_date = args.trade_date or get_latest_quote_trade_date() or datetime.now().strftime("%Y%m%d")

    create_stock_premarket_table()
    df = fetch_stock_premarket(trade_date)
    source = df.attrs.get("source", "daily_basic")
    print(f"Fetched {len(df)} stock_premarket row(s) for {trade_date} from {source}.")

    if args.dry_run:
        print("Dry run finished. No rows were written.")
        return

    saved_count = save_stock_premarket(df)
    print(f"Done. Saved or updated {saved_count} stock_premarket row(s).")


if __name__ == "__main__":
    main()
