from collections import defaultdict
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text

from settings import DATABASE_URL


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
    if value is None:
        return None
    if value != value:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def serialize_row(row):
    if not row:
        return None
    return {key: serialize_value(value) for key, value in row.items()}


def fetch_optional_row(conn, sql, params):
    try:
        row = conn.execute(text(sql), params).mappings().first()
    except Exception:
        return None
    return serialize_row(row)


def table_exists(conn, table_name):
    return conn.execute(
        text("SHOW TABLES LIKE :table_name"),
        {"table_name": table_name},
    ).first() is not None


def resolve_ts_code(conn, ts_code: str):
    exact = conn.execute(
        text("""
            SELECT ts_code
            FROM stocks
            WHERE ts_code = :ts_code
            LIMIT 1
        """),
        {"ts_code": ts_code},
    ).scalar_one_or_none()
    if exact:
        return exact

    symbol = (ts_code or "").split(".", 1)[0]
    if not symbol:
        return ts_code

    return conn.execute(
        text("""
            SELECT ts_code
            FROM stocks
            WHERE symbol = :symbol
            ORDER BY ts_code
            LIMIT 1
        """),
        {"symbol": symbol},
    ).scalar_one_or_none() or ts_code


def search_stocks(query: str, limit: int = 10, db_engine=engine):
    keyword = (query or "").strip()
    if not keyword:
        return []

    try:
        safe_limit = int(limit)
    except (TypeError, ValueError):
        safe_limit = 10
    safe_limit = min(max(safe_limit, 1), 20)

    upper_keyword = keyword.upper()
    params = {
        "keyword": keyword,
        "upper_keyword": upper_keyword,
        "prefix": f"{keyword}%",
        "upper_prefix": f"{upper_keyword}%",
        "like": f"%{keyword}%",
        "upper_like": f"%{upper_keyword}%",
        "limit": safe_limit,
    }

    with db_engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    ts_code,
                    symbol,
                    name,
                    industry,
                    sw_l1_name,
                    sw_l2_name,
                    sw_l3_name,
                    sw_l3_code
                FROM stocks
                WHERE UPPER(ts_code) LIKE :upper_like
                    OR symbol LIKE :like
                    OR name LIKE :like
                ORDER BY
                    CASE
                        WHEN UPPER(ts_code) = :upper_keyword
                            OR symbol = :keyword
                            OR name = :keyword THEN 0
                        WHEN UPPER(ts_code) LIKE :upper_prefix
                            OR symbol LIKE :prefix THEN 1
                        WHEN name LIKE :prefix THEN 2
                        ELSE 3
                    END,
                    ts_code
                LIMIT :limit
            """),
            params,
        ).mappings().all()

    return [serialize_row(row) for row in rows]


def get_baseline_close(conn, ts_code: str, start_date: str, inclusive: bool = False):
    operator = "<=" if inclusive else "<"
    return conn.execute(
        text(f"""
            SELECT close
            FROM daily_quotes
            WHERE ts_code = :ts_code
                AND trade_date {operator} :start_date
                AND close IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        """),
        {
            "ts_code": ts_code,
            "start_date": start_date,
        },
    ).scalar_one_or_none()


def calculate_pct_change(current_close, baseline_close):
    if current_close is None or baseline_close in (None, 0):
        return None

    current = float(current_close)
    baseline = float(baseline_close)
    if baseline == 0:
        return None

    return (current / baseline - 1) * 100


def add_months(value: datetime, months: int):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def get_stock_performance(conn, ts_code: str, latest_trade_date: str, current_close, today_pct_chg):
    try:
        trade_date = datetime.strptime(latest_trade_date, "%Y%m%d")
    except (TypeError, ValueError):
        return {
            "today_pct_chg": today_pct_chg,
            "month_pct_chg": None,
            "two_month_pct_chg": None,
            "three_month_pct_chg": None,
            "six_month_pct_chg": None,
            "year_pct_chg": None,
            "three_year_pct_chg": None,
        }

    month_start = trade_date.replace(day=1).strftime("%Y%m%d")
    two_month_start = add_months(trade_date, -2).strftime("%Y%m%d")
    three_month_start = add_months(trade_date, -3).strftime("%Y%m%d")
    six_month_start = add_months(trade_date, -6).strftime("%Y%m%d")
    year_start = trade_date.replace(month=1, day=1).strftime("%Y%m%d")
    try:
        three_year_start = trade_date.replace(year=trade_date.year - 3).strftime("%Y%m%d")
    except ValueError:
        three_year_start = trade_date.replace(year=trade_date.year - 3, day=28).strftime("%Y%m%d")

    month_base = get_baseline_close(conn, ts_code, month_start)
    two_month_base = get_baseline_close(conn, ts_code, two_month_start, inclusive=True)
    three_month_base = get_baseline_close(conn, ts_code, three_month_start, inclusive=True)
    six_month_base = get_baseline_close(conn, ts_code, six_month_start, inclusive=True)
    year_base = get_baseline_close(conn, ts_code, year_start)
    three_year_base = get_baseline_close(conn, ts_code, three_year_start, inclusive=True)

    return {
        "today_pct_chg": today_pct_chg,
        "month_pct_chg": calculate_pct_change(current_close, month_base),
        "two_month_pct_chg": calculate_pct_change(current_close, two_month_base),
        "three_month_pct_chg": calculate_pct_change(current_close, three_month_base),
        "six_month_pct_chg": calculate_pct_change(current_close, six_month_base),
        "year_pct_chg": calculate_pct_change(current_close, year_base),
        "three_year_pct_chg": calculate_pct_change(current_close, three_year_base),
    }


def safe_replace_year(value: datetime, years_delta: int):
    try:
        return value.replace(year=value.year + years_delta)
    except ValueError:
        return value.replace(year=value.year + years_delta, day=28)


def get_month_end(value: datetime):
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def get_margin_balance_on_or_before(conn, ts_code: str, target_date: str):
    row = fetch_optional_row(conn, """
        SELECT trade_date, rzye
        FROM stock_margin_detail
        WHERE ts_code = :ts_code
            AND trade_date <= :target_date
            AND rzye IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 1
    """, {"ts_code": ts_code, "target_date": target_date})

    if not row:
        return {"trade_date": None, "rzye": None}

    return row


def get_stock_margin_balances(conn, ts_code: str, latest_trade_date: str):
    empty = {
        "current": {"trade_date": None, "rzye": None},
        "last_week_end": {"trade_date": None, "rzye": None},
        "last_month_end": {"trade_date": None, "rzye": None},
        "three_month_end": {"trade_date": None, "rzye": None},
        "one_year_ago": {"trade_date": None, "rzye": None},
        "two_year_ago": {"trade_date": None, "rzye": None},
    }

    if not table_exists(conn, "stock_margin_detail"):
        return empty

    try:
        trade_date = datetime.strptime(latest_trade_date, "%Y%m%d")
    except (TypeError, ValueError):
        return empty

    last_week_end = trade_date - timedelta(days=trade_date.weekday() + 1)
    last_month_end = trade_date.replace(day=1) - timedelta(days=1)
    three_month = add_months(trade_date.replace(day=1), -3)
    three_month_end = get_month_end(three_month)
    one_year_ago = safe_replace_year(trade_date, -1)
    two_year_ago = safe_replace_year(trade_date, -2)

    anchors = {
        "current": trade_date,
        "last_week_end": last_week_end,
        "last_month_end": last_month_end,
        "three_month_end": three_month_end,
        "one_year_ago": one_year_ago,
        "two_year_ago": two_year_ago,
    }

    return {
        key: get_margin_balance_on_or_before(conn, ts_code, value.strftime("%Y%m%d"))
        for key, value in anchors.items()
    }


def get_stock_concepts(conn, ts_code: str):
    if not table_exists(conn, "concepts") or not table_exists(conn, "stock_concepts"):
        return []

    rows = conn.execute(
        text("""
            SELECT
                c.concept_code,
                c.concept_name,
                c.source
            FROM stock_concepts sc
            INNER JOIN concepts c
                ON c.source = sc.source
                AND c.concept_code = sc.concept_code COLLATE utf8mb4_unicode_ci
            WHERE sc.ts_code = :ts_code
                AND sc.is_current = 1
            ORDER BY sc.rank_no IS NULL, sc.rank_no, c.concept_name
        """),
        {"ts_code": ts_code},
    ).mappings().all()

    return [serialize_row(row) for row in rows]


def get_daily_stock(ts_code: str, trade_date=None):
    quote_date_filter = "AND q.trade_date <= :trade_date" if trade_date else ""

    with engine.connect() as conn:
        resolved_ts_code = resolve_ts_code(conn, ts_code)
        params = {"ts_code": resolved_ts_code}
        if trade_date:
            params["trade_date"] = trade_date

        quote = fetch_optional_row(conn, f"""
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
                s.symbol,
                s.area,
                s.industry,
                s.sw_l1_code,
                s.sw_l1_name,
                s.sw_l2_code,
                s.sw_l2_name,
                s.sw_l3_code,
                s.sw_l3_name,
                p.total_share,
                p.float_share,
                CASE
                    WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                    ELSE q.vol / p.float_share
                END AS turnover_rate,
                CASE
                    WHEN p.total_share IS NULL OR p.total_share = 0 THEN NULL
                    ELSE q.close * p.total_share
                END AS market_value
            FROM daily_quotes q
            LEFT JOIN stocks s ON s.ts_code = q.ts_code COLLATE utf8mb4_0900_ai_ci
            LEFT JOIN stock_premarket p
                ON p.ts_code = q.ts_code
                AND p.trade_date = q.trade_date
            WHERE q.ts_code = :ts_code
                {quote_date_filter}
            ORDER BY q.trade_date DESC
            LIMIT 1
        """, params)

        if not quote:
            return None

        performance = get_stock_performance(
            conn,
            quote["ts_code"],
            quote["trade_date"],
            quote["close"],
            quote["pct_chg"],
        )
        margin_balances = get_stock_margin_balances(
            conn,
            quote["ts_code"],
            quote["trade_date"],
        )
        concepts = get_stock_concepts(conn, quote["ts_code"])

        quote_metrics = fetch_optional_row(conn, """
            SELECT
                ts_code,
                trade_date,
                avg_vol_5,
                avg_vol_20,
                vol_ratio_5,
                vol_ratio_20,
                avg_amount_20,
                amount_ratio_20,
                volume_signal
            FROM daily_quote_metrics
            WHERE ts_code = :ts_code
                AND trade_date = :trade_date
            LIMIT 1
        """, {"ts_code": quote["ts_code"], "trade_date": quote["trade_date"]})

        company = fetch_optional_row(conn, """
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
            WHERE ts_code = :ts_code
            LIMIT 1
        """, params)

        indicator = fetch_optional_row(conn, """
            SELECT
                ts_code,
                end_date,
                ann_date,
                eps,
                bps,
                roe,
                grossprofit_margin,
                netprofit_margin,
                debt_to_assets,
                or_yoy,
                netprofit_yoy
            FROM financial_indicator
            WHERE ts_code = :ts_code
            ORDER BY end_date DESC, ann_date DESC
            LIMIT 1
        """, params)

        income = fetch_optional_row(conn, """
            SELECT
                ts_code,
                end_date,
                ann_date,
                revenue,
                total_revenue,
                total_profit,
                n_income_attr_p,
                basic_eps
            FROM financial_income
            WHERE ts_code = :ts_code
            ORDER BY end_date DESC, ann_date DESC
            LIMIT 1
        """, params)

        balance = fetch_optional_row(conn, """
            SELECT
                ts_code,
                end_date,
                ann_date,
                total_assets,
                total_liab,
                total_hldr_eqy_exc_min_int,
                money_cap
            FROM financial_balancesheet
            WHERE ts_code = :ts_code
            ORDER BY end_date DESC, ann_date DESC
            LIMIT 1
        """, params)

        cashflow = fetch_optional_row(conn, """
            SELECT
                ts_code,
                end_date,
                ann_date,
                n_cashflow_act,
                n_cashflow_inv_act,
                n_cash_flows_fnc_act,
                free_cashflow
            FROM financial_cashflow
            WHERE ts_code = :ts_code
            ORDER BY end_date DESC, ann_date DESC
            LIMIT 1
        """, params)

        main_business_composition = []
        main_business_composition_groups = {
            "product": [],
            "region": [],
            "industry": [],
        }
        if table_exists(conn, "financial_mainbz"):
            rows = conn.execute(
                text("""
                    SELECT
                        ts_code,
                        end_date,
                        bz_item,
                        bz_code,
                        bz_sales,
                        bz_profit,
                        bz_cost,
                        curr_type
                    FROM financial_mainbz
                    WHERE ts_code = :ts_code
                        AND end_date = (
                            SELECT MAX(end_date)
                            FROM financial_mainbz
                            WHERE ts_code = :ts_code
                        )
                        AND bz_code IN ('P', 'D', 'I')
                    ORDER BY
                        FIELD(bz_code, 'P', 'D', 'I'),
                        CASE WHEN bz_sales IS NULL THEN 1 ELSE 0 END,
                        bz_sales DESC
                """),
                params,
            ).mappings().all()
            main_business_rows = [serialize_row(row) for row in rows]
            group_map = {
                "P": "product",
                "D": "region",
                "I": "industry",
            }
            for row in main_business_rows:
                group_name = group_map.get(row.get("bz_code"))
                if group_name:
                    main_business_composition_groups[group_name].append(row)
            main_business_composition = main_business_composition_groups["product"]

    basic = {
        "ts_code": quote["ts_code"],
        "symbol": quote.get("symbol"),
        "name": quote["name"],
        "area": quote.get("area"),
        "industry": quote.get("industry"),
        "sw_l1_code": quote.get("sw_l1_code"),
        "sw_l1_name": quote.get("sw_l1_name"),
        "sw_l2_code": quote.get("sw_l2_code"),
        "sw_l2_name": quote.get("sw_l2_name"),
        "sw_l3_code": quote.get("sw_l3_code"),
        "sw_l3_name": quote.get("sw_l3_name"),
    }
    share = {
        "total_share": quote.get("total_share"),
        "float_share": quote.get("float_share"),
        "turnover_rate": quote.get("turnover_rate"),
        "market_value": quote.get("market_value"),
    }
    financial = {
        "period": (indicator or income or balance or cashflow or {}).get("end_date"),
        "ann_date": (indicator or income or balance or cashflow or {}).get("ann_date"),
        "indicator": indicator,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
        "main_business_composition": main_business_composition,
        "main_business_composition_groups": main_business_composition_groups,
    }

    return {
        **quote,
        "basic": basic,
        "quote": {field: quote.get(field) for field in STOCK_FIELDS},
        "company": company,
        "share": share,
        "financial": financial,
        "performance": performance,
        "metrics": quote_metrics,
        "concepts": concepts,
        "margin": {
            "financing_balance": margin_balances,
        },
    }


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


VOLUME_MOVER_SORTS = {
    "vol_ratio_20_desc": "m.vol_ratio_20 DESC, q.amount DESC",
    "vol_ratio_20_asc": "m.vol_ratio_20 ASC, q.amount DESC",
    "vol_ratio_5_desc": "m.vol_ratio_5 DESC, q.amount DESC",
    "vol_ratio_5_asc": "m.vol_ratio_5 ASC, q.amount DESC",
    "amount_ratio_20_desc": "m.amount_ratio_20 DESC, q.amount DESC",
    "amount_ratio_20_asc": "m.amount_ratio_20 ASC, q.amount DESC",
    "amount_desc": "q.amount DESC, m.vol_ratio_20 DESC",
    "pct_chg_desc": "q.pct_chg DESC, m.vol_ratio_20 DESC",
}


def get_volume_movers(page: int = 1, page_size: int = 50, sort: str = "vol_ratio_20_desc"):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    order_sql = VOLUME_MOVER_SORTS.get(sort, VOLUME_MOVER_SORTS["vol_ratio_20_desc"])

    with engine.connect() as conn:
        if not table_exists(conn, "daily_quote_metrics"):
            return {
                "trade_date": None,
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "items": [],
            }

        latest_trade_date = conn.execute(
            text("SELECT MAX(trade_date) FROM daily_quote_metrics")
        ).scalar_one_or_none()

        if not latest_trade_date:
            return {
                "trade_date": None,
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "items": [],
            }

        total = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM daily_quote_metrics m
                WHERE m.trade_date = :trade_date
                    AND m.vol_ratio_20 IS NOT NULL
            """),
            {"trade_date": latest_trade_date},
        ).scalar_one()
        total_pages = (total + page_size - 1) // page_size if total else 0
        page = min(page, total_pages or 1)
        offset = (page - 1) * page_size

        rows = conn.execute(
            text(f"""
                SELECT
                    q.ts_code,
                    COALESCE(s.name, q.ts_code) AS name,
                    q.trade_date,
                    q.close,
                    q.`change`,
                    q.pct_chg,
                    q.vol,
                    q.amount,
                    m.vol_ratio_20,
                    m.volume_signal,
                    s.industry,
                    s.sw_l2_name,
                    s.sw_l3_name,
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
                    m.avg_vol_5,
                    m.avg_vol_20,
                    m.vol_ratio_5,
                    m.vol_ratio_20,
                    m.avg_amount_20,
                    m.amount_ratio_20,
                    m.volume_signal
                FROM daily_quote_metrics m
                INNER JOIN daily_quotes q
                    ON q.ts_code = m.ts_code COLLATE utf8mb4_unicode_ci
                    AND q.trade_date = m.trade_date COLLATE utf8mb4_unicode_ci
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                LEFT JOIN stock_premarket p
                    ON p.ts_code = q.ts_code
                    AND p.trade_date = q.trade_date
                WHERE m.trade_date = :trade_date
                    AND m.vol_ratio_20 IS NOT NULL
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
        "total": serialize_value(total),
        "total_pages": serialize_value(total_pages),
        "items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in rows
        ],
    }


INDUSTRY_LEVELS = {
    "l1": {
        "code": "s.sw_l1_code",
        "name": "s.sw_l1_name",
        "parent_code": "NULL",
        "parent_name": "NULL",
        "child_code": "s.sw_l2_code",
    },
    "l2": {
        "code": "s.sw_l2_code",
        "name": "s.sw_l2_name",
        "parent_code": "NULL",
        "parent_name": "NULL",
        "child_code": "s.sw_l3_code",
    },
    "l3": {
        "code": "s.sw_l3_code",
        "name": "s.sw_l3_name",
        "parent_code": "s.sw_l2_code",
        "parent_name": "s.sw_l2_name",
        "child_code": "NULL",
    },
}

INDUSTRY_STOCK_SORTS = {
    "pct_chg_desc": "q.pct_chg DESC, q.amount DESC",
    "pct_chg_asc": "q.pct_chg ASC, q.amount DESC",
    "amount_desc": "q.amount DESC, q.pct_chg DESC",
    "market_value_desc": "market_value DESC, q.amount DESC",
    "turnover_rate_desc": "turnover_rate DESC, q.amount DESC",
}


def get_industry_config(level: str):
    if level not in INDUSTRY_LEVELS:
        raise ValueError(f"Unsupported industry level: {level}")
    return INDUSTRY_LEVELS[level]


def get_latest_trade_date(conn):
    return conn.execute(text("SELECT MAX(trade_date) FROM daily_quotes")).scalar_one_or_none()


def get_industry_list(level: str = "l2"):
    config = get_industry_config(level)

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    {code_expr} AS industry_code,
                    {name_expr} AS industry_name,
                    COUNT(*) AS stock_count,
                    COUNT(DISTINCT {child_code_expr}) AS children_count,
                    MAX(s.industry_updated_at) AS updated_at
                FROM stocks s
                WHERE {code_expr} IS NOT NULL
                    AND {name_expr} IS NOT NULL
                GROUP BY {code_expr}, {name_expr}
                ORDER BY {code_expr}
            """.format(
                code_expr=config["code"],
                name_expr=config["name"],
                child_code_expr=config["child_code"],
            ))
        ).mappings().all()

    return {
        "level": level,
        "source": "sw",
        "items": [
            {
                **{key: serialize_value(value) for key, value in row.items()},
                "level": level,
                "source": "sw",
            }
            for row in rows
        ],
    }


