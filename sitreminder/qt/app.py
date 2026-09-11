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
from ..quips import DEFAULT_STYLE, pick_quip
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
        # 本次「打开设置」期间提醒间隔是否被改动（决定关窗后继续计时 or 按新间隔重算）
        self._settings_interval_changed = False
        # 用户在设置窗内是否显式点过「暂停/继续」。
        # 点过说明暂停状态已被用户接管，关窗时不能再用「未改设置则继续」
        # 的默认规则去改写他的选择。
        self._settings_pause_touched = False
        # 托盘菜单里的「暂停/继续」项：必须在状态变化时同步文字，
        # 否则从托盘永远看不出现在是停着还是跑着。
        self._tray_act_pause = None
        self._exiting = False

    # ------------------------------------------------------------ 启动
    def _build_main_window(self):
        win = SitReminderWindow(self)
        return win

    def run(self):
        self.main_window = self._build_main_window()
        # 贴纸显示模式按配置注入（常驻淡显 / 悬停才出现）
        self.main_window.set_capsule_always(
            bool(self.cfg.get("capsule_always_visible", True)))
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
        tray_menu.addAction("设置", self.open_settings)
        # 保存引用：状态变化时要改文字（暂停计时 / 继续计时），
        # 与浮窗右键菜单保持一致。原先没存引用，所以从托盘永远看不出当前状态。
        self._tray_act_pause = tray_menu.addAction("暂停计时", self.toggle_pause)
        tray_menu.addAction("跳过本次", self.on_skip)
        tray_menu.addSeparator()
        tray_menu.addAction("退出", self.do_exit)
        self._tray_menu = tray_menu

        icon = self._load_tray_icon()
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("久坐提醒 · 妮子")
        # 每次弹出菜单前再同步一次：即使某条路径漏了更新，打开菜单时也必然正确。
        tray_menu.aboutToShow.connect(self._sync_pause_state)
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

    def toggle_pause_from_settings(self):
        """设置窗里的「暂停/继续」。

        与普通 toggle 的唯一区别：记下「用户已显式接管暂停状态」，
        这样关窗时不会被「未改设置则继续计时」的默认规则覆盖掉。
        （打开设置时本来已自动冻结，所以这里点一下等于选择「继续计时」。）
        """
        self._settings_pause_touched = True
        self.toggle_pause()

    def on_skip(self):
        """跳过本轮：剩余时间归位到完整间隔。

        设置窗打开期间计时处于冻结，此时只归位、保持冻结（关窗后再由
        默认规则继续）；平时则直接重置并开始新一轮计时。
        """
        frozen = self._settings is not None and self._settings.isVisible()
        self.timer.skip(keep_paused=frozen)
        self._sync_pause_state()

    def _sync_pause_state(self):
        """把暂停状态同步到所有能显示它的地方（浮窗菜单 / 托盘菜单 / 设置窗）。"""
        paused = self.timer.is_paused
        if self.main_window:
            self.main_window.set_paused(paused)
        if self._tray_act_pause is not None:
            self._tray_act_pause.setText("继续计时" if paused else "暂停计时")
        if self._settings is not None:
            # 不要求"可见"：打开设置时同步发生在 show() 之前（此刻 isVisible 还是
            # False），若加可见判断就会漏掉首次同步，按钮会停留在「暂停/继续」。
            self._settings.set_paused(paused)
        if self.tray is not None:
            self.tray.setToolTip("久坐提醒 · 妮子" + ("（已暂停）" if paused else ""))

    def on_due(self):
        if self._bubble is not None and self._bubble.isVisible():
            return
        self._bubble = BubbleWindow(self, pick_quip(self.cfg.get("quip_style")))
        self._bubble.show_near(self.main_window)
        self._bubble.bubble_closed.connect(self.on_bubble_closed)

    def on_bubble_closed(self):
        """气泡关闭 = 这一轮结束，重新计下一轮。

        用 keep_paused=True：若用户在气泡显示期间按过暂停，这个暂停必须保留。
        原先直接连 timer.reset（会清掉 paused），于是刚按下的暂停被悄悄抹掉，
        过一会儿又被提醒一次。
        """
        self.timer.reset(keep_paused=True)
        self._sync_pause_state()

    def open_settings(self):
        if self._settings is not None and self._settings.isVisible():
            self._settings.raise_()
            self._settings.activateWindow()
            return
        # 打开设置期间冻结倒计时：剩余秒数被记下、时钟停走；
        # 关窗时再决定「从冻结处继续」还是「按新间隔重算」（见 _on_settings_closed）。
        self._settings_interval_changed = False
        self._settings_pause_touched = False
        self.timer.pause()
        self._settings = SettingsWindow(self, self.cfg)
        self._settings.saved.connect(self.apply_settings)
        self._settings.closed.connect(self._on_settings_closed)
        # 同步放在设置窗创建之后：这样窗内「暂停/继续」按钮的文字
        # 一打开就是真实状态（此刻已冻结 → 显示「继续计时」）。
        self._sync_pause_state()
        self._settings.show_right_of(self.main_window)

    def _on_settings_closed(self):
        """设置窗关闭后的计时处理。

        - 间隔没改（含"改了但没点保存就关窗"）且用户没在窗内动过暂停
          → 从冻结处继续计时；
        - 用户在窗内点过「暂停/继续」→ 尊重他的选择，不用默认规则覆盖；
        - 间隔改了并已保存 → apply_settings 里已按新间隔从头重算，这里不再动。
        """
        if self._exiting:
            return
        if not self._settings_interval_changed and not self._settings_pause_touched:
            # resume() 对"本来就是运行中"的状态是空操作，安全
            self.timer.resume()
        self._settings_interval_changed = False
        self._settings_pause_touched = False
        self._sync_pause_state()

    def apply_settings(self, interval_seconds: int, autostart: bool,
                       capsule_always: bool = True,
                       quip_style: str = DEFAULT_STYLE):
        old_interval = int(self.cfg["interval_seconds"])
        self.cfg["interval_seconds"] = interval_seconds
        self.cfg["autostart"] = autostart
        self.cfg["capsule_always_visible"] = capsule_always
        self.cfg["quip_style"] = quip_style
        if save_config(self.cfg):
            log.info("配置已保存")
        # 贴纸显示模式立即生效（不依赖间隔是否变化）
        if self.main_window:
            self.main_window.set_capsule_always(capsule_always)
        if interval_seconds != old_interval:
            # 间隔变了：按新间隔从完整时长重新开始计时
            self.timer.set_interval(interval_seconds)
            self._settings_interval_changed = True
            log.info("提醒间隔 %s → %s 秒，已按新间隔重新计时",
                     old_interval, interval_seconds)
        else:
            # 间隔未变：不碰计时器（保持冻结），关窗时从暂停处继续
            log.info("提醒间隔未变，计时保持冻结，关窗后继续")
        self._sync_pause_state()
        if autostart:
            log.info("「开机自启」偏好已记录，具体写入逻辑待实现（FR-7）")

    def do_minimize(self):
        self.main_window.hide()

    def open_close_choice(self):
        win = ChoiceWindow(self, self.do_exit, self.do_minimize)
        win.show_beside(self.main_window)

    def do_exit(self):
        self._exiting = True
        if self.tray is not None:
            self.tray.hide()
        self._qapp.quit()
