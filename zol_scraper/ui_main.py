"""数码回收报价工具 - 主窗口"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QTableWidgetItem, QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from .constants import (
    APP_NAME, APP_VERSION, WINDOW_WIDTH, WINDOW_HEIGHT,
    load_config, save_config,
)
from .worker import ScrapeWorker
from .ui_widgets import (
    build_toolbar, build_settings_bar, build_stats_bar,
    build_search_bar, build_table, build_log_area,
)

_MATCHED_BG = QColor("#e8f5e9")
_UNMATCHED_BG = QColor("#ffffff")


def _row_to_vals(r_idx: int, row: dict) -> list[str]:
    return [
        str(r_idx + 1),
        str(row.get("品牌", "")),
        str(row.get("机型", "")),
        str(row.get("内存", "")),
        row.get("小程序匹配", ""),
        str(row.get("类型", "")),
    ]


def _row_bg(row: dict) -> QColor:
    if row.get("小程序匹配") == "已匹配":
        return _MATCHED_BG
    return _UNMATCHED_BG


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._all_rows = []
        self._filtered = []
        self._worker = None
        self._config = load_config()
        self._init_ui()
        self._apply_config()

    def _init_ui(self):
        c = QWidget()
        self.setCentralWidget(c)
        lay = QVBoxLayout(c)
        lay.setSpacing(6)
        lay.setContentsMargins(12, 10, 12, 10)

        lay.addLayout(build_toolbar(self))
        lay.addLayout(build_settings_bar(self))
        lay.addLayout(build_stats_bar(self))
        lay.addLayout(build_search_bar(self))
        lay.addWidget(build_table(self), 1)
        lay.addLayout(build_log_area(self))

        self.statusBar().showMessage("就绪 — 选择 Excel 文件后点击 [开始查询]")

    def _apply_config(self):
        cfg = self._config
        self.txt_excel.setText(str(cfg.get("excel_path", "")))
        self.txt_username.setText(str(cfg.get("username", "不貮二手数码")))
        self.txt_password.setText(str(cfg.get("password", "不貮二手数码")))
        self.spin_threads.setValue(int(cfg.get("threads", 5)))

    def _save_config(self):
        save_config({
            "excel_path": self.txt_excel.text().strip(),
            "output_dir": str(self._output_dir()),
            "username": self.txt_username.text().strip(),
            "password": self.txt_password.text().strip(),
            "threads": self.spin_threads.value(),
        })

    def _output_dir(self) -> Path:
        cfg_dir = self._config.get("output_dir", "")
        return Path(cfg_dir) if cfg_dir else Path(__file__).resolve().parent.parent / "output"

    # ── 文件选择 ─────────────────────────────────────────
    def _on_browse_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Excel 文件", "",
            "Excel (*.xls *.xlsx);;All (*)",
        )
        if path:
            self.txt_excel.setText(path)

    # ── 开始查询 ─────────────────────────────────────────
    def _on_start_scrape(self):
        excel = self.txt_excel.text().strip()
        if not excel or not os.path.exists(excel):
            QMessageBox.warning(self, "缺少文件", "请先选择 Excel 文件")
            return
        if self._worker and self._worker.isRunning():
            return

        self._save_config()
        out = self._output_dir()
        out.mkdir(parents=True, exist_ok=True)

        self.btn_scrape.setEnabled(False)
        self.btn_scrape.setText("查询中...")
        self.progress.setVisible(True)
        self.log_text.clear()
        self._add_log("[*] 开始查询，请稍等...")

        self._worker = ScrapeWorker(
            excel_path=excel,
            output_dir=str(out),
            username=self.txt_username.text().strip(),
            password=self.txt_password.text().strip(),
            threads=self.spin_threads.value(),
            scrape_xcx=self.chk_xcx.isChecked(),
        )
        self._worker.progress.connect(self._add_log)
        self._worker.rows_batch.connect(self._on_rows_batch)
        self._worker.finished.connect(self._on_scrape_done)
        self._worker.error.connect(self._on_scrape_error)
        self.table.setRowCount(0)
        self._all_rows = []
        self._worker.start()

    def _on_rows_batch(self, batch):
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        start = self.table.rowCount()
        self.table.setRowCount(start + len(batch))
        for idx, row in enumerate(batch):
            self._all_rows.append(row)
            r = start + idx
            bg = _row_bg(row)
            vals = _row_to_vals(r, row)
            for c, val in enumerate(vals):
                cell = QTableWidgetItem(val)
                cell.setBackground(bg)
                if c == 0:
                    cell.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, cell)
        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)

    def _on_scrape_done(self, result):
        self.progress.setVisible(False)
        self.btn_scrape.setEnabled(True)
        self.btn_scrape.setText("  开始查询  ")

        self._all_rows = result.rows

        # 更新统计
        self.lbl_admin_count.setText(f"后台报价: {result.admin_prices_count}")
        self.lbl_excel_count.setText(f"Excel行数: {result.total_excel}")
        self.lbl_xcx.setText(f"小程序匹配: {result.xcx_matched}/{result.total_excel}")

        pct = result.xcx_matched / result.total_excel * 100 if result.total_excel else 0
        self._add_log(f"[+] 完成! 小程序匹配 {result.xcx_matched}/{result.total_excel} ({pct:.1f}%)")
        self._add_log(f"[+] 结果: {result.output.excel_path}")
        self.statusBar().showMessage(
            f"完成: 后台 {result.admin_prices_count} 条报价, 小程序匹配 {result.xcx_matched}/{result.total_excel}"
        )

        self._on_search()

    def _on_scrape_error(self, msg):
        self.progress.setVisible(False)
        self.btn_scrape.setEnabled(True)
        self.btn_scrape.setText("  开始查询  ")
        self._add_log(f"[!] 错误: {msg}")
        QMessageBox.warning(self, "查询失败", msg)

    # ── 搜索/筛选 ────────────────────────────────────────
    def _on_search(self):
        keyword = self.txt_search.text().strip().lower()
        matched_only = self.chk_matched_only.isChecked()

        filtered = []
        for row in self._all_rows:
            if matched_only and row.get("小程序匹配") != "已匹配":
                continue
            if keyword:
                haystack = f"{row.get('品牌', '')} {row.get('机型', '')} {row.get('内存', '')}".lower()
                if keyword not in haystack:
                    continue
            filtered.append(row)

        self._filtered = filtered
        self._refresh_table()
        self.lbl_showing.setText(f"显示: {len(filtered)}")

    def _refresh_table(self):
        rows = self._filtered
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            bg = _row_bg(row)
            vals = _row_to_vals(r, row)
            for c, val in enumerate(vals):
                cell = QTableWidgetItem(val)
                cell.setBackground(bg)
                if c == 0:
                    cell.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, cell)
        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)

    # ── 缓存/目录 ────────────────────────────────────────
    def _on_clear_cache(self):
        out = self._output_dir()
        cleared = False
        for name in ["admin_prices_cache.json", "xcx_prices_cache.json"]:
            cache = out / name
            if cache.exists():
                cache.unlink()
                cleared = True
                self._add_log(f"[+] 已清除: {name}")
        if cleared:
            self.statusBar().showMessage("缓存已清除，下次将重新抓取")
        else:
            self._add_log("[*] 没有缓存文件")

    def _on_open_output(self):
        out = self._output_dir()
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(out)], check=False)

    # ── 日志 ─────────────────────────────────────────────
    def _add_log(self, msg: str):
        self.log_text.append(msg)
