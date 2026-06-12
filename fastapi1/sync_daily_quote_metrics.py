import argparse

from sqlalchemy import create_engine, text

from settings import DATABASE_URL


engine = create_engine(DATABASE_URL)


def parse_args():
    parser = argparse.ArgumentParser(description="Calculate and save daily quote volume/amount metrics.")
    parser.add_argument(
        "--trade-date",
        default=None,
        help="Trade date to calculate in YYYYMMDD. Default: latest daily_quotes trade_date.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned rows without writing.")
    return parser.parse_args()


def create_daily_quote_metrics_table():
    sql = text("""
        CREATE TABLE IF NOT EXISTS daily_quote_metrics (
            id BIGINT NOT NULL AUTO_INCREMENT,
            ts_code VARCHAR(20) NOT NULL,
            trade_date CHAR(8) NOT NULL,
            avg_vol_5 DECIMAL(24, 4) NULL,
            avg_vol_20 DECIMAL(24, 4) NULL,
            vol_ratio_5 DECIMAL(18, 6) NULL,
            vol_ratio_20 DECIMAL(18, 6) NULL,
            avg_amount_20 DECIMAL(24, 4) NULL,
            amount_ratio_20 DECIMAL(18, 6) NULL,
            volume_signal VARCHAR(20) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_daily_quote_metrics_ts_code_trade_date (ts_code, trade_date),
            KEY idx_daily_quote_metrics_trade_date (trade_date),
            KEY idx_daily_quote_metrics_vol_ratio_20 (trade_date, vol_ratio_20),
            KEY idx_daily_quote_metrics_amount_ratio_20 (trade_date, amount_ratio_20)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def get_latest_trade_date():
    with engine.connect() as conn:
        return conn.execute(text("SELECT MAX(trade_date) FROM daily_quotes")).scalar_one_or_none()


def get_volume_signal(vol_ratio_20):
    if vol_ratio_20 is None:
        return None
    ratio = float(vol_ratio_20)
    if ratio >= 3:
        return "极端放量"
    if ratio >= 2:
        return "明显放量"
    if ratio >= 1.5:
        return "温和放量"
    if ratio <= 0.8:
        return "缩量"
    return "正常"


def calculate_daily_quote_metrics(trade_date):
    sql = text("""
        WITH previous_trade_dates AS (
            SELECT trade_date
            FROM (
                SELECT DISTINCT trade_date
                FROM daily_quotes
                WHERE trade_date < :trade_date
                ORDER BY trade_date DESC
                LIMIT 20
            ) dates
        ),
        ranked_quotes AS (
            SELECT
                q.ts_code,
                q.trade_date,
                q.vol,
                q.amount,
                ROW_NUMBER() OVER (
                    PARTITION BY q.ts_code
                    ORDER BY q.trade_date DESC
                ) AS rn
            FROM daily_quotes q
            INNER JOIN previous_trade_dates d ON d.trade_date = q.trade_date
        )
        SELECT
            q.ts_code,
            q.trade_date,
            AVG(CASE WHEN rq.rn <= 5 THEN rq.vol END) AS avg_vol_5,
            AVG(CASE WHEN rq.rn <= 20 THEN rq.vol END) AS avg_vol_20,
            CASE
                WHEN AVG(CASE WHEN rq.rn <= 5 THEN rq.vol END) IS NULL
                    OR AVG(CASE WHEN rq.rn <= 5 THEN rq.vol END) = 0
                THEN NULL
                ELSE q.vol / AVG(CASE WHEN rq.rn <= 5 THEN rq.vol END)
            END AS vol_ratio_5,
            CASE
                WHEN AVG(CASE WHEN rq.rn <= 20 THEN rq.vol END) IS NULL
                    OR AVG(CASE WHEN rq.rn <= 20 THEN rq.vol END) = 0
                THEN NULL
                ELSE q.vol / AVG(CASE WHEN rq.rn <= 20 THEN rq.vol END)
            END AS vol_ratio_20,
            AVG(CASE WHEN rq.rn <= 20 THEN rq.amount END) AS avg_amount_20,
            CASE
                WHEN AVG(CASE WHEN rq.rn <= 20 THEN rq.amount END) IS NULL
                    OR AVG(CASE WHEN rq.rn <= 20 THEN rq.amount END) = 0
                THEN NULL
                ELSE q.amount / AVG(CASE WHEN rq.rn <= 20 THEN rq.amount END)
            END AS amount_ratio_20
        FROM daily_quotes q
        LEFT JOIN ranked_quotes rq
            ON rq.ts_code = q.ts_code
            AND rq.rn <= 20
        WHERE q.trade_date = :trade_date
        GROUP BY q.ts_code, q.trade_date, q.vol, q.amount
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, {"trade_date": trade_date}).mappings().all()

    result = []
    for row in rows:
        item = dict(row)
        item["volume_signal"] = get_volume_signal(item.get("vol_ratio_20"))
        result.append(item)
    return result


def save_daily_quote_metrics(rows):
    if not rows:
        return 0

    sql = text("""
        INSERT INTO daily_quote_metrics (
            ts_code,
            trade_date,
            avg_vol_5,
            avg_vol_20,
            vol_ratio_5,
            vol_ratio_20,
            avg_amount_20,
            amount_ratio_20,
            volume_signal
        )
        VALUES (
            :ts_code,
            :trade_date,
            :avg_vol_5,
            :avg_vol_20,
            :vol_ratio_5,
            :vol_ratio_20,
            :avg_amount_20,
            :amount_ratio_20,
            :volume_signal
        )
        ON DUPLICATE KEY UPDATE
            avg_vol_5 = VALUES(avg_vol_5),
            avg_vol_20 = VALUES(avg_vol_20),
            vol_ratio_5 = VALUES(vol_ratio_5),
            vol_ratio_20 = VALUES(vol_ratio_20),
            avg_amount_20 = VALUES(avg_amount_20),
            amount_ratio_20 = VALUES(amount_ratio_20),
            volume_signal = VALUES(volume_signal)
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def sync_daily_quote_metrics(trade_date=None, dry_run=False):
    target_trade_date = trade_date or get_latest_trade_date()
    if not target_trade_date:
        return {"trade_date": None, "saved": 0, "calculated": 0}

    if not dry_run:
        create_daily_quote_metrics_table()

    rows = calculate_daily_quote_metrics(target_trade_date)
    saved_count = 0 if dry_run else save_daily_quote_metrics(rows)
    return {
        "trade_date": target_trade_date,
        "calculated": len(rows),
        "saved": saved_count,
    }


def main():
    args = parse_args()
    result = sync_daily_quote_metrics(args.trade_date, args.dry_run)
    print(f"trade_date: {result['trade_date'] or 'none'}")
    print(f"calculated rows: {result['calculated']}")
    print(f"saved rows: {result['saved']}")
    if args.dry_run:
        print("Dry run: no daily_quote_metrics rows were written.")


if __name__ == "__main__":
    main()