def get_industry_detail(level: str, industry_code: str):
    config = get_industry_config(level)

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    {code_expr} AS industry_code,
                    {name_expr} AS industry_name,
                    {parent_code_expr} AS parent_code,
                    {parent_name_expr} AS parent_name,
                    COUNT(*) AS stock_count,
                    COUNT(DISTINCT {child_code_expr}) AS children_count,
                    MAX(s.industry_updated_at) AS updated_at
                FROM stocks s
                WHERE {code_expr} = :industry_code
                    AND {name_expr} IS NOT NULL
                GROUP BY
                    {code_expr},
                    {name_expr},
                    {parent_code_expr},
                    {parent_name_expr}
                LIMIT 1
            """.format(
                code_expr=config["code"],
                name_expr=config["name"],
                parent_code_expr=config["parent_code"],
                parent_name_expr=config["parent_name"],
                child_code_expr=config["child_code"],
            )),
            {"industry_code": industry_code},
        ).mappings().first()

    if not row:
        return None

    return {
        **{key: serialize_value(value) for key, value in row.items()},
        "level": level,
        "source": "sw",
    }


def get_l2_industry_children(l2_code: str):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    s.sw_l3_code AS industry_code,
                    s.sw_l3_name AS industry_name,
                    s.sw_l2_code AS parent_code,
                    s.sw_l2_name AS parent_name,
                    COUNT(*) AS stock_count,
                    MAX(s.industry_updated_at) AS updated_at
                FROM stocks s
                WHERE s.sw_l2_code = :l2_code
                    AND s.sw_l3_code IS NOT NULL
                    AND s.sw_l3_name IS NOT NULL
                GROUP BY
                    s.sw_l3_code,
                    s.sw_l3_name,
                    s.sw_l2_code,
                    s.sw_l2_name
                ORDER BY s.sw_l3_code
            """),
            {"l2_code": l2_code},
        ).mappings().all()

    return {
        "parent_code": l2_code,
        "level": "l3",
        "source": "sw",
        "items": [
            {
                **{key: serialize_value(value) for key, value in row.items()},
                "level": "l3",
                "source": "sw",
            }
            for row in rows
        ],
    }


