"""小程序回收报价爬取 + SKU 匹配"""
from __future__ import annotations

import json
import re
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
XCX_SCAN_START_ID = 1
XCX_SCAN_END_ID = 420
XCX_SCAN_EMPTY_BATCH_LIMIT = 3
DEFAULT_CATEGORIES_PATH = Path(__file__).resolve().parent.parent / "data" / "all_categories.json"

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
    """兼容旧版本的分类文件读取。主流程已改为实时扫描。"""
    paths = []
    if data_dir:
        paths.append(Path(data_dir) / "all_categories.json")
    paths.append(DEFAULT_CATEGORIES_PATH)

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
    categories: Optional[List[Dict]] = None,
    threads: int = 10,
    progress: Callable = print,
    cache_path: Optional[Path] = None,
    cat_id_range: Optional[range] = None,
) -> List[Dict]:
    """实时爬取小程序回收报价。"""

    if cache_path:
        progress("  [*] 小程序报价已改为实时抓取，不再使用缓存")

    today = date.today().strftime("%Y-%m-%d")
    all_products: List[Dict] = []
    dynamic_scan = not categories
    if categories:
        targets = list(categories)
    else:
        targets = [{"offer_cat_id": cat_id} for cat_id in (cat_id_range or range(XCX_SCAN_START_ID, XCX_SCAN_END_ID + 1))]
    total = len(targets)
    batch_size = XCX_BATCH_SIZE if categories else max(XCX_BATCH_SIZE * 2, threads)

    def fetch_cat(cat: Dict) -> tuple[int, List[Dict]]:
        cat_id = int(cat["offer_cat_id"])
        url = f"{XCX_BASE_URL}/catId/{cat_id}/hash/{XCX_HASH}/store_id/0//history_date/{today}/points/0"
        try:
            resp = SESSION.get(url, timeout=30)
            if resp.status_code != 200:
                return cat_id, []
            resp.encoding = "utf-8"
            products = _parse_products_from_html(resp.text)
            for p in products:
                if cat.get("cat_name"):
                    p["category"] = cat["cat_name"]
                if cat.get("top_category"):
                    p["top_category"] = cat["top_category"]
                p["offer_cat_id"] = cat_id
            return cat_id, products
        except Exception:
            return cat_id, []

    done = 0
    empty_batches = 0
    for start in range(0, total, batch_size):
        batch = targets[start:start + batch_size]
        batch_hits = 0
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = {pool.submit(fetch_cat, cat): cat for cat in batch}
            for future in as_completed(futures):
                _, prods = future.result()
                if prods:
                    batch_hits += 1
                    all_products.extend(prods)
        done += len(batch)
        if dynamic_scan:
            progress(f"  小程序扫描: {done}/{total} (命中 {batch_hits}, 累计 {len(all_products)} 产品)")
            empty_batches = empty_batches + 1 if batch_hits == 0 else 0
            if cat_id_range is None and empty_batches >= XCX_SCAN_EMPTY_BATCH_LIMIT:
                break
        elif done % 5 == 0 or done == total:
            progress(f"  小程序分类: {done}/{total} (累计 {len(all_products)} 产品)")

    return all_products


# ── 品牌别名映射（Excel品牌 → 小程序category可能的值）──────
XCX_BRAND_ALIASES: dict[str, list[str]] = {
    "华为OK板": ["华为"],
    "华为旗舰": ["华为旗舰", "华为"],
    "红米、黑鲨": ["红米、黑鲨", "小米"],
    "荣耀其他": ["荣耀其他", "荣耀"],
    "锤子坚果": ["锤子坚果", "锤子"],
    "苹果平板": ["苹果平板"],
    "华为平板": ["华为平板", "OPPO/vivo平板", "OPPO/VIVO平板"],
    "三星平板": ["三星平板"],
    "统货功能机": ["热门老年机"],
    "MP3、MP4": [],
    "海康录像机": [],
    "华为随身4Gwifi": [],
}


# ── 构建价格索引 ──────────────────────────────────────────
def build_price_index(price_data: List[Dict]) -> tuple[Dict[str, Dict], Dict[str, Dict], Dict[str, Dict]]:
    """返回 (带top_cat索引, 品牌回退索引, 型号回退索引)。"""
    index: Dict[str, Dict] = {}
    brand_model_index: Dict[str, Dict] = {}  # 不含 top_cat 的回退索引
    model_index: Dict[str, Dict] = {}  # 不含品牌/分类的回退索引
    for p in price_data:
        brand = _normalize(p.get("category", ""))
        model = _normalize(p.get("model", ""))
        mem = _norm_mem(p.get("sub_category", ""))
        top_cat = p.get("top_category", "")
        if not model:
            continue
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

        # 回退索引（不含 top_cat）
        bm_key = f"{brand}|{model}|{mem}"
        if bm_key not in brand_model_index:
            brand_model_index[bm_key] = prices
        if not mem:
            bm_key2 = f"{brand}|{model}|"
            if bm_key2 not in brand_model_index:
                brand_model_index[bm_key2] = prices

        model_key = f"{model}|{mem}"
        if model_key not in model_index:
            model_index[model_key] = prices
        if not mem:
            model_key2 = f"{model}|"
            if model_key2 not in model_index:
                model_index[model_key2] = prices

    return index, brand_model_index, model_index


