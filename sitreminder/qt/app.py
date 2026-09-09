"""Qt6 控制器：组合计时器、主浮窗与对话框。

复用框架无关的逻辑模块（config / timer / quips），UI 全走 Qt。
"""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt
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
        self.main_window.move(40, 40)
        self.main_window.show()
        return self._qapp.exec()

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
        # 复用主浮窗同款素材与朝向（B 朝向），保证托盘小图标与主窗方向一致
        from .window import _load_scaled_mascot
        pm = _load_scaled_mascot()
        if pm is not None:
            return QIcon(pm.scaled(64, 64, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation))
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
