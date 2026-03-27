"""型号匹配引擎 — 将 Excel 机型与 ZOL 产品匹配（主图数据库版）"""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from typing import Any, Callable, List, Optional

import pandas as pd

from .types import MatchedRow, MatchResult, Product

# ── 品牌名映射 ───────────────────────────────────────────
BRAND_MAP: dict[str, list[str]] = {
    "苹果": ["苹果", "APPLE", "IPHONE"],
    "华为": ["HUAWEI", "华为"], "华为旗舰": ["HUAWEI", "华为"],
    "小米": ["小米", "XIAOMI", "MI"], "红米、黑鲨": ["REDMI", "红米", "黑鲨"],
    "VIVO": ["VIVO"], "OPPO": ["OPPO"], "iQOO": ["IQOO"],
    "荣耀": ["荣耀", "HONOR"], "荣耀其他": ["荣耀", "HONOR"],
    "一加": ["一加", "ONEPLUS"], "三星": ["三星", "SAMSUNG", "GALAXY"],
    "真我/realme": ["REALME", "真我"], "魅族": ["魅族", "MEIZU"],
    "努比亚": ["努比亚", "NUBIA"], "联想": ["联想", "LENOVO"],
    "摩托罗拉": ["摩托罗拉", "MOTOROLA", "MOTO"],
    "锤子坚果": ["坚果", "锤子", "SMARTISAN"],
    "华硕": ["华硕", "ASUS", "ROG"],
    "索尼": ["索尼", "SONY", "XPERIA"],
    "谷歌Google": ["GOOGLE", "PIXEL"],
}

# 反向索引：品牌关键词 → Excel品牌名列表
_BRAND_KEYWORDS: dict[str, list[str]] = {}
for _brand, _keys in BRAND_MAP.items():
    for _k in _keys:
        _BRAND_KEYWORDS.setdefault(_k.upper(), []).append(_brand)

_SUFFIX_RE = re.compile(r"\b(PRO|MAX|PLUS|MINI|ULTRA|LITE|SE|NOTE|AIR|FLIP|FOLD|POCKET|TURBO)\b")

# 预编译所有 _clean 中使用的正则，避免每次调用时编译
_RE_XG = re.compile(r"\s*[54]G\b")
_RE_MEM_PAREN = re.compile(r"\([^)]*\d+[GT]B[^)]*\)")
_RE_MEM_PAREN2 = re.compile(r"\(\d+[GT]B\)")
_RE_SUFFIX_NAMES = re.compile(r"(钛金属特别版|特别版|典藏版|至臻版|艺术版|先锋版|纪念版|卫星[^\s]*版|北斗[^\s]*版|活力版|乐活版|高配版|标配版|星耀版)")
_RE_D_A = re.compile(r"(\d)([A-Z])")
_RE_A_D = re.compile(r"([A-Z])(\d)")
_RE_CN_AN = re.compile(r"([\u4e00-\u9fff])([A-Z0-9])")
_RE_AN_CN = re.compile(r"([A-Z0-9])([\u4e00-\u9fff])")
_RE_IPHONE_APPLE = re.compile(r"^IPHONE\s*苹果")
_RE_NP = re.compile(r"\b(\d+)\s*P\b(?!\w)")
_RE_NDAI = re.compile(r"\b(\d+)代\b")
_RE_SE3 = re.compile(r"SE\s*（第三代）")
_RE_SE2 = re.compile(r"SE\s*（第二代）")
_RE_SEN = re.compile(r"SE(\d)")
_RE_EMPTY_PAREN = re.compile(r"\(\s*\)")
_RE_MULTI_SPACE = re.compile(r"\s+")
_RE_MEM_CONFIG = re.compile(r"\(?\d+GB/\d+[GT]B\)?")


@lru_cache(maxsize=8192)
def _clean(name: str) -> str:
    """深度清洗名称，最大化匹配率（带缓存）"""
    if not name:
        return ""
    name = str(name).strip().upper()
    name = name.replace("（", "(").replace("）", ")")
    name = _RE_XG.sub("", name)
    name = _RE_MEM_PAREN.sub("", name)
    name = _RE_MEM_PAREN2.sub("", name)
    name = _RE_SUFFIX_NAMES.sub("", name)
    name = _RE_D_A.sub(r"\1 \2", name)
    name = _RE_A_D.sub(r"\1 \2", name)
    name = _RE_CN_AN.sub(r"\1 \2", name)
    name = _RE_AN_CN.sub(r"\1 \2", name)
    name = name.replace("UITRA", "ULTRA").replace("UITER", "ULTRA")
    name = name.replace("FIIP", "FLIP").replace("FIP", "FLIP")
    name = name.replace("钦金属", "钛金属")
    name = _RE_IPHONE_APPLE.sub("IPHONE ", name)
    name = name.replace("苹果X", "X").replace("苹果", "")
    name = _RE_NP.sub(r"\1 PLUS", name)
    name = _RE_NDAI.sub(r"\1", name)
    name = _RE_SE3.sub("SE 3", name)
    name = _RE_SE2.sub("SE 2", name)
    name = _RE_SEN.sub(r"SE \1", name)
    name = _RE_EMPTY_PAREN.sub("", name)
    name = _RE_MULTI_SPACE.sub(" ", name)
    return name.strip()


