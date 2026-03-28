"""后台工作线程 — QThread + pyqtSignal"""
from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from .service import run_pipeline, RunResult


class ScrapeWorker(QThread):
    """登录后台 + 抓取报价 + 小程序匹配 + 导出"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # RunResult
    error = pyqtSignal(str)

    def __init__(
        self, excel_path: str, output_dir: str,
        username: str = "不貮二手数码",
        password: str = "不貮二手数码",
        threads: int = 5,
        scrape_xcx: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._excel_path = excel_path
        self._output_dir = output_dir
        self._username = username
        self._password = password
        self._threads = threads
        self._scrape_xcx = scrape_xcx

    def run(self):
        try:
            result = run_pipeline(
                excel_path=self._excel_path,
                output_dir=self._output_dir,
                username=self._username,
                password=self._password,
                threads=self._threads,
                scrape_xcx=self._scrape_xcx,
                progress=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
