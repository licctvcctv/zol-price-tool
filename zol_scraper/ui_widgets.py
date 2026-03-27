"""UI 组件构建"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QLineEdit, QCheckBox, QTableWidget, QHeaderView,
    QGroupBox, QProgressBar, QSpinBox, QFileDialog,
)
from PyQt5.QtGui import QFont


def build_toolbar(win) -> QHBoxLayout:
    """顶部: Excel选择 + 开始按钮 + 进度条"""
    row = QHBoxLayout()

    # Excel 文件选择
    grp_file = QGroupBox("数据文件")
    gl = QHBoxLayout(grp_file)
    gl.setContentsMargins(10, 4, 10, 4)

    win.txt_excel = QLineEdit()
    win.txt_excel.setPlaceholderText("选择 Excel 文件 (.xls / .xlsx)")
    win.txt_excel.setMinimumWidth(300)
    gl.addWidget(win.txt_excel)

    btn_browse = QPushButton("选择")
    btn_browse.clicked.connect(win._on_browse_excel)
    gl.addWidget(btn_browse)
    row.addWidget(grp_file)

    row.addSpacing(10)

    # 开始按钮
    win.btn_scrape = QPushButton("  开始查询  ")
    win.btn_scrape.setFixedHeight(42)
    win.btn_scrape.setStyleSheet(
        "QPushButton{background:#174d43;color:#fff;font-size:15px;"
        "font-weight:bold;border-radius:5px;padding:0 28px;border:none}"
        "QPushButton:hover{background:#0f3e35}"
        "QPushButton:disabled{background:#ccc}"
    )
    win.btn_scrape.clicked.connect(win._on_start_scrape)
    row.addWidget(win.btn_scrape)

    # 进度条
    win.progress = QProgressBar()
    win.progress.setVisible(False)
    win.progress.setRange(0, 0)
    win.progress.setFixedWidth(140)
    row.addWidget(win.progress)

    row.addStretch()
    return row


def build_settings_bar(win) -> QHBoxLayout:
    """设置栏: 后台账号密码 + 线程数 + 选项"""
    row = QHBoxLayout()

    # 后台账号
    grp_account = QGroupBox("后台账号")
    al = QHBoxLayout(grp_account)
    al.setContentsMargins(10, 4, 10, 4)

    al.addWidget(QLabel("账号"))
    win.txt_username = QLineEdit()
    win.txt_username.setText("不貮二手数码")
    win.txt_username.setMinimumWidth(120)
    al.addWidget(win.txt_username)

    al.addSpacing(6)
    al.addWidget(QLabel("密码"))
    win.txt_password = QLineEdit()
    win.txt_password.setText("不貮二手数码")
    win.txt_password.setEchoMode(QLineEdit.Password)
    win.txt_password.setMinimumWidth(120)
    al.addWidget(win.txt_password)

    row.addWidget(grp_account)

    row.addSpacing(6)

    # 爬取设置
    grp = QGroupBox("设置")
    gl = QHBoxLayout(grp)
    gl.setContentsMargins(10, 4, 10, 4)

    gl.addWidget(QLabel("线程数"))
    win.spin_threads = QSpinBox()
    win.spin_threads.setRange(1, 20)
    win.spin_threads.setValue(10)
    gl.addWidget(win.spin_threads)

    gl.addSpacing(10)
    win.chk_xcx = QCheckBox("小程序回收价")
    win.chk_xcx.setChecked(True)
    gl.addWidget(win.chk_xcx)

    row.addWidget(grp)
    row.addStretch()

    # 操作按钮
    win.btn_clear_cache = QPushButton("清除缓存")
    win.btn_clear_cache.setStyleSheet("QPushButton{color:#999;border:1px solid #ddd;font-size:12px;}")
    win.btn_clear_cache.clicked.connect(win._on_clear_cache)
    row.addWidget(win.btn_clear_cache)

    win.btn_open_dir = QPushButton("打开输出目录")
    win.btn_open_dir.clicked.connect(win._on_open_output)
    row.addWidget(win.btn_open_dir)

    return row


def build_stats_bar(win) -> QHBoxLayout:
    """统计栏"""
    row = QHBoxLayout()
    s = "font-size:13px;padding:4px 12px;border-radius:3px;"

    win.lbl_admin_count = QLabel("后台报价: --")
    win.lbl_admin_count.setStyleSheet(s + "background:#e3f2fd;color:#1565c0;")
    row.addWidget(win.lbl_admin_count)

    win.lbl_excel_count = QLabel("Excel行数: --")
    win.lbl_excel_count.setStyleSheet(s + "background:#e8f5e9;color:#2e7d32;")
    row.addWidget(win.lbl_excel_count)

    win.lbl_admin_matched = QLabel("后台匹配: --")
    win.lbl_admin_matched.setStyleSheet(s + "background:#fff3e0;color:#e65100;font-weight:bold;")
    row.addWidget(win.lbl_admin_matched)

    win.lbl_xcx = QLabel("小程序匹配: --")
    win.lbl_xcx.setStyleSheet(s + "background:#e0f7fa;color:#00695c;font-weight:bold;")
    row.addWidget(win.lbl_xcx)

    win.lbl_showing = QLabel("显示: --")
    win.lbl_showing.setStyleSheet(s + "background:#f3e5f5;color:#6a1b9a;")
    row.addWidget(win.lbl_showing)

    row.addStretch()
    return row


def build_search_bar(win) -> QHBoxLayout:
    """搜索栏"""
    row = QHBoxLayout()
    row.addWidget(QLabel("搜索"))

    win.txt_search = QLineEdit()
    win.txt_search.setPlaceholderText("按品牌、机型、内存筛选...")
    win.txt_search.textChanged.connect(win._on_search)
    row.addWidget(win.txt_search)

    btn_clear = QPushButton("清空")
    btn_clear.clicked.connect(lambda: win.txt_search.clear())
    row.addWidget(btn_clear)

    row.addStretch()

    win.chk_matched_only = QCheckBox("仅看已匹配")
    win.chk_matched_only.stateChanged.connect(win._on_search)
    row.addWidget(win.chk_matched_only)

    return row


def build_table(win) -> QTableWidget:
    """结果表格"""
    win.table = QTableWidget()
    win.table.setColumnCount(8)
    win.table.setHorizontalHeaderLabels(
        ["序号", "类型", "品牌", "机型", "内存", "后台匹配", "小程序匹配", "后台对应"]
    )
    h = win.table.horizontalHeader()
    h.setSectionResizeMode(0, QHeaderView.Fixed)
    win.table.setColumnWidth(0, 50)
    h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
    h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
    h.setSectionResizeMode(3, QHeaderView.Stretch)
    h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
    h.setSectionResizeMode(5, QHeaderView.Fixed)
    win.table.setColumnWidth(5, 80)
    h.setSectionResizeMode(6, QHeaderView.Fixed)
    win.table.setColumnWidth(6, 90)
    h.setSectionResizeMode(7, QHeaderView.Stretch)

    win.table.setSelectionBehavior(QTableWidget.SelectRows)
    win.table.setEditTriggers(QTableWidget.NoEditTriggers)
    win.table.setAlternatingRowColors(True)
    return win.table


def build_log_area(win) -> QVBoxLayout:
    """日志区"""
    from PyQt5.QtWidgets import QTextEdit
    lay = QVBoxLayout()
    lbl = QLabel("运行日志")
    lbl.setStyleSheet("font-weight:bold;color:#555;")
    lay.addWidget(lbl)

    win.log_text = QTextEdit()
    win.log_text.setReadOnly(True)
    win.log_text.setMaximumHeight(180)
    win.log_text.setStyleSheet(
        "background:#1f1d1a;color:#efe8dc;font-family:'SF Mono','Consolas';"
        "font-size:12px;border:1px solid #ccc;border-radius:4px;"
    )
    lay.addWidget(win.log_text)
    return lay
