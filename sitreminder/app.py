"""主应用：串起计时器、浮窗 UI 与系统托盘。"""

from __future__ import annotations

import logging
import tkinter as tk
import tkinter.messagebox as mb

from . import imagery, theme
from .config import load_config, save_config
from .quips import pick_quip
from .timer import TimerState
from .tray import TrayIcon
from .ui.bubble import BubbleWindow
from .ui.choice import open_choice
from .ui.settings import SettingsWindow
from .ui.shapes import round_rect

log = logging.getLogger(__name__)

WINDOW_GEOMETRY = "210x214+40+40"
TICK_MS = 250          # 倒计时刷新间隔（秒级显示足够，也保证暂停切换响应及时）
PREWARM_MS = 500       # 启动后空闲时预生成动画帧，避免首次 hover 卡顿


class App:
    """桌面浮窗主体：只显示妮子，悬停看倒计时，到点弹气泡。"""

    def __init__(self):
        self.cfg = load_config()
        self.timer = TimerState(self.cfg["interval_seconds"])

        self.root = tk.Tk()
        self.root.title("久坐提醒 · 妮子")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg=theme.TRANS_KEY)
        try:
            self.root.wm_attributes("-transparentcolor", theme.TRANS_KEY)
        except tk.TclError:
            log.info("当前平台不支持 -transparentcolor，浮窗将显示为实底色")
        self.root.geometry(WINDOW_GEOMETRY)
        # 打包成 --noconsole 后，回调里的异常没人看得见，统一记日志
        self.root.report_callback_exception = self._on_tk_error

        self._drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0, "moved": False}
        self._bubble = None
        self._settings = None
        self.hover = False

        # 倒计时胶囊状态
        self._time_frames = None
        self._time_after = None
        self._time_text_id = None
        self._time_txt = ""
        self._time_rendered = None

        self._build_ui()
        self._tray = TrayIcon(self.root, {
            "show": self.show_window,
            "toggle_pause": self.toggle_pause,
            "skip": self.on_skip,
            "exit": self.do_exit,
        })
        self._tray.start()
        self.root.after(PREWARM_MS, self._prewarm)
        self._tick()

    def run(self):
        self.root.mainloop()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        self.mascot = imagery.load_mascot(imagery.MASCOT_SIZE)
        if self.mascot:
            self.img_label = tk.Label(self.root, image=self.mascot,
                                      bg=theme.TRANS_KEY, bd=0, cursor="hand2")
        else:
            self.img_label = tk.Label(self.root, text="(妮子形象\n未找到)",
                                      bg=theme.TRANS_KEY, fg="#999")
        self.img_label.place(relx=0.5, rely=0.46, anchor="center")

        # 倒计时小气泡：绝对定位，出现/隐藏都不会挤压图片
        self.time_canvas = tk.Canvas(self.root, width=imagery.MASCOT_SIZE[0], height=44,
                                     bg=theme.TRANS_KEY, highlightthickness=0)
        self.time_canvas.place_forget()

        # 鼠标在猫和气泡之间移动时保持显示
        for widget in (self.img_label, self.time_canvas):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
        self.img_label.bind("<ButtonPress-1>", self._on_press)
        self.img_label.bind("<B1-Motion>", self._on_drag)
        self.img_label.bind("<ButtonRelease-1>", self._on_release)
        self.img_label.bind("<Button-3>", self.on_close)

    def _on_tk_error(self, exc_type, value, traceback):
        log.error("Tk 回调异常", exc_info=(exc_type, value, traceback))

    # ---------------------------------------------------------------- 倒计时胶囊
    def _prewarm(self):
        """空闲时把动画帧生成好，第一次 hover 就不用等。"""
        if self._time_frames is None:
            self._time_frames = imagery.make_time_frames()

    def _cancel_time_anim(self):
        if self._time_after is not None:
            try:
                self.root.after_cancel(self._time_after)
            except tk.TclError:
                pass
            self._time_after = None

    def _on_enter(self, _event):
        self.hover = True
        if self._time_frames is None:
            self._time_frames = imagery.make_time_frames()
        if not self._time_frames:           # 无 PIL：降级为矢量胶囊
            self._draw_time_fallback()
            return
        self._cancel_time_anim()
        if self.time_canvas.winfo_ismapped() and self._time_text_id is not None:
            return                          # 已完整显示，不重播动画
        self.time_canvas.place(relx=0.5, rely=1.0, anchor="s", y=-2)
        self._time_text_id = None
        self._show_time_frame(0)

    def _draw_time_fallback(self):
        canvas = self.time_canvas
        canvas.delete("all")
        round_rect(canvas, 19, 7, 131, 37, 15,
                   fill=theme.FALLBACK_CAPSULE, outline=theme.FALLBACK_CAPSULE, width=1)
        self._time_text_id = canvas.create_text(*imagery.time_text_pos(),
                                                text=self._time_txt,
                                                font=theme.FONT_TIME,
                                                fill=theme.TIME_TEXT)
        self._time_rendered = self._time_txt
        canvas.place(relx=0.5, rely=1.0, anchor="s", y=-2)

    def _show_time_frame(self, index: int):
        frames = self._time_frames
        idx = min(index, len(frames) - 1)
        self.time_canvas.delete("all")
        self.time_canvas.create_image(0, 0, image=frames[idx], anchor="nw")
        if idx >= len(frames) - 1:          # 末帧：补上文字
            self._time_text_id = self.time_canvas.create_text(
                *imagery.time_text_pos(), text=self._time_txt,
                font=theme.FONT_TIME, fill=theme.TIME_TEXT)
            self._time_rendered = self._time_txt
            self._time_after = None
            return
        self._time_after = self.root.after(
            theme.ANIM_DELAY, lambda: self._show_time_frame(index + 1))

    def _on_leave(self, _event):
        self.hover = False
        self._cancel_time_anim()
        if not self._time_frames:
            self.time_canvas.place_forget()
            return
        # 延迟收起：鼠标在猫↔气泡之间来回时不闪烁
        self._time_after = self.root.after(theme.HOVER_HIDE_DELAY,
                                           self._hide_time_frame_start)

    def _hide_time_frame_start(self):
        if self.hover:                      # 期间又回到猫/气泡上
            self._time_after = None
            return
        self._time_text_id = None
        self._time_rendered = None
        self._hide_time_frame(1)

    def _hide_time_frame(self, index: int):
        if self.hover:
            self._time_after = None
            return
        frames = self._time_frames
        idx = len(frames) - 1 - index
        if idx <= 0:
            self.time_canvas.delete("all")
            self.time_canvas.place_forget()
            self._time_after = None
            return
        self.time_canvas.delete("all")
        self.time_canvas.create_image(0, 0, image=frames[idx], anchor="nw")
        self._time_after = self.root.after(
            theme.ANIM_HIDE_DELAY, lambda: self._hide_time_frame(index + 1))

    def _draw_time(self, text: str):
        """刷新胶囊上的数字；文本没变就不碰画布，省掉每秒 4 次无效重绘。"""
        self._time_txt = text
        if self._time_text_id is None or text == self._time_rendered:
            return
        try:
            self.time_canvas.itemconfig(self._time_text_id, text=text)
            self._time_rendered = text
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- 拖动 / 点击
    def _on_press(self, event):
        # 同时记录鼠标起点和窗口起点：拖动必须用「窗口起点 + 累计位移」，
        # 每帧都基于当前 winfo_x() 叠加会越拖越飞。
        self._drag["sx"] = event.x_root
        self._drag["sy"] = event.y_root
        self._drag["wx"] = self.root.winfo_x()
        self._drag["wy"] = self.root.winfo_y()
        self._drag["moved"] = False

    def _on_drag(self, event):
        dx = event.x_root - self._drag["sx"]
        dy = event.y_root - self._drag["sy"]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag["moved"] = True
        self.root.geometry(f"+{self._drag['wx'] + dx}+{self._drag['wy'] + dy}")

    def _on_release(self, _event):
        if not self._drag["moved"]:     # 没怎么移动 = 单击
            self.open_settings()

    # ---------------------------------------------------------------- 计时循环
    def _tick(self):
        try:
            remaining = self.timer.remaining()
            minutes, seconds = divmod(remaining, 60)
            text = f"{minutes:02d}:{seconds:02d}"
            if self.timer.is_paused:
                text += " ⏸"
            self._time_txt = text
            if self.hover:
                self._draw_time(text)
            if self.timer.is_due():
                self.pop_bubble()
        finally:
            self.root.after(TICK_MS, self._tick)

    def pop_bubble(self):
        if self._bubble is not None:
            try:
                if self._bubble.winfo_exists():
                    return
            except tk.TclError:
                pass
        self._bubble = BubbleWindow(self.root, pick_quip(), self.timer.reset)

    # ---------------------------------------------------------------- 控制
    def toggle_pause(self):
        self.timer.toggle()

    def on_skip(self):
        self.timer.skip()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()

    def open_settings(self):
        if self._settings is not None:
            try:
                if self._settings.winfo_exists():
                    self._settings.lift()
                    self._settings.focus_force()
                    return
            except tk.TclError:
                pass
        try:
            self._settings = SettingsWindow(self.root, self.cfg, self)
            self._settings.bind("<Destroy>", lambda _e: self._clear_settings())
        except Exception:
            log.exception("打开设置窗口失败")
            mb.showerror("打开设置失败",
                         "设置窗口创建失败，详细原因已写入日志文件。",
                         parent=self.root)

    def _clear_settings(self):
        self._settings = None

    def apply_settings(self, interval_seconds: int, autostart: bool):
        self.cfg["interval_seconds"] = interval_seconds
        self.cfg["autostart"] = autostart
        if not save_config(self.cfg):
            mb.showwarning("保存失败",
                           "配置没能写入 config.json，重启后可能会恢复默认值。",
                           parent=self._settings or self.root)
        self.timer.set_interval(interval_seconds)
        if autostart:
            # TODO: 开机自启（Win 注册表 / macOS plist / Linux .desktop）待实现
            log.info("已记录「开机自启」偏好，具体写入逻辑尚未实现")

    # ---------------------------------------------------------------- 关闭
    def on_close(self, _event=None):
        open_choice(self.root, self.do_exit, self.do_minimize)

    def do_exit(self):
        self._tray.stop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def do_minimize(self):
        self.root.withdraw()
