"""主服务 — 串联登录、爬取后台报价、匹配Excel、导出"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

import pandas as pd

from .admin_scraper import _create_session, admin_login, scrape_admin_prices
from .admin_matcher import match_admin_prices
from .exporter import export_excel
from .xcx_scraper import load_categories, scrape_xcx_prices, merge_xcx_prices
from .types import OutputPaths


@dataclass(frozen=True)
class RunResult:
    admin_prices_count: int
    admin_matched: int
    total_excel: int
    xcx_matched: int
    output: OutputPaths
    rows: List[dict]


def run_pipeline(
    excel_path: str,
    output_dir: str,
    username: str = "不貮二手数码",
    password: str = "不貮二手数码",
    threads: int = 10,
    scrape_xcx: bool = True,
    progress: Callable = print,
    on_row: Optional[Callable] = None,
) -> RunResult:
    """完整流程: 读Excel → 登录后台 → 抓取报价 → 后台匹配 → 小程序匹配 → 导出"""

    out_dir = Path(output_dir)

    # 1. 读取 Excel
    progress("[1/5] 读取 Excel...")
    df = pd.read_excel(excel_path)
    progress(f"  共 {len(df)} 行")

    # 2. 登录后台 + 抓取报价
    progress("[2/5] 登录后台...")
    session = _create_session()
    if not admin_login(session, username, password):
        raise RuntimeError("后台登录失败，请检查账号密码")
    progress("  登录成功")

    cache_path = out_dir / "admin_prices_cache.json"
    admin_prices = scrape_admin_prices(
        session, threads=threads,
        progress=progress, cache_path=cache_path,
    )
    progress(f"  后台报价: {len(admin_prices)} 条")

    # 3. 后台报价匹配
    progress("[3/5] 后台报价匹配...")
    rows = df.to_dict("records")
    rows, admin_matched = match_admin_prices(rows, admin_prices, progress=progress)
    pct = admin_matched / len(rows) * 100 if rows else 0
    progress(f"  后台匹配: {admin_matched}/{len(rows)} ({pct:.1f}%)")

    # 4. 小程序回收价匹配
    xcx_matched = 0
    if scrape_xcx:
        progress("[4/5] 小程序报价匹配...")
        categories = load_categories(data_dir=out_dir)
        if categories:
            xcx_cache = out_dir / "xcx_prices_cache.json"
            xcx_data = scrape_xcx_prices(
                categories, threads=threads,
                progress=progress, cache_path=xcx_cache,
            )
            _, xcx_matched = merge_xcx_prices(
                rows, xcx_data, progress=progress,
            )
            progress(f"  小程序匹配: {xcx_matched}/{len(rows)}")
        else:
            progress("  未找到小程序分类数据，跳过")
    else:
        progress("[4/5] 跳过小程序匹配")

    # 推送每一行给 UI
    if on_row:
        for row in rows:
            on_row(row)

    # 5. 导出
    progress("[5/5] 导出结果...")
    excel_out = out_dir / "匹配结果_报价.xlsx"
    export_excel(rows, excel_out)
    progress(f"  已保存: {excel_out}")

    output = OutputPaths(excel_path=excel_out, image_dir=out_dir)
    return RunResult(
        admin_prices_count=len(admin_prices),
        admin_matched=admin_matched,
        total_excel=len(rows),
        xcx_matched=xcx_matched,
        output=output,
        rows=rows,
    )
