import argparse
import hashlib
import time
from datetime import datetime

import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


engine = create_engine(DATABASE_URL)
pro = ts.pro_api(TUSHARE_TOKEN)

REQUEST_INTERVAL_SECONDS = 0.35

FINANCIAL_INTERFACES = {
    "income": "financial_income",
    "balancesheet": "financial_balancesheet",
    "cashflow": "financial_cashflow",
    "fina_indicator": "financial_indicator",
}

KEY_FIELD_PRIORITY = [
    "ts_code",
    "end_date",
    "report_type",
    "ann_date",
    "f_ann_date",
    "comp_type",
]

CHAR8_FIELDS = {
    "ann_date",
    "f_ann_date",
    "end_date",
    "start_date",
    "trade_date",
}

SHORT_TEXT_FIELDS = {
    "ts_code",
    "report_type",
    "comp_type",
    "update_flag",
    "end_type",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync all returned Tushare financial fields into local MySQL tables."
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Start date in YYYYMMDD. Default: exactly 10 years before today.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date in YYYYMMDD. Default: today.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only sync the first N stocks from the stocks table. Useful for testing.",
    )
    parser.add_argument(
        "--ts-code",
        default=None,
        help="Only sync one stock code, for example 600519.SH.",
    )
    parser.add_argument(
        "--interfaces",
        default=",".join(FINANCIAL_INTERFACES),
        help=(
            "Comma-separated interfaces to sync. "
            "Default: income,balancesheet,cashflow,fina_indicator."
        ),
    )
    parser.add_argument(
        "--skip-synced",
        action="store_true",
        help="Skip interface/stock/date-range combinations already marked as success.",
    )
    parser.add_argument(
        "--verbose-skips",
        action="store_true",
        help="Print every skipped task when --skip-synced is enabled.",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=REQUEST_INTERVAL_SECONDS,
        help=f"Seconds to sleep after each Tushare request. Default: {REQUEST_INTERVAL_SECONDS}.",
    )
    return parser.parse_args()


def default_date_range():
    end_date = datetime.now()
    try:
        start_date = end_date.replace(year=end_date.year - 10)
    except ValueError:
        start_date = end_date.replace(year=end_date.year - 10, day=28)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def quote_name(name):
    return f"`{name.replace('`', '``')}`"


def table_exists(table_name):
    with engine.connect() as conn:
        return conn.execute(
            text("SHOW TABLES LIKE :table_name"),
            {"table_name": table_name},
        ).first() is not None


def get_table_columns(table_name):
    if not table_exists(table_name):
        return set()

    with engine.connect() as conn:
        rows = conn.execute(text(f"SHOW COLUMNS FROM {quote_name(table_name)}")).mappings().all()
    return {row["Field"] for row in rows}


def get_table_column_info(table_name):
    if not table_exists(table_name):
        return {}

    with engine.connect() as conn:
        rows = conn.execute(text(f"SHOW COLUMNS FROM {quote_name(table_name)}")).mappings().all()
    return {row["Field"]: row for row in rows}


