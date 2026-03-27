"""后台工作线程 — QThread + pyqtSignal"""
from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from .service import run_pipeline, RunResult


class ScrapeWorker(QThread):
    """爬取 + 匹配 + 导出 + 下载图片"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # RunResult
    error = pyqtSignal(str)

    def __init__(
        self, excel_path: str, output_dir: str,
        total_pages: int = 91, threads_pages: int = 10,
        threads_images: int = 20, download_imgs: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._excel_path = excel_path
        self._output_dir = output_dir
        self._total_pages = total_pages
        self._threads_pages = threads_pages
        self._threads_images = threads_images
        self._download_imgs = download_imgs

    def run(self):
        try:
            result = run_pipeline(
                excel_path=self._excel_path,
                output_dir=self._output_dir,
                total_pages=self._total_pages,
                threads_pages=self._threads_pages,
                threads_images=self._threads_images,
                download_imgs=self._download_imgs,
                progress=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
