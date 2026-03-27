"""后台报价匹配引擎 — 将 Excel 行与后台报价数据匹配"""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple


# Excel品牌 → 后台可能的品牌列表（扩大搜索范围）
BRAND_EXPAND: dict[str, list[str]] = {
    "苹果": ["苹果", "苹果有保", "苹果无保"],
    "华为": ["华为", "华为OK板", "华为旗舰"],
    "华为旗舰": ["华为旗舰", "华为", "华为OK板"],
    "华为OK板": ["华为OK板", "华为", "华为旗舰"],
    "荣耀": ["荣耀", "荣耀其他"],
    "荣耀其他": ["荣耀其他", "荣耀"],
    "锤子坚果": ["锤子坚果", "锤子"],
    "锤子": ["锤子", "锤子坚果"],
    "红米、黑鲨": ["红米、黑鲨", "小米"],
    "小米": ["小米", "红米、黑鲨"],
    "VIVO": ["VIVO", "iQOO"],
    "iQOO": ["iQOO", "VIVO"],
    "OPPO": ["OPPO", "一加", "真我/realme"],
    "一加": ["一加", "OPPO"],
    "真我/realme": ["真我/realme", "OPPO"],
    "华为随身4Gwifi": ["随身4Gwifi", "华为"],
    "家教机": ["品牌学习机"],
    "苹果平板": ["苹果平板", "苹果"],
    "华为平板": ["华为平板", "华为"],
    "三星平板": ["三星平板", "三星"],
    "荣耀平板": ["荣耀平板", "荣耀"],
    "小米平板": ["小米平板", "小米", "小米/红米 平板"],
    "小米/红米 平板": ["小米/红米 平板", "小米平板", "小米"],
    "联想平板": ["联想平板", "联想"],
    "苹果手表": ["苹果手表", "苹果"],
    "华为手表": ["华为手表", "华为"],
    "小米手表": ["小米手表", "小米"],
    "MP3、MP4": ["ipod系列", "索尼cd"],
    "海康录像机": ["海康威视摄像头"],
}

# 清洗型号名时要去掉的内容
_RE_5G4G = re.compile(r"[54]g$")
_RE_PAREN_MEM = re.compile(r"\(\d+\+\d+\)")  # (12+256)
_RE_PAREN_ANY = re.compile(r"\([^)]*\)")  # 任意括号内容
_RE_SUFFIX_VER = re.compile(r"(冠军版|至尊版|典藏版|特别版|纪念版|活力版|高能版|标配版|星耀版|卫星[^\s]*版|北斗[^\s]*版|艺术定制版|徕卡版)")


@lru_cache(maxsize=8192)
def _norm(s: str) -> str:
    """归一化名称用于匹配"""
    s = str(s).lower().replace(" ", "").replace("-", "").replace("_", "").strip()
    s = _RE_5G4G.sub("", s)
    return s


@lru_cache(maxsize=8192)
def _norm_deep(s: str) -> str:
    """深度清洗：去掉括号内存配置、版本后缀等"""
    s = _norm(s)
    s = _RE_PAREN_MEM.sub("", s)  # (12+256) -> ""
    s = _RE_SUFFIX_VER.sub("", s)
    return s.strip()


def build_admin_index(
    admin_prices: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], List[Tuple[str, str, Dict]]]:
    """构建后台报价索引: (顶级分类, 品牌) -> [(norm, norm_deep, 原始数据), ...]"""
    index: Dict[Tuple[str, str], List[Tuple[str, str, Dict]]] = defaultdict(list)
    for d in admin_prices:
        key = (d["顶级分类"], d["品牌"])
        n = _norm(d["分类"])
        nd = _norm_deep(d["分类"])
        index[key].append((n, nd, d))
    return dict(index)


def _find_best_match(
    model_norm: str,
    model_deep: str,
    entries: List[Tuple[str, str, Dict]],
) -> Optional[Dict]:
    """在候选列表中找最佳匹配"""
    if not model_norm:
        return None

    # 1. 精确匹配（norm）
    for an, and_, d in entries:
        if model_norm == an:
            return d

    # 2. 精确匹配（deep norm）
    for an, and_, d in entries:
        if model_deep == and_ and model_deep:
            return d

    # 3. 子串匹配 — 取最高分
    best = None
    best_score = 0.0
    for an, and_, d in entries:
        if not an:
            continue
        # 用 deep norm 做子串比较
        mn = model_deep or model_norm
        an_cmp = and_ or an
        if mn in an_cmp:
            score = len(mn) / len(an_cmp)
        elif an_cmp in mn:
            score = len(an_cmp) / len(mn)
        else:
            # 再试 norm
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
        model_deep = _norm_deep(model)

        row.setdefault("后台匹配", "未匹配")

        if not model_norm or model_norm == "nan":
            continue

        brand_variants = BRAND_EXPAND.get(brand, [brand])
        result = None

        # 1. 在品牌变体中查找（同分类）
        for bv in brand_variants:
            entries = index.get((cat, bv))
            if not entries:
                continue
            result = _find_best_match(model_norm, model_deep, entries)
            if result:
                break

        # 2. 跨分类搜索（同品牌变体）
        if not result:
            for bv in brand_variants:
                for key, entries in index.items():
                    if key[1] != bv:
                        continue
                    result = _find_best_match(model_norm, model_deep, entries)
                    if result:
                        break
                if result:
                    break

        if result:
            matched += 1
            row["后台匹配"] = "已匹配"
            sku_names = result.get("SKU列名", [])
            for j, sku in enumerate(sku_names[:6]):
                row[f"SKU{j + 1}名称"] = sku
                row[f"SKU{j + 1}价格"] = result.get(sku, "")
            row["后台备注"] = result.get("备注", "")
            row["后台分类"] = result.get("分类", "")

    return rows, matched
