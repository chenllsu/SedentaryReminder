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
from ..quips import DEFAULT_STYLE, STYLES

log = logging.getLogger(__name__)

MINUTES_MIN, MINUTES_MAX = 1, 600


class SettingsWindow(QWidget):
    saved = Signal(int, bool, bool, str)   # (interval_seconds, autostart, capsule_always, quip_style)
    closed = Signal()           # 窗口关闭（点「保存」或点右上角 X 都算）

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
        # 必须回显当前配置：原先建了复选框却没 setChecked，
        # 于是每次打开设置窗都显示「未勾选」——配置里明明开着，界面却像关着，
        # 用户无法判断真实状态；点一下保存还会把已开的自启写成关闭。
        self._auto = QCheckBox("开机自动启动")
        self._auto.setChecked(bool(cfg.get("autostart", False)))

        # ---- 倒计时贴纸显示模式
        self._capsule = QCheckBox("倒计时始终显示")
        self._capsule.setChecked(bool(cfg.get("capsule_always_visible", True)))
        self._capsule.setToolTip("勾选：贴纸常驻（平时淡显，悬停变清晰）\n"
                                 "不勾：平时隐藏，鼠标悬停或暂停时才出现")

        # ---- 话术风格
        # 龙哥 2026-09-11 需求：妮子支持 5 类性格话术（傲娇/温柔/呆萌/冷漠/可爱），
        # 外加「默认」（原 10 条，未设置时用它）与「随机」（每次全池抽）。
        # 随「保存」生效：与间隔/自启等一致，选了不点保存就不算数。
        style_row = QHBoxLayout()
        style_label = QLabel("话术风格")
        self._style = QComboBox()
        self._style.addItems(STYLES)
        self._style.setCurrentText(str(cfg.get("quip_style") or DEFAULT_STYLE))
        style_row.addWidget(style_label)
        style_row.addWidget(self._style)
        style_row.addStretch(1)

        # ---- 操作行
        # 「暂停/继续」按钮的文字必须反映真实状态：打开设置时倒计时已被冻结，
        # 所以这里会显示「继续计时」。若不显示状态，用户看不到当前是停是跑，
        # 随手一点就把冻结解掉了。
        # 点击走 toggle_pause_from_settings()，让控制器知道这是用户的显式操作，
        # 关窗时就不会被「未改设置则继续」的默认规则覆盖。
        ops = QHBoxLayout()
        self._btn_pause = QPushButton("暂停/继续")
        self._btn_pause.clicked.connect(self.ctrl.toggle_pause_from_settings)
        b_skip = QPushButton("跳过本次")
        b_skip.clicked.connect(self.ctrl.on_skip)
        b_save = QPushButton("保存")
        b_save.clicked.connect(self._on_save)
        b_save.setDefault(True)
        ops.addWidget(self._btn_pause)
        ops.addWidget(b_skip)
        ops.addStretch(1)
        ops.addWidget(b_save)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.addWidget(group)
        root.addLayout(style_row)
        root.addWidget(self._capsule)
        root.addWidget(self._auto)
        root.addLayout(ops)
        # ⚠️ 这里绝不能调 _unit_changed()：走到这一步 _val 里已经是「目标单位」
        # 的数值，再换算一次就等于算错 —— 5 分钟会被当成 5 分钟又 ÷60（=1 分钟），
        # 90 秒会被当成 90 分钟 ×60（=5400 秒）。该方法只应由单位切换信号触发。

    def _unit_changed(self):
        """切单位时输入框里的数字保持原样（龙哥 2026-09-11 指定）。

        只更新当前单位标记，数值不做任何换算——用户输入 5，
        分钟切秒、秒切分钟都仍是 5，具体含义由保存时按单位解释。
        """
        if not hasattr(self, "_unit"):
            return
        self._unit_min = self._unit.currentIndex() == 0

    def _current_value(self):
        try:
            return int(self._val.text().strip())
        except ValueError:
            return None

    def set_paused(self, paused: bool):
        """同步「暂停/继续」按钮文字（控制器在暂停状态变化时调用）。"""
        self._btn_pause.setText("继续计时" if paused else "暂停计时")

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
        self.saved.emit(seconds, self._auto.isChecked(),
                        self._capsule.isChecked(), self._style.currentText())
        self.close()

    def _err(self, msg: str):
        QMessageBox.warning(self, "输入错误", msg)

    def closeEvent(self, e):
        """关闭时通知控制器（无论点「保存」还是点 X）。

        控制器据此决定：从冻结处继续计时，还是已按新间隔重算过了。
        """
        super().closeEvent(e)
        self.closed.emit()

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