def get_industry_movers_rankings(exclude_high: int = 1, exclude_low: int = 1, level: str = "l2"):
    exclude_high = max(0, min(exclude_high, 10))
    exclude_low = max(0, min(exclude_low, 10))
    config = get_industry_config(level)

    with engine.connect() as conn:
        latest_trade_date = get_latest_trade_date(conn)

        if not latest_trade_date:
            return {
                "trade_date": None,
                "level": level,
                "source": "sw",
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
                    q.vol,
                    q.amount,
                    m.avg_vol_5,
                    m.avg_vol_20,
                    m.avg_amount_20,
                    m.volume_signal,
                    {code_expr} AS industry_code,
                    {name_expr} AS industry_name
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                LEFT JOIN daily_quote_metrics m
                    ON m.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
                    AND m.trade_date = q.trade_date COLLATE utf8mb4_unicode_ci
                WHERE
                    q.trade_date = :trade_date
                    AND q.pct_chg IS NOT NULL
                    AND {code_expr} IS NOT NULL
                    AND {name_expr} IS NOT NULL
            """.format(
                code_expr=config["code"],
                name_expr=config["name"],
            )),
            {"trade_date": latest_trade_date},
        ).mappings().all()

    industry_groups = defaultdict(list)
    for row in rows:
        industry_key = (row["industry_code"], row["industry_name"])
        industry_groups[industry_key].append({
            "ts_code": row["ts_code"],
            "name": row["name"],
            "pct_chg": serialize_value(row["pct_chg"]),
            "vol": serialize_value(row["vol"]),
            "amount": serialize_value(row["amount"]),
            "avg_vol_5": serialize_value(row["avg_vol_5"]),
            "avg_vol_20": serialize_value(row["avg_vol_20"]),
            "avg_amount_20": serialize_value(row["avg_amount_20"]),
            "volume_signal": row["volume_signal"],
        })

    ranking_items = []
    for (industry_code, industry_name), stocks in industry_groups.items():
        sorted_stocks = sorted(stocks, key=lambda stock: stock["pct_chg"])
        excluded_count = exclude_high + exclude_low
        if len(sorted_stocks) <= excluded_count:
            continue

        end_index = len(sorted_stocks) - exclude_high if exclude_high else len(sorted_stocks)
        included_stocks = sorted_stocks[exclude_low:end_index]
        avg_pct_chg = sum(stock["pct_chg"] for stock in included_stocks) / len(included_stocks)
        total_vol = sum(float(stock["vol"] or 0) for stock in sorted_stocks)
        total_amount = sum(float(stock["amount"] or 0) for stock in sorted_stocks)
        total_avg_vol_5 = sum(float(stock["avg_vol_5"] or 0) for stock in sorted_stocks)
        total_avg_vol_20 = sum(float(stock["avg_vol_20"] or 0) for stock in sorted_stocks)
        total_avg_amount_20 = sum(float(stock["avg_amount_20"] or 0) for stock in sorted_stocks)

        ranking_items.append({
            "industry_code": industry_code,
            "industry_name": industry_name,
            "level": level,
            "source": "sw",
            "avg_pct_chg": avg_pct_chg,
            "stock_count": len(sorted_stocks),
            "up_count": sum(1 for stock in sorted_stocks if stock["pct_chg"] > 0),
            "down_count": sum(1 for stock in sorted_stocks if stock["pct_chg"] < 0),
            "vol_ratio_5": total_vol / total_avg_vol_5 if total_avg_vol_5 else None,
            "vol_ratio_20": total_vol / total_avg_vol_20 if total_avg_vol_20 else None,
            "amount_ratio_20": total_amount / total_avg_amount_20 if total_avg_amount_20 else None,
            "extreme_volume_count": sum(1 for stock in sorted_stocks if stock["volume_signal"] == "极端放量"),
            "strong_volume_count": sum(1 for stock in sorted_stocks if stock["volume_signal"] == "明显放量"),
            "shrink_volume_count": sum(1 for stock in sorted_stocks if stock["volume_signal"] == "缩量"),
        })

    ranking_items.sort(key=lambda item: item["avg_pct_chg"], reverse=True)

    return {
        "trade_date": latest_trade_date,
        "level": level,
        "source": "sw",
        "exclude_high": exclude_high,
        "exclude_low": exclude_low,
        "items": [
            {key: serialize_value(value) for key, value in item.items()}
            for item in ranking_items
        ],
    }


def get_industry_stocks(
    level: str,
    industry_code: str,
    page: int = 1,
    page_size: int = 50,
    sort: str = "pct_chg_desc",
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    config = get_industry_config(level)
    order_sql = INDUSTRY_STOCK_SORTS.get(sort, INDUSTRY_STOCK_SORTS["pct_chg_desc"])

    with engine.connect() as conn:
        latest_trade_date = get_latest_trade_date(conn)

        if not latest_trade_date:
            return {
                "trade_date": None,
                "industry_code": industry_code,
                "level": level,
                "source": "sw",
                "page": page,
                "page_size": page_size,
                "total": 0,
                "items": [],
            }

        total = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                WHERE
                    q.trade_date = :trade_date
                    AND {code_expr} = :industry_code
            """.format(code_expr=config["code"])),
            {
                "trade_date": latest_trade_date,
                "industry_code": industry_code,
            },
        ).scalar_one()

        rows = conn.execute(
            text("""
                SELECT
                    q.ts_code,
                    COALESCE(s.name, q.ts_code) AS name,
                    q.trade_date,
                    q.close,
                    q.`change`,
                    q.pct_chg,
                    q.vol,
                    q.amount,
                    m.vol_ratio_20,
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
                    {code_expr} AS industry_code,
                    {name_expr} AS industry_name
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                LEFT JOIN stock_premarket p
                    ON p.ts_code = q.ts_code
                    AND p.trade_date = q.trade_date
                LEFT JOIN daily_quote_metrics m
                    ON m.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
                    AND m.trade_date = q.trade_date COLLATE utf8mb4_unicode_ci
                WHERE
                    q.trade_date = :trade_date
                    AND {code_expr} = :industry_code
                ORDER BY {order_sql}
                LIMIT :limit
                OFFSET :offset
            """.format(
                code_expr=config["code"],
                name_expr=config["name"],
                order_sql=order_sql,
            )),
            {
                "trade_date": latest_trade_date,
                "industry_code": industry_code,
                "limit": page_size,
                "offset": offset,
            },
        ).mappings().all()

    return {
        "trade_date": latest_trade_date,
        "industry_code": industry_code,
        "level": level,
        "source": "sw",
        "page": page,
        "page_size": page_size,
        "total": serialize_value(total),
        "items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in rows
        ],
    }