def _get_brand_variants(brand: str, top_cat: str) -> list[str]:
    """获取品牌在小程序中可能的所有 category 名"""
    variants = []
    # 别名映射
    if brand in XCX_BRAND_ALIASES:
        aliases = XCX_BRAND_ALIASES[brand]
        variants.extend(_normalize(a) for a in aliases)
    # 苹果在新机靓机下拆分有保/无保
    if _normalize(brand) == "苹果" and top_cat == "新机靓机报价":
        variants = ["苹果有保", "苹果无保"]
    elif not variants:
        variants = [_normalize(brand)]
    return variants


def _find_prices(
    price_index: Dict[str, Dict],
    brand_model_index: Dict[str, Dict],
    model_index: Dict[str, Dict],
    client_type: str, client_brand: str, client_model: str, mem: str,
) -> Optional[Dict]:
    top_cat = TYPE_MAP.get(client_type, client_type)
    brand = client_brand.strip()
    model = _normalize(client_model)
    mem_norm = _norm_mem(mem)

    brand_variants = _get_brand_variants(brand, top_cat)

    model_variants = [
        model,
        model + "5g",
        model.replace("5g", ""),
        model.replace("8p", "8plus"),
        model.replace("7p", "7plus"),
        model.replace("6sp", "6splus"),
        model.replace("iphone苹果x", "iphonex"),
    ]
    # 去掉 "代" 后缀：iphone7代 -> iphone7
    import re
    cleaned = re.sub(r"(\d+)代", r"\1", model)
    if cleaned != model:
        model_variants.append(cleaned)
    model_variants = list(dict.fromkeys(model_variants))

    # 1. 精确匹配（带 top_cat）
    for mv in model_variants:
        for bv in brand_variants:
            for key in [f"{top_cat}|{bv}|{mv}|{mem_norm}", f"{top_cat}|{bv}|{mv}|"]:
                if key in price_index:
                    return price_index[key]

    # 2. 模糊匹配（带 top_cat，包含关系）
    for mv in model_variants:
        for bv in brand_variants:
            for key, prices in price_index.items():
                parts = key.split("|")
                if len(parts) < 4:
                    continue
                if parts[0] == top_cat and parts[1] == bv:
                    im, imem = parts[2], parts[3]
                    if (im in mv or mv in im) and len(im) > 1 and len(mv) > 1:
                        if not mem_norm or imem == mem_norm or not imem:
                            return prices

    # 3. 回退：跨 top_category 搜索（只匹配品牌+型号）
    for mv in model_variants:
        for bv in brand_variants:
            for key in [f"{bv}|{mv}|{mem_norm}", f"{bv}|{mv}|"]:
                if key in brand_model_index:
                    return brand_model_index[key]

    # 4. 回退：跨 top_category 模糊匹配
    for mv in model_variants:
        for bv in brand_variants:
            for key, prices in brand_model_index.items():
                parts = key.split("|")
                if len(parts) < 3:
                    continue
                if parts[0] == bv:
                    im, imem = parts[1], parts[2]
                    if (im in mv or mv in im) and len(im) > 1 and len(mv) > 1:
                        if not mem_norm or imem == mem_norm or not imem:
                            return prices

    # 5. 回退：只按型号+内存精确匹配
    for mv in model_variants:
        for key in [f"{mv}|{mem_norm}", f"{mv}|"]:
            if key in model_index:
                return model_index[key]

    # 6. 回退：只按型号+内存模糊匹配
    for mv in model_variants:
        for key, prices in model_index.items():
            parts = key.split("|")
            if len(parts) < 2:
                continue
            im, imem = parts[0], parts[1]
            if (im in mv or mv in im) and len(im) > 1 and len(mv) > 1:
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
    price_index, brand_model_index, model_index = build_price_index(price_data)
    progress(
        f"  小程序价格索引: {len(price_index)} 条 "
        f"(品牌回退: {len(brand_model_index)} 条, 型号回退: {len(model_index)} 条)"
    )

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

        # 内存可能是逗号分隔的多值（如 "1TB,512G,256G"），逐个尝试
        mem_variants = [m.strip() for m in client_mem.split(",") if m.strip()] if "," in client_mem else [client_mem]
        # 加上空内存做回退
        if "" not in mem_variants:
            mem_variants.append("")

        prices = None
        for mem_v in mem_variants:
            prices = _find_prices(price_index, brand_model_index, model_index, client_type, client_brand, client_model, mem_v)
            if prices:
                break
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
