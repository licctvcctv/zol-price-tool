"""后台工作线程 — QThread + pyqtSignal"""
from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from .service import run_pipeline, RunResult

_BATCH_SIZE = 100  # 每积攒 N 行才推送一次，减少 Qt 信号开销


class ScrapeWorker(QThread):
    """爬取 + 匹配 + 导出 + 下载图片"""
    progress = pyqtSignal(str)
    rows_batch = pyqtSignal(list)  # 批量推送匹配行
    finished = pyqtSignal(object)  # RunResult
    error = pyqtSignal(str)

    def __init__(
        self, excel_path: str, output_dir: str,
        total_pages: int = 91, threads_pages: int = 10,
        threads_images: int = 20, download_imgs: bool = True,
        scrape_xcx: bool = True, parent=None,
    ):
        super().__init__(parent)
        self._excel_path = excel_path
        self._output_dir = output_dir
        self._total_pages = total_pages
        self._threads_pages = threads_pages
        self._threads_images = threads_images
        self._download_imgs = download_imgs
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
                total_pages=self._total_pages,
                threads_pages=self._threads_pages,
                threads_images=self._threads_images,
                download_imgs=self._download_imgs,
                scrape_xcx=self._scrape_xcx,
                progress=lambda msg: self.progress.emit(msg),
                on_row=self._on_row,
            )
            self._flush_batch()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
