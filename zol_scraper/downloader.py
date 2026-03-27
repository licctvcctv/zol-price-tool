"""多线程图片下载器"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Tuple

import requests

from .constants import HEADERS
from .types import MatchedRow


def _create_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _download_one(args: Tuple[str, str]) -> bool:
    img_url, save_path = args
    if os.path.exists(save_path):
        return True
    try:
        s = _create_session()
        r = s.get(img_url, timeout=10)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False


def download_images(
    rows: List[MatchedRow],
    image_dir: str,
    threads: int = 20,
    progress: Callable = print,
) -> int:
    """多线程下载匹配到的产品主图，返回成功数量"""
    os.makedirs(image_dir, exist_ok=True)

    tasks: list[Tuple[str, str]] = []
    for row in rows:
        if row.get("匹配状态") != "已匹配":
            continue
        img_url = row.get("ZOL图片", "")
        model = str(row.get("机型", "unknown"))
        if not img_url:
            continue
        safe_name = re.sub(r"[^\w\-.]", "_", model)
        ext = os.path.splitext(img_url.split("?")[0])[-1] or ".jpg"
        save_path = os.path.join(image_dir, f"{safe_name}{ext}")
        tasks.append((img_url, save_path))

    if not tasks:
        progress("[下载] 没有需要下载的图片")
        return 0

    progress(f"[下载] {threads} 线程并发下载 {len(tasks)} 张图片...")
    downloaded = 0

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(_download_one, t): t for t in tasks}
        for future in as_completed(futures):
            if future.result():
                downloaded += 1
            if downloaded % 50 == 0 and downloaded > 0:
                progress(f"[下载] 已完成: {downloaded}/{len(tasks)}")

    progress(f"[下载] 完成: {downloaded}/{len(tasks)} 张图片")
    return downloaded
