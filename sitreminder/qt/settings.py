"""Qt6 设置窗口：间隔（分钟/秒切换）、开机自启、暂停/跳过/保存。"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QHBoxLayout, QVBoxLayout, QMessageBox, QGroupBox,
)

from ..config import MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS

log = logging.getLogger(__name__)

MINUTES_MIN, MINUTES_MAX = 1, 600


class SettingsWindow(QWidget):
    saved = Signal(int, bool)   # (interval_seconds, autostart)

    def __init__(self, ctrl, cfg):
        super().__init__()
        self.ctrl = ctrl
        self.setWindowTitle("设置 · 久坐提醒")
        # 显式声明为带「关闭按钮」的顶层窗口。
        # 之前只做 windowFlags() & ~WindowStaysOnTopHint，结果初始 flags 恰好缺
        # WindowCloseButtonHint → Windows 标题栏右上角 X 变灰不可点，无法关闭。
        # 这里明确给齐 标题/系统菜单/最小化/关闭 四个按钮位（定宽窗不需要最大化）。
        self.setWindowFlags(
            Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFixedWidth(300)

        seconds = int(cfg["interval_seconds"])
        use_min = seconds % 60 == 0 and seconds >= 60
        self._unit_min = use_min

        # ---- 间隔行
        group = QGroupBox("提醒间隔")
        lay = QHBoxLayout(group)
        self._val = QLineEdit()
        self._val.setFixedWidth(64)
        self._val.setAlignment(Qt.AlignCenter)
        self._val.setText(str(seconds // 60 if use_min else seconds))
        self._unit = QComboBox()
        self._unit.addItems(["分钟", "秒"])
        self._unit.setCurrentIndex(0 if use_min else 1)
        self._unit.currentIndexChanged.connect(self._unit_changed)
        lay.addWidget(self._val)
        lay.addWidget(self._unit)
        lay.addStretch(1)

        # ---- 自启
        self._auto = QCheckBox("开机自动启动")

        # ---- 操作行
        ops = QHBoxLayout()
        b_pause = QPushButton("暂停/继续")
        b_pause.clicked.connect(self.ctrl.toggle_pause)
        b_skip = QPushButton("跳过本次")
        b_skip.clicked.connect(self.ctrl.on_skip)
        b_save = QPushButton("保存")
        b_save.clicked.connect(self._on_save)
        b_save.setDefault(True)
        ops.addWidget(b_pause)
        ops.addWidget(b_skip)
        ops.addStretch(1)
        ops.addWidget(b_save)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.addWidget(group)
        root.addWidget(self._auto)
        root.addLayout(ops)

        self._unit_changed()

    def _unit_changed(self):
        """切单位时尽量换算当前值，方便连续调整。"""
        if not hasattr(self, "_unit"):
            return
        cur = self._current_value()
        is_min = self._unit.currentIndex() == 0
        self._unit_min = is_min
        if cur is not None:
            if is_min:
                self._val.setText(str(max(1, cur // 60)))
            else:
                self._val.setText(str(cur * 60))

    def _current_value(self):
        try:
            return int(self._val.text().strip())
        except ValueError:
            return None

    def _on_save(self):
        v = self._current_value()
        if v is None:
            self._err(f"请输入整数，当前输入不合法")
            return
        if self._unit_min:
            if not (MINUTES_MIN <= v <= MINUTES_MAX):
                self._err(f"请输入 {MINUTES_MIN}-{MINUTES_MAX} 之间的整数分钟")
                return
            seconds = v * 60
        else:
            if not (MIN_INTERVAL_SECONDS <= v <= MAX_INTERVAL_SECONDS):
                self._err(f"请输入 {MIN_INTERVAL_SECONDS}-{MAX_INTERVAL_SECONDS} 之间的整数秒")
                return
            seconds = v
        self.saved.emit(seconds, self._auto.isChecked())
        self.close()

    def _err(self, msg: str):
        QMessageBox.warning(self, "输入错误", msg)

    def show_right_of(self, ref):
        """置于妮子浮窗右侧、垂直居中，并保证不超出屏幕。"""
        ref_geo = ref.window().frameGeometry()
        scr = ref.window().screen()
        if scr is None:
            scr = self.screen()
        avail = scr.availableGeometry()

        # 布局已建好，先按内容算出尺寸再定位
        self.adjustSize()
        w, h = self.width(), self.height()

        # 默认放右侧
        x = ref_geo.right() + 12
        y = ref_geo.center().y() - h // 2
        # 右侧放不下就放左侧
        if x + w > avail.right():
            x = ref_geo.left() - 12 - w
        # 若仍超出屏幕，退回屏幕内
        x = max(avail.left(), min(x, avail.right() - w))
        y = max(avail.top(), min(y, avail.bottom() - h))
        self.move(x, y)
        self.show()
