"""小程序回收报价爬取 + SKU 匹配"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import date

import requests

# ── 配置 ─────────────────────────────────────────────────
XCX_HASH = "eJ9NdVl"
XCX_BASE_URL = "https://smbjd.smhsw.com/index/make/indexV2"
XCX_BATCH_SIZE = 10
DEFAULT_CATEGORIES_PATH = Path(__file__).resolve().parent.parent / "data" / "all_categories.json"
FALLBACK_CATEGORIES_PATH = Path("/Users/a136/vs/WMPFDebugger-mac/all_categories.json")

# ── 类型映射 ──────────────────────────────────────────────
TYPE_MAP = {
    "靓机回收报价": "新机靓机报价",
    "废旧手机回收报价": "环保手机报价",
    "手表报价/靓机平板": "新机靓机报价",
    "数码相机回收报价": "数码相机报价",
    "环保品牌平板": "电脑主机报价",
    "废旧手机内配回收报价": "手机内配报价",
    "电子产品杂货铺报价": "电子杂货报价",
    "笔记本电脑/平板回收报价": "电脑主机报价",
    "台式电脑报价": "电脑主机报价",
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
})


@lru_cache(maxsize=4096)
def _normalize(s: str) -> str:
    if not s:
        return ""
    return str(s).lower().replace(" ", "").strip()


@lru_cache(maxsize=2048)
def _norm_mem(s: str) -> str:
    if not s:
        return ""
    s = str(s).lower().replace(" ", "")
    s = s.replace("1tg", "1tb")
    if s == "1t":
        s = "1tb"
    return s.strip()


# ── 分类加载 ──────────────────────────────────────────────
def load_categories(data_dir: Optional[Path] = None) -> List[Dict]:
    """加载小程序分类列表"""
    paths = []
    if data_dir:
        paths.append(Path(data_dir) / "all_categories.json")
    paths.extend([DEFAULT_CATEGORIES_PATH, FALLBACK_CATEGORIES_PATH])

    for p in paths:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if data_dir:
                dst = Path(data_dir) / "all_categories.json"
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
    return []


# ── HTML 解析 ─────────────────────────────────────────────
_RE_JSON_PARSE = re.compile(r"JSON\.parse\('(\[.*?\])'\)", re.DOTALL)


def _parse_products_from_html(html: str) -> List[Dict]:
    products = []
    for m in _RE_JSON_PARSE.finditer(html):
        try:
            json_str = m.group(1).replace("\\'", "'").replace("\\n", "\n").replace("\\t", "\t")
            data = json.loads(json_str)
            if not isinstance(data, list) or not data:
                continue
            if "recovery_serie_id" not in data[0]:
                continue
            for serie in data:
                prods = serie.get("products", {})
                cols = prods.get("col", [])
                for col_group in cols:
                    for group in col_group:
                        for product in group.get("child", []):
                            item: Dict[str, Any] = {
                                "series": serie.get("series_name", ""),
                                "sub_category": group.get("one_level_sub_category_name", ""),
                            }
                            sku_names = []
                            for key, val in product.items():
                                if key == "型号":
                                    item["model"] = val.get("title", "")
                                elif key == "排序":
                                    item["product_id"] = val.get("product_id", "")
                                    item["sort"] = val.get("title", "")
                                elif key == "网络型号":
                                    item["network"] = val.get("title", "")
                                elif isinstance(val, dict) and "store_price" in val:
                                    item[key + "_store"] = val["store_price"]
                                    item[key + "_deliver"] = val["deliver_price"]
                                    sku_names.append(key)
                            if sku_names:
                                item["sku_names"] = sku_names
                            if item.get("model"):
                                products.append(item)
        except (json.JSONDecodeError, KeyError):
            continue
    return products


# ── 爬取小程序报价 ────────────────────────────────────────
def scrape_xcx_prices(
    categories: List[Dict],
    threads: int = 10,
    progress: Callable = print,
    cache_path: Optional[Path] = None,
) -> List[Dict]:
    """爬取全部分类的小程序回收报价"""

    if cache_path and cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            progress(f"  使用缓存: {len(data)} 个产品")
            return data
        except Exception:
            pass

    if not categories:
        progress("  [!] 没有分类数据，跳过小程序爬取")
        return []

    today = date.today().strftime("%Y-%m-%d")
    all_products: List[Dict] = []
    total = len(categories)

    def fetch_cat(cat: Dict) -> List[Dict]:
        url = f"{XCX_BASE_URL}/catId/{cat['offer_cat_id']}/hash/{XCX_HASH}/store_id/0//history_date/{today}/points/0"
        try:
            resp = SESSION.get(url, timeout=30)
            resp.encoding = "utf-8"
            products = _parse_products_from_html(resp.text)
            for p in products:
                p["category"] = cat.get("cat_name", "")
                p["top_category"] = cat.get("top_category", "")
                p["offer_cat_id"] = cat.get("offer_cat_id", "")
            return products
        except Exception:
            return []

    done = 0
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(fetch_cat, cat): cat for cat in categories}
        for future in as_completed(futures):
            prods = future.result()
            all_products.extend(prods)
            done += 1
            if done % 5 == 0 or done == total:
                progress(f"  小程序分类: {done}/{total} (累计 {len(all_products)} 产品)")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(all_products, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    return all_products


# ── 构建价格索引 ──────────────────────────────────────────
def build_price_index(price_data: List[Dict]) -> Dict[str, Dict]:
    index: Dict[str, Dict] = {}
    for p in price_data:
        brand = _normalize(p.get("category", ""))
        model = _normalize(p.get("model", ""))
        mem = _norm_mem(p.get("sub_category", ""))
        top_cat = p.get("top_category", "")
        prices: Dict[str, Any] = {}
        for k, v in p.items():
            if k.endswith("_store"):
                prices[k.replace("_store", "")] = v
        if p.get("sku_names"):
            prices["_skuNames"] = p["sku_names"]

        key = f"{top_cat}|{brand}|{model}|{mem}"
        if key not in index:
            index[key] = prices
        if not mem:
            k2 = f"{top_cat}|{brand}|{model}|"
            if k2 not in index:
                index[k2] = prices
    return index


def _find_prices(
    price_index: Dict[str, Dict],
    client_type: str, client_brand: str, client_model: str, mem: str,
) -> Optional[Dict]:
    top_cat = TYPE_MAP.get(client_type, client_type)
    brand = _normalize(client_brand)
    model = _normalize(client_model)
    mem_norm = _norm_mem(mem)

    brand_variants = [brand]
    if brand == "苹果" and top_cat == "新机靓机报价":
        brand_variants = ["苹果有保", "苹果无保"]

    model_variants = [
        model,
        model + "5g",
        model.replace("5g", ""),
        model.replace("8p", "8plus"),
        model.replace("7p", "7plus"),
        model.replace("6sp", "6splus"),
        model.replace("iphone苹果x", "iphonex"),
    ]

    # 精确匹配
    for mv in model_variants:
        for bv in brand_variants:
            bv_norm = _normalize(bv)
            for key in [f"{top_cat}|{bv_norm}|{mv}|{mem_norm}", f"{top_cat}|{bv_norm}|{mv}|"]:
                if key in price_index:
                    return price_index[key]

    # 模糊匹配
    for mv in model_variants:
        for bv in brand_variants:
            bv_norm = _normalize(bv)
            for key, prices in price_index.items():
                parts = key.split("|")
                if len(parts) < 4:
                    continue
                if parts[0] == top_cat and parts[1] == bv_norm:
                    im, imem = parts[2], parts[3]
                    if (im in mv or mv in im) and len(im) > 3:
                        if not mem_norm or imem == mem_norm or not imem:
                            return prices
    return None


# ── SKU 匹配（合并到已有行） ──────────────────────────────
def merge_xcx_prices(
    rows: List[Dict],
    price_data: List[Dict],
    progress: Callable = print,
    on_row_update: Optional[Callable] = None,
) -> tuple[List[Dict], int]:
    """将小程序回收价合并到匹配结果行中，返回 (更新后的rows, 匹配数)"""
    price_index = build_price_index(price_data)
    progress(f"  小程序价格索引: {len(price_index)} 条")

    matched = 0
    total = len(rows)

    for i, row in enumerate(rows):
        if progress and (i % 100 == 0 or i == total - 1):
            progress(f"  小程序匹配进度: {i + 1}/{total} ({(i + 1) * 100 // total}%)")

        client_type = str(row.get("类型", ""))
        client_brand = str(row.get("品牌", ""))
        client_model = str(row.get("机型", ""))
        client_mem = str(row.get("内存", ""))

        for j in range(1, 7):
            row.setdefault(f"SKU{j}名称", "")
            row.setdefault(f"SKU{j}回收价", "")
        row.setdefault("小程序匹配", "未匹配")

        prices = _find_prices(price_index, client_type, client_brand, client_model, client_mem)
        if prices:
            matched += 1
            row["小程序匹配"] = "已匹配"
            sku_names = prices.get("_skuNames", [k for k in prices if not k.startswith("_")])
            for j, sku in enumerate(sku_names[:6]):
                if sku in prices:
                    row[f"SKU{j + 1}名称"] = sku
                    row[f"SKU{j + 1}回收价"] = prices[sku]

        if on_row_update:
            on_row_update(i, row)

    return rows, matched
