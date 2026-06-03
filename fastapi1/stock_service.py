from datetime import datetime

import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


pro = ts.pro_api(TUSHARE_TOKEN)
engine = create_engine(DATABASE_URL)

# Fields required by the frontend quote row.
STOCK_FIELDS = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]


def get_today():
    # Tushare expects dates in YYYYMMDD format.
    return datetime.now().strftime("%Y%m%d")


def serialize_value(value):
    # Pandas/numpy scalar values need conversion before FastAPI serializes JSON.
    if value != value:
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def get_stock_name(ts_code: str):
    # Stock name is display-only, so fall back to the code when this optional call fails.
    try:
        basic = pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
    except Exception:
        return ts_code

    if basic.empty:
        return ts_code

    return serialize_value(basic.iloc[0]["name"])


def get_daily_stock(ts_code: str, trade_date=None):
    target_date = trade_date or get_today()
    # Query one trading day directly instead of keeping a fixed date range in main.py.
    df = pro.daily(
        ts_code=ts_code,
        trade_date=target_date,
    )

    if df.empty:
        return None

    latest = df.iloc[0]
    stock = {field: serialize_value(latest[field]) for field in STOCK_FIELDS}
    stock["name"] = get_stock_name(ts_code)

    return stock


def get_previous_day_movers(limit: int = 50, direction: str = "top"):
    limit = max(1, min(limit, 100))
    order_sql = "q.pct_chg DESC, q.amount DESC"
    if direction == "bottom":
        order_sql = "q.pct_chg ASC, q.amount DESC"

    with engine.connect() as conn:
        latest_trade_date = conn.execute(
            text("SELECT MAX(trade_date) FROM daily_quotes")
        ).scalar_one_or_none()

        if not latest_trade_date:
            return {
                "trade_date": None,
                "items": [],
            }

        rows = conn.execute(
            text(f"""
                SELECT
                    q.ts_code,
                    COALESCE(s.name, q.ts_code) AS name,
                    q.trade_date,
                    q.open,
                    q.high,
                    q.low,
                    q.close,
                    q.pre_close,
                    q.`change`,
                    q.pct_chg,
                    q.vol,
                    q.amount,
                    p.total_share,
                    p.float_share,
                    CASE
                        WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                        ELSE q.vol / p.float_share
                    END AS turnover_rate
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                LEFT JOIN stock_premarket p
                    ON p.ts_code = q.ts_code
                    AND p.trade_date = q.trade_date
                WHERE q.trade_date = :trade_date
                ORDER BY {order_sql}
                LIMIT :limit
            """),
            {
                "trade_date": latest_trade_date,
                "limit": limit,
            },
        ).mappings().all()

    return {
        "trade_date": latest_trade_date,
        "items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in rows
        ],
    }


def get_previous_day_top_movers(limit: int = 50):
    return get_previous_day_movers(limit, "top")


def get_previous_day_bottom_movers(limit: int = 50):
    return get_previous_day_movers(limit, "bottom")
