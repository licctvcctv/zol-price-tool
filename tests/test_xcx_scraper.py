import json
import re
import unittest
from unittest.mock import patch

from zol_scraper import xcx_scraper


def _build_html(products):
    return f"<script>const list = JSON.parse('{json.dumps(products, ensure_ascii=False)}');</script>"


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"


class XcxScraperTests(unittest.TestCase):
    def test_scrape_xcx_prices_scans_live_cat_ids_without_category_file(self):
        product_block = [
            {
                "recovery_serie_id": 1,
                "series_name": "苹果手机",
                "products": {
                    "col": [
                        [
                            {
                                "one_level_sub_category_name": "256G",
                                "child": [
                                    {
                                        "型号": {"title": "iPhone 15"},
                                        "排序": {"title": 1, "product_id": 1001},
                                        "网络型号": {"title": ""},
                                        "充新": {"store_price": 3999, "deliver_price": 3980},
                                    }
                                ],
                            }
                        ]
                    ]
                },
            }
        ]

        def fake_get(url, timeout=30):
            match = re.search(r"/catId/(\d+)/", url)
            cat_id = int(match.group(1))
            if cat_id == 2:
                return _FakeResponse(_build_html(product_block))
            return _FakeResponse("<html></html>")

        with patch.object(xcx_scraper.SESSION, "get", side_effect=fake_get):
            data = xcx_scraper.scrape_xcx_prices(
                categories=None,
                threads=1,
                progress=lambda *_: None,
                cat_id_range=range(1, 5),
            )

        self.assertEqual(1, len(data))
        self.assertEqual("iPhone 15", data[0]["model"])
        self.assertEqual(2, data[0]["offer_cat_id"])

    def test_merge_xcx_prices_can_match_without_category_metadata(self):
        rows = [
            {
                "类型": "靓机回收报价",
                "品牌": "苹果",
                "机型": "iPhone 15",
                "内存": "256G",
            }
        ]
        price_data = [
            {
                "model": "iPhone 15",
                "sub_category": "256G",
                "充新_store": 3999,
                "充新_deliver": 3980,
                "sku_names": ["充新"],
                "offer_cat_id": 2,
            }
        ]

        merged, matched = xcx_scraper.merge_xcx_prices(
            rows,
            price_data,
            progress=lambda *_: None,
        )

        self.assertEqual(1, matched)
        self.assertEqual("已匹配", merged[0]["小程序匹配"])
        self.assertEqual("充新", merged[0]["SKU1名称"])
        self.assertEqual(3999, merged[0]["SKU1回收价"])


if __name__ == "__main__":
    unittest.main()
