"""后台报价匹配引擎 — 将 Excel 行与后台报价数据匹配"""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple


# Excel品牌 → 后台可能的品牌列表
BRAND_EXPAND: dict[str, list[str]] = {
    "苹果": ["苹果", "苹果有保", "苹果无保"],
    "华为旗舰": ["华为旗舰", "华为"],
    "荣耀其他": ["荣耀其他", "荣耀"],
    "锤子坚果": ["锤子坚果", "锤子"],
    "华为OK板": ["华为OK板", "华为"],
    "红米、黑鲨": ["红米、黑鲨", "小米"],
    "华为随身4Gwifi": ["随身4Gwifi"],
    "家教机": ["品牌学习机"],
    "MP3、MP4": [],
    "海康录像机": [],
}

_RE_5G4G = re.compile(r"[54]g$")


@lru_cache(maxsize=8192)
def _norm(s: str) -> str:
    """归一化名称用于匹配"""
    s = str(s).lower().replace(" ", "").replace("-", "").replace("_", "").strip()
    s = _RE_5G4G.sub("", s)
    return s


def build_admin_index(
    admin_prices: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], List[Tuple[str, Dict]]]:
    """构建后台报价索引: (顶级分类, 品牌) -> [(norm分类名, 原始数据), ...]"""
    index: Dict[Tuple[str, str], List[Tuple[str, Dict]]] = defaultdict(list)
    for d in admin_prices:
        key = (d["顶级分类"], d["品牌"])
        index[key].append((_norm(d["分类"]), d))
    return dict(index)


def _find_best_match(
    model_norm: str,
    entries: List[Tuple[str, Dict]],
) -> Optional[Dict]:
    """在候选列表中找最佳匹配"""
    if not model_norm:
        return None

    # 1. 精确匹配
    for an, d in entries:
        if model_norm == an:
            return d

    # 2. 子串匹配 — 取最高分（相似度 >= 0.5）
    best = None
    best_score = 0.0
    for an, d in entries:
        if not an:
            continue
        if model_norm in an:
            score = len(model_norm) / len(an)
        elif an in model_norm:
            score = len(an) / len(model_norm)
        else:
            continue
        if score > best_score and score >= 0.5:
            best_score = score
            best = d

    return best


def match_admin_prices(
    rows: List[Dict],
    admin_prices: List[Dict[str, Any]],
    progress: Optional[Callable] = None,
) -> Tuple[List[Dict], int]:
    """将后台报价匹配到 Excel 行中，返回 (更新后的rows, 匹配数)"""

    index = build_admin_index(admin_prices)
    matched = 0
    total = len(rows)

    for i, row in enumerate(rows):
        if progress and (i % 100 == 0 or i == total - 1):
            progress(f"  后台匹配进度: {i + 1}/{total} ({(i + 1) * 100 // total}%)")

        cat = str(row.get("类型", ""))
        brand = str(row.get("品牌", ""))
        model = str(row.get("机型", ""))
        model_norm = _norm(model)

        row.setdefault("后台匹配", "未匹配")

        if not model_norm or model_norm == "nan":
            continue

        brand_variants = BRAND_EXPAND.get(brand, [brand])
        result = None

        # 在品牌变体中查找
        for bv in brand_variants:
            entries = index.get((cat, bv))
            if not entries:
                continue
            result = _find_best_match(model_norm, entries)
            if result:
                break

        # 跨分类回退
        if not result:
            for bv in brand_variants:
                for key, entries in index.items():
                    if key[1] != bv:
                        continue
                    for an, d in entries:
                        if model_norm == an:
                            result = d
                            break
                    if result:
                        break
                if result:
                    break

        if result:
            matched += 1
            row["后台匹配"] = "已匹配"
            # 写入SKU价格列
            sku_names = result.get("SKU列名", [])
            for j, sku in enumerate(sku_names[:6]):
                row[f"SKU{j + 1}名称"] = sku
                row[f"SKU{j + 1}价格"] = result.get(sku, "")
            row["后台备注"] = result.get("备注", "")
            row["后台分类"] = result.get("分类", "")

    return rows, matched
