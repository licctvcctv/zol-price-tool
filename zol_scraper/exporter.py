"""导出结果到 Excel"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from .types import MatchedRow


def export_excel(rows: List[MatchedRow], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_excel(str(output_path), index=False, engine="xlsxwriter")
    return output_path
