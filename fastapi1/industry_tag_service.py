from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import math

from sqlalchemy import bindparam, create_engine, text

from settings import DATABASE_URL


engine = create_engine(DATABASE_URL)


TAG_DEFINITIONS = {
    "industry_leader": ("position", "行业地位", "行业龙头"),
    "second_tier": ("position", "行业地位", "第二梯队"),
    "small_beautiful": ("position", "行业地位", "小而美"),
    "tail_company": ("position", "行业地位", "尾部公司"),
    "high_growth": ("growth", "成长性", "高成长"),
    "stable_growth": ("growth", "成长性", "稳定增长"),
    "growth_slowdown": ("growth", "成长性", "成长放缓"),
    "revenue_up_profit_down": ("growth", "成长性", "增收不增利"),
    "negative_growth": ("growth", "成长性", "负增长"),
    "high_gross_margin": ("profitability", "盈利能力", "高毛利"),
    "low_gross_margin": ("profitability", "盈利能力", "低毛利"),
    "high_net_margin": ("profitability", "盈利能力", "高净利"),
    "profitability_improving": ("profitability", "盈利能力", "盈利改善"),
    "profitability_deteriorating": ("profitability", "盈利能力", "盈利恶化"),
    "excellent_cashflow": ("quality", "财务质量", "现金流优秀"),
    "low_profit_cash_quality": ("quality", "财务质量", "利润含金量低"),
    "receivable_pressure": ("quality", "财务质量", "应收压力大"),
    "inventory_pressure": ("quality", "财务质量", "存货压力大"),
    "high_leverage": ("quality", "财务质量", "高杠杆"),
    "asset_light": ("quality", "财务质量", "轻资产"),
    "asset_heavy": ("quality", "财务质量", "重资产"),
    "collection_risk": ("risk", "风险", "回款风险"),
    "inventory_risk": ("risk", "风险", "库存堆积风险"),
    "profit_decline_risk": ("risk", "风险", "盈利下滑风险"),
    "debt_risk": ("risk", "风险", "高负债风险"),
}


METRIC_FIELDS = [
    "revenue",
    "net_profit",
    "deducted_net_profit",
    "operating_cashflow",
    "gross_margin",
    "net_margin",
    "roe",
    "debt_to_assets",
    "accounts_receiv",
    "inventories",
    "total_assets",
    "assets_turn",
    "market_value",
    "price",
]


def serialize_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def serialize_row(row):
    return {key: serialize_value(value) for key, value in row.items()}


def safe_float(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def ratio_change(current, previous):
    current = safe_float(current)
    previous = safe_float(previous)
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous)


def percentile_map(rows, field):
    values = [safe_float(row.get(field)) for row in rows]
    values = sorted(value for value in values if value is not None)
    if not values:
        return {}

    count = len(values)
    result = {}
    for row in rows:
        value = safe_float(row.get(field))
        if value is None:
            result[row["ts_code"]] = None
            continue
        less_or_equal = sum(1 for item in values if item <= value)
        result[row["ts_code"]] = less_or_equal / count
    return result


def metric_label(row, field, digits=2):
    value = safe_float(row.get(field))
    if value is None:
        return "--"
    return f"{value:.{digits}f}"


def percent_label(value):
    value = safe_float(value)
    if value is None:
        return "--"
    return f"{value * 100:.2f}%"


def add_tag(tags, row, tag_code, value=None, percentile=None, explanation=""):
    category, category_label, tag_name = TAG_DEFINITIONS[tag_code]
    tag = {
        "ts_code": row["ts_code"],
        "name": row.get("name"),
        "sw_l1_code": row.get("sw_l1_code"),
        "sw_l1_name": row.get("sw_l1_name"),
        "sw_l2_code": row.get("sw_l2_code"),
        "sw_l2_name": row.get("sw_l2_name"),
        "sw_l3_code": row.get("sw_l3_code"),
        "sw_l3_name": row.get("sw_l3_name"),
        "end_date": row.get("end_date"),
        "tag_category": category,
        "tag_category_label": category_label,
        "tag_code": tag_code,
        "tag_name": tag_name,
        "metric_value": safe_float(value),
        "industry_percentile": safe_float(percentile),
        "explanation": explanation,
    }
    for field in METRIC_FIELDS:
        tag[field] = safe_float(row.get(field))
    tags.append(tag)


