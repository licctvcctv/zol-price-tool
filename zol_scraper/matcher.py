"""型号匹配引擎 — 将 Excel 机型与 ZOL 产品匹配（主图数据库版）"""
from __future__ import annotations

import re
from typing import Any, List, Optional

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

_SUFFIX_RE = re.compile(r"\b(PRO|MAX|PLUS|MINI|ULTRA|LITE|SE|NOTE|AIR|FLIP|FOLD|POCKET|TURBO)\b")


def _clean(name: str) -> str:
    """深度清洗名称，最大化匹配率"""
    if not name:
        return ""
    name = str(name).strip().upper()
    # 统一括号
    name = name.replace("（", "(").replace("）", ")")
    # 去掉 5G/4G 标记
    name = re.sub(r"\s*[54]G\b", "", name)
    # 去掉括号内的内存/存储信息
    name = re.sub(r"\([^)]*\d+[GT]B[^)]*\)", "", name)
    name = re.sub(r"\(\d+[GT]B\)", "", name)
    # 去掉「版」「版本」等后缀
    name = re.sub(r"(钛金属特别版|特别版|典藏版|至臻版|艺术版|先锋版|纪念版|卫星[^\s]*版|北斗[^\s]*版|活力版|乐活版|高配版|标配版|星耀版)", "", name)
    # 标准化空格：在字母和数字之间加空格 (如 小米15PRO -> 小米 15 PRO)
    name = re.sub(r"(\d)([A-Z])", r"\1 \2", name)
    name = re.sub(r"([A-Z])(\d)", r"\1 \2", name)
    # 中文和数字/字母之间加空格
    name = re.sub(r"([\u4e00-\u9fff])([A-Z0-9])", r"\1 \2", name)
    name = re.sub(r"([A-Z0-9])([\u4e00-\u9fff])", r"\1 \2", name)
    # 修复常见拼写错误
    name = name.replace("UITRA", "ULTRA").replace("UITER", "ULTRA")
    name = name.replace("FIIP", "FLIP").replace("FIP", "FLIP")
    name = name.replace("钦金属", "钛金属")
    # 去掉 「苹果」前缀 (Excel 里 品牌=苹果, 机型=iPhone 苹果X)
    name = re.sub(r"^IPHONE\s*苹果", "IPHONE ", name)
    name = name.replace("苹果X", "X").replace("苹果", "")
    # 数字代简称: 8P -> 8 PLUS, 7P -> 7 PLUS (仅单独出现时)
    name = re.sub(r"\b(\d+)\s*P\b(?!\w)", r"\1 PLUS", name)
    # 8代 -> 8
    name = re.sub(r"\b(\d+)代\b", r"\1", name)
    # SE3 -> SE 3, SE（第三代）-> SE 3
    name = re.sub(r"SE\s*（第三代）", "SE 3", name)
    name = re.sub(r"SE\s*（第二代）", "SE 2", name)
    name = re.sub(r"SE(\d)", r"SE \1", name)
    # 清理残留空括号
    name = re.sub(r"\(\s*\)", "", name)
    # 压缩空格
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _extract_core(name: str) -> str:
    """提取ZOL名称的核心型号"""
    name = _clean(name)
    # 去掉内存配置 (12GB/256GB) 等
    name = re.sub(r"\(\d+GB/\d+[GT]B\)", "", name)
    name = re.sub(r"\d+GB/\d+[GT]B", "", name)
    return name.strip()


def _safe_price(x: Product) -> int:
    try:
        return int(x.get("ZOL报价", ""))
    except (ValueError, TypeError):
        return 999999


def _tokens(s: str) -> list[str]:
    """把名称拆成token列表"""
    return [t for t in s.split() if len(t) >= 1]


def _token_match_score(excel_tokens: list[str], zol_tokens: list[str]) -> float:
    """计算token匹配分数 (0-1)"""
    if not excel_tokens:
        return 0
    matched = 0
    for et in excel_tokens:
        for zt in zol_tokens:
            if et == zt or et in zt or zt in et:
                matched += 1
                break
    return matched / len(excel_tokens)


def _is_exact_suffix_match(excel_clean: str, zol_core: str) -> bool:
    """检查是否精确匹配（型号后缀一致）"""
    # 如果 excel 是 zol 的子串，检查剩余部分不含型号后缀
    if excel_clean in zol_core:
        remaining = zol_core.replace(excel_clean, "").strip()
        if not remaining:
            return True
        # 如果剩余部分有型号后缀词，说明不是同一型号
        if _SUFFIX_RE.search(remaining):
            return False
        return True
    return False


def match_products(
    excel_df: pd.DataFrame,
    zol_products: List[Product],
) -> MatchResult:
    """多策略匹配：精确 → token → 模糊"""

    # 构建索引（用清洗后的名称）
    zol_clean_index: list[tuple[str, str, Product]] = []  # (clean, core, product)
    for p in zol_products:
        raw = p.get("名称", "")
        clean = _clean(raw)
        core = _extract_core(raw)
        zol_clean_index.append((clean, core, p))

    matched = 0
    rows: list[MatchedRow] = []

    for _, row in excel_df.iterrows():
        brand = str(row.get("品牌", ""))
        model = str(row.get("机型", ""))

        result: MatchedRow = row.to_dict()
        result["ZOL报价"] = ""
        result["ZOL图片"] = ""
        result["ZOL链接"] = ""
        result["匹配状态"] = "未匹配"

        if not model or model == "nan":
            rows.append(result)
            continue

        excel_clean = _clean(model)
        excel_tokens = _tokens(excel_clean)
        brand_prefixes = BRAND_MAP.get(brand, [])

        best: Optional[Product] = None
        best_score = 0.0

        for zol_clean, zol_core, zol_prod in zol_clean_index:
            # 品牌过滤
            if brand_prefixes:
                zol_name_upper = _clean(zol_prod.get("名称", ""))
                if not any(p.upper() in zol_name_upper for p in brand_prefixes):
                    continue

            zol_tokens = _tokens(zol_core)

            # 策略1: 精确子串匹配（最高优先级）
            if _is_exact_suffix_match(excel_clean, zol_core):
                score = 2.0  # 最高分
            # 策略2: token 匹配
            else:
                score = _token_match_score(excel_tokens, zol_tokens)
                # 还要反向检查：ZOL的关键token是否也在Excel里
                if score > 0.5:
                    reverse_score = _token_match_score(zol_tokens, excel_tokens)
                    # 双向匹配取平均，防止短名称误匹配长名称
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

    return MatchResult(total_excel=len(excel_df), matched_count=matched, rows=rows)
