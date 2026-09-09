"""到点提醒气泡：白色卡片 + 细尾巴（始终指向妮子）+ 生长动画。"""

from __future__ import annotations

import tkinter as tk

from .. import theme
from .shapes import round_rect


class BubbleWindow(tk.Toplevel):
    WIDTH, HEIGHT = 300, 184
    PAD, TAIL, RADIUS = 16, 16, 14
    SCREEN_MARGIN = 8
    GAP = 14          # 气泡与妮子之间的距离

    def __init__(self, parent, text: str, on_confirm):
        super().__init__(parent)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        try:
            self.wm_attributes("-transparentcolor", theme.TRANS_KEY)
        except tk.TclError:
            pass  # Linux/X11 不一定支持透明色键，退化成实底色也能用
        self.configure(bg=theme.TRANS_KEY)

        self.on_confirm = on_confirm
        self.parent = parent
        self._text = text
        self._confirmed = False
        self._drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}

        width, height = self.WIDTH, self.HEIGHT
        self.width, self.height = width, height
        self._place(width, height)
        self._build()
        self._anim_i = 0
        self._animate()

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.bind("<Escape>", lambda _e: self.confirm())

    # ----- 定位：优先放在妮子上方，空间不够则放下方；尾巴始终指向本体 -----
    def _place(self, width, height):
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        px = self.parent.winfo_rootx()
        py = self.parent.winfo_rooty()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        cat_cx = px + pw // 2

        self.above = (py - height - self.GAP) >= 0
        x = cat_cx - width // 2
        y = (py - height - self.GAP) if self.above else (py + ph + self.GAP)
        x = max(self.SCREEN_MARGIN,
                min(x, screen_w - width - self.SCREEN_MARGIN))
        y = max(self.SCREEN_MARGIN,
                min(y, screen_h - height - self.SCREEN_MARGIN - 10))
        self.geometry(f"+{x}+{y}")

        # 尾巴尖（窗口内坐标）：x 对准妮子中心；窗口被屏幕边缘 clamp 后，
        # 要把尾巴 x 收在气泡范围内，保证「箭头永远指着本体」。
        pad = self.PAD
        tx = max(x + pad + 30, min(cat_cx, x + width - pad - 30)) - x
        ty = (height - pad) if self.above else pad
        self.anchor = (tx, ty)

        if self.above:
            self.body = (pad, pad, width - pad, height - pad - self.TAIL)
        else:
            self.body = (pad, pad + self.TAIL, width - pad, height - pad)

    def _build(self):
        self.canvas = tk.Canvas(self, width=self.WIDTH, height=self.HEIGHT,
                                bg=theme.TRANS_KEY, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        # 文案等动画结束后再出现，避免和小尺寸卡面打架
        self._label = tk.Label(self, text=self._text, bg=theme.CARD_BG,
                               fg=theme.CARD_TEXT, font=theme.FONT_QUOTE,
                               wraplength=self.WIDTH - 64, justify="center")

    # ----- 出现动画：从尾巴尖向气泡体生长 -----
    def _animate(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._render(theme.grow_scale(self._anim_i / theme.ANIM_STEPS))
        if self._anim_i >= theme.ANIM_STEPS:
            self._show_widgets()
            return
        self._anim_i += 1
        self.after(theme.ANIM_DELAY, self._animate)

    def _render(self, scale: float, button: bool = False):
        """按缩放系数（绕尾巴锚点）重绘气泡。"""
        canvas = self.canvas
        canvas.delete("all")
        ax, ay = self.anchor
        bx0, by0, bx1, by1 = self.body

        def T(point):
            return (ax + (point[0] - ax) * scale, ay + (point[1] - ay) * scale)

        # 阴影两层（远层大而淡 → 近层小而实），营造悬浮感
        p0 = T((bx0 + 6, by0 + 10))
        p1 = T((bx1 + 6, by1 + 10))
        round_rect(canvas, p0[0], p0[1], p1[0], p1[1], self.RADIUS * scale,
                   fill=theme.SHADOW_FAR, outline=theme.SHADOW_FAR, width=1)
        p0 = T((bx0 + 2, by0 + 4))
        p1 = T((bx1 + 2, by1 + 4))
        round_rect(canvas, p0[0], p0[1], p1[0], p1[1], self.RADIUS * scale,
                   fill=theme.SHADOW_NEAR, outline=theme.SHADOW_NEAR, width=1)
        # 纯白卡面（描边同色 = 无描边线）
        q0 = T((bx0, by0))
        q1 = T((bx1, by1))
        round_rect(canvas, q0[0], q0[1], q1[0], q1[1], self.RADIUS * scale,
                   fill=theme.CARD_BG, outline=theme.CARD_BG, width=1)
        # 尾巴：底边贴在气泡边缘，尖端固定在锚点
        if self.above:
            b1 = T((ax - 11, by1 - 1))
            b2 = T((ax + 11, by1 - 1))
        else:
            b1 = T((ax - 11, by0 + 1))
            b2 = T((ax + 11, by0 + 1))
        canvas.create_polygon(b1[0], b1[1], b2[0], b2[1], ax, ay,
                              fill=theme.CARD_BG, outline=theme.CARD_BG)
        if button:
            self._draw_button(canvas)

    # ----- 按钮 -----
    def _draw_button(self, canvas):
        """自绘圆角主按钮（带 hover 反馈）。

        重要：hover 只能 itemconfig 原地改色，绝不能 delete + 重建——
        删掉指针下的图元会触发 <Leave>，新建的又触发 <Enter>，
        两者互相重绘形成事件风暴，事件循环直接卡死（实测复现过）。
        """
        bx0, by0, _bx1, _by1 = self.body
        btn_w, btn_h = 96, 28
        cy = by0 + 102
        x0, x1 = self.WIDTH / 2 - btn_w / 2, self.WIDTH / 2 + btn_w / 2
        round_rect(canvas, x0, cy, x1, cy + btn_h, btn_h / 2,
                   fill=theme.BTN_BLUE, outline=theme.BTN_BLUE, width=1,
                   tags=("btn", "btnshape"))
        canvas.create_text(self.WIDTH / 2, cy + btn_h / 2, text="知道了",
                           font=theme.FONT_BTN, fill="white",
                           tags=("btn", "btntext"))
        canvas.tag_bind("btn", "<Button-1>", lambda _e: self.confirm())
        canvas.tag_bind("btn", "<Enter>", lambda _e: self._set_btn_color(theme.BTN_BLUE_HOVER))
        canvas.tag_bind("btn", "<Leave>", lambda _e: self._set_btn_color(theme.BTN_BLUE))

    def _set_btn_color(self, color: str):
        try:
            self.canvas.itemconfig("btnshape", fill=color, outline=color)
        except tk.TclError:
            pass

    def _show_widgets(self):
        bx0, by0, _bx1, _by1 = self.body
        self._render(1.0, button=True)
        # 眉头小标签
        self.canvas.create_text(self.WIDTH / 2, by0 + 28, text="久 坐 提 醒",
                                font=theme.FONT_TAG, fill=theme.CARD_SUBTEXT)
        # 标签下的细短线
        self.canvas.create_line(self.WIDTH / 2 - 12, by0 + 42,
                                self.WIDTH / 2 + 12, by0 + 42,
                                fill=theme.CARD_RULE, width=2)
        self._label.place(x=self.WIDTH / 2, y=by0 + 74, anchor="center")

    # ----- 拖动 -----
    def _on_press(self, event):
        self._drag["sx"] = event.x_root
        self._drag["sy"] = event.y_root
        self._drag["wx"] = self.winfo_x()
        self._drag["wy"] = self.winfo_y()

    def _on_drag(self, event):
        dx = event.x_root - self._drag["sx"]
        dy = event.y_root - self._drag["sy"]
        self.geometry(f"+{self._drag['wx'] + dx}+{self._drag['wy'] + dy}")

    # ----- 关闭 -----
    def confirm(self):
        if self._confirmed:
            return
        self._confirmed = True
        # Windows 上 <Button-1> 触发时窗口还持有隐式指针 grab，
        # 此时直接 destroy 会卡死事件循环，所以推迟到本轮事件结束后。
        self.after(80, self._do_confirm)

    def _do_confirm(self):
        try:
            if self.winfo_exists():
                self.destroy()
        except tk.TclError:
            pass
        if self.on_confirm:
            self.on_confirm()
