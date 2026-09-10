"""Qt6 控制器：组合计时器、主浮窗与对话框。

复用框架无关的逻辑模块（config / timer / quips），UI 全走 Qt。
"""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget
from PySide6.QtGui import QIcon, QPixmap, QImage

from .. import paths
from ..config import load_config, save_config
from ..timer import TimerState
from ..quips import pick_quip
from .window import SitReminderWindow
from .settings import SettingsWindow
from .choice import ChoiceWindow
from .bubble import BubbleWindow

log = logging.getLogger(__name__)

# 首次启动（配置里没有位置记录）时，浮窗距屏幕右下角的边距（逻辑像素）。
# 用 availableGeometry 而非 geometry，右侧/底部自动避开任务栏。
FIRST_RUN_MARGIN = 20

# 判定「记录的位置仍然可用」的最低可见比例：窗口与某块屏幕可用区的交叠面积
# 需达到窗口自身面积的这个比例，否则回退到默认右下角。
# 目的：换显示器 / 改分辨率后，不至于把窗口"恢复"到看不见的地方。
POS_MIN_VISIBLE_RATIO = 0.3


class QtController:
    """Qt 应用入口与状态编排。"""

    def __init__(self):
        self.cfg = load_config()
        self.timer = TimerState(self.cfg["interval_seconds"])

        self._qapp = QApplication.instance() or QApplication([])
        # 关键：设置全局字体抗锯齿
        from PySide6.QtGui import QFont
        self._qapp.setFont(QFont("Microsoft YaHei", 9))
        self._qapp.setQuitOnLastWindowClosed(False)  # 关了设置窗不退出

        self.main_window = None
        self._settings = None
        self._bubble = None
        self.tray = None
        self._tray_menu = None
        self._minimized = False

    # ------------------------------------------------------------ 启动
    def _build_main_window(self):
        win = SitReminderWindow(self)
        return win

    def run(self):
        self.main_window = self._build_main_window()
        self._setup_tray()
        self.main_window.move(self._initial_pos())
        self.main_window.show()
        return self._qapp.exec()

    # ------------------------------------------------------------ 窗口位置
    def _default_pos(self) -> QPoint:
        """首次启动的默认位置：主屏右下角（留边距，已在任务栏之上）。"""
        g = self._qapp.primaryScreen().availableGeometry()
        win = self.main_window
        return QPoint(
            g.x() + g.width() - win.width() - FIRST_RUN_MARGIN,
            g.y() + g.height() - win.height() - FIRST_RUN_MARGIN,
        )

    def _pos_still_visible(self, pos: QPoint) -> bool:
        """记录的位置是否仍落在某块屏幕内（防换屏 / 改分辨率后落到屏幕外）。"""
        win = self.main_window
        rect = QRect(pos, win.size())
        area = rect.width() * rect.height()
        if area <= 0:
            return False
        for scr in self._qapp.screens():
            inter = rect.intersected(scr.availableGeometry())
            if inter.width() * inter.height() >= area * POS_MIN_VISIBLE_RATIO:
                return True
        return False

    def _initial_pos(self) -> QPoint:
        """启动位置：有记录且仍可见就用记录，否则用默认右下角。"""
        saved = self.cfg.get("window_pos")
        if saved:
            pos = QPoint(int(saved[0]), int(saved[1]))
            if self._pos_still_visible(pos):
                return pos
            log.info("记录的位置 %s 已不在任何屏幕内，回退到右下角", saved)
        else:
            log.info("首次启动：浮窗默认放在屏幕右下角")
        return self._default_pos()

    def save_window_pos(self, pos: QPoint):
        """记住浮窗最后位置（拖动结束时调用）。与上次相同则不写盘，避免多余 IO。"""
        new = [int(pos.x()), int(pos.y())]
        if self.cfg.get("window_pos") == new:
            return
        self.cfg["window_pos"] = new
        if save_config(self.cfg):
            log.info("窗口位置已保存：%s", new)
        else:
            log.warning("窗口位置保存失败：%s", new)

    def show_main(self):
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()

    # ------------------------------------------------------------ 系统托盘
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("系统托盘不可用，跳过")
            self.tray = None
            return
        tray_menu = QMenu()
        tray_menu.addAction("显示", self.show_main)
        tray_menu.addAction("暂停/继续", self.toggle_pause)
        tray_menu.addAction("跳过本次", self.on_skip)
        tray_menu.addSeparator()
        tray_menu.addAction("退出", self.do_exit)
        self._tray_menu = tray_menu

        icon = self._load_tray_icon()
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("久坐提醒 · 妮子")
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:   # 单击托盘
            self.show_main()

    def _load_tray_icon(self) -> QIcon:
        """托盘图标：复用主浮窗同款素材与朝向（B 朝向），保证方向一致。

        从高清源一次性生成多档尺寸塞进 QIcon，让系统按托盘实际像素挑选，
        避免"小图被放大"导致的糊边。
        """
        from .window import load_mascot_pixmap
        src = load_mascot_pixmap(256, 1.0)      # 256 物理像素的高清源
        if src is not None:
            icon = QIcon()
            for s in (16, 20, 24, 32, 48, 64, 128, 256):
                icon.addPixmap(src.scaled(s, s, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
            return icon
        # 降级：1920 原图
        p = paths.MASCOT_PATH
        if os.path.exists(p):
            img = QImage(p)
            if not img.isNull():
                pm = QPixmap.fromImage(img)
                return QIcon(pm.scaled(64, 64, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))
        return QIcon()

    # ------------------------------------------------------------ 交互接口
    def toggle_pause(self):
        self.timer.toggle()
        self._sync_pause_state()

    def on_skip(self):
        self.timer.skip()
        self._sync_pause_state()

    def _sync_pause_state(self):
        paused = self.timer.is_paused
        if self.main_window:
            self.main_window.set_paused(paused)
        if self.tray is not None:
            self.tray.setToolTip("久坐提醒 · 妮子" + ("（已暂停）" if paused else ""))

    def on_due(self):
        if self._bubble is not None and self._bubble.isVisible():
            return
        self._bubble = BubbleWindow(self, pick_quip())
        self._bubble.show_near(self.main_window)
        self._bubble.bubble_closed.connect(self.timer.reset)

    def open_settings(self):
        if self._settings is not None and self._settings.isVisible():
            self._settings.raise_()
            self._settings.activateWindow()
            return
        self._settings = SettingsWindow(self, self.cfg)
        self._settings.saved.connect(self.apply_settings)
        self._settings.show_right_of(self.main_window)

    def apply_settings(self, interval_seconds: int, autostart: bool):
        self.cfg["interval_seconds"] = interval_seconds
        self.cfg["autostart"] = autostart
        if save_config(self.cfg):
            log.info("配置已保存")
        self.timer.set_interval(interval_seconds)
        if autostart:
            log.info("「开机自启」偏好已记录，具体写入逻辑待实现（FR-7）")

    def do_minimize(self):
        self.main_window.hide()

    def open_close_choice(self):
        win = ChoiceWindow(self, self.do_exit, self.do_minimize)
        win.show_beside(self.main_window)

    def do_exit(self):
        if self.tray is not None:
            self.tray.hide()
        self._qapp.quit()
