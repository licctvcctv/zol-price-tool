"""ZOL 列表页爬虫 — 多线程抓取所有手机产品"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from .constants import BASE_URL, HEADERS, LIST_URL_FIRST, LIST_URL_TEMPLATE
from .types import Product, ScrapeResult

# 全局 Session — 复用 TCP 连接池，避免每次请求重建连接
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
        adapter = HTTPAdapter(
            pool_connections=20, pool_maxsize=20,
            max_retries=Retry(total=0),  # 手动控制重试
        )
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


def _fetch_page(url: str, retries: int = 3) -> Optional[str]:
    s = _get_session()
    for i in range(retries):
        try:
            r = s.get(url, timeout=10)
            r.encoding = "gbk"
            return r.text
        except Exception:
            if i < retries - 1:
                time.sleep(0.5 * (2 ** i))  # 指数退避: 0.5s, 1s, 2s
    return None


def _parse_list_page(html: str) -> List[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []
    ul = soup.select_one("#J_PicMode")
    if not ul:
        return products

    for li in ul.select("li[data-follow-id]"):
        try:
            product: Product = {}
            h3_a = li.select_one("h3 a")
            if h3_a:
                title = h3_a.get("title", "") or h3_a.get_text(strip=True)
                span = h3_a.select_one("span")
                if span:
                    title = title.replace(span.get_text(), "").strip()
                product["名称"] = title.strip()

            price_el = li.select_one(".price-type")
            if price_el:
                product["ZOL报价"] = price_el.get_text(strip=True)

            img = li.select_one("a.pic img")
            if img:
                img_url = img.get(".src") or img.get("src") or img.get("data-src", "")
                if img_url and not img_url.startswith("http"):
                    img_url = "https:" + img_url
                product["图片URL"] = img_url

            link_a = li.select_one("a.pic")
            if link_a:
                href = link_a.get("href", "")
                if href and not href.startswith("http"):
                    href = ("https:" + href) if href.startswith("//") else (BASE_URL + href)
                product["详情链接"] = href

            product["产品ID"] = li.get("data-follow-id", "").replace("p", "")

            if product.get("名称"):
                products.append(product)
        except Exception:
            continue
    return products


def _fetch_and_parse(page: int, total: int, progress: Callable) -> List[Product]:
    url = LIST_URL_FIRST if page == 1 else LIST_URL_TEMPLATE.format(page=page)
    html = _fetch_page(url)
    if not html:
        progress(f"  [{page}/{total}] 请求失败")
        return []
    products = _parse_list_page(html)
    progress(f"  [{page}/{total}] 获取 {len(products)} 个产品")
    return products


def scrape_all_pages(
    total_pages: int = 91,
    threads: int = 10,
    progress: Callable = print,
    cache_path: Optional[Path] = None,
) -> ScrapeResult:
    """多线程爬取 ZOL 列表页，支持缓存"""

    # 尝试从缓存加载
    if cache_path and cache_path.exists():
        progress(f"[缓存] 从 {cache_path.name} 加载...")
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        progress(f"[缓存] 已加载 {len(data)} 个产品")
        return ScrapeResult(
            products=data, pages_fetched=total_pages,
            total_pages=total_pages, is_complete=True,
        )

    progress(f"[爬取] {threads} 线程并发，共 {total_pages} 页...")
    all_products: list[Product] = []
    pages_ok = 0

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {
            pool.submit(_fetch_and_parse, p, total_pages, progress): p
            for p in range(1, total_pages + 1)
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                all_products.extend(result)
                if result:
                    pages_ok += 1
            except Exception:
                pass

    progress(f"[爬取] 完成: {len(all_products)} 个产品 ({pages_ok}/{total_pages} 页)")

    # 写缓存（紧凑格式减少序列化和磁盘开销）
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(all_products, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        progress(f"[缓存] 已保存到 {cache_path.name}")

    return ScrapeResult(
        products=all_products, pages_fetched=pages_ok,
        total_pages=total_pages, is_complete=pages_ok == total_pages,
    )
