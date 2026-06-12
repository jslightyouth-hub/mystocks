import unittest
from unittest.mock import patch
from pathlib import Path
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("TUSHARE_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import auth_watchlist_service as service
from main import app


class PasswordAndTokenTests(unittest.TestCase):
    def test_hash_password_round_trip(self):
        password_hash = service.hash_password("secret123")

        self.assertTrue(service.verify_password("secret123", password_hash))
        self.assertFalse(service.verify_password("wrong", password_hash))

    def test_parse_token_rejects_tampering(self):
        token = service.create_token({"id": 7, "username": "alice"})
        tampered = f"{token}x"

        with self.assertRaises(Exception):
            service.parse_token(tampered)


class WatchlistServiceTests(unittest.TestCase):
    def test_list_watchlist_stocks_includes_latest_quote_fields(self):
        rows = [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "industry": "银行",
                "sw_l2_name": "股份制银行",
                "price": 11.32,
                "price_change": 0.19,
                "change_percent": 1.71,
                "turnover_rate": 0.82,
                "amount": 1234567.0,
                "trade_date": "20260611",
                "group_id": 1,
                "group_name": "核心池",
            },
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "industry": "银行",
                "sw_l2_name": "股份制银行",
                "price": 11.32,
                "price_change": 0.19,
                "change_percent": 1.71,
                "turnover_rate": 0.82,
                "amount": 1234567.0,
                "trade_date": "20260611",
                "group_id": 2,
                "group_name": "观察",
            },
        ]

        class FakeResult:
            def mappings(self):
                return self

            def all(self):
                return rows

        class FakeConnection:
            def execute(self, *_args, **_kwargs):
                return FakeResult()

        class FakeBegin:
            def __enter__(self):
                return FakeConnection()

            def __exit__(self, *_args):
                return False

        class FakeEngine:
            def begin(self):
                return FakeBegin()

        items = service.list_watchlist_stocks(7, FakeEngine())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["price"], 11.32)
        self.assertEqual(items[0]["change"], 0.19)
        self.assertEqual(items[0]["change_percent"], 1.71)
        self.assertEqual(items[0]["trade_date"], "20260611")
        self.assertEqual([group["name"] for group in items[0]["groups"]], ["核心池", "观察"])


class AuthRouteTests(unittest.TestCase):
    def setUp(self):
        self.startup_patch = patch("main.ensure_tables", return_value=None)
        self.startup_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.startup_patch.stop()

    def test_register_success(self):
        with patch("main.register_user", return_value={"token": "abc", "user": {"id": 1, "username": "demo"}}) as register:
            response = self.client.post("/api/v1/auth/register", json={"username": "demo", "password": "pw"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "demo")
        register.assert_called_once_with("demo", "pw")

    def test_login_success(self):
        with patch("main.login_user", return_value={"token": "abc", "user": {"id": 2, "username": "bob"}}) as login:
            response = self.client.post("/api/v1/auth/login", json={"username": "bob", "password": "pw"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], 2)
        login.assert_called_once_with("bob", "pw")

    def test_me_requires_authorization(self):
        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 401)

    def test_create_group_uses_current_user(self):
        with patch("main.get_current_user_from_authorization", return_value={"id": 9, "username": "demo"}), patch(
            "main.create_group",
            return_value={"id": 3, "name": "成长", "stock_count": 0},
        ) as create_group:
            response = self.client.post(
                "/api/v1/watchlist/groups",
                headers={"Authorization": "Bearer token"},
                json={"name": "成长"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "成长")
        create_group.assert_called_once_with(9, "成长")

    def test_add_watchlist_stock(self):
        with patch("main.get_current_user_from_authorization", return_value={"id": 11, "username": "demo"}), patch(
            "main.add_stock_to_groups",
            return_value={
                "ts_code": "000001.SZ",
                "in_watchlist": True,
                "groups": [{"id": 5, "name": "默认"}],
            },
        ) as add_stock:
            response = self.client.post(
                "/api/v1/watchlist/stocks/000001.SZ",
                headers={"Authorization": "Bearer token"},
                json={"group_ids": [5]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["in_watchlist"])
        add_stock.assert_called_once_with(11, "000001.SZ", [5])

    def test_delete_watchlist_stock(self):
        with patch("main.get_current_user_from_authorization", return_value={"id": 11, "username": "demo"}), patch(
            "main.remove_stock_from_watchlist",
            return_value={"ts_code": "000001.SZ", "in_watchlist": False, "groups": []},
        ) as remove_stock:
            response = self.client.delete(
                "/api/v1/watchlist/stocks/000001.SZ",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["in_watchlist"])
        remove_stock.assert_called_once_with(11, "000001.SZ")


if __name__ == "__main__":
    unittest.main()
