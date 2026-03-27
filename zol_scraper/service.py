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
from .types import MatchResult, OutputPaths, ScrapeResult


@dataclass(frozen=True)
class RunResult:
    scrape: ScrapeResult
    match: MatchResult
    output: OutputPaths
    images_downloaded: int


def run_pipeline(
    excel_path: str,
    output_dir: str,
    total_pages: int = 91,
    threads_pages: int = 10,
    threads_images: int = 20,
    download_imgs: bool = True,
    progress: Callable = print,
) -> RunResult:
    """完整流程: 读Excel → 爬ZOL → 匹配 → 导出 → 下载图片"""

    # 1. 读取 Excel
    progress("[1/5] 读取 Excel...")
    df = pd.read_excel(excel_path)
    progress(f"  共 {len(df)} 行, {df['机型'].nunique()} 个独立机型")

    # 2. 爬取 ZOL
    progress("[2/5] 爬取 ZOL 手机报价...")
    cache_path = Path(output_dir) / "zol_products_cache.json"
    scrape_result = scrape_all_pages(
        total_pages=total_pages,
        threads=threads_pages,
        progress=progress,
        cache_path=cache_path,
    )

    # 3. 匹配
    progress("[3/5] 型号匹配...")
    match_result = match_products(df, scrape_result.products)
    progress(f"  匹配成功: {match_result.matched_count}/{match_result.total_excel}")

    # 4. 导出 Excel
    out_dir = Path(output_dir)
    excel_out = out_dir / "匹配结果_ZOL报价.xlsx"
    image_dir = out_dir / "zol_images"
    progress("[4/5] 导出结果...")
    export_excel(match_result.rows, excel_out)
    progress(f"  已保存: {excel_out}")

    # 5. 下载图片
    images_downloaded = 0
    if download_imgs:
        progress("[5/5] 下载产品主图...")
        images_downloaded = download_images(
            match_result.rows, str(image_dir),
            threads=threads_images, progress=progress,
        )
    else:
        progress("[5/5] 跳过图片下载")

    output = OutputPaths(excel_path=excel_out, image_dir=image_dir)
    return RunResult(
        scrape=scrape_result, match=match_result,
        output=output, images_downloaded=images_downloaded,
    )