def get_industry_market(level: str, industry_code: str):
    config = get_industry_config(level)

    with engine.connect() as conn:
        latest_trade_date = get_latest_trade_date(conn)

        if not latest_trade_date:
            return {
                "trade_date": None,
                "industry_code": industry_code,
                "level": level,
                "source": "sw",
            }

        row = conn.execute(
            text("""
                SELECT
                    {code_expr} AS industry_code,
                    {name_expr} AS industry_name,
                    COUNT(*) AS stock_count,
                    SUM(CASE WHEN q.pct_chg > 0 THEN 1 ELSE 0 END) AS up_count,
                    SUM(CASE WHEN q.pct_chg < 0 THEN 1 ELSE 0 END) AS down_count,
                    SUM(CASE WHEN q.pct_chg = 0 THEN 1 ELSE 0 END) AS flat_count,
                    AVG(q.pct_chg) AS avg_pct_chg,
                    SUM(q.amount) AS amount,
                    AVG(CASE
                        WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                        ELSE q.vol / p.float_share
                    END) AS avg_turnover_rate,
                    SUM(CASE
                        WHEN p.total_share IS NULL OR p.total_share = 0 THEN NULL
                        ELSE q.close * p.total_share
                    END) AS market_value,
                    CASE
                        WHEN SUM(m.avg_vol_5) IS NULL OR SUM(m.avg_vol_5) = 0 THEN NULL
                        ELSE SUM(q.vol) / SUM(m.avg_vol_5)
                    END AS vol_ratio_5,
                    CASE
                        WHEN SUM(m.avg_vol_20) IS NULL OR SUM(m.avg_vol_20) = 0 THEN NULL
                        ELSE SUM(q.vol) / SUM(m.avg_vol_20)
                    END AS vol_ratio_20,
                    CASE
                        WHEN SUM(m.avg_amount_20) IS NULL OR SUM(m.avg_amount_20) = 0 THEN NULL
                        ELSE SUM(q.amount) / SUM(m.avg_amount_20)
                    END AS amount_ratio_20,
                    SUM(CASE WHEN m.volume_signal = '极端放量' THEN 1 ELSE 0 END) AS extreme_volume_count,
                    SUM(CASE WHEN m.volume_signal = '明显放量' THEN 1 ELSE 0 END) AS strong_volume_count,
                    SUM(CASE WHEN m.volume_signal = '缩量' THEN 1 ELSE 0 END) AS shrink_volume_count
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                LEFT JOIN stock_premarket p
                    ON p.ts_code = q.ts_code
                    AND p.trade_date = q.trade_date
                LEFT JOIN daily_quote_metrics m
                    ON m.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
                    AND m.trade_date = q.trade_date COLLATE utf8mb4_unicode_ci
                WHERE
                    q.trade_date = :trade_date
                    AND {code_expr} = :industry_code
                GROUP BY {code_expr}, {name_expr}
                LIMIT 1
            """.format(
                code_expr=config["code"],
                name_expr=config["name"],
            )),
            {
                "trade_date": latest_trade_date,
                "industry_code": industry_code,
            },
        ).mappings().first()

    if not row:
        return None

    return {
        **{key: serialize_value(value) for key, value in row.items()},
        "trade_date": latest_trade_date,
        "level": level,
        "source": "sw",
    }


