#!/usr/bin/env python3
"""ZOL 手机报价爬虫 - 程序入口"""

import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont, QPalette, QColor
from zol_scraper.constants import APP_NAME
from zol_scraper.ui_main import MainWindow

os.environ["QT_MAC_WANTS_LAYER"] = "1"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    # 浅色调色板
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#f0f2f5"))
    p.setColor(QPalette.WindowText, QColor("#1a1a1a"))
    p.setColor(QPalette.Base, QColor("#ffffff"))
    p.setColor(QPalette.Text, QColor("#1a1a1a"))
    p.setColor(QPalette.Button, QColor("#ffffff"))
    p.setColor(QPalette.ButtonText, QColor("#1a1a1a"))
    p.setColor(QPalette.Highlight, QColor("#174d43"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(p)

    font = QFont()
    font.setFamilies(["PingFang SC", "Microsoft YaHei", "SimHei"])
    font.setPointSize(12)
    app.setFont(font)

    app.setStyleSheet("""
        QMainWindow { background: #f0f2f5; }
        QLabel { color: #1a1a1a; font-size: 13px; }
        QGroupBox {
            color: #333; font-weight: bold; font-size: 13px;
            border: 1px solid #bbb; border-radius: 5px;
            margin-top: 8px; padding: 16px 8px 6px 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; left: 10px; padding: 0 6px;
        }
        QLineEdit, QSpinBox {
            color: #222; background: white;
            border: 1px solid #bbb; border-radius: 3px;
            padding: 4px 8px;
        }
        QCheckBox { color: #222; font-size: 13px; spacing: 6px; }
        QTableWidget {
            color: #222; background: white;
            gridline-color: #e0e0e0; font-size: 13px;
            border: 1px solid #ccc; border-radius: 4px;
        }
        QHeaderView::section {
            background: #174d43; color: white;
            padding: 7px; border: none;
            font-size: 13px; font-weight: bold;
        }
        QPushButton {
            color: #333; padding: 6px 16px;
            border: 1px solid #bbb; border-radius: 4px;
            background: white; font-size: 13px;
        }
        QPushButton:hover { background: #e8e8e8; }
        QPushButton:disabled { color: #999; background: #eee; }
        QStatusBar {
            color: #444; font-size: 12px;
            border-top: 1px solid #ddd;
        }
        QProgressBar {
            border: 1px solid #ccc; border-radius: 3px;
            text-align: center; max-height: 18px;
        }
        QProgressBar::chunk { background: #174d43; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
