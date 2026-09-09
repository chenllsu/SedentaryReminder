"""关闭浮窗时的二选一：退出程序 / 最小化到托盘。"""

from __future__ import annotations

import tkinter as tk

from .. import theme

_WINDOW_ATTR = "_choice_window"


def open_choice(parent, on_exit, on_minimize) -> "ChoiceWindow":
    """打开选择框。

    原实现每次右键都新建一个窗口，连点几次会叠出一排。
    这里把实例挂在 parent 上：已存在就聚焦，保证同时只有一个。
    """
    existing = getattr(parent, _WINDOW_ATTR, None)
    try:
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
    except tk.TclError:
        pass

    win = ChoiceWindow(parent, on_exit, on_minimize)
    setattr(parent, _WINDOW_ATTR, win)

    def _clear(_event, _win=win):
        if getattr(parent, _WINDOW_ATTR, None) is _win:
            setattr(parent, _WINDOW_ATTR, None)

    win.bind("<Destroy>", _clear)
    return win


class ChoiceWindow(tk.Toplevel):
    BG = "#fff7e6"

    def __init__(self, parent, on_exit, on_minimize):
        super().__init__(parent)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg=self.BG)
        self.geometry("250x140")
        self.update_idletasks()
        x = parent.winfo_rootx() + 20
        y = parent.winfo_rooty() + 20
        self.geometry(f"+{x}+{y}")

        tk.Label(self, text="要怎么关闭浮窗？", bg=self.BG,
                 font=(theme.FONT_FAMILY, 11)).pack(pady=(14, 6))

        row = tk.Frame(self, bg=self.BG)
        row.pack()
        tk.Button(row, text="退出程序", width=8,
                  command=lambda: (self.destroy(), on_exit())).pack(side="left", padx=4)
        tk.Button(row, text="最小化到托盘", width=11,
                  command=lambda: (self.destroy(), on_minimize())).pack(side="left", padx=4)
        tk.Button(self, text="取消", width=8, command=self.destroy).pack(pady=8)
