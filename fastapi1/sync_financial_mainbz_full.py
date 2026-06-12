import argparse
import time
from datetime import datetime

import pandas as pd

from sync_financials import (
    FINANCIAL_INTERFACES,
    create_financial_table,
    pro,
    save_financial_rows,
)


TABLE_NAME = FINANCIAL_INTERFACES["fina_mainbz_vip"]
DEFAULT_LIMIT = 10000
REPORT_DATES = ("0331", "0630", "0930", "1231")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk sync Tushare fina_mainbz_vip by report period and type."
    )
    current_year = datetime.now().year
    parser.add_argument("--start-year", type=int, default=current_year - 10)
    parser.add_argument("--end-year", type=int, default=current_year)
    parser.add_argument(
        "--types",
        default="P,D,I",
        help="Comma-separated main business types. P=product, D=region, I=industry.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--request-interval", type=float, default=0.35)
    return parser.parse_args()


def iter_periods(start_year, end_year):
    for year in range(start_year, end_year + 1):
        for report_date in REPORT_DATES:
            yield f"{year}{report_date}"


def fetch_period_type(period, bz_type, limit, request_interval):
    offset = 0
    frames = []

    while True:
        df = pro.fina_mainbz_vip(
            period=period,
            type=bz_type,
            limit=limit,
            offset=offset,
        )
        if df.empty:
            break

        frames.append(df)
        print(f"  {period} {bz_type} offset={offset}: fetched {len(df)} row(s)", flush=True)

        if len(df) < limit:
            break

        offset += limit
        time.sleep(request_interval)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def main():
    args = parse_args()
    bz_types = [item.strip().upper() for item in args.types.split(",") if item.strip()]
    create_financial_table(TABLE_NAME)

    total_saved = 0
    for period in iter_periods(args.start_year, args.end_year):
        for bz_type in bz_types:
            try:
                df = fetch_period_type(period, bz_type, args.limit, args.request_interval)
                saved = save_financial_rows(TABLE_NAME, df)
                total_saved += saved
                print(f"{period} {bz_type}: saved {saved} row(s)", flush=True)
            except Exception as exc:
                print(f"{period} {bz_type}: failed: {exc}", flush=True)

            time.sleep(args.request_interval)

    print(f"Done. Saved or updated {total_saved} main business row(s).", flush=True)


if __name__ == "__main__":
    main()
