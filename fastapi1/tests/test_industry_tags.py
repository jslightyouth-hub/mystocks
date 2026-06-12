import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("TUSHARE_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from industry_tag_service import (
    build_l3_industry_tag_overview,
    build_stock_tag_payload,
    build_fetch_periods,
    generate_industry_financial_tags,
    get_target_annual_periods,
)
import main


def base_row(ts_code, l3, period, **values):
    row = {
        "ts_code": ts_code,
        "name": ts_code,
        "sw_l1_code": "L1",
        "sw_l1_name": "一级",
        "sw_l2_code": "L2",
        "sw_l2_name": "二级",
        "sw_l3_code": l3,
        "sw_l3_name": l3,
        "end_date": period,
        "revenue": 100,
        "net_profit": 10,
        "deducted_net_profit": 9,
        "operating_cashflow": 11,
        "gross_margin": 30,
        "net_margin": 10,
        "roe": 8,
        "debt_to_assets": 40,
        "accounts_receiv": 10,
        "inventories": 10,
        "total_assets": 100,
        "assets_turn": 1,
        "market_value": 100,
        "price": 10,
    }
    row.update(values)
    return row


class IndustryTagRuleTests(unittest.TestCase):
    def test_tags_compare_only_inside_same_l3_and_period(self):
        rows = [
            base_row("A", "酒", "20251231", revenue=1000, net_profit=100, gross_margin=10, net_margin=8, roe=8),
            base_row("D", "酒", "20251231", revenue=700, net_profit=70, gross_margin=12, net_margin=9, roe=9, market_value=700),
            base_row("E", "酒", "20251231", revenue=500, net_profit=50, gross_margin=13, net_margin=10, roe=10, market_value=500),
            base_row("F", "酒", "20251231", revenue=300, net_profit=30, gross_margin=14, net_margin=11, roe=11, market_value=300),
            base_row("B", "酒", "20251231", revenue=100, net_profit=10, gross_margin=30, net_margin=20, roe=20, market_value=10),
            base_row("C", "建筑", "20251231", revenue=5000, net_profit=500, gross_margin=80, net_margin=40, roe=30),
        ]

        tags = generate_industry_financial_tags(rows, ["20251231"])
        by_stock = {}
        for tag in tags:
            by_stock.setdefault(tag["ts_code"], set()).add(tag["tag_code"])

        self.assertIn("industry_leader", by_stock["A"])
        self.assertIn("small_beautiful", by_stock["B"])
        self.assertIn("industry_leader", by_stock["C"])
        self.assertNotIn("tail_company", by_stock["B"])

    def test_annual_growth_uses_previous_annual_periods(self):
        rows = [
            base_row("A", "软件", "20231231", revenue=100, net_profit=10, gross_margin=20, net_margin=8),
            base_row("A", "软件", "20241231", revenue=120, net_profit=12, gross_margin=25, net_margin=9),
            base_row("A", "软件", "20251231", revenue=150, net_profit=16, gross_margin=30, net_margin=11),
            base_row("B", "软件", "20251231", revenue=80, net_profit=8, gross_margin=10, net_margin=5),
        ]

        tags = generate_industry_financial_tags(rows, ["20251231"])
        stock_a_tags = {tag["tag_code"] for tag in tags if tag["ts_code"] == "A"}

        self.assertIn("stable_growth", stock_a_tags)
        self.assertIn("profitability_improving", stock_a_tags)

    def test_missing_market_value_blocks_small_beautiful_only(self):
        rows = [
            base_row("A", "设备", "20251231", revenue=1000, net_profit=100, gross_margin=10, net_margin=8, roe=8),
            base_row("B", "设备", "20251231", revenue=100, net_profit=10, gross_margin=30, net_margin=20, roe=20, market_value=None),
        ]

        tags = generate_industry_financial_tags(rows, ["20251231"])
        stock_b_tags = {tag["tag_code"] for tag in tags if tag["ts_code"] == "B"}

        self.assertNotIn("small_beautiful", stock_b_tags)
        self.assertIn("high_gross_margin", stock_b_tags)

    def test_build_fetch_periods_includes_two_prior_annual_periods(self):
        self.assertEqual(
            build_fetch_periods(["20251231", "20241231"]),
            ["20221231", "20231231", "20241231", "20251231"],
        )


class PeriodSelectionTests(unittest.TestCase):
    def test_get_target_annual_periods_returns_latest_five_annual_reports(self):
        class FakeResult:
            def __init__(self, value):
                self.value = value

            def scalar_one_or_none(self):
                return self.value

            def scalars(self):
                return self

            def all(self):
                return ["20251231", "20241231", "20231231", "20221231", "20211231"]

        class FakeConnection:
            def execute(self, sql, params=None):
                if params:
                    self.params = params
                    return FakeResult(None)
                return FakeResult("20251231")

        class FakeContext:
            def __init__(self):
                self.conn = FakeConnection()

            def __enter__(self):
                return self.conn

            def __exit__(self, *_args):
                return False

        class FakeEngine:
            def __init__(self):
                self.ctx = FakeContext()

            def connect(self):
                return self.ctx

        engine = FakeEngine()
        periods = get_target_annual_periods(engine)

        self.assertEqual(periods, ["20251231", "20241231", "20231231", "20221231", "20211231"])
        self.assertEqual(engine.ctx.conn.params["min_year"], 2021)
        self.assertEqual(engine.ctx.conn.params["latest_year"], 2025)


