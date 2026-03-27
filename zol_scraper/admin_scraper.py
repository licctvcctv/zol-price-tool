"""后台管理系统爬虫 — 登录后台抓取三方报价数据"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

ADMIN_BASE = "https://xcx1540.ycdongxu.com"
LOGIN_URL = f"{ADMIN_BASE}/index.php/Admin/Admin/login"
CATEGORY_URL = f"{ADMIN_BASE}/index.php/Admin/San/categoryList222"


def _create_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })
    return s


def admin_login(session: requests.Session, username: str, password: str) -> bool:
    """登录后台，成功返回 True"""
    try:
        r = session.post(LOGIN_URL, data={
            "username": username,
            "password": password,
        }, timeout=15)
        data = r.json()
        return data.get("status") == 1
    except Exception:
        return False


def _parse_nav_links(html: str, pattern: str) -> List[Tuple[str, str]]:
    """从 nav-pills 中解析链接列表，返回 [(name, url), ...]"""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for ul in soup.select("ul.nav-pills"):
        for li in ul.select("li"):
            a = li.select_one("a")
            if a and a.get("href", "").startswith(pattern):
                name = a.get_text(strip=True)
                href = a["href"]
                if not href.startswith("http"):
                    href = ADMIN_BASE + href
                results.append((name, href))
    return results


def _parse_price_table(html: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """解析报价表格，返回 (表头列名列表, [{分类: xxx, col1: val1, ...}, ...])"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#list-table")
    if not table:
        return [], []

    # 解析表头
    headers = []
    for th in table.select("thead tr th"):
        headers.append(th.get_text(strip=True))

    # 解析数据行
    rows = []
    for tr in table.select("tbody tr"):
        inputs = tr.select("input.input-sm")
        if not inputs:
            continue
        values = [inp.get("value", "") for inp in inputs]
        if len(values) < 1:
            continue

        row: Dict[str, str] = {}
        # 第一个 input 是分类名（机型名）
        row["分类"] = values[0]

        # 后面的 input 对应表头列（从第2列开始）
        for i, val in enumerate(values[1:]):
            col_name = headers[i + 1] if (i + 1) < len(headers) else f"列{i + 1}"
            row[col_name] = val

        rows.append(row)

    return headers, rows


def scrape_admin_prices(
    session: requests.Session,
    threads: int = 5,
    progress: Callable = print,
    cache_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """爬取后台所有分类、品牌下的报价数据"""

    # 有缓存直接返回
    if cache_path and cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            progress(f"  [缓存] 加载 {len(data)} 条报价")
            return data
        except Exception:
            pass

    # 1. 获取顶级分类（废旧手机回收报价、数码相机回收报价...）
    progress("  获取分类列表...")
    r = session.get(CATEGORY_URL, timeout=15)
    r.encoding = "utf-8"
    top_categories = _parse_nav_links(r.text, "/index.php/Admin/San/categoryList222/ptab/")
    progress(f"  顶级分类: {len(top_categories)} 个")

    # 2. 对每个顶级分类，获取品牌列表
    all_brand_tasks: List[Tuple[str, str, str]] = []  # (top_cat_name, brand_name, brand_url)

    for cat_name, cat_url in top_categories:
        try:
            r = session.get(cat_url, timeout=15)
            r.encoding = "utf-8"
            brands = _parse_nav_links(r.text, "/index.php/Admin/San/categoryList222/brand/")
            for brand_name, brand_url in brands:
                all_brand_tasks.append((cat_name, brand_name, brand_url))
            progress(f"  [{cat_name}] {len(brands)} 个品牌")
        except Exception:
            progress(f"  [{cat_name}] 获取品牌失败")
        time.sleep(0.1)

    progress(f"  总计 {len(all_brand_tasks)} 个品牌页面待抓取...")

    # 3. 并发抓取每个品牌的报价表
    all_prices: List[Dict[str, Any]] = []

    def fetch_brand(task: Tuple[str, str, str]) -> List[Dict[str, Any]]:
        top_cat, brand, url = task
        try:
            resp = session.get(url, timeout=15)
            resp.encoding = "utf-8"
            headers, rows = _parse_price_table(resp.text)
            results = []
            for row in rows:
                row["顶级分类"] = top_cat
                row["品牌"] = brand
                row["SKU列名"] = [h for h in headers if h not in ("分类", "备注")]
                results.append(row)
            return results
        except Exception:
            return []

    done = 0
    total = len(all_brand_tasks)
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(fetch_brand, t): t for t in all_brand_tasks}
        for future in as_completed(futures):
            results = future.result()
            all_prices.extend(results)
            done += 1
            if done % 10 == 0 or done == total:
                progress(f"  品牌抓取: {done}/{total} (累计 {len(all_prices)} 条)")

    progress(f"  抓取完成: {len(all_prices)} 条报价")

    # 写缓存
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(all_prices, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        progress(f"  [缓存] 已保存到 {cache_path.name}")

    return all_prices