@lru_cache(maxsize=8192)
def _extract_core(name: str) -> str:
    """提取ZOL名称的核心型号（带缓存）"""
    name = _clean(name)
    name = _RE_MEM_CONFIG.sub("", name)
    return name.strip()


def _safe_price(x: Product) -> int:
    try:
        return int(x.get("ZOL报价", ""))
    except (ValueError, TypeError):
        return 999999


@lru_cache(maxsize=8192)
def _tokens(s: str) -> tuple[str, ...]:
    """把名称拆成token元组（hashable 以支持缓存）"""
    return tuple(t for t in s.split() if len(t) >= 1)


def _token_match_score(excel_tokens: tuple[str, ...], zol_tokens: tuple[str, ...]) -> float:
    """计算token匹配分数 (0-1) — 用集合加速"""
    if not excel_tokens:
        return 0
    # 先做精确集合交集（O(n+m)）
    zol_set = set(zol_tokens)
    matched = 0
    for et in excel_tokens:
        if et in zol_set:
            matched += 1
        else:
            # 子串匹配回退（仅未精确命中时）
            for zt in zol_tokens:
                if et in zt or zt in et:
                    matched += 1
                    break
    return matched / len(excel_tokens)


def _is_exact_suffix_match(excel_clean: str, zol_core: str) -> bool:
    """检查是否精确匹配（型号后缀一致）"""
    if excel_clean in zol_core:
        remaining = zol_core.replace(excel_clean, "").strip()
        if not remaining:
            return True
        if _SUFFIX_RE.search(remaining):
            return False
        return True
    return False


def _detect_zol_brands(clean_name: str) -> set[str]:
    """从清洗后的ZOL名称中检测它属于哪些Excel品牌"""
    brands = set()
    for kw, brand_list in _BRAND_KEYWORDS.items():
        if kw in clean_name:
            brands.update(brand_list)
    return brands


def match_products(
    excel_df: pd.DataFrame,
    zol_products: List[Product],
    progress: Any = None,
    on_row: Optional[Callable[[MatchedRow], None]] = None,
) -> MatchResult:
    """多策略匹配：精确 → token → 模糊，按品牌分组加速"""

    # 预计算：清洗名称、core、tokens，按品牌分组索引
    # 使用 tuple 而非 list 减少内存开销
    brand_index: dict[str, list[tuple]] = defaultdict(list)
    all_entries: list[tuple] = []

    for p in zol_products:
        raw = p.get("名称", "")
        core = _extract_core(raw)  # _extract_core 内部会调用 _clean，都有缓存
        clean = _clean(raw)
        tokens = _tokens(core)
        entry = (clean, core, tokens, p)
        all_entries.append(entry)
        detected = _detect_zol_brands(clean)
        for b in detected:
            brand_index[b].append(entry)

    matched = 0
    rows: list[MatchedRow] = []
    total = len(excel_df)

    # 使用 itertuples 替代 iterrows，性能提升约 10 倍
    brand_col = excel_df.columns.get_loc("品牌") if "品牌" in excel_df.columns else -1
    model_col = excel_df.columns.get_loc("机型") if "机型" in excel_df.columns else -1

    for i, tup in enumerate(excel_df.itertuples(index=False)):
        if progress and (i % 50 == 0 or i == total - 1):
            progress(f"  匹配进度: {i + 1}/{total} ({(i + 1) * 100 // total}%)")

        brand = str(tup[brand_col]) if brand_col >= 0 else ""
        model = str(tup[model_col]) if model_col >= 0 else ""

        result: MatchedRow = {col: getattr(tup, col, "") for col in excel_df.columns}
        result["ZOL报价"] = ""
        result["ZOL图片"] = ""
        result["ZOL链接"] = ""
        result["匹配状态"] = "未匹配"

        if not model or model == "nan":
            rows.append(result)
            if on_row:
                on_row(result)
            continue

        excel_clean = _clean(model)
        excel_tokens = _tokens(excel_clean)

        # 用品牌索引缩小搜索范围
        candidates = brand_index.get(brand, all_entries) if brand and brand != "nan" else all_entries

        best: Optional[Product] = None
        best_score = 0.0

        for zol_clean, zol_core, zol_tokens, zol_prod in candidates:
            # 策略1: 精确子串匹配
            if _is_exact_suffix_match(excel_clean, zol_core):
                best = zol_prod
                break  # 精确匹配直接跳出

            # 策略2: token 匹配
            score = _token_match_score(excel_tokens, zol_tokens)
            if score > 0.5:
                reverse_score = _token_match_score(zol_tokens, excel_tokens)
                score = (score + reverse_score) / 2

            if score > best_score and score >= 0.6:
                best_score = score
                best = zol_prod

        if best:
            result["ZOL图片"] = best.get("图片URL", "")
            result["ZOL链接"] = best.get("详情链接", "")
            result["ZOL报价"] = best.get("ZOL报价", "")
            result["匹配状态"] = "已匹配"
            matched += 1

        rows.append(result)
        if on_row:
            on_row(result)

    return MatchResult(total_excel=len(excel_df), matched_count=matched, rows=rows)
