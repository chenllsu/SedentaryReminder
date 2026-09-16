"""Qt6 设置窗口：间隔（分钟/秒切换 + 快捷值）、话术风格、妮子大小、
贴纸常驻、开机自启、暂停超时自动继续、免打扰时段、暂停/跳过/保存。

v1.2 改造（体验优化）：
  - 间隔组里加一排快捷值按钮（15/30/45/60 分钟），省得手打数字
  - 新增「妮子大小」三档、暂停超时自动继续、免打扰时段三组开关
  - saved 信号由「一长串位置参数」改为 Signal(dict)：字段还在增加，
    位置参数每加一个就要改三处签名，字典更不容易漏传/传错。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal, QTime
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, QSpinBox,
    QTimeEdit, QHBoxLayout, QVBoxLayout, QMessageBox, QGroupBox,
)

from .. import quiet
from ..config import (
    MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS,
    MASCOT_SIZE_PRESETS, sanitize_mascot_size,
    DEFAULT_PAUSE_AUTO_RESUME_SECONDS,
)
from ..quips import DEFAULT_STYLE, STYLES

log = logging.getLogger(__name__)

MINUTES_MIN, MINUTES_MAX = 1, 600

# 间隔快捷值（分钟）。点一下 = 把上面的数值框填成它，仍需「保存」才生效。
QUICK_MINUTES = (15, 30, 45, 60)

# 妮子大小三档的显示名，与 config.MASCOT_SIZE_PRESETS 一一对应（长度必须相等）。
SIZE_LABELS = ("小", "中", "大")

# 设置窗与妮子浮窗之间的间距（逻辑像素）。
PANEL_GAP = 12


def clamp_into_area(x: int, y: int, w: int, h: int, area):
    """把 w×h 的矩形左上角 (x, y) 收敛进 area，保证矩形**整体**可见。

    area 只要是「有 x()/y()/width()/height() 的对象」即可（QRect 就是），
    因此这个函数不依赖 Qt 运行时，可以直接单测。
    ⚠️ 边界一律用 `area 原点 + 宽高` 现算，**不要**用 QRect.right()/bottom()：
    那两个是**包含式**坐标（等于 x + w - 1），拿它们当「右边/下边能到哪」会凭空少 1 像素。
    矩形比 area 还大时贴左上角，至少保证标题栏一侧可见。
    """
    max_x = area.x() + area.width() - w
    max_y = area.y() + area.height() - h
    return (max(area.x(), min(x, max_x)),
            max(area.y(), min(y, max_y)))


class SettingsWindow(QWidget):
    saved = Signal(dict)        # 保存：dict 里是本次要落盘的字段
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
        glay = QVBoxLayout(group)
        glay.setSpacing(6)
        row = QHBoxLayout()
        self._val = QLineEdit()
        self._val.setFixedWidth(64)
        self._val.setAlignment(Qt.AlignCenter)
        self._val.setText(str(seconds // 60 if use_min else seconds))
        self._unit = QComboBox()
        self._unit.addItems(["分钟", "秒"])
        self._unit.setCurrentIndex(0 if use_min else 1)
        self._unit.currentIndexChanged.connect(self._unit_changed)
        row.addWidget(self._val)
        row.addWidget(self._unit)
        row.addStretch(1)
        glay.addLayout(row)

        # 快捷值：常用间隔一键填入（单位同时切到「分钟」）
        quick = QHBoxLayout()
        quick.setSpacing(6)
        for m in QUICK_MINUTES:
            b = QPushButton(f"{m}分")
            b.setFixedWidth(46)
            b.setToolTip(f"填入 {m} 分钟（仍需点「保存」生效）")
            b.clicked.connect(lambda _=False, mins=m: self._apply_quick(mins))
            quick.addWidget(b)
        quick.addStretch(1)
        glay.addLayout(quick)

        # ---- 自启
        # 必须回显当前配置：原先建了复选框却没 setChecked，
        # 于是每次打开设置窗都显示「未勾选」——配置里明明开着，界面却像关着，
        # 用户无法判断真实状态；点一下保存还会把已开的自启写成关闭。
        self._auto = QCheckBox("开机自动启动")
        self._auto.setChecked(bool(cfg.get("autostart", False)))
        self._auto.setToolTip("勾选：把妮子登记到系统的开机启动项，下次开机自动运行\n"
                              "不勾：移除该启动项（只动本程序那一条，不影响其它软件）")

        # ---- 倒计时贴纸显示模式
        self._capsule = QCheckBox("倒计时始终显示")
        self._capsule.setChecked(bool(cfg.get("capsule_always_visible", True)))
        self._capsule.setToolTip("勾选：贴纸常驻（平时淡显，悬停变清晰）\n"
                                 "不勾：平时隐藏，鼠标悬停或暂停时才出现")

        # ---- 妮子大小（三档）
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("妮子大小"))
        self._size = QComboBox()
        self._size.addItems(list(SIZE_LABELS))
        current_size = sanitize_mascot_size(cfg.get("mascot_size"))
        self._size.setCurrentIndex(MASCOT_SIZE_PRESETS.index(current_size))
        self._size.setToolTip("妮子的显示大小；切换后立即生效，位置保持原地不动")
        size_row.addWidget(self._size)
        size_row.addStretch(1)

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

        # ---- 暂停超时自动继续
        # 暂停是个"静态"状态：用户忘了取消，提醒就再也不会响。给一个超时兜底。
        resume_row = QHBoxLayout()
        self._resume_on = QCheckBox("暂停超时自动继续")
        self._resume = QSpinBox()
        self._resume.setRange(1, 600)
        self._resume.setSuffix(" 分钟")
        self._resume.setFixedWidth(86)
        auto_resume = int(cfg.get("pause_auto_resume_seconds",
                                  DEFAULT_PAUSE_AUTO_RESUME_SECONDS))
        self._resume.setValue(max(1, auto_resume // 60) if auto_resume > 0 else 30)
        self._resume_on.setChecked(auto_resume > 0)
        self._resume.setEnabled(auto_resume > 0)
        self._resume_on.toggled.connect(self._resume.setEnabled)
        self._resume_on.setToolTip("勾选：暂停超过设定时长后自动恢复计时，免得一直停着\n"
                                   "不勾：暂停完全由你手动解除")
        resume_row.addWidget(self._resume_on)
        resume_row.addWidget(self._resume)
        resume_row.addStretch(1)

        # ---- 免打扰时段
        # 该时段内到点不弹气泡（计时照走）。跨夜可用，比如 22:00 至 08:00。
        quiet_row = QHBoxLayout()
        self._quiet_on = QCheckBox("免打扰")
        self._quiet_on.setChecked(bool(cfg.get("quiet_enabled", False)))
        self._quiet_on.setToolTip("勾选：这个时段内到点不弹提醒气泡（计时照常）\n"
                                  "支持跨夜，例如 22:00 至 08:00")
        self._quiet_start = QTimeEdit()
        self._quiet_start.setDisplayFormat("HH:mm")
        self._quiet_start.setFixedWidth(78)
        self._quiet_start.setTime(_to_qtime(cfg.get("quiet_start"), quiet.DEFAULT_START))
        self._quiet_end = QTimeEdit()
        self._quiet_end.setDisplayFormat("HH:mm")
        self._quiet_end.setFixedWidth(78)
        self._quiet_end.setTime(_to_qtime(cfg.get("quiet_end"), quiet.DEFAULT_END))
        for w in (self._quiet_start, self._quiet_end):
            w.setEnabled(self._quiet_on.isChecked())
        self._quiet_on.toggled.connect(self._quiet_start.setEnabled)
        self._quiet_on.toggled.connect(self._quiet_end.setEnabled)
        quiet_row.addWidget(self._quiet_on)
        quiet_row.addWidget(self._quiet_start)
        quiet_row.addWidget(QLabel("至"))
        quiet_row.addWidget(self._quiet_end)
        quiet_row.addStretch(1)

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
        root.setSpacing(8)
        root.addWidget(group)
        root.addLayout(style_row)
        root.addLayout(size_row)
        root.addWidget(self._capsule)
        root.addWidget(self._auto)
        root.addLayout(resume_row)
        root.addLayout(quiet_row)
        root.addLayout(ops)
        # ⚠️ 这里绝不能调 _unit_changed()：走到这一步 _val 里已经是「目标单位」
        # 的数值，再换算一次就等于算错 —— 5 分钟会被当成 5 分钟又 ÷60（=1 分钟），
        # 90 秒会被当成 90 分钟 ×60（=5400 秒）。该方法只应由单位切换信号触发。

    def _apply_quick(self, minutes: int):
        """快捷值：单位切到「分钟」、数值框填成 N。

        只改界面，**不直接生效** —— 与其它字段一样要点「保存」，
        免得手一滑就把当前计时重置掉。
        """
        self._unit.setCurrentIndex(0)     # 触发 _unit_changed，把单位标记切回分钟
        self._val.setText(str(int(minutes)))

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
        self.saved.emit({
            "interval_seconds": seconds,
            "autostart": self._auto.isChecked(),
            "capsule_always_visible": self._capsule.isChecked(),
            "quip_style": self._style.currentText(),
            "mascot_size": MASCOT_SIZE_PRESETS[self._size.currentIndex()],
            # 未勾选 = 0 = 永不自动恢复
            "pause_auto_resume_seconds": (self._resume.value() * 60
                                          if self._resume_on.isChecked() else 0),
            "quiet_enabled": self._quiet_on.isChecked(),
            "quiet_start": self._quiet_start.time().toString("HH:mm"),
            "quiet_end": self._quiet_end.time().toString("HH:mm"),
        })
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
        """置于妮子浮窗右侧、垂直居中，并保证**整个窗口（含标题栏）**完整落在屏幕可用区内。

        v1.2 修复「设置窗贴屏幕底部时显示不全、要手动拖上来」：
        原先用 `self.width()/height()`（**客户区**尺寸）算位置，可 `move()` 摆的是
        **含标题栏/边框的外框**，两者差一个标题栏高度（本机 125% DPI 下 30px）。
        妮子靠下时这 30px 就探出屏幕，底部的「保存」一行被切掉。
        现在分两步：先按客户区尺寸粗排，上屏后再按**真实外框**收敛一次。
        """
        ref_win = ref.window()
        ref_geo = ref_win.frameGeometry()
        scr = ref_win.screen() or self.screen()
        avail = scr.availableGeometry()

        # 布局已建好，先按内容算出尺寸（此刻拿到的是客户区尺寸，只够粗排）
        self.adjustSize()
        w, h = self.width(), self.height()

        # 优先放妮子右侧、与其垂直居中
        x = ref_geo.right() + PANEL_GAP
        y = ref_geo.center().y() - h // 2
        # 右侧放不下就翻到左侧
        if x + w > avail.x() + avail.width():
            x = ref_geo.left() - PANEL_GAP - w
        x, y = clamp_into_area(x, y, w, h, avail)
        self.move(x, y)
        self.show()

        # ⚠️ 关键一步：show() 之前原生窗口还没建立，frameGeometry() 拿不到真实外框；
        # 必须等窗口上屏后，按「含标题栏」的外框再收敛一次，否则底部会溢出屏幕。
        self.clamp_frame_into_avail(avail)

    def clamp_frame_into_avail(self, avail):
        """按含窗口装饰的**真实外框**把窗口整体收进 avail；已在区内则原地不动。

        用「增量平移」而不是绝对坐标：move() 与 frameGeometry() 的参照系
        在两个平台上不完全一致（客户区 or 外框），而增量对两者都成立。
        """
        for _ in range(2):
            fg = self.frameGeometry()
            x, y = clamp_into_area(fg.x(), fg.y(), fg.width(), fg.height(), avail)
            if (x, y) == (fg.x(), fg.y()):
                return
            self.move(self.x() + (x - fg.x()), self.y() + (y - fg.y()))


def _to_qtime(value, fallback: str) -> QTime:
    """把配置里的 "HH:MM" 转成 QTime；非法值退回 fallback（默认 22:00/08:00）。"""
    parsed = quiet.parse_hhmm(value) or quiet.parse_hhmm(fallback)
    if parsed is None:
        return QTime(0, 0)
    return QTime(parsed[0], parsed[1])
