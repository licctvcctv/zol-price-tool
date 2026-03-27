"""主服务 — 串联爬取、匹配、导出、下载"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .downloader import download_images
from .exporter import export_excel
from .matcher import match_products
from .scraper import scrape_all_pages
from .xcx_scraper import load_categories, scrape_xcx_prices, merge_xcx_prices
from .types import MatchResult, OutputPaths, ScrapeResult


@dataclass(frozen=True)
class RunResult:
    scrape: ScrapeResult
    match: MatchResult
    output: OutputPaths
    images_downloaded: int
    xcx_matched: int


def run_pipeline(
    excel_path: str,
    output_dir: str,
    total_pages: int = 91,
    threads_pages: int = 10,
    threads_images: int = 20,
    download_imgs: bool = True,
    scrape_xcx: bool = True,
    progress: Callable = print,
    on_row: Callable = None,
) -> RunResult:
    """完整流程: 读Excel → 爬ZOL → 匹配 → 小程序回收价 → 导出 → 下载图片"""

    out_dir = Path(output_dir)

    # 1. 读取 Excel
    progress("[1/7] 读取 Excel...")
    df = pd.read_excel(excel_path)
    progress(f"  共 {len(df)} 行, {df['机型'].nunique()} 个独立机型")

    # 2. 爬取 ZOL
    progress("[2/7] 爬取 ZOL 手机报价...")
    cache_path = out_dir / "zol_products_cache.json"
    scrape_result = scrape_all_pages(
        total_pages=total_pages,
        threads=threads_pages,
        progress=progress,
        cache_path=cache_path,
    )

    # 3. ZOL 型号匹配
    progress("[3/7] ZOL 型号匹配...")
    match_result = match_products(df, scrape_result.products, progress=progress, on_row=on_row)
    progress(f"  ZOL 匹配成功: {match_result.matched_count}/{match_result.total_excel}")

    # 4. 小程序回收价
    xcx_matched = 0
    if scrape_xcx:
        progress("[4/7] 加载小程序分类...")
        categories = load_categories(data_dir=out_dir)
        if categories:
            progress(f"  分类数: {len(categories)}")
            progress("[5/7] 爬取小程序回收报价...")
            xcx_cache = out_dir / "xcx_prices_cache.json"
            xcx_data = scrape_xcx_prices(
                categories, threads=threads_pages,
                progress=progress, cache_path=xcx_cache,
            )
            progress(f"  小程序产品: {len(xcx_data)}")

            progress("[6/7] 合并小程序回收价...")
            _, xcx_matched = merge_xcx_prices(
                match_result.rows, xcx_data, progress=progress,
            )
            progress(f"  小程序匹配成功: {xcx_matched}/{match_result.total_excel}")
        else:
            progress("[4/7] 未找到小程序分类数据，跳过")
            progress("[5/7] 跳过")
            progress("[6/7] 跳过")
    else:
        progress("[4/7] 跳过小程序爬取")
        progress("[5/7] 跳过")
        progress("[6/7] 跳过")

    # 7. 导出 + 下载图片
    excel_out = out_dir / "匹配结果_ZOL报价.xlsx"
    image_dir = out_dir / "zol_images"
    progress("[7/7] 导出结果...")
    export_excel(match_result.rows, excel_out)
    progress(f"  已保存: {excel_out}")

    images_downloaded = 0
    if download_imgs:
        progress("  下载产品主图...")
        images_downloaded = download_images(
            match_result.rows, str(image_dir),
            threads=threads_images, progress=progress,
        )

    output = OutputPaths(excel_path=excel_out, image_dir=image_dir)
    return RunResult(
        scrape=scrape_result, match=match_result,
        output=output, images_downloaded=images_downloaded,
        xcx_matched=xcx_matched,
    )
