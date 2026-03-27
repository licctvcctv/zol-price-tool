"""ZOL 手机报价爬虫 - 配置"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── 应用信息 ─────────────────────────────────────────────
APP_NAME = "ZOL 手机报价爬虫"
APP_VERSION = "1.0.0"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 860

# ── ZOL 配置 ─────────────────────────────────────────────
BASE_URL = "https://detail.zol.com.cn"
LIST_URL_FIRST = "https://detail.zol.com.cn/cell_phone_index/subcate57_list_1.html"
LIST_URL_TEMPLATE = "https://detail.zol.com.cn/cell_phone_index/subcate57_0_list_1_0_1_2_0_{page}.html"
TOTAL_PAGES = 91

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://detail.zol.com.cn/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ── 默认设置 ─────────────────────────────────────────────
APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_ROOT / ".zol_scraper_gui.json"

DEFAULTS: dict[str, Any] = {
    "excel_path": "",
    "output_dir": str(APP_ROOT / "output"),
    "username": "不貮二手数码",
    "password": "不貮二手数码",
    "threads": 5,
}


# ── 配置读写 ─────────────────────────────────────────────
def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    for k, v in data.items():
        if k in merged:
            merged[k] = v
    return merged


def save_config(payload: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
