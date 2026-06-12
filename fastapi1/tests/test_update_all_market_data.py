import sys
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch


FASTAPI_DIR = Path(__file__).resolve().parents[1]
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

import update_all_market_data as updater


def quietly(callable_obj, *args, **kwargs):
    with redirect_stdout(StringIO()):
        return callable_obj(*args, **kwargs)


class UpdateAllMarketDataTests(unittest.TestCase):
    def test_validate_yyyymmdd_accepts_valid_date(self):
        updater.validate_yyyymmdd("20260604", "--end-date")

    def test_validate_yyyymmdd_rejects_invalid_date(self):
        with self.assertRaises(SystemExit) as raised:
            updater.validate_yyyymmdd("2026-06-04", "--end-date")

        self.assertIn("YYYYMMDD", str(raised.exception))

    def test_choose_premarket_dates_prefers_quote_targets(self):
        dates = updater.choose_premarket_dates(
            Namespace(),
            {"target_dates": ["20260603", "20260604"]},
        )

        self.assertEqual(dates, ["20260603", "20260604"])

    def test_choose_premarket_dates_falls_back_to_latest_quote_date(self):
        with patch.object(
            updater,
            "get_daily_quote_status",
            return_value={"latest_trade_date": "20260604"},
        ):
            dates = updater.choose_premarket_dates(Namespace(), {"target_dates": []})

        self.assertEqual(dates, ["20260604"])

    def test_run_stock_update_dry_run_does_not_write(self):
        args = Namespace(limit=None, dry_run=True)

        with patch.object(
            updater.update_stocks,
            "get_database_status",
            return_value={"row_count": 10},
        ), patch.object(
            updater.update_stocks,
            "fetch_latest_stocks",
            return_value=[{"ts_code": "000001.SZ", "name": "平安银行"}],
        ), patch.object(
            updater.update_stocks,
            "get_existing_stocks",
            return_value={},
        ), patch.object(
            updater.update_stocks,
            "diff_stocks",
            return_value=([{"ts_code": "000001.SZ"}], []),
        ), patch.object(
            updater.update_stocks,
            "ensure_stocks_table",
        ) as ensure_table, patch.object(
            updater.update_stocks,
            "save_stocks",
        ) as save_stocks:
            result = quietly(updater.run_stock_update, args)

        self.assertEqual(result["new"], 1)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(result["saved"], 0)
        ensure_table.assert_not_called()
        save_stocks.assert_not_called()

    def test_run_company_profile_update_dry_run_does_not_write(self):
        args = Namespace(limit=None, dry_run=True)

        with patch.object(
            updater.sync_stock_company_profile,
            "fetch_company_profiles",
            return_value=[{"ts_code": "000001.SZ", "com_name": "平安银行股份有限公司"}],
        ), patch.object(
            updater.sync_stock_company_profile,
            "dedupe_company_profiles",
            side_effect=lambda rows: rows,
        ), patch.object(
            updater.sync_stock_company_profile,
            "get_existing_company_profiles",
            return_value={},
        ), patch.object(
            updater.sync_stock_company_profile,
            "diff_company_profiles",
            return_value=([{"ts_code": "000001.SZ"}], []),
        ), patch.object(
            updater.sync_stock_company_profile,
            "create_stock_company_profile_table",
        ) as create_table, patch.object(
            updater.sync_stock_company_profile,
            "save_company_profiles",
        ) as save_profiles:
            result = quietly(updater.run_company_profile_update, args)

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["new"], 1)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(result["saved"], 0)
        create_table.assert_not_called()
        save_profiles.assert_not_called()

    def test_run_premarket_update_dry_run_fetches_but_does_not_write(self):
        args = Namespace(dry_run=True)
        fake_df = Mock()
        fake_df.__len__ = Mock(return_value=2)

        with patch.object(
            updater.sync_stock_premarket,
            "fetch_stock_premarket",
            return_value=fake_df,
        ) as fetch_premarket, patch.object(
            updater.sync_stock_premarket,
            "create_stock_premarket_table",
        ) as create_table, patch.object(
            updater.sync_stock_premarket,
            "save_stock_premarket",
        ) as save_premarket, patch.object(updater.time, "sleep"):
            result = quietly(
                updater.run_premarket_update,
                args,
                {"target_dates": ["20260604"]},
            )

        self.assertEqual(result["total_saved"], 0)
        self.assertEqual(result["updated_dates"], [])
        self.assertEqual(result["empty_dates"], [])
        fetch_premarket.assert_called_once_with("20260604")
        create_table.assert_not_called()
        save_premarket.assert_not_called()

    def test_run_premarket_update_records_empty_tushare_result(self):
        args = Namespace(dry_run=False)
        fake_df = Mock()
        fake_df.__len__ = Mock(return_value=0)

        with patch.object(
            updater.sync_stock_premarket,
            "create_stock_premarket_table",
        ), patch.object(
            updater.sync_stock_premarket,
            "fetch_stock_premarket",
            return_value=fake_df,
        ), patch.object(
            updater.sync_stock_premarket,
            "save_stock_premarket",
        ) as save_premarket, patch.object(updater.time, "sleep"):
            result = quietly(
                updater.run_premarket_update,
                args,
                {"target_dates": ["20260604"]},
            )

        self.assertEqual(result["empty_dates"], ["20260604"])
        self.assertEqual(result["failed_dates"], [])
        self.assertEqual(result["total_saved"], 0)
        save_premarket.assert_not_called()

    def test_fetch_stock_premarket_uses_daily_basic(self):
        daily_basic_df = Mock()
        daily_basic_df.attrs = {}

        with patch.object(
            updater.sync_stock_premarket,
            "fetch_daily_basic_shares",
            return_value=daily_basic_df,
        ) as fetch_daily_basic:
            result = updater.sync_stock_premarket.fetch_stock_premarket("20260604")

        self.assertIs(result, daily_basic_df)
        fetch_daily_basic.assert_called_once_with("20260604")

    def test_run_margin_detail_update_dry_run_fetches_but_does_not_write(self):
        args = Namespace(dry_run=True, force_refresh=False)
        fake_df = Mock()
        fake_df.__len__ = Mock(return_value=2)

        with patch.object(
            updater.sync_stock_margin_detail,
            "get_existing_counts",
            return_value={"20260604": 0},
        ), patch.object(
            updater.sync_stock_margin_detail,
            "fetch_margin_detail",
            return_value=fake_df,
        ) as fetch_margin_detail, patch.object(
            updater.sync_stock_margin_detail,
            "create_stock_margin_detail_table",
        ) as create_table, patch.object(
            updater.sync_stock_margin_detail,
            "save_margin_detail",
        ) as save_margin_detail, patch.object(updater.time, "sleep"):
            result = quietly(
                updater.run_margin_detail_update,
                args,
                {"target_dates": ["20260604"]},
            )

        self.assertEqual(result["total_saved"], 0)
        self.assertEqual(result["updated_dates"], [])
        self.assertEqual(result["empty_dates"], [])
        fetch_margin_detail.assert_called_once_with("20260604")
        create_table.assert_not_called()
        save_margin_detail.assert_not_called()

    def test_get_latest_verification_without_daily_quotes_table(self):
        with patch.object(updater, "table_exists", return_value=False):
            result = updater.get_latest_verification()

        self.assertIsNone(result["latest_trade_date"])
        self.assertEqual(result["quote_count"], 0)
        self.assertEqual(result["premarket_count"], 0)
        self.assertEqual(result["margin_detail_count"], 0)
        self.assertEqual(result["missing_float_share_count"], 0)
        self.assertEqual(result["samples"], [])

    def test_main_dry_run_does_not_raise_when_verification_warns(self):
        args = Namespace(
            end_date="20260604",
            lookback_open_days=1,
            dry_run=True,
            force_refresh=False,
            limit=None,
            skip_stocks=True,
            skip_company_profiles=True,
            skip_industries=True,
            skip_quotes=True,
            skip_premarket=True,
            skip_margin_detail=True,
        )

        with patch.object(updater, "parse_args", return_value=args), patch.object(
            updater,
            "print_final_verification",
            return_value=False,
        ):
            quietly(updater.main)

    def test_main_non_dry_run_exits_when_verification_fails(self):
        args = Namespace(
            end_date="20260604",
            lookback_open_days=1,
            dry_run=False,
            force_refresh=False,
            limit=None,
            skip_stocks=True,
            skip_company_profiles=True,
            skip_industries=True,
            skip_quotes=True,
            skip_premarket=True,
            skip_margin_detail=True,
        )

        with patch.object(updater, "parse_args", return_value=args), patch.object(
            updater,
            "print_final_verification",
            return_value=False,
        ):
            with self.assertRaises(SystemExit) as raised:
                quietly(updater.main)

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