def ensure_industry_financial_tags_table(db_engine=engine):
    sql = text("""
        CREATE TABLE IF NOT EXISTS industry_financial_tags (
            id BIGINT NOT NULL AUTO_INCREMENT,
            ts_code VARCHAR(20) NOT NULL,
            name VARCHAR(100) NULL,
            sw_l1_code VARCHAR(20) NULL,
            sw_l1_name VARCHAR(100) NULL,
            sw_l2_code VARCHAR(20) NULL,
            sw_l2_name VARCHAR(100) NULL,
            sw_l3_code VARCHAR(20) NULL,
            sw_l3_name VARCHAR(100) NULL,
            end_date CHAR(8) NOT NULL,
            tag_category VARCHAR(40) NOT NULL,
            tag_category_label VARCHAR(40) NOT NULL,
            tag_code VARCHAR(80) NOT NULL,
            tag_name VARCHAR(80) NOT NULL,
            metric_value DOUBLE NULL,
            industry_percentile DOUBLE NULL,
            revenue DOUBLE NULL,
            net_profit DOUBLE NULL,
            deducted_net_profit DOUBLE NULL,
            operating_cashflow DOUBLE NULL,
            gross_margin DOUBLE NULL,
            net_margin DOUBLE NULL,
            roe DOUBLE NULL,
            debt_to_assets DOUBLE NULL,
            accounts_receiv DOUBLE NULL,
            inventories DOUBLE NULL,
            total_assets DOUBLE NULL,
            assets_turn DOUBLE NULL,
            market_value DOUBLE NULL,
            price DOUBLE NULL,
            explanation TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_industry_financial_tag (ts_code, end_date, tag_code),
            KEY idx_industry_financial_tags_period (end_date),
            KEY idx_industry_financial_tags_l3 (sw_l3_code, end_date),
            KEY idx_industry_financial_tags_category (tag_category, end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    with db_engine.begin() as conn:
        conn.execute(sql)


def get_target_annual_periods(db_engine=engine):
    with db_engine.connect() as conn:
        latest_period = conn.execute(
            text("""
                SELECT MAX(end_date)
                FROM financial_indicator
                WHERE end_date LIKE '%1231'
            """)
        ).scalar_one_or_none()

        if not latest_period:
            return []

        latest_year = int(str(latest_period)[:4])
        min_year = latest_year - 4
        rows = conn.execute(
            text("""
                SELECT DISTINCT end_date
                FROM financial_indicator
                WHERE end_date LIKE '%1231'
                    AND CAST(LEFT(end_date, 4) AS UNSIGNED) BETWEEN :min_year AND :latest_year
                ORDER BY end_date DESC
            """),
            {"min_year": min_year, "latest_year": latest_year},
        ).scalars().all()

    return list(rows)


def build_fetch_periods(target_periods):
    years = {int(period[:4]) for period in target_periods if period and len(period) >= 4}
    all_years = set(years)
    for year in years:
        all_years.add(year - 1)
        all_years.add(year - 2)
    return [f"{year}1231" for year in sorted(all_years)]


def fetch_financial_tag_rows(periods, ts_code=None, sw_l3_code=None, db_engine=engine):
    if not periods:
        return []

    stock_params = {}
    stock_filters = ["sw_l3_code IS NOT NULL"]
    if ts_code:
        stock_filters.append("ts_code = :ts_code")
        stock_params["ts_code"] = ts_code
    if sw_l3_code:
        stock_filters.append("sw_l3_code = :sw_l3_code")
        stock_params["sw_l3_code"] = sw_l3_code

    with db_engine.connect() as conn:
        stocks = [
            serialize_row(row)
            for row in conn.execute(
                text(f"""
                    SELECT ts_code, name, sw_l1_code, sw_l1_name, sw_l2_code,
                        sw_l2_name, sw_l3_code, sw_l3_name
                    FROM stocks
                    WHERE {" AND ".join(stock_filters)}
                """),
                stock_params,
            ).mappings().all()
        ]

        stock_codes = [row["ts_code"] for row in stocks]
        if not stock_codes:
            return []

        params = {"periods": tuple(periods), "stock_codes": tuple(stock_codes)}

        def fetch_rows(table_name, fields):
            return [
                serialize_row(row)
                for row in conn.execute(
                    text(f"""
                        SELECT ts_code, end_date, ann_date, {", ".join(fields)}
                        FROM {table_name}
                        WHERE ts_code IN :stock_codes
                            AND end_date IN :periods
                        ORDER BY ts_code, end_date, ann_date
                    """).bindparams(
                        bindparam("stock_codes", expanding=True),
                        bindparam("periods", expanding=True),
                    ),
                    params,
                ).mappings().all()
            ]

        indicators = fetch_rows(
            "financial_indicator",
            [
                "profit_dedt AS deducted_net_profit",
                "grossprofit_margin AS gross_margin",
                "netprofit_margin AS net_margin",
                "roe",
                "debt_to_assets",
                "assets_turn",
            ],
        )
        incomes = fetch_rows(
            "financial_income",
            [
                "revenue",
                "n_income_attr_p AS net_profit",
            ],
        )
        balances = fetch_rows(
            "financial_balancesheet",
            [
                "accounts_receiv",
                "inventories",
                "total_assets",
            ],
        )
        cashflows = fetch_rows(
            "financial_cashflow",
            [
                "n_cashflow_act AS operating_cashflow",
            ],
        )

        quotes = [
            serialize_row(row)
            for row in conn.execute(
                text("""
                    SELECT q.ts_code, q.close AS price
                    FROM daily_quotes q
                    INNER JOIN (
                        SELECT ts_code, MAX(trade_date) AS trade_date
                        FROM daily_quotes
                        WHERE ts_code IN :stock_codes
                        GROUP BY ts_code
                    ) latest ON latest.ts_code = q.ts_code AND latest.trade_date = q.trade_date
                """).bindparams(bindparam("stock_codes", expanding=True)),
                {"stock_codes": tuple(stock_codes)},
            ).mappings().all()
        ]
        shares = [
            serialize_row(row)
            for row in conn.execute(
                text("""
                    SELECT p.ts_code, p.total_share
                    FROM stock_premarket p
                    INNER JOIN (
                        SELECT ts_code, MAX(trade_date) AS trade_date
                        FROM stock_premarket
                        WHERE ts_code IN :stock_codes
                        GROUP BY ts_code
                    ) latest ON latest.ts_code = p.ts_code AND latest.trade_date = p.trade_date
                """).bindparams(bindparam("stock_codes", expanding=True)),
                {"stock_codes": tuple(stock_codes)},
            ).mappings().all()
        ]

    stock_map = {row["ts_code"]: row for row in stocks}
    quote_map = {row["ts_code"]: row for row in quotes}
    share_map = {row["ts_code"]: row for row in shares}

    rows = {}
    for row in indicators:
        base = dict(stock_map[row["ts_code"]])
        base.update(row)
        quote = quote_map.get(row["ts_code"], {})
        share = share_map.get(row["ts_code"], {})
        price = safe_float(quote.get("price"))
        total_share = safe_float(share.get("total_share"))
        base["price"] = price
        base["market_value"] = price * total_share if price is not None and total_share is not None else None
        rows[(row["ts_code"], row["end_date"])] = base

    for source_rows in [incomes, balances, cashflows]:
        for row in source_rows:
            key = (row["ts_code"], row["end_date"])
            if key in rows:
                rows[key].update(row)

    return list(rows.values())


def rows_by_stock_period(rows):
    return {(row["ts_code"], row["end_date"]): row for row in rows}


def get_previous_annual_row(row, row_map, years_back=1):
    year = int(row["end_date"][:4]) - years_back
    return row_map.get((row["ts_code"], f"{year}1231"))


def annotate_growth(rows, row_map):
    for row in rows:
        prev = get_previous_annual_row(row, row_map)
        prev2 = get_previous_annual_row(row, row_map, 2)
        prev3 = get_previous_annual_row(row, row_map, 3)

        row["revenue_yoy"] = ratio_change(row.get("revenue"), prev.get("revenue") if prev else None)
        row["net_profit_yoy"] = ratio_change(row.get("net_profit"), prev.get("net_profit") if prev else None)
        row["accounts_receiv_yoy"] = ratio_change(row.get("accounts_receiv"), prev.get("accounts_receiv") if prev else None)
        row["inventories_yoy"] = ratio_change(row.get("inventories"), prev.get("inventories") if prev else None)

        prev_revenue_yoy = ratio_change(prev.get("revenue") if prev else None, prev2.get("revenue") if prev2 else None)
        prev_profit_yoy = ratio_change(prev.get("net_profit") if prev else None, prev2.get("net_profit") if prev2 else None)
        prev2_revenue_yoy = ratio_change(prev2.get("revenue") if prev2 else None, prev3.get("revenue") if prev3 else None)
        prev2_profit_yoy = ratio_change(prev2.get("net_profit") if prev2 else None, prev3.get("net_profit") if prev3 else None)
        row["prev_revenue_yoy"] = prev_revenue_yoy
        row["prev_net_profit_yoy"] = prev_profit_yoy
        row["prev2_revenue_yoy"] = prev2_revenue_yoy
        row["prev2_net_profit_yoy"] = prev2_profit_yoy

        row["gross_margin_prev"] = safe_float(prev.get("gross_margin") if prev else None)
        row["gross_margin_prev2"] = safe_float(prev2.get("gross_margin") if prev2 else None)
        row["net_margin_prev"] = safe_float(prev.get("net_margin") if prev else None)
        row["net_margin_prev2"] = safe_float(prev2.get("net_margin") if prev2 else None)

        revenue_yoy = row["revenue_yoy"]
        row["receivable_growth_gap"] = None
        if row["accounts_receiv_yoy"] is not None and revenue_yoy is not None:
            row["receivable_growth_gap"] = row["accounts_receiv_yoy"] - revenue_yoy
        row["inventory_growth_gap"] = None
        if row["inventories_yoy"] is not None and revenue_yoy is not None:
            row["inventory_growth_gap"] = row["inventories_yoy"] - revenue_yoy

        net_profit = safe_float(row.get("net_profit"))
        operating_cashflow = safe_float(row.get("operating_cashflow"))
        if net_profit not in (None, 0) and net_profit > 0 and operating_cashflow is not None:
            row["cashflow_profit_ratio"] = operating_cashflow / net_profit
        else:
            row["cashflow_profit_ratio"] = None


def generate_tags_for_group(rows):
    tags = []
    if not rows:
        return tags

    pct = {
        field: percentile_map(rows, field)
        for field in [
            "revenue",
            "net_profit",
            "gross_margin",
            "net_margin",
            "roe",
            "market_value",
            "revenue_yoy",
            "net_profit_yoy",
            "cashflow_profit_ratio",
            "receivable_growth_gap",
            "inventory_growth_gap",
            "debt_to_assets",
            "assets_turn",
        ]
    }

    for row in rows:
        code = row["ts_code"]
        revenue_pct = pct["revenue"].get(code)
        profit_pct = pct["net_profit"].get(code)
        gross_pct = pct["gross_margin"].get(code)
        net_margin_pct = pct["net_margin"].get(code)
        roe_pct = pct["roe"].get(code)
        market_pct = pct["market_value"].get(code)
        debt_pct = pct["debt_to_assets"].get(code)

        leader = (revenue_pct is not None and revenue_pct >= 0.8) or (profit_pct is not None and profit_pct >= 0.8)
        second_tier = not leader and (
            (revenue_pct is not None and 0.5 <= revenue_pct < 0.8)
            or (profit_pct is not None and 0.5 <= profit_pct < 0.8)
        )
        small_beautiful = not leader and not second_tier and market_pct is not None and market_pct <= 0.5 and (
            (gross_pct is not None and gross_pct >= 0.75)
            or (net_margin_pct is not None and net_margin_pct >= 0.75)
            or (roe_pct is not None and roe_pct >= 0.75)
        )
        tail_company = not leader and not second_tier and not small_beautiful and (
            revenue_pct is not None and revenue_pct <= 0.2
            and profit_pct is not None and profit_pct <= 0.2
            and all(value is not None and value <= 0.2 for value in [gross_pct, net_margin_pct, roe_pct])
        )

        if leader:
            add_tag(tags, row, "industry_leader", row.get("revenue"), max(revenue_pct or 0, profit_pct or 0), "营业收入或归母净利润位于同三级行业前20%。")
        elif second_tier:
            add_tag(tags, row, "second_tier", row.get("revenue"), max(revenue_pct or 0, profit_pct or 0), "营业收入或归母净利润位于同三级行业前20%-50%。")
        elif small_beautiful:
            add_tag(tags, row, "small_beautiful", row.get("market_value"), market_pct, "总市值不在行业前50%，且盈利能力指标进入行业前25%。")
        elif tail_company:
            add_tag(tags, row, "tail_company", row.get("revenue"), revenue_pct, "收入、归母净利润和盈利能力均位于同三级行业后20%。")

        revenue_yoy_pct = pct["revenue_yoy"].get(code)
        profit_yoy_pct = pct["net_profit_yoy"].get(code)
        if (revenue_yoy_pct is not None and revenue_yoy_pct >= 0.8) or (profit_yoy_pct is not None and profit_yoy_pct >= 0.8):
            add_tag(tags, row, "high_growth", row.get("revenue_yoy"), max(revenue_yoy_pct or 0, profit_yoy_pct or 0), "收入同比或归母净利润同比位于同三级行业前20%。")

        if all(safe_float(row.get(field)) is not None and safe_float(row.get(field)) > 0 for field in ["revenue_yoy", "net_profit_yoy", "prev_revenue_yoy", "prev_net_profit_yoy"]):
            add_tag(tags, row, "stable_growth", row.get("revenue_yoy"), revenue_yoy_pct, "营业收入和归母净利润连续两个年报周期同比为正。")

        if (
            row.get("revenue_yoy") is not None
            and row.get("prev_revenue_yoy") is not None
            and row.get("prev2_revenue_yoy") is not None
            and row["revenue_yoy"] < row["prev_revenue_yoy"] < row["prev2_revenue_yoy"]
        ) or (
            row.get("net_profit_yoy") is not None
            and row.get("prev_net_profit_yoy") is not None
            and row.get("prev2_net_profit_yoy") is not None
            and row["net_profit_yoy"] < row["prev_net_profit_yoy"] < row["prev2_net_profit_yoy"]
        ):
            add_tag(tags, row, "growth_slowdown", row.get("revenue_yoy"), revenue_yoy_pct, "收入同比或归母净利润同比连续两个年报周期下降。")

        if safe_float(row.get("revenue_yoy")) is not None and safe_float(row.get("net_profit_yoy")) is not None:
            if row["revenue_yoy"] > 0 and row["net_profit_yoy"] < 0:
                add_tag(tags, row, "revenue_up_profit_down", row.get("net_profit_yoy"), profit_yoy_pct, "营业收入同比增长，但归母净利润同比下降。")
            if row["revenue_yoy"] < 0 or row["net_profit_yoy"] < 0:
                add_tag(tags, row, "negative_growth", min(row["revenue_yoy"], row["net_profit_yoy"]), min(revenue_yoy_pct or 1, profit_yoy_pct or 1), "营业收入或归母净利润同比下降。")

        if gross_pct is not None and gross_pct >= 0.75:
            add_tag(tags, row, "high_gross_margin", row.get("gross_margin"), gross_pct, "毛利率位于同三级行业前25%。")
        if gross_pct is not None and gross_pct <= 0.25:
            add_tag(tags, row, "low_gross_margin", row.get("gross_margin"), gross_pct, "毛利率位于同三级行业后25%。")
        if net_margin_pct is not None and net_margin_pct >= 0.75:
            add_tag(tags, row, "high_net_margin", row.get("net_margin"), net_margin_pct, "净利率位于同三级行业前25%。")

        gross_margin = safe_float(row.get("gross_margin"))
        net_margin = safe_float(row.get("net_margin"))
        if (
            gross_margin is not None and row.get("gross_margin_prev") is not None and row.get("gross_margin_prev2") is not None
            and gross_margin > row["gross_margin_prev"] > row["gross_margin_prev2"]
        ) or (
            net_margin is not None and row.get("net_margin_prev") is not None and row.get("net_margin_prev2") is not None
            and net_margin > row["net_margin_prev"] > row["net_margin_prev2"]
        ):
            add_tag(tags, row, "profitability_improving", gross_margin, gross_pct, "毛利率或净利率连续两个年报周期提升。")
        if (
            gross_margin is not None and row.get("gross_margin_prev") is not None and row.get("gross_margin_prev2") is not None
            and gross_margin < row["gross_margin_prev"] < row["gross_margin_prev2"]
        ) or (
            net_margin is not None and row.get("net_margin_prev") is not None and row.get("net_margin_prev2") is not None
            and net_margin < row["net_margin_prev"] < row["net_margin_prev2"]
        ):
            add_tag(tags, row, "profitability_deteriorating", gross_margin, gross_pct, "毛利率或净利率连续两个年报周期下降。")

        cashflow = safe_float(row.get("operating_cashflow"))
        net_profit = safe_float(row.get("net_profit"))
        cash_ratio = safe_float(row.get("cashflow_profit_ratio"))
        cash_ratio_pct = pct["cashflow_profit_ratio"].get(code)
        if cashflow is not None and cashflow > 0 and cash_ratio is not None and cash_ratio > 1:
            add_tag(tags, row, "excellent_cashflow", cash_ratio, cash_ratio_pct, "经营现金流为正，且经营现金流/归母净利润大于1。")
        if net_profit is not None and net_profit > 0 and cash_ratio_pct is not None and cash_ratio_pct <= 0.25:
            add_tag(tags, row, "low_profit_cash_quality", cash_ratio, cash_ratio_pct, "归母净利润为正，但经营现金流/归母净利润位于同行业后25%。")

        receivable_gap_pct = pct["receivable_growth_gap"].get(code)
        inventory_gap_pct = pct["inventory_growth_gap"].get(code)
        if receivable_gap_pct is not None and receivable_gap_pct >= 0.75:
            add_tag(tags, row, "receivable_pressure", row.get("receivable_growth_gap"), receivable_gap_pct, "应收账款同比增速相对收入增速的差值位于行业前25%。")
            add_tag(tags, row, "collection_risk", row.get("receivable_growth_gap"), receivable_gap_pct, "应收账款增速明显高于收入增速，存在回款风险。")
        if inventory_gap_pct is not None and inventory_gap_pct >= 0.75:
            add_tag(tags, row, "inventory_pressure", row.get("inventory_growth_gap"), inventory_gap_pct, "存货同比增速相对收入增速的差值位于行业前25%。")
            add_tag(tags, row, "inventory_risk", row.get("inventory_growth_gap"), inventory_gap_pct, "存货增速明显高于收入增速，存在库存堆积风险。")

        if debt_pct is not None and debt_pct >= 0.75:
            add_tag(tags, row, "high_leverage", row.get("debt_to_assets"), debt_pct, "资产负债率位于同三级行业前25%。")
        if pct["assets_turn"].get(code) is not None and pct["assets_turn"][code] >= 0.75:
            add_tag(tags, row, "asset_light", row.get("assets_turn"), pct["assets_turn"][code], "总资产周转率位于同三级行业前25%。")

        if safe_float(row.get("revenue_yoy")) is not None and row["revenue_yoy"] > 0:
            margin_down = False
            if gross_margin is not None and row.get("gross_margin_prev") is not None and gross_margin < row["gross_margin_prev"]:
                margin_down = True
            if net_margin is not None and row.get("net_margin_prev") is not None and net_margin < row["net_margin_prev"]:
                margin_down = True
            if margin_down:
                add_tag(tags, row, "profit_decline_risk", row.get("revenue_yoy"), revenue_yoy_pct, "收入增长，但毛利率或净利率下降。")

        if debt_pct is not None and debt_pct >= 0.75 and (cashflow is not None and cashflow < 0 or cash_ratio_pct is not None and cash_ratio_pct <= 0.5):
            add_tag(tags, row, "debt_risk", row.get("debt_to_assets"), debt_pct, "资产负债率位于行业前25%，且经营现金流偏弱。")

    return tags


def generate_industry_financial_tags(rows, target_periods):
    target_periods = set(target_periods)
    row_map = rows_by_stock_period(rows)
    annotate_growth(rows, row_map)

    groups = defaultdict(list)
    for row in rows:
        if row.get("end_date") in target_periods and row.get("sw_l3_code"):
            groups[(row["sw_l3_code"], row["end_date"])].append(row)

    tags = []
    for group_rows in groups.values():
        tags.extend(generate_tags_for_group(group_rows))
    return tags


def replace_industry_financial_tags(tags, periods, dry_run=False, db_engine=engine):
    if dry_run:
        return {"periods": periods, "tag_count": len(tags), "dry_run": True}

    ensure_industry_financial_tags_table(db_engine)

    with db_engine.begin() as conn:
        if periods:
            conn.execute(
                text("DELETE FROM industry_financial_tags WHERE end_date IN :periods").bindparams(bindparam("periods", expanding=True)),
                {"periods": tuple(periods)},
            )

        if tags:
            conn.execute(
                text("""
                    INSERT INTO industry_financial_tags (
                        ts_code, name, sw_l1_code, sw_l1_name, sw_l2_code, sw_l2_name,
                        sw_l3_code, sw_l3_name, end_date, tag_category, tag_category_label,
                        tag_code, tag_name, metric_value, industry_percentile,
                        revenue, net_profit, deducted_net_profit, operating_cashflow,
                        gross_margin, net_margin, roe, debt_to_assets, accounts_receiv,
                        inventories, total_assets, assets_turn, market_value, price, explanation
                    )
                    VALUES (
                        :ts_code, :name, :sw_l1_code, :sw_l1_name, :sw_l2_code, :sw_l2_name,
                        :sw_l3_code, :sw_l3_name, :end_date, :tag_category, :tag_category_label,
                        :tag_code, :tag_name, :metric_value, :industry_percentile,
                        :revenue, :net_profit, :deducted_net_profit, :operating_cashflow,
                        :gross_margin, :net_margin, :roe, :debt_to_assets, :accounts_receiv,
                        :inventories, :total_assets, :assets_turn, :market_value, :price, :explanation
                    )
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        tag_category = VALUES(tag_category),
                        tag_category_label = VALUES(tag_category_label),
                        tag_name = VALUES(tag_name),
                        metric_value = VALUES(metric_value),
                        industry_percentile = VALUES(industry_percentile),
                        explanation = VALUES(explanation),
                        updated_at = CURRENT_TIMESTAMP
                """),
                tags,
            )

    return {"periods": periods, "tag_count": len(tags), "dry_run": False}


def sync_industry_financial_tags(end_date=None, ts_code=None, sw_l3_code=None, dry_run=False, db_engine=engine):
    target_periods = [end_date] if end_date else get_target_annual_periods(db_engine)
    target_periods = [period for period in target_periods if period and str(period).endswith("1231")]
    fetch_periods = build_fetch_periods(target_periods)
    rows = fetch_financial_tag_rows(fetch_periods, ts_code=ts_code, sw_l3_code=sw_l3_code, db_engine=db_engine)
    tags = generate_industry_financial_tags(rows, target_periods)
    return replace_industry_financial_tags(tags, target_periods, dry_run=dry_run, db_engine=db_engine)


def list_industry_tag_periods(db_engine=engine):
    ensure_industry_financial_tags_table(db_engine)
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT end_date, COUNT(*) AS tag_count, COUNT(DISTINCT ts_code) AS stock_count
                FROM industry_financial_tags
                GROUP BY end_date
                ORDER BY end_date DESC
            """)
        ).mappings().all()
    return {"items": [serialize_row(row) for row in rows]}


