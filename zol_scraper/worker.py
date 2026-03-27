"""后台工作线程 — QThread + pyqtSignal"""
from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from .service import run_pipeline, RunResult

_BATCH_SIZE = 100  # 每积攒 N 行才推送一次，减少 Qt 信号开销


class ScrapeWorker(QThread):
    """登录后台 + 抓取报价 + 小程序匹配 + 导出"""
    progress = pyqtSignal(str)
    rows_batch = pyqtSignal(list)
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
        self._batch: list[dict] = []

    def _on_row(self, row: dict):
        self._batch.append(row)
        if len(self._batch) >= _BATCH_SIZE:
            self.rows_batch.emit(self._batch)
            self._batch = []

    def _flush_batch(self):
        if self._batch:
            self.rows_batch.emit(self._batch)
            self._batch = []

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
                on_row=self._on_row,
            )
            self._flush_batch()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