def get_industry_stock_movers(level: str, industry_code: str, limit: int = 10):
    limit = max(1, min(limit, 50))
    config = get_industry_config(level)

    with engine.connect() as conn:
        latest_trade_date = get_latest_trade_date(conn)

        if not latest_trade_date:
            return {
                "trade_date": None,
                "industry_code": industry_code,
                "level": level,
                "source": "sw",
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
                    m.vol_ratio_20,
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
                    {code_expr} AS industry_code,
                    {name_expr} AS industry_name
                FROM daily_quotes q
                LEFT JOIN stocks s ON s.ts_code COLLATE utf8mb4_unicode_ci = q.ts_code
                LEFT JOIN stock_premarket p
                    ON p.ts_code = q.ts_code
                    AND p.trade_date = q.trade_date
                LEFT JOIN daily_quote_metrics m
                    ON m.ts_code = q.ts_code COLLATE utf8mb4_unicode_ci
                    AND m.trade_date = q.trade_date COLLATE utf8mb4_unicode_ci
                WHERE
                    q.trade_date = :trade_date
                    AND q.pct_chg IS NOT NULL
                    AND {code_expr} = :industry_code
                ORDER BY {order_sql}
                LIMIT :limit
            """
        params = {
            "trade_date": latest_trade_date,
            "industry_code": industry_code,
            "limit": limit,
        }
        top_rows = conn.execute(
            text(base_sql.format(
                code_expr=config["code"],
                name_expr=config["name"],
                order_sql="q.pct_chg DESC, q.amount DESC",
            )),
            params,
        ).mappings().all()
        bottom_rows = conn.execute(
            text(base_sql.format(
                code_expr=config["code"],
                name_expr=config["name"],
                order_sql="q.pct_chg ASC, q.amount DESC",
            )),
            params,
        ).mappings().all()

    return {
        "trade_date": latest_trade_date,
        "industry_code": industry_code,
        "level": level,
        "source": "sw",
        "top_items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in top_rows
        ],
        "bottom_items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in bottom_rows
        ],
    }


def get_concept_movers_rankings():
    with engine.connect() as conn:
        latest_trade_date = get_latest_trade_date(conn)

        if not latest_trade_date:
            return {
                "trade_date": None,
                "source": "ths",
                "items": [],
            }

        rows = conn.execute(
            text("""
                SELECT
                    c.concept_code,
                    c.concept_name,
                    COUNT(DISTINCT sc.ts_code) AS stock_count,
                    SUM(CASE WHEN q.pct_chg > 0 THEN 1 ELSE 0 END) AS up_count,
                    SUM(CASE WHEN q.pct_chg < 0 THEN 1 ELSE 0 END) AS down_count,
                    SUM(CASE WHEN q.pct_chg = 0 THEN 1 ELSE 0 END) AS flat_count,
                    AVG(q.pct_chg) AS avg_pct_chg,
                    MAX(c.updated_at) AS updated_at
                FROM concepts c
                INNER JOIN stock_concepts sc
                    ON sc.source = c.source
                    AND sc.concept_code = c.concept_code COLLATE utf8mb4_unicode_ci
                    AND sc.is_current = 1
                INNER JOIN daily_quotes q
                    ON q.ts_code = sc.ts_code COLLATE utf8mb4_unicode_ci
                    AND q.trade_date = :trade_date
                WHERE q.pct_chg IS NOT NULL
                GROUP BY c.concept_code, c.concept_name
                ORDER BY avg_pct_chg DESC, stock_count DESC
            """),
            {"trade_date": latest_trade_date},
        ).mappings().all()

    return {
        "trade_date": latest_trade_date,
        "source": "ths",
        "items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in rows
        ],
    }


def get_concept_detail(concept_code: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    c.concept_code,
                    c.concept_name,
                    c.source,
                    c.detail_url,
                    COUNT(DISTINCT sc.ts_code) AS stock_count,
                    MAX(c.updated_at) AS updated_at
                FROM concepts c
                LEFT JOIN stock_concepts sc
                    ON sc.source = c.source
                    AND sc.concept_code = c.concept_code COLLATE utf8mb4_unicode_ci
                    AND sc.is_current = 1
                WHERE c.concept_code = :concept_code
                GROUP BY
                    c.concept_code,
                    c.concept_name,
                    c.source,
                    c.detail_url
                LIMIT 1
            """),
            {"concept_code": concept_code},
        ).mappings().first()

    if not row:
        return None

    return {key: serialize_value(value) for key, value in row.items()}


