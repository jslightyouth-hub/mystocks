from collections import defaultdict
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


def get_previous_day_movers(
    page: int = 1,
    page_size: int = 50,
    direction: str = "top",
    total_pages: int = 5,
):
    page = max(1, min(page, total_pages))
    page_size = max(1, min(page_size, 50))
    offset = (page - 1) * page_size
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
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
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
                    s.industry,
                    s.sw_l1_name,
                    s.sw_l2_name,
                    s.sw_l3_name,
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
                OFFSET :offset
            """),
            {
                "trade_date": latest_trade_date,
                "limit": page_size,
                "offset": offset,
            },
        ).mappings().all()

    return {
        "trade_date": latest_trade_date,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in rows
        ],
    }


def get_previous_day_top_movers(page: int = 1, page_size: int = 50):
    return get_previous_day_movers(page, page_size, "top")


def get_previous_day_bottom_movers(page: int = 1, page_size: int = 50):
    return get_previous_day_movers(page, page_size, "bottom")


def get_industry_expr(level: str = "l2"):
    if level == "l3":
        return "s.sw_l3_name"
    return "COALESCE(s.sw_l2_name, s.industry)"


def get_industry_movers_rankings(exclude_high: int = 1, exclude_low: int = 1, level: str = "l2"):
    exclude_high = max(0, min(exclude_high, 10))
    exclude_low = max(0, min(exclude_low, 10))
    industry_expr = get_industry_expr(level)

    with engine.connect() as conn:
        latest_trade_date = conn.execute(
            text("SELECT MAX(trade_date) FROM daily_quotes")
        ).scalar_one_or_none()

        if not latest_trade_date:
            return {
                "trade_date": None,
                "exclude_high": exclude_high,
                "exclude_low": exclude_low,
                "items": [],
            }

        rows = conn.execute(
            text("""
                SELECT
                    q.ts_code,
                    COALESCE(s.name, q.ts_code) AS name,
                    q.pct_chg,
                    {industry_expr} AS industry_name
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                WHERE
                    q.trade_date = :trade_date
                    AND q.pct_chg IS NOT NULL
                    AND {industry_expr} IS NOT NULL
            """.format(industry_expr=industry_expr)),
            {"trade_date": latest_trade_date},
        ).mappings().all()

    industry_groups = defaultdict(list)
    for row in rows:
        industry_groups[row["industry_name"]].append({
            "ts_code": row["ts_code"],
            "name": row["name"],
            "pct_chg": serialize_value(row["pct_chg"]),
        })

    ranking_items = []
    for industry_name, stocks in industry_groups.items():
        sorted_stocks = sorted(stocks, key=lambda stock: stock["pct_chg"])
        excluded_count = exclude_high + exclude_low
        if len(sorted_stocks) <= excluded_count:
            continue

        end_index = len(sorted_stocks) - exclude_high if exclude_high else len(sorted_stocks)
        included_stocks = sorted_stocks[exclude_low:end_index]
        avg_pct_chg = sum(stock["pct_chg"] for stock in included_stocks) / len(included_stocks)

        ranking_items.append({
            "industry_name": industry_name,
            "avg_pct_chg": avg_pct_chg,
            "stock_count": len(sorted_stocks),
        })

    ranking_items.sort(key=lambda item: item["avg_pct_chg"], reverse=True)

    return {
        "trade_date": latest_trade_date,
        "exclude_high": exclude_high,
        "exclude_low": exclude_low,
        "items": [
            {key: serialize_value(value) for key, value in item.items()}
            for item in ranking_items
        ],
    }


def get_industry_stocks_rankings(industry_name: str, limit: int = 10, level: str = "l2"):
    limit = max(1, min(limit, 50))
    industry_expr = get_industry_expr(level)

    with engine.connect() as conn:
        latest_trade_date = conn.execute(
            text("SELECT MAX(trade_date) FROM daily_quotes")
        ).scalar_one_or_none()

        if not latest_trade_date:
            return {
                "trade_date": None,
                "industry_name": industry_name,
                "top_items": [],
                "bottom_items": [],
            }

        base_sql = """
                SELECT
                    q.ts_code,
                    COALESCE(s.name, q.ts_code) AS name,
                    q.trade_date,
                    q.close,
                    q.`change`,
                    q.pct_chg,
                    q.vol,
                    q.amount,
                    p.total_share,
                    p.float_share,
                    CASE
                        WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                        ELSE q.vol / p.float_share
                    END AS turnover_rate,
                    CASE
                        WHEN p.total_share IS NULL OR p.total_share = 0 THEN NULL
                        ELSE q.close * p.total_share
                    END AS market_value,
                    {industry_expr} AS industry_name
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                LEFT JOIN stock_premarket p
                    ON p.ts_code = q.ts_code
                    AND p.trade_date = q.trade_date
                WHERE
                    q.trade_date = :trade_date
                    AND q.pct_chg IS NOT NULL
                    AND {industry_expr} = :industry_name
                ORDER BY {order_sql}
                LIMIT :limit
            """
        params = {
            "trade_date": latest_trade_date,
            "industry_name": industry_name,
            "limit": limit,
        }
        top_rows = conn.execute(
            text(base_sql.format(
                industry_expr=industry_expr,
                order_sql="q.pct_chg DESC, q.amount DESC",
            )),
            params,
        ).mappings().all()
        bottom_rows = conn.execute(
            text(base_sql.format(
                industry_expr=industry_expr,
                order_sql="q.pct_chg ASC, q.amount DESC",
            )),
            params,
        ).mappings().all()

    return {
        "trade_date": latest_trade_date,
        "industry_name": industry_name,
        "top_items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in top_rows
        ],
        "bottom_items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in bottom_rows
        ],
    }
