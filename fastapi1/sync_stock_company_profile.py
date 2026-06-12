import argparse

import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


engine = create_engine(DATABASE_URL)
pro = ts.pro_api(TUSHARE_TOKEN)

COMPANY_FIELDS = [
    "ts_code",
    "com_name",
    "chairman",
    "manager",
    "city",
    "introduction",
    "employees",
    "main_business",
    "exchange",
]
TUSHARE_COMPANY_FIELDS = ",".join(COMPANY_FIELDS)
DEFAULT_EXCHANGES = ["SSE", "SZSE", "BSE"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync slow-changing company profile fields from Tushare stock_company."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N company profiles. Useful for development testing.",
    )
    parser.add_argument(
        "--exchange",
        default=None,
        help="Only fetch one exchange, for example SSE, SZSE, or BSE.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and diff company profiles without writing to the database.",
    )
    return parser.parse_args()


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def create_stock_company_profile_table():
    sql = text("""
        CREATE TABLE IF NOT EXISTS stock_company_profile (
            id BIGINT NOT NULL AUTO_INCREMENT,
            ts_code VARCHAR(20) NOT NULL,
            com_name VARCHAR(255) NULL,
            chairman VARCHAR(100) NULL,
            manager VARCHAR(100) NULL,
            city VARCHAR(100) NULL,
            introduction TEXT NULL,
            employees INT NULL,
            main_business TEXT NULL,
            exchange VARCHAR(20) NULL,
            created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_stock_company_profile_ts_code (ts_code),
            KEY idx_stock_company_profile_exchange (exchange),
            KEY idx_stock_company_profile_city (city)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def table_exists(table_name):
    with engine.connect() as conn:
        return conn.execute(
            text("SHOW TABLES LIKE :table_name"),
            {"table_name": table_name},
        ).first() is not None


def normalize_company_rows(df, exchange=None, limit=None):
    if limit:
        df = df.head(limit)

    rows = []
    for _, row in df.iterrows():
        item = {
            field: clean_value(row.get(field))
            for field in COMPANY_FIELDS
        }
        if not item.get("exchange"):
            item["exchange"] = exchange
        if item.get("ts_code"):
            rows.append(item)

    return rows


def fetch_company_profiles(exchange=None, limit=None):
    exchanges = [exchange] if exchange else DEFAULT_EXCHANGES
    rows = []

    for current_exchange in exchanges:
        df = pro.stock_company(
            exchange=current_exchange,
            fields=TUSHARE_COMPANY_FIELDS,
        )
        rows.extend(normalize_company_rows(df, current_exchange))
        if limit and len(rows) >= limit:
            return rows[:limit]

    return rows


def dedupe_company_profiles(rows):
    deduped = {}
    for row in rows:
        deduped[row["ts_code"]] = row
    return list(deduped.values())


def get_existing_company_profiles():
    if not table_exists("stock_company_profile"):
        return {}

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    ts_code,
                    com_name,
                    chairman,
                    manager,
                    city,
                    introduction,
                    employees,
                    main_business,
                    exchange
                FROM stock_company_profile
            """)
        ).mappings().all()

    return {
        row["ts_code"]: {field: row[field] for field in COMPANY_FIELDS}
        for row in rows
    }


def diff_company_profiles(latest_rows, existing_rows):
    new_rows = []
    changed_rows = []

    for row in latest_rows:
        existing = existing_rows.get(row["ts_code"])
        if not existing:
            new_rows.append(row)
            continue

        changed_fields = [
            field
            for field in COMPANY_FIELDS
            if (existing.get(field) or None) != (row.get(field) or None)
        ]
        if changed_fields:
            changed = dict(row)
            changed["changed_fields"] = changed_fields
            changed_rows.append(changed)

    return new_rows, changed_rows


def save_company_profiles(rows):
    if not rows:
        return 0

    sql = text("""
        INSERT INTO stock_company_profile (
            ts_code,
            com_name,
            chairman,
            manager,
            city,
            introduction,
            employees,
            main_business,
            exchange
        )
        VALUES (
            :ts_code,
            :com_name,
            :chairman,
            :manager,
            :city,
            :introduction,
            :employees,
            :main_business,
            :exchange
        )
        ON DUPLICATE KEY UPDATE
            com_name = VALUES(com_name),
            chairman = VALUES(chairman),
            manager = VALUES(manager),
            city = VALUES(city),
            introduction = VALUES(introduction),
            employees = VALUES(employees),
            main_business = VALUES(main_business),
            exchange = VALUES(exchange)
    """)

    payload = [
        {field: row.get(field) for field in COMPANY_FIELDS}
        for row in rows
    ]

    with engine.begin() as conn:
        conn.execute(sql, payload)

    return len(payload)


def print_profile_list(title, rows, include_changed_fields=False):
    if not rows:
        return

    print(title)
    for row in rows[:10]:
        suffix = ""
        if include_changed_fields:
            suffix = f" changed_fields={','.join(row['changed_fields'])}"
        print(f"  {row['ts_code']} {row.get('com_name') or ''}{suffix}")
    if len(rows) > 10:
        print(f"  ... {len(rows) - 10} more")


def main():
    args = parse_args()
    latest_rows = dedupe_company_profiles(fetch_company_profiles(args.exchange, args.limit))
    existing_rows = get_existing_company_profiles()
    new_rows, changed_rows = diff_company_profiles(latest_rows, existing_rows)

    print(f"Tushare company profiles checked: {len(latest_rows)}")
    print(f"New company profiles: {len(new_rows)}")
    print(f"Changed company profiles: {len(changed_rows)}")
    print_profile_list("New profiles:", new_rows)
    print_profile_list("Changed profiles:", changed_rows, include_changed_fields=True)

    if args.dry_run:
        print("Dry run finished. No rows were written.")
        return

    create_stock_company_profile_table()
    saved_count = save_company_profiles(new_rows + changed_rows)
    print(f"Done. Saved or updated {saved_count} company profile row(s).")


if __name__ == "__main__":
    main()