def get_concept_stock_movers(
    concept_code: str,
    page: int = 1,
    page_size: int = 10,
    direction: str = "top",
):
    total_pages_limit = 5
    page = max(1, min(page, total_pages_limit))
    page_size = max(1, min(page_size, 10))
    offset = (page - 1) * page_size
    order_sql = "q.pct_chg DESC, q.amount DESC"
    if direction == "bottom":
        order_sql = "q.pct_chg ASC, q.amount DESC"

    with engine.connect() as conn:
        latest_trade_date = get_latest_trade_date(conn)

        concept = conn.execute(
            text("""
                SELECT concept_code, concept_name, source
                FROM concepts
                WHERE concept_code = :concept_code
                LIMIT 1
            """),
            {"concept_code": concept_code},
        ).mappings().first()

        if not concept:
            return None

        if not latest_trade_date:
            return {
                "trade_date": None,
                "concept_code": concept_code,
                "concept_name": concept["concept_name"],
                "source": serialize_value(concept["source"]).lower(),
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "items": [],
            }

        total = conn.execute(
            text("""
                SELECT COUNT(DISTINCT COALESCE(s.ts_code, sc.ts_code))
                FROM stock_concepts sc
                LEFT JOIN stocks s
                    ON s.ts_code COLLATE utf8mb4_unicode_ci = sc.ts_code
                    OR s.symbol COLLATE utf8mb4_unicode_ci = SUBSTRING_INDEX(sc.ts_code, '.', 1)
                INNER JOIN daily_quotes q
                    ON q.ts_code COLLATE utf8mb4_unicode_ci = COALESCE(s.ts_code, sc.ts_code) COLLATE utf8mb4_unicode_ci
                    AND q.trade_date = :trade_date
                WHERE
                    sc.concept_code = :concept_code
                    AND sc.source = :source
                    AND sc.is_current = 1
                    AND q.pct_chg IS NOT NULL
            """),
            {
                "trade_date": latest_trade_date,
                "concept_code": concept_code,
                "source": concept["source"],
            },
        ).scalar_one()

        rows = conn.execute(
            text("""
                SELECT
                    q.ts_code,
                    COALESCE(s.name, sc.stock_name, q.ts_code) AS name,
                    q.trade_date,
                    q.close,
                    q.`change`,
                    q.pct_chg,
                    q.vol,
                    q.amount,
                    m.vol_ratio_20,
                    m.volume_signal,
                    s.industry,
                    s.sw_l2_name,
                    s.sw_l3_name,
                    p.total_share,
                    p.float_share,
                    CASE
                        WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                        ELSE q.vol / p.float_share
                    END AS turnover_rate,
                    CASE
                        WHEN p.total_share IS NULL OR p.total_share = 0 THEN NULL
                        ELSE q.close * p.total_share
                    END AS market_value
                FROM stock_concepts sc
                LEFT JOIN stocks s
                    ON s.ts_code COLLATE utf8mb4_unicode_ci = sc.ts_code
                    OR s.symbol COLLATE utf8mb4_unicode_ci = SUBSTRING_INDEX(sc.ts_code, '.', 1)
                INNER JOIN daily_quotes q
                    ON q.ts_code COLLATE utf8mb4_unicode_ci = COALESCE(s.ts_code, sc.ts_code) COLLATE utf8mb4_unicode_ci
                    AND q.trade_date = :trade_date
                LEFT JOIN stock_premarket p
                    ON p.ts_code = q.ts_code
                    AND p.trade_date = q.trade_date
                WHERE
                    sc.concept_code = :concept_code
                    AND sc.source = :source
                    AND sc.is_current = 1
                    AND q.pct_chg IS NOT NULL
                ORDER BY {order_sql}
                LIMIT :limit
                OFFSET :offset
            """.format(order_sql=order_sql)),
            {
                "trade_date": latest_trade_date,
                "concept_code": concept_code,
                "source": concept["source"],
                "limit": page_size,
                "offset": offset,
            },
        ).mappings().all()

    total_pages = min(total_pages_limit, (total + page_size - 1) // page_size)

    return {
        "trade_date": latest_trade_date,
        "concept_code": concept_code,
        "concept_name": concept["concept_name"],
        "source": serialize_value(concept["source"]).lower(),
        "page": page,
        "page_size": page_size,
        "total": serialize_value(total),
        "total_pages": serialize_value(total_pages),
        "items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in rows
        ],
    }


