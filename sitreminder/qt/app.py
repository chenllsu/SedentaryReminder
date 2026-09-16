"""Qt6 控制器：组合计时器、主浮窗与对话框。

复用框架无关的逻辑模块（config / timer / quips / quiet），UI 全走 Qt。

v1.2 体验优化：
  - 暂停超时自动恢复（check_pause_timeout，由主窗心跳驱动）
  - 提醒气泡「N 分钟后」延后本轮（on_bubble_snoozed）
  - 免打扰时段内不弹气泡（on_due 拦截，计时照走）
  - 妮子大小三档即时应用（apply_settings）
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget
from PySide6.QtGui import QIcon, QPixmap, QImage

from .. import autostart, paths, quiet
from ..config import (
    DEFAULT_MASCOT_SIZE, DEFAULT_SNOOZE_SECONDS,
    load_config, save_config, sanitize_mascot_size,
)
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
        # 托盘菜单首项（显示/隐藏妮子）：文字要跟着显隐状态走，不能写死。
        self._tray_act_toggle = None
        self._exiting = False

    # ------------------------------------------------------------ 启动
    def _build_main_window(self):
        # 妮子大小按配置注入（三档之一，见 config.MASCOT_SIZE_PRESETS）
        return SitReminderWindow(self, self.cfg.get("mascot_size", DEFAULT_MASCOT_SIZE))

    def run(self):
        self.main_window = self._build_main_window()
        # 贴纸显示模式按配置注入（常驻淡显 / 悬停才出现）
        self.main_window.set_capsule_always(
            bool(self.cfg.get("capsule_always_visible", True)))
        self._sync_autostart()
        self._setup_tray()
        self.main_window.move(self._initial_pos())
        self.main_window.show()
        return self._qapp.exec()

    def _sync_autostart(self):
        """启动时校正自启项（FR-7）。

        配置里勾着「开机自启」但系统里查不到项（首次勾选后程序被移动、
        或换了 exe 路径）时补写一次，避免「界面上开着、开机却不启动」。
        没勾选则不动，绝不擅自删掉用户手工加的启动项。
        """
        if not self.cfg.get("autostart"):
            return
        if not autostart.is_supported():
            return
        if autostart.enable():
            log.info("开机自启项已确认：%s", autostart.launch_command())
        else:
            log.warning("开机自启项写入失败，重启后可能不会自动启动")

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
        self._minimized = False

    def toggle_main_visible(self):
        """托盘右键菜单首项：正显示 → 收起；已收起 → 唤回。

        入口只保留右键菜单一处（2026-09-14 起）：托盘单击不再切换显隐，
        免得同一个动作有两个入口、随手一点就把妮子收没了。
        注意：收起只是隐藏，**不是退出**——计时照走，到点仍会弹气泡。
        """
        if self.main_window is None:
            return
        if self.main_window.isVisible():
            self.main_window.hide()
            self._minimized = True
        else:
            self.show_main()
        self._sync_main_visible_state()

    # ------------------------------------------------------------ 系统托盘
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("系统托盘不可用，跳过")
            self.tray = None
            return
        tray_menu = QMenu()
        # 首项是「显示 / 隐藏」切换：文字随妮子当前是否在桌面上而变（见
        # _sync_main_visible_state）。点击行为统一走 toggle_main_visible，
        # 与单击托盘图标一致。
        self._tray_act_toggle = tray_menu.addAction("显示", self.toggle_main_visible)
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
        # （暂停项文字里带「已停 N 分钟」，是个活值，必须弹出前重算。）
        tray_menu.aboutToShow.connect(self._sync_pause_state)
        tray_menu.aboutToShow.connect(self._sync_main_visible_state)
        self.tray.setContextMenu(tray_menu)
        # 刻意不接 activated 信号：显隐统一由右键菜单首项承担，
        # 单击托盘图标不做任何事——同一个动作留两个入口，随手一点就容易把妮子收没了。
        self.tray.show()

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

    def pause_label(self, paused: bool) -> str:
        """暂停项的文字（浮窗右键菜单与托盘菜单共用同一份文案）。

        暂停中带上「已停多久」：暂停是个没有尽头的状态，
        用户需要一眼看出自己停了多长时间，好判断要不要继续。
        """
        if not paused:
            return "暂停计时"
        mins = self.timer.paused_seconds() // 60
        if mins < 1:
            return "继续计时"
        if mins < 60:
            return f"继续计时（已停 {mins} 分钟）"
        return f"继续计时（已停 {mins // 60} 小时 {mins % 60} 分）"

    def check_pause_timeout(self):
        """暂停超时自动恢复（由主窗每 250ms 的心跳调用）。

        暂停是个"静态"状态，容易被遗忘：用户按了暂停去开会，
        回来早就忘了这回事，提醒从此再也不响。超时后自动继续，
        从**暂停那一刻冻结的剩余时间**接着走（不是跳过这一轮）。
        配置为 0 表示永不自动恢复，暂停完全交给用户手动解除。
        """
        limit = int(self.cfg.get("pause_auto_resume_seconds", 0) or 0)
        if limit <= 0 or not self.timer.is_paused:
            return
        # 设置窗打开时计时是"程序冻结"，不是用户主动暂停，不参与超时判断。
        if self._settings is not None and self._settings.isVisible():
            return
        if self.timer.paused_seconds() < limit:
            return
        log.info("暂停已超过 %s 秒，自动恢复计时", limit)
        self.timer.resume()
        self._sync_pause_state()

    def _sync_pause_state(self):
        """把暂停状态同步到所有能显示它的地方（浮窗菜单 / 托盘菜单 / 设置窗）。"""
        paused = self.timer.is_paused
        if self.main_window:
            self.main_window.set_paused(paused)
        if self._tray_act_pause is not None:
            self._tray_act_pause.setText(self.pause_label(paused))
        if self._settings is not None:
            # 不要求"可见"：打开设置时同步发生在 show() 之前（此刻 isVisible 还是
            # False），若加可见判断就会漏掉首次同步，按钮会停留在「暂停/继续」。
            self._settings.set_paused(paused)
        if self.tray is not None:
            self.tray.setToolTip("久坐提醒 · 妮子" + ("（已暂停）" if paused else ""))

    def _sync_main_visible_state(self):
        """托盘菜单首项文字跟着妮子显隐走：在桌上 → 「隐藏」，已收起 → 「显示」。

        该项的点击行为是 toggle_main_visible()，所以文字必须与当前状态严格对应；
        写死成「显示」的话，妮子明明就在桌面上，点一下反而把它收起来了。
        """
        if self._tray_act_toggle is None or self.main_window is None:
            return
        self._tray_act_toggle.setText(
            "隐藏" if self.main_window.isVisible() else "显示")

    # ------------------------------------------------------------ 提醒
    def _in_quiet_hours(self) -> bool:
        """当前是否处于免打扰时段（未启用一律 False）。"""
        if not self.cfg.get("quiet_enabled"):
            return False
        return quiet.is_quiet_now(datetime.now(),
                                  self.cfg.get("quiet_start"),
                                  self.cfg.get("quiet_end"))

    def _snooze_minutes(self) -> int:
        """气泡「N 分钟后」按钮上的 N（分钟）。"""
        seconds = int(self.cfg.get("snooze_seconds", DEFAULT_SNOOZE_SECONDS))
        return max(1, seconds // 60)

    def on_due(self):
        if self._bubble is not None and self._bubble.isVisible():
            return
        if self._in_quiet_hours():
            # 免打扰时段：不上屏，但**必须把这一轮翻过去**——
            # 否则 is_due() 会一直为真，每 250ms 反复走到这里空转。
            # 计时本身照走，时段一结束就恢复正常提醒。
            log.info("处于免打扰时段（%s–%s），跳过本次提醒",
                     self.cfg.get("quiet_start"), self.cfg.get("quiet_end"))
            self.timer.reset(keep_paused=True)
            self._sync_pause_state()
            return
        self._bubble = BubbleWindow(self, pick_quip(self.cfg.get("quip_style")),
                                    snooze_minutes=self._snooze_minutes())
        self._bubble.show_near(self.main_window)
        self._bubble.bubble_closed.connect(self.on_bubble_closed)
        self._bubble.bubble_snoozed.connect(self.on_bubble_snoozed)

    def on_bubble_closed(self):
        """气泡关闭 = 这一轮结束，重新计下一轮。

        用 keep_paused=True：若用户在气泡显示期间按过暂停，这个暂停必须保留。
        原先直接连 timer.reset（会清掉 paused），于是刚按下的暂停被悄悄抹掉，
        过一会儿又被提醒一次。
        """
        self.timer.reset(keep_paused=True)
        self._sync_pause_state()

    def on_bubble_snoozed(self):
        """气泡里点「N 分钟后」：只把这一轮往后推，不动用户设定的间隔。

        「这个提醒我先缓缓」和「以后都改成 5 分钟一次」是两件事，
        所以走 timer.defer() 而不是 set_interval()。
        """
        seconds = int(self.cfg.get("snooze_seconds", DEFAULT_SNOOZE_SECONDS))
        self.timer.defer(seconds)
        self._sync_pause_state()
        log.info("本次提醒已延后 %s 秒", seconds)

    # ------------------------------------------------------------ 设置
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
        # 这次冻结是程序行为（不是用户按的暂停），把「已暂停多久」的起点
        # 挪到此刻，免得开着设置窗发会儿呆就被判成"暂停超时"。
        self.timer.restart_pause_clock()
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
        # 若关窗后仍是暂停（用户显式接管），把暂停计时起点重置到此刻 ——
        # 开窗期间那段时间不算进「暂停超时」。
        self.timer.restart_pause_clock()
        self._settings_interval_changed = False
        self._settings_pause_touched = False
        self._sync_pause_state()

    def apply_settings(self, values: dict):
        """设置窗「保存」：落盘 + 即时应用。

        values 只需要带**本次界面上有的**字段；没带的（如 snooze_seconds）
        保持配置原值不动 —— 这也是把信号换成 dict 的原因之一。
        """
        values = dict(values or {})
        old_interval = int(self.cfg["interval_seconds"])
        self.cfg.update(values)
        if save_config(self.cfg):
            log.info("配置已保存")
        else:
            log.warning("配置保存失败，界面改动可能不会保留")

        if self.main_window:
            # 贴纸显示模式立即生效（不依赖间隔是否变化）
            self.main_window.set_capsule_always(
                bool(self.cfg.get("capsule_always_visible", True)))
            # 妮子大小：换档保持的是窗口中心，左上角坐标会变，
            # 所以换档后要补存一次位置，否则下次启动会按旧坐标把新尺寸窗口放歪。
            if self.main_window.set_mascot_size(
                    sanitize_mascot_size(self.cfg.get("mascot_size"))):
                self.save_window_pos(self.main_window.pos())

        interval_seconds = int(self.cfg["interval_seconds"])
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
        self._apply_autostart(bool(self.cfg.get("autostart", False)))

    def _apply_autostart(self, enabled: bool):
        """把「开机自启」偏好真正落到操作系统（FR-7）。

        写失败只记日志、不抛错：偏好已经存进 config.json 了，下次启动
        _sync_autostart() 还会再试；不该因为写注册表失败就让「保存」整体失败。
        """
        if not autostart.is_supported():
            log.info("当前平台不支持开机自启，偏好已记录：%s", enabled)
            return
        if autostart.set_enabled(enabled):
            log.info("开机自启已%s（%s）", "开启" if enabled else "关闭",
                     autostart.launch_command())
        else:
            log.warning("开机自启%s失败，偏好已保存，下次启动会重试",
                        "开启" if enabled else "关闭")

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
