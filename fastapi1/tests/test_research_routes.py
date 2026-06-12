import unittest
from pathlib import Path
from unittest.mock import patch
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("TUSHARE_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from main import app
from research_service import build_trigger_mock_state, calculate_total_score


class ResearchServiceHelpersTests(unittest.TestCase):
    def test_calculate_total_score(self):
        self.assertEqual(
            calculate_total_score(
                {
                    "industry_trend": 4,
                    "competitive_advantage": 5,
                    "financial_quality": 3,
                    "management": 2,
                    "valuation": 1,
                }
            ),
            15,
        )

    def test_build_trigger_mock_state_requires_trigger_condition(self):
        item = {"ts_code": "000001.SZ", "name": "平安银行", "trigger_condition": "", "tags": []}
        self.assertIsNone(build_trigger_mock_state(item))

    def test_build_trigger_mock_state_returns_mock_payload(self):
        item = {
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "trigger_condition": "放量突破前高",
            "change_percent": 6.2,
            "price": 12.3,
            "tags": ["银行"],
        }
        payload = build_trigger_mock_state(item)
        self.assertTrue(payload["isMock"])
        self.assertEqual(payload["ts_code"], "000001.SZ")


class ResearchRouteTests(unittest.TestCase):
    def setUp(self):
        self.startup_patch = patch("main.ensure_tables", return_value=None)
        self.research_startup_patch = patch("main.ensure_research_tables", return_value=None)
        self.startup_patch.start()
        self.research_startup_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.startup_patch.stop()
        self.research_startup_patch.stop()

    def test_dashboard_uses_current_user(self):
        with patch("main.get_current_user_from_authorization", return_value={"id": 8, "username": "demo"}), patch(
            "main.get_research_dashboard",
            return_value={"statusCounts": {"focus": 1}, "todayMovers": [], "triggeredItems": [], "recentLogs": [], "staleResearchItems": []},
        ) as dashboard:
            response = self.client.get("/api/v1/research/dashboard", headers={"Authorization": "Bearer token"})

        self.assertEqual(response.status_code, 200)
        dashboard.assert_called_once_with(8)

    def test_list_research_stocks_passes_filters(self):
        with patch("main.get_current_user_from_authorization", return_value={"id": 3, "username": "demo"}), patch(
            "main.list_research_stocks",
            return_value=[],
        ) as list_stocks:
            response = self.client.get(
                "/api/v1/research/stocks?status=focus&priority=high&tag=AI&q=bank",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        list_stocks.assert_called_once_with(3, status="focus", priority="high", tag="AI", q="bank")

    def test_create_research_stock(self):
        payload = {
            "ts_code": "000001.SZ",
            "status": "focus",
            "priority": "high",
            "tags": ["银行"],
            "thesis": "低估值修复",
            "trigger_condition": "放量突破",
            "risk": "地产链拖累",
            "exit_condition": "估值修复完成",
            "score": {
                "industry_trend": 4,
                "competitive_advantage": 4,
                "financial_quality": 4,
                "management": 3,
                "valuation": 5,
            },
        }
        with patch("main.get_current_user_from_authorization", return_value={"id": 5, "username": "demo"}), patch(
            "main.create_research_stock",
            return_value={"ts_code": "000001.SZ", "status": "focus"},
        ) as create_stock:
            response = self.client.post(
                "/api/v1/research/stocks",
                headers={"Authorization": "Bearer token"},
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ts_code"], "000001.SZ")
        create_stock.assert_called_once()

    def test_update_research_stock(self):
        payload = {
            "status": "portfolio",
            "priority": "medium",
            "tags": ["红利"],
            "thesis": "稳定现金流",
            "trigger_condition": "回调到支撑位",
            "risk": "利率变化",
            "exit_condition": "逻辑破坏",
            "score": {
                "industry_trend": 3,
                "competitive_advantage": 4,
                "financial_quality": 5,
                "management": 3,
                "valuation": 4,
            },
        }
        with patch("main.get_current_user_from_authorization", return_value={"id": 12, "username": "demo"}), patch(
            "main.update_research_stock",
            return_value={"ts_code": "600000.SH", "status": "portfolio"},
        ) as update_stock:
            response = self.client.put(
                "/api/v1/research/stocks/600000.SH",
                headers={"Authorization": "Bearer token"},
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        update_stock.assert_called_once()

    def test_add_research_log(self):
        payload = {"date": "2026-06-11", "type": "复盘", "content": "验证买点执行情况"}
        with patch("main.get_current_user_from_authorization", return_value={"id": 12, "username": "demo"}), patch(
            "main.create_research_log",
            return_value={"id": 9, "ts_code": "600000.SH", "date": "2026-06-11", "type": "复盘", "content": "验证买点执行情况"},
        ) as add_log:
            response = self.client.post(
                "/api/v1/research/stocks/600000.SH/logs",
                headers={"Authorization": "Bearer token"},
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], 9)
        add_log.assert_called_once_with(12, "600000.SH", payload)


if __name__ == "__main__":
    unittest.main()