def create_financial_table(table_name):
    # MySQL requires indexed columns to exist when creating the table, so create a
    # minimal shape with the most common financial dimensions.
    sql = text(f"""
        CREATE TABLE IF NOT EXISTS {quote_name(table_name)} (
            id BIGINT NOT NULL AUTO_INCREMENT,
            row_key CHAR(64) NOT NULL,
            ts_code VARCHAR(20) NULL,
            ann_date CHAR(8) NULL,
            f_ann_date CHAR(8) NULL,
            end_date CHAR(8) NULL,
            report_type VARCHAR(20) NULL,
            comp_type VARCHAR(20) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_row_key (row_key),
            KEY idx_ts_code (ts_code),
            KEY idx_end_date (end_date),
            KEY idx_ann_date (ann_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def convert_wide_varchar_columns(table_name):
    column_info = get_table_column_info(table_name)
    alter_columns = []

    for field_name, info in column_info.items():
        if field_name in {
            "row_key",
            "ts_code",
            "ann_date",
            "f_ann_date",
            "end_date",
            "report_type",
            "comp_type",
            "update_flag",
            "end_type",
        }:
            continue
        if str(info["Type"]).lower() == "varchar(255)":
            alter_columns.append(field_name)

    if not alter_columns:
        return

    with engine.begin() as conn:
        for field_name in alter_columns:
            conn.execute(
                text(
                    f"ALTER TABLE {quote_name(table_name)} "
                    f"MODIFY COLUMN {quote_name(field_name)} TEXT NULL"
                )
            )
            print(f"Converted {table_name}.{field_name} to TEXT")


def infer_column_type(field_name, series):
    if field_name in CHAR8_FIELDS:
        return "CHAR(8) NULL"
    if field_name in SHORT_TEXT_FIELDS:
        return "VARCHAR(20) NULL"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT NULL"
    if pd.api.types.is_float_dtype(series) or pd.api.types.is_numeric_dtype(series):
        return "DOUBLE NULL"
    return "TEXT NULL"


def ensure_table_columns(table_name, df):
    create_financial_table(table_name)
    convert_wide_varchar_columns(table_name)
    existing_columns = get_table_columns(table_name)
    add_columns = []

    for field_name in df.columns:
        if field_name in existing_columns or field_name in {"id", "row_key", "created_at", "updated_at"}:
            continue
        column_type = infer_column_type(field_name, df[field_name])
        add_columns.append((field_name, column_type))

    if not add_columns:
        return

    with engine.begin() as conn:
        for field_name, column_type in add_columns:
            conn.execute(
                text(
                    f"ALTER TABLE {quote_name(table_name)} "
                    f"ADD COLUMN {quote_name(field_name)} {column_type}"
                )
            )
            print(f"Added column {table_name}.{field_name} {column_type}")


def create_sync_status_table():
    sql = text("""
        CREATE TABLE IF NOT EXISTS financial_sync_status (
            id BIGINT NOT NULL AUTO_INCREMENT,
            interface_name VARCHAR(50) NOT NULL,
            table_name VARCHAR(100) NOT NULL,
            ts_code VARCHAR(20) NOT NULL,
            start_date CHAR(8) NOT NULL,
            end_date CHAR(8) NOT NULL,
            row_count INT NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL,
            error_message TEXT NULL,
            synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_financial_sync_status (
                interface_name,
                ts_code,
                start_date,
                end_date
            ),
            KEY idx_financial_sync_status_status (status),
            KEY idx_financial_sync_status_ts_code (ts_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def get_stock_codes(limit=None, ts_code=None):
    if ts_code:
        return [ts_code]

    sql = "SELECT ts_code FROM stocks ORDER BY ts_code"
    params = {}
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit

    with engine.connect() as conn:
        return list(conn.execute(text(sql), params).scalars().all())


def was_synced(interface_name, ts_code, start_date, end_date):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT 1
                FROM financial_sync_status
                WHERE interface_name = :interface_name
                    AND ts_code = :ts_code
                    AND start_date = :start_date
                    AND end_date = :end_date
                    AND status = 'success'
                LIMIT 1
            """),
            {
                "interface_name": interface_name,
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
            },
        ).first() is not None


def get_synced_task_keys(start_date, end_date):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT interface_name, ts_code
                FROM financial_sync_status
                WHERE start_date = :start_date
                    AND end_date = :end_date
                    AND status = 'success'
            """),
            {
                "start_date": start_date,
                "end_date": end_date,
            },
        ).mappings().all()

    return {(row["interface_name"], row["ts_code"]) for row in rows}


def save_sync_status(
    interface_name,
    table_name,
    ts_code,
    start_date,
    end_date,
    row_count,
    status,
    error_message=None,
):
    sql = text("""
        INSERT INTO financial_sync_status (
            interface_name,
            table_name,
            ts_code,
            start_date,
            end_date,
            row_count,
            status,
            error_message,
            synced_at
        )
        VALUES (
            :interface_name,
            :table_name,
            :ts_code,
            :start_date,
            :end_date,
            :row_count,
            :status,
            :error_message,
            CURRENT_TIMESTAMP
        )
        ON DUPLICATE KEY UPDATE
            table_name = VALUES(table_name),
            row_count = VALUES(row_count),
            status = VALUES(status),
            error_message = VALUES(error_message),
            synced_at = CURRENT_TIMESTAMP
    """)

    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "interface_name": interface_name,
                "table_name": table_name,
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
                "row_count": row_count,
                "status": status,
                "error_message": error_message,
            },
        )