class StockTagPayloadTests(unittest.TestCase):
    def test_build_stock_tag_payload_groups_by_period_desc(self):
        rows = [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "sw_l1_name": "银行",
                "sw_l2_name": "股份制银行",
                "sw_l3_name": "股份制银行",
                "end_date": "20241231",
                "tag_category": "quality",
                "tag_category_label": "财务质量",
                "tag_code": "excellent_cashflow",
                "tag_name": "现金流优秀",
                "revenue": 100,
            },
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "sw_l1_name": "银行",
                "sw_l2_name": "股份制银行",
                "sw_l3_name": "股份制银行",
                "end_date": "20251231",
                "tag_category": "position",
                "tag_category_label": "行业地位",
                "tag_code": "industry_leader",
                "tag_name": "行业龙头",
                "revenue": 120,
            },
        ]

        payload = build_stock_tag_payload("000001.SZ", rows)

        self.assertEqual(payload["periods"], ["20251231", "20241231"])
        self.assertEqual([group["end_date"] for group in payload["groups"]], ["20251231", "20241231"])
        self.assertEqual(payload["groups"][0]["tags"][0]["tag_name"], "行业龙头")

    def test_build_stock_tag_payload_empty(self):
        payload = build_stock_tag_payload("NOPE", [])

        self.assertEqual(payload["ts_code"], "NOPE")
        self.assertEqual(payload["periods"], [])
        self.assertEqual(payload["groups"], [])
        self.assertEqual(payload["total_tags"], 0)


class L3IndustryTagOverviewTests(unittest.TestCase):
    def test_build_l3_overview_groups_tags_by_stock(self):
        rows = [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "sw_l1_name": "银行",
                "sw_l2_name": "股份制银行",
                "sw_l3_code": "851111.SI",
                "sw_l3_name": "股份制银行",
                "end_date": "20251231",
                "tag_category": "position",
                "tag_category_label": "行业地位",
                "tag_code": "industry_leader",
                "tag_name": "行业龙头",
                "revenue": 100,
            },
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "sw_l1_name": "银行",
                "sw_l2_name": "股份制银行",
                "sw_l3_code": "851111.SI",
                "sw_l3_name": "股份制银行",
                "end_date": "20251231",
                "tag_category": "quality",
                "tag_category_label": "财务质量",
                "tag_code": "excellent_cashflow",
                "tag_name": "现金流优秀",
                "revenue": 100,
            },
            {
                "ts_code": "000002.SZ",
                "name": "万科A",
                "sw_l1_name": "房地产",
                "sw_l2_name": "房地产开发",
                "sw_l3_code": "851811.SI",
                "sw_l3_name": "住宅开发",
                "end_date": "20241231",
                "tag_category": "risk",
                "tag_category_label": "风险",
                "tag_code": "debt_risk",
                "tag_name": "高负债风险",
                "revenue": 80,
            },
        ]

        payload = build_l3_industry_tag_overview("851111.SI", "20251231", rows, rows[:2])

        self.assertEqual(payload["period"], "20251231")
        self.assertEqual(payload["periods"], ["20251231", "20241231"])
        self.assertEqual(payload["stock_count"], 1)
        self.assertEqual(payload["tag_count"], 2)
        self.assertEqual(payload["items"][0]["ts_code"], "000001.SZ")
        self.assertEqual(len(payload["items"][0]["tags"]), 2)

    def test_build_l3_overview_empty(self):
        payload = build_l3_industry_tag_overview("NOPE", None, [], [])

        self.assertEqual(payload["sw_l3_code"], "NOPE")
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["stock_count"], 0)


class IndustryTagRouteTests(unittest.TestCase):
    def test_periods_route(self):
        with patch("main.list_industry_tag_periods", return_value={"items": [{"end_date": "20251231"}]}) as periods:
            response = main.get_industry_tag_periods()

        self.assertEqual(response["items"][0]["end_date"], "20251231")
        periods.assert_called_once_with()

    def test_industries_route_passes_period(self):
        with patch("main.list_industry_tag_industries", return_value={"period": "20251231", "items": []}) as industries:
            response = main.get_industry_tag_industries(period="20251231")

        self.assertEqual(response["period"], "20251231")
        industries.assert_called_once_with("20251231")

    def test_stock_tags_route_passes_filters(self):
        with patch("main.get_industry_tags_for_stock", return_value={"ts_code": "000001.SZ", "periods": [], "groups": []}) as stock_tags:
            response = main.get_industry_stock_tags("000001.SZ", period="20251231", tag_category="risk")

        self.assertEqual(response["ts_code"], "000001.SZ")
        stock_tags.assert_called_once_with("000001.SZ", period="20251231", tag_category="risk")

    def test_l3_tags_route_passes_period(self):
        with patch("main.get_l3_industry_tag_overview", return_value={"sw_l3_code": "851111.SI", "items": []}) as overview:
            response = main.get_l3_industry_tags("851111.SI", period="20251231")

        self.assertEqual(response["sw_l3_code"], "851111.SI")
        overview.assert_called_once_with("851111.SI", period="20251231")

    def test_list_route_passes_filters_and_pagination(self):
        with patch("main.list_industry_tags", return_value={"period": "20251231", "items": []}) as list_tags:
            response = main.get_industry_tags(
                period="20251231",
                sw_l3_code="850111",
                tag_category="risk",
                page=2,
                page_size=20,
            )

        self.assertEqual(response["period"], "20251231")
        list_tags.assert_called_once_with(
            period="20251231",
            sw_l3_code="850111",
            tag_category="risk",
            tag_code=None,
            page=2,
            page_size=20,
        )


if __name__ == "__main__":
    unittest.main()
