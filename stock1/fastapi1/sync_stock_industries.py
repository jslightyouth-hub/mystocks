import argparse

import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


engine = create_engine(DATABASE_URL)
pro = ts.pro_api(TUSHARE_TOKEN)

INDUSTRY_COLUMNS = {
    "sw_l1_code": "VARCHAR(20) NULL",
    "sw_l1_name": "VARCHAR(100) NULL",
    "sw_l2_code": "VARCHAR(20) NULL",
    "sw_l2_name": "VARCHAR(100) NULL",
    "sw_l3_code": "VARCHAR(20) NULL",
    "sw_l3_name": "VARCHAR(100) NULL",
    "sw_industry_src": "VARCHAR(20) NULL",
    "sw_in_date": "VARCHAR(20) NULL",
    "industry_updated_at": "TIMESTAMP NULL",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync current Shenwan industry membership into the stocks table."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only sync the first N industry rows. Useful for testing.",
    )
    parser.add_argument(
        "--ts-code",
        default=None,
        help="Only sync one stock code, for example 000001.SZ.",
    )
    return parser.parse_args()


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def get_table_columns(table_name):
    with engine.connect() as conn:
        rows = conn.execute(text(f"SHOW COLUMNS FROM {table_name}")).mappings().all()
    return {row["Field"] for row in rows}


def ensure_industry_columns():
    existing_columns = get_table_columns("stocks")
    missing_columns = [
        (name, definition)
        for name, definition in INDUSTRY_COLUMNS.items()
        if name not in existing_columns
    ]

    if not missing_columns:
        return []

    with engine.begin() as conn:
        for name, definition in missing_columns:
            conn.execute(text(f"ALTER TABLE stocks ADD COLUMN {name} {definition}"))

    return [name for name, _ in missing_columns]


def normalize_industry_rows(df, limit=None):
    if limit:
        df = df.head(limit)

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "ts_code": clean_value(row.get("ts_code")),
            "sw_l1_code": clean_value(row.get("l1_code")),
            "sw_l1_name": clean_value(row.get("l1_name")),
            "sw_l2_code": clean_value(row.get("l2_code")),
            "sw_l2_name": clean_value(row.get("l2_name")),
            "sw_l3_code": clean_value(row.get("l3_code")),
            "sw_l3_name": clean_value(row.get("l3_name")),
            "sw_industry_src": "SW",
            "sw_in_date": clean_value(row.get("in_date")),
        })

    return [row for row in rows if row["ts_code"]]


def fetch_l1_codes():
    df = pro.index_classify(
        level="L1",
        src="SW2021",
        fields="index_code,industry_name",
    )
    return [
        clean_value(row.get("index_code"))
        for _, row in df.iterrows()
        if clean_value(row.get("index_code"))
    ]


def fetch_current_industries(ts_code=None, limit=None):
    fields = (
        "ts_code,l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,"
        "in_date,is_new"
    )

    if ts_code:
        df = pro.index_member_all(
            ts_code=ts_code,
            is_new="Y",
            fields=fields,
        )
        return normalize_industry_rows(df, limit)

    rows = []
    for l1_code in fetch_l1_codes():
        df = pro.index_member_all(
            l1_code=l1_code,
            is_new="Y",
            fields=fields,
        )
        rows.extend(normalize_industry_rows(df))
        if limit and len(rows) >= limit:
            return rows[:limit]

    return rows


def dedupe_industries(rows):
    deduped = {}
    for row in rows:
        deduped[row["ts_code"]] = row
    return list(deduped.values())


def save_industries(rows):
    if not rows:
        return 0

    sql = text("""
        UPDATE stocks
        SET
            sw_l1_code = :sw_l1_code,
            sw_l1_name = :sw_l1_name,
            sw_l2_code = :sw_l2_code,
            sw_l2_name = :sw_l2_name,
            sw_l3_code = :sw_l3_code,
            sw_l3_name = :sw_l3_name,
            sw_industry_src = :sw_industry_src,
            sw_in_date = :sw_in_date,
            industry_updated_at = CURRENT_TIMESTAMP
        WHERE ts_code = :ts_code
    """)

    with engine.begin() as conn:
        result = conn.execute(sql, rows)

    return result.rowcount


def get_sample_rows(limit=8):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT
                    ts_code,
                    name,
                    industry,
                    sw_l1_name,
                    sw_l2_name,
                    sw_l3_name,
                    sw_industry_src,
                    sw_in_date,
                    industry_updated_at
                FROM stocks
                WHERE sw_l1_name IS NOT NULL
                ORDER BY ts_code
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().all()


def main():
    args = parse_args()
    added_columns = ensure_industry_columns()
    if added_columns:
        print("Added columns: " + ", ".join(added_columns))
    else:
        print("Industry columns already exist.")

    rows = dedupe_industries(fetch_current_industries(args.ts_code, args.limit))
    updated_count = save_industries(rows)
    print(f"Fetched industry rows: {len(rows)}")
    print(f"Updated stock rows: {updated_count}")

    sample_rows = get_sample_rows()
    if sample_rows:
        print("Sample stocks:")
        for row in sample_rows:
            print(
                f"  {row['ts_code']} {row['name'] or ''} | "
                f"basic={row['industry'] or ''} | "
                f"SW={row['sw_l1_name'] or ''} / "
                f"{row['sw_l2_name'] or ''} / {row['sw_l3_name'] or ''} | "
                f"src={row['sw_industry_src'] or ''}"
            )


if __name__ == "__main__":
    main()
