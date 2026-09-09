"""设置窗口（原生系统风格：标准标题栏 / 可拖动）。"""

from __future__ import annotations

import tkinter as tk
import tkinter.messagebox as mb

from .. import theme
from ..config import MAX_INTERVAL_SECONDS, MIN_INTERVAL_SECONDS

MINUTES_MIN = 1
MINUTES_MAX = 600     # MAX_INTERVAL_SECONDS // 60


class SettingsWindow(tk.Toplevel):
    BG = "#f0f0f0"

    def __init__(self, parent, cfg, app):
        super().__init__(parent)
        self.app = app
        self.title("设置 · 久坐提醒")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        font = theme.FONT_TAG

        seconds = int(cfg["interval_seconds"])
        use_minutes = (seconds % 60 == 0 and seconds >= 60)
        self.unit = tk.StringVar(value="分钟" if use_minutes else "秒")
        self.var = tk.StringVar(value=str(seconds // 60 if use_minutes else seconds))
        self.auto = tk.BooleanVar(value=bool(cfg["autostart"]))

        frame = tk.Frame(self, bg=self.BG)
        frame.pack(fill="both", expand=True, padx=14, pady=10)

        row1 = tk.Frame(frame, bg=self.BG)
        row1.pack(fill="x", pady=(0, 8))
        tk.Label(row1, text="提醒间隔", bg=self.BG, font=font).pack(side="left")
        tk.Entry(row1, textvariable=self.var, width=6, justify="center",
                 font=font).pack(side="left", padx=(10, 4))
        opt = tk.OptionMenu(row1, self.unit, "分钟", "秒")
        opt.config(font=font)
        opt.pack(side="left")

        tk.Checkbutton(frame, text="开机自动启动", variable=self.auto,
                       bg=self.BG, font=font, anchor="w").pack(fill="x", pady=(0, 10))

        row2 = tk.Frame(frame, bg=self.BG)
        row2.pack(fill="x")
        tk.Button(row2, text="暂停/继续", command=self.app.toggle_pause,
                  font=font).pack(side="left", padx=(0, 6))
        tk.Button(row2, text="跳过本次", command=self.app.on_skip,
                  font=font).pack(side="left", padx=(0, 6))
        tk.Button(row2, text="保存", command=self.save, font=font).pack(side="right")

        # 出现在浮窗右侧，被屏幕边缘 clamp
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x = parent.winfo_rootx() + parent.winfo_width() + 12
        y = parent.winfo_rooty()
        x = max(8, min(x, screen_w - width - 8))
        y = max(8, min(y, screen_h - height - 8))
        self.geometry(f"+{x}+{y}")

    def save(self):
        raw = self.var.get().strip()
        try:
            value = int(raw)
        except ValueError:
            self._error(f"请输入整数，当前输入「{raw}」不合法")
            return

        if self.unit.get() == "分钟":
            if not (MINUTES_MIN <= value <= MINUTES_MAX):
                self._error(f"请输入 {MINUTES_MIN}-{MINUTES_MAX} 之间的整数分钟")
                return
            seconds = value * 60
        else:
            if not (MIN_INTERVAL_SECONDS <= value <= MAX_INTERVAL_SECONDS):
                self._error(
                    f"请输入 {MIN_INTERVAL_SECONDS}-{MAX_INTERVAL_SECONDS} 之间的整数秒"
                )
                return
            seconds = value

        self.app.apply_settings(seconds, self.auto.get())
        self.destroy()

    def _error(self, message: str):
        mb.showerror("输入错误", message, parent=self)
