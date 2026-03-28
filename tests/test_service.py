import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from zol_scraper.service import run_pipeline


class RunPipelineTests(unittest.TestCase):
    @patch("zol_scraper.service.export_excel")
    @patch("zol_scraper.service.merge_xcx_prices")
    @patch("zol_scraper.service.scrape_xcx_prices")
    @patch("zol_scraper.service.match_admin_prices")
    @patch("zol_scraper.service.scrape_admin_prices")
    @patch("zol_scraper.service.admin_login")
    @patch("zol_scraper.service._create_session")
    @patch("zol_scraper.service.pd.read_excel")
    def test_run_pipeline_does_not_emit_rows_after_export(
        self,
        mock_read_excel,
        mock_create_session,
        mock_admin_login,
        mock_scrape_admin_prices,
        mock_match_admin_prices,
        mock_scrape_xcx_prices,
        mock_merge_xcx_prices,
        mock_export_excel,
    ):
        rows = [{"类型": "靓机回收报价", "品牌": "苹果", "机型": "iPhone 15", "内存": "256G"}]
        mock_read_excel.return_value = pd.DataFrame(rows)
        mock_create_session.return_value = object()
        mock_admin_login.return_value = True
        mock_scrape_admin_prices.return_value = [{"分类": "iPhone 15", "品牌": "苹果", "顶级分类": "靓机回收报价"}]
        mock_match_admin_prices.return_value = (rows, 1)
        mock_scrape_xcx_prices.return_value = [{"model": "iPhone 15", "sub_category": "256G", "充新_store": 3999}]
        mock_merge_xcx_prices.return_value = (rows, 1)

        on_row = Mock()
        result = run_pipeline(
            excel_path="fake.xls",
            output_dir=str(Path("output")),
            progress=lambda *_: None,
            on_row=on_row,
        )

        self.assertEqual(1, result.total_excel)
        self.assertEqual(1, result.xcx_matched)
        on_row.assert_not_called()


if __name__ == "__main__":
    unittest.main()