def list_industry_tag_industries(period="latest", db_engine=engine):
    ensure_industry_financial_tags_table(db_engine)
    with db_engine.connect() as conn:
        resolved_period = resolve_tag_period(conn, period)
        if not resolved_period:
            return {"period": None, "items": []}
        rows = conn.execute(
            text("""
                SELECT sw_l3_code, sw_l3_name, sw_l2_name, sw_l1_name,
                    COUNT(DISTINCT ts_code) AS stock_count,
                    COUNT(*) AS tag_count
                FROM industry_financial_tags
                WHERE end_date = :period
                GROUP BY sw_l3_code, sw_l3_name, sw_l2_name, sw_l1_name
                ORDER BY sw_l1_name, sw_l2_name, sw_l3_name
            """),
            {"period": resolved_period},
        ).mappings().all()
    return {"period": resolved_period, "items": [serialize_row(row) for row in rows]}


def resolve_tag_period(conn, period):
    if period and period != "latest":
        return period
    return conn.execute(text("SELECT MAX(end_date) FROM industry_financial_tags")).scalar_one_or_none()


def list_industry_tags(period="latest", sw_l3_code=None, tag_category=None, tag_code=None, page=1, page_size=50, db_engine=engine):
    ensure_industry_financial_tags_table(db_engine)
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 50), 200))
    offset = (page - 1) * page_size

    with db_engine.connect() as conn:
        resolved_period = resolve_tag_period(conn, period)
        if not resolved_period:
            return {
                "period": None,
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 1,
                "items": [],
            }

        filters = ["end_date = :period"]
        params = {"period": resolved_period, "limit": page_size, "offset": offset}
        if sw_l3_code:
            filters.append("sw_l3_code = :sw_l3_code")
            params["sw_l3_code"] = sw_l3_code
        if tag_category:
            filters.append("tag_category = :tag_category")
            params["tag_category"] = tag_category
        if tag_code:
            filters.append("tag_code = :tag_code")
            params["tag_code"] = tag_code

        where_sql = " AND ".join(filters)
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM industry_financial_tags WHERE {where_sql}"),
            params,
        ).scalar_one()
        rows = conn.execute(
            text(f"""
                SELECT *
                FROM industry_financial_tags
                WHERE {where_sql}
                ORDER BY sw_l1_name, sw_l2_name, sw_l3_name, ts_code, tag_category, tag_name
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

    total_pages = max(1, math.ceil(total / page_size))
    return {
        "period": resolved_period,
        "page": page,
        "page_size": page_size,
        "total": serialize_value(total),
        "total_pages": total_pages,
        "items": [serialize_row(row) for row in rows],
    }


def build_stock_tag_payload(ts_code, rows, all_rows=None):
    rows = [serialize_row(row) for row in rows]
    all_rows = [serialize_row(row) for row in (all_rows if all_rows is not None else rows)]
    rows.sort(key=lambda row: (row.get("end_date") or "", row.get("tag_category") or "", row.get("tag_name") or ""), reverse=True)

    stock_source = (all_rows or rows or [{}])[0]
    periods = sorted({row.get("end_date") for row in all_rows if row.get("end_date")}, reverse=True)
    groups = []
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("end_date")].append(row)

    for end_date in sorted(grouped, reverse=True):
        items = sorted(grouped[end_date], key=lambda row: (row.get("tag_category") or "", row.get("tag_name") or ""))
        metric_source = items[0] if items else {}
        groups.append({
            "end_date": end_date,
            "metrics": {field: serialize_value(metric_source.get(field)) for field in METRIC_FIELDS},
            "tags": items,
        })

    return {
        "ts_code": ts_code,
        "name": stock_source.get("name"),
        "sw_l1_code": stock_source.get("sw_l1_code"),
        "sw_l1_name": stock_source.get("sw_l1_name"),
        "sw_l2_code": stock_source.get("sw_l2_code"),
        "sw_l2_name": stock_source.get("sw_l2_name"),
        "sw_l3_code": stock_source.get("sw_l3_code"),
        "sw_l3_name": stock_source.get("sw_l3_name"),
        "periods": periods,
        "groups": groups,
        "total_tags": len(rows),
    }


def get_industry_tags_for_stock(ts_code, period=None, tag_category=None, db_engine=engine):
    ensure_industry_financial_tags_table(db_engine)
    with db_engine.connect() as conn:
        all_rows = conn.execute(
            text("""
                SELECT *
                FROM industry_financial_tags
                WHERE ts_code = :ts_code
                ORDER BY end_date DESC, tag_category, tag_name
            """),
            {"ts_code": ts_code},
        ).mappings().all()

        filters = ["ts_code = :ts_code"]
        params = {"ts_code": ts_code}
        if period and period != "all":
            filters.append("end_date = :period")
            params["period"] = period
        if tag_category:
            filters.append("tag_category = :tag_category")
            params["tag_category"] = tag_category

        rows = conn.execute(
            text(f"""
                SELECT *
                FROM industry_financial_tags
                WHERE {" AND ".join(filters)}
                ORDER BY end_date DESC, tag_category, tag_name
            """),
            params,
        ).mappings().all()

    return build_stock_tag_payload(ts_code, rows, all_rows)


def build_l3_industry_tag_overview(sw_l3_code, period, all_rows, rows):
    all_rows = [serialize_row(row) for row in all_rows]
    rows = [serialize_row(row) for row in rows]
    source = (all_rows or rows or [{}])[0]
    periods = sorted({row.get("end_date") for row in all_rows if row.get("end_date")}, reverse=True)

    grouped = {}
    for row in rows:
        stock = grouped.setdefault(
            row["ts_code"],
            {
                "ts_code": row["ts_code"],
                "name": row.get("name"),
                "metrics": {field: serialize_value(row.get(field)) for field in METRIC_FIELDS},
                "tags": [],
            },
        )
        stock["tags"].append(row)

    items = []
    for stock in grouped.values():
        stock["tags"].sort(key=lambda row: (row.get("tag_category") or "", row.get("tag_name") or ""))
        items.append(stock)
    items.sort(key=lambda row: row["ts_code"])

    return {
        "sw_l1_code": source.get("sw_l1_code"),
        "sw_l1_name": source.get("sw_l1_name"),
        "sw_l2_code": source.get("sw_l2_code"),
        "sw_l2_name": source.get("sw_l2_name"),
        "sw_l3_code": sw_l3_code,
        "sw_l3_name": source.get("sw_l3_name"),
        "period": period,
        "periods": periods,
        "stock_count": len(items),
        "tag_count": sum(len(item["tags"]) for item in items),
        "items": items,
    }


def get_l3_industry_tag_overview(sw_l3_code, period="latest", db_engine=engine):
    ensure_industry_financial_tags_table(db_engine)
    with db_engine.connect() as conn:
        resolved_period = resolve_tag_period(conn, period)
        if not resolved_period:
            return build_l3_industry_tag_overview(sw_l3_code, None, [], [])

        all_rows = conn.execute(
            text("""
                SELECT *
                FROM industry_financial_tags
                WHERE sw_l3_code = :sw_l3_code
                ORDER BY end_date DESC, ts_code, tag_category, tag_name
            """),
            {"sw_l3_code": sw_l3_code},
        ).mappings().all()
        rows = conn.execute(
            text("""
                SELECT *
                FROM industry_financial_tags
                WHERE sw_l3_code = :sw_l3_code
                    AND end_date = :period
                ORDER BY ts_code, tag_category, tag_name
            """),
            {"sw_l3_code": sw_l3_code, "period": resolved_period},
        ).mappings().all()

    return build_l3_industry_tag_overview(sw_l3_code, resolved_period, all_rows, rows)
