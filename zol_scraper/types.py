from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

Product = Dict[str, Any]
MatchedRow = Dict[str, Any]


@dataclass(frozen=True)
class ScrapeResult:
    products: List[Product]
    pages_fetched: int
    total_pages: int
    is_complete: bool


@dataclass(frozen=True)
class MatchResult:
    total_excel: int
    matched_count: int
    rows: List[MatchedRow]


@dataclass(frozen=True)
class OutputPaths:
    excel_path: Path
    image_dir: Path