def build_row_key(row):
    key_parts = []
    for field_name in KEY_FIELD_PRIORITY:
        if field_name in row and row.get(field_name) is not None:
            key_parts.append(f"{field_name}={row.get(field_name)}")

    if not key_parts:
        key_parts = [f"{field_name}={row.get(field_name)}" for field_name in sorted(row)]

    raw_key = "|".join(key_parts)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def fetch_financial(interface_name, ts_code, start_date, end_date, retries=3):
    fetcher = getattr(pro, interface_name)
    for attempt in range(1, retries + 1):
        try:
            return fetcher(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception:
            if attempt == retries:
                raise
            time.sleep(attempt * 2)


def save_financial_rows(table_name, df):
    if df.empty:
        return 0

    ensure_table_columns(table_name, df)

    data_columns = list(df.columns)
    insert_columns = ["row_key"] + data_columns
    column_sql = ", ".join(quote_name(column) for column in insert_columns)
    value_sql = ", ".join(f":{column}" for column in insert_columns)
    update_sql = ", ".join(
        f"{quote_name(column)} = VALUES({quote_name(column)})"
        for column in data_columns
    )

    sql = text(f"""
        INSERT INTO {quote_name(table_name)} ({column_sql})
        VALUES ({value_sql})
        ON DUPLICATE KEY UPDATE
            {update_sql}
    """)

    rows = []
    for _, source_row in df.iterrows():
        row = {column: clean_value(source_row[column]) for column in data_columns}
        row["row_key"] = build_row_key(row)
        rows.append(row)

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def parse_interfaces(value):
    names = [item.strip() for item in value.split(",") if item.strip()]
    invalid = [name for name in names if name not in FINANCIAL_INTERFACES]
    if invalid:
        valid = ",".join(FINANCIAL_INTERFACES)
        raise ValueError(f"Unsupported interface(s): {','.join(invalid)}. Valid: {valid}")
    return names


def main():
    args = parse_args()
    start_date, end_date = default_date_range()
    start_date = args.start_date or start_date
    end_date = args.end_date or end_date
    interfaces = parse_interfaces(args.interfaces)

    create_sync_status_table()
    for table_name in FINANCIAL_INTERFACES.values():
        create_financial_table(table_name)

    stock_codes = get_stock_codes(args.limit, args.ts_code)
    if not stock_codes:
        print("No stock codes found. Please sync the stocks table first.")
        return

    print(
        f"Syncing {len(stock_codes)} stock(s), interfaces={','.join(interfaces)}, "
        f"date range {start_date} to {end_date}"
    )

    total_saved = 0
    skipped_count = 0
    failures = []
    total_tasks = len(stock_codes) * len(interfaces)
    task_index = 0
    synced_task_keys = set()
    if args.skip_synced:
        synced_task_keys = get_synced_task_keys(start_date, end_date)

    for stock_index, ts_code in enumerate(stock_codes, start=1):
        for interface_name in interfaces:
            task_index += 1
            table_name = FINANCIAL_INTERFACES[interface_name]

            if args.skip_synced and (interface_name, ts_code) in synced_task_keys:
                skipped_count += 1
                if args.verbose_skips:
                    print(
                        f"[{task_index}/{total_tasks}] {ts_code} {interface_name}: "
                        "skipped, already synced"
                    )
                continue

            try:
                df = fetch_financial(interface_name, ts_code, start_date, end_date)
                saved_count = save_financial_rows(table_name, df)
                total_saved += saved_count
                save_sync_status(
                    interface_name,
                    table_name,
                    ts_code,
                    start_date,
                    end_date,
                    saved_count,
                    "success",
                )
                print(
                    f"[{task_index}/{total_tasks}] "
                    f"stock {stock_index}/{len(stock_codes)} {ts_code} "
                    f"{interface_name}: saved {saved_count} row(s)"
                )
            except Exception as exc:
                error_message = str(exc)
                failures.append((ts_code, interface_name, error_message))
                save_sync_status(
                    interface_name,
                    table_name,
                    ts_code,
                    start_date,
                    end_date,
                    0,
                    "failed",
                    error_message,
                )
                print(
                    f"[{task_index}/{total_tasks}] {ts_code} {interface_name}: "
                    f"failed: {error_message}"
                )

            time.sleep(args.request_interval)

    print(
        f"Done. Saved or updated {total_saved} financial row(s). "
        f"Skipped {skipped_count} already-synced task(s)."
    )
    if failures:
        print("Failed tasks:")
        for ts_code, interface_name, error_message in failures:
            print(f"  {ts_code} {interface_name}: {error_message}")


if __name__ == "__main__":
    main()