CONCEPT_STOCK_SORTS = {
    "pct_chg_desc": "q.pct_chg IS NULL, q.pct_chg DESC, q.amount DESC",
    "pct_chg_asc": "q.pct_chg IS NULL, q.pct_chg ASC, q.amount DESC",
    "amount_desc": "q.amount IS NULL, q.amount DESC, q.pct_chg DESC",
    "code_asc": "sc.ts_code ASC",
}


def get_concept_stocks(
    concept_code: str,
    page: int = 1,
    page_size: int = 50,
    sort: str = "pct_chg_desc",
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    order_sql = CONCEPT_STOCK_SORTS.get(sort, CONCEPT_STOCK_SORTS["pct_chg_desc"])

    with engine.connect() as conn:
        latest_trade_date = get_latest_trade_date(conn)

        concept = conn.execute(
            text("""
                SELECT concept_code, concept_name, source
                FROM concepts
                WHERE concept_code = :concept_code
                LIMIT 1
            """),
            {"concept_code": concept_code},
        ).mappings().first()

        if not concept:
            return None

        total = conn.execute(
            text("""
                SELECT COUNT(DISTINCT sc.ts_code)
                FROM stock_concepts sc
                WHERE
                    sc.concept_code = :concept_code
                    AND sc.source = :source
                    AND sc.is_current = 1
            """),
            {
                "concept_code": concept_code,
                "source": concept["source"],
            },
        ).scalar_one()

        total_pages = (total + page_size - 1) // page_size if total else 0
        page = min(page, total_pages or 1)
        offset = (page - 1) * page_size

        rows = conn.execute(
            text("""
                SELECT
                    COALESCE(q.ts_code, s.ts_code, sc.ts_code) AS ts_code,
                    COALESCE(s.name, sc.stock_name, sc.ts_code) AS name,
                    q.trade_date,
                    q.close,
                    q.`change`,
                    q.pct_chg,
                    q.vol,
                    q.amount,
                    m.vol_ratio_20,
                    m.volume_signal,
                    s.industry,
                    s.sw_l2_name,
                    s.sw_l3_name,
                    p.total_share,
                    p.float_share,
                    CASE
                        WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                        ELSE q.vol / p.float_share
                    END AS turnover_rate,
                    CASE
                        WHEN p.total_share IS NULL OR p.total_share = 0 THEN NULL
                        ELSE q.close * p.total_share
                    END AS market_value
                FROM stock_concepts sc
                LEFT JOIN stocks s
                    ON s.ts_code COLLATE utf8mb4_unicode_ci = sc.ts_code
                    OR s.symbol COLLATE utf8mb4_unicode_ci = SUBSTRING_INDEX(sc.ts_code, '.', 1)
                LEFT JOIN daily_quotes q
                    ON q.ts_code COLLATE utf8mb4_unicode_ci = COALESCE(s.ts_code, sc.ts_code) COLLATE utf8mb4_unicode_ci
                    AND q.trade_date = :trade_date
                LEFT JOIN stock_premarket p
                    ON p.ts_code COLLATE utf8mb4_unicode_ci = COALESCE(q.ts_code, s.ts_code, sc.ts_code) COLLATE utf8mb4_unicode_ci
                    AND p.trade_date = q.trade_date
                LEFT JOIN daily_quote_metrics m
                    ON m.ts_code COLLATE utf8mb4_unicode_ci = COALESCE(q.ts_code, s.ts_code, sc.ts_code) COLLATE utf8mb4_unicode_ci
                    AND m.trade_date = q.trade_date
                WHERE
                    sc.concept_code = :concept_code
                    AND sc.source = :source
                    AND sc.is_current = 1
                ORDER BY {order_sql}
                LIMIT :limit
                OFFSET :offset
            """.format(order_sql=order_sql)),
            {
                "trade_date": latest_trade_date,
                "concept_code": concept_code,
                "source": concept["source"],
                "limit": page_size,
                "offset": offset,
            },
        ).mappings().all()

    return {
        "trade_date": latest_trade_date,
        "concept_code": concept_code,
        "concept_name": concept["concept_name"],
        "source": serialize_value(concept["source"]).lower(),
        "page": page,
        "page_size": page_size,
        "total": serialize_value(total),
        "total_pages": serialize_value(total_pages),
        "sort": sort,
        "items": [
            {key: serialize_value(value) for key, value in row.items()}
            for row in rows
        ],
    }


def get_industry_financial_summary(level: str, industry_code: str):
    config = get_industry_config(level)

    with engine.connect() as conn:
        latest_period = conn.execute(
            text("""
                SELECT MAX(fi.end_date)
                FROM financial_indicator fi
                INNER JOIN stocks s ON s.ts_code = fi.ts_code COLLATE utf8mb4_unicode_ci
                WHERE {code_expr} = :industry_code
            """.format(code_expr=config["code"])),
            {"industry_code": industry_code},
        ).scalar_one_or_none()

        if not latest_period:
            return {
                "industry_code": industry_code,
                "level": level,
                "source": "sw",
                "period": None,
                "stock_count": 0,
                "metrics": {},
            }

        row = conn.execute(
            text("""
                SELECT
                    {code_expr} AS industry_code,
                    {name_expr} AS industry_name,
                    COUNT(DISTINCT s.ts_code) AS stock_count,
                    AVG(fi.roe) AS avg_roe,
                    AVG(fi.grossprofit_margin) AS avg_grossprofit_margin,
                    AVG(fi.debt_to_assets) AS avg_debt_to_assets,
                    SUM(inc.revenue) AS total_revenue,
                    SUM(inc.n_income_attr_p) AS total_net_profit
                FROM stocks s
                LEFT JOIN financial_indicator fi
                    ON fi.ts_code COLLATE utf8mb4_unicode_ci = s.ts_code
                    AND fi.end_date = :period
                LEFT JOIN financial_income inc
                    ON inc.ts_code COLLATE utf8mb4_unicode_ci = s.ts_code
                    AND inc.end_date = :period
                WHERE {code_expr} = :industry_code
                GROUP BY {code_expr}, {name_expr}
                LIMIT 1
            """.format(
                code_expr=config["code"],
                name_expr=config["name"],
            )),
            {
                "industry_code": industry_code,
                "period": latest_period,
            },
        ).mappings().first()

    if not row:
        return None

    return {
        "industry_code": serialize_value(row["industry_code"]),
        "industry_name": serialize_value(row["industry_name"]),
        "level": level,
        "source": "sw",
        "period": latest_period,
        "stock_count": serialize_value(row["stock_count"]),
        "metrics": {
            "avg_roe": serialize_value(row["avg_roe"]),
            "avg_grossprofit_margin": serialize_value(row["avg_grossprofit_margin"]),
            "avg_debt_to_assets": serialize_value(row["avg_debt_to_assets"]),
            "total_revenue": serialize_value(row["total_revenue"]),
            "total_net_profit": serialize_value(row["total_net_profit"]),
        },
    }
