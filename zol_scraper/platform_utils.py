"""跨平台系统工具。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_directory(path: Path | str) -> None:
    target = Path(path)
    if sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(target)], check=False)
        return
    subprocess.run(["xdg-open", str(target)], check=False)
