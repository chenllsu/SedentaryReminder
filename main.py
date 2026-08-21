#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SitReminder - 久坐提醒小工具（浮窗仅显示妮子形象）
================================================
完全本地化，不联网。

界面规则（按龙哥要求）：
- 浮窗只显示妮子形象，背景透明（窗口透明色键，桌面透出）。
- 鼠标移到妮子上 → 显示剩余倒计时；移开 → 隐藏。
- 单击妮子 → 打开设置；右键妮子 → 退出/最小化菜单；按住拖动 → 移动浮窗。
- 到点弹漫画思考气泡框（内置 10 条诙谐文案随机展示），点确认后重新计时。

依赖（可选，用于系统托盘）：pip install pystray pillow
无该依赖时，关闭行为退化为「隐藏窗口」，其余功能不受影响。
"""

import os
import sys
import json
import random
import threading
from datetime import datetime, timedelta

import tkinter as tk
import tkinter.messagebox as mb

if getattr(sys, "frozen", False):
    # PyInstaller 打包运行：资源在临时解包目录；config.json 必须写到
    # exe 旁边，否则 onefile 每次运行后配置丢失。
    BASE_DIR = os.path.dirname(sys.executable)
    ASSET_DIR = os.path.join(sys._MEIPASS, "assets")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ASSET_DIR = os.path.join(BASE_DIR, "assets")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MASCOT_PATH = os.path.join(ASSET_DIR, "nizi_clean.png")  # 已抠掉背景的透明版本

DEFAULT_CONFIG = {"interval_seconds": 1800, "autostart": False}
TRANS_KEY = "#f0e5e7"  # 透明色键：淡粉，已验证不出现在猫身/控件配色中。
# 关键：色键必须是浅色。半透明阴影像素会和色键混色——
# 近黑色键会混出黑边，浅色键混出的还是浅色，才能做真羽化柔边阴影。

# 简洁字体（Windows 用微软雅黑）
FONT_QUOTE = ("Microsoft YaHei", 11)   # 提醒主文案
FONT_TAG   = ("Microsoft YaHei", 9)    # 眉头小标签
FONT_BTN   = ("Microsoft YaHei", 9)    # 按钮文字
FONT_TIME  = ("Consolas", 12)          # 倒计时（等宽数字，跳秒不抖动）

# ---------------------------------------------------------------- 配置
def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("interval_seconds", DEFAULT_CONFIG["interval_seconds"])
    cfg.setdefault("autostart", DEFAULT_CONFIG["autostart"])
    # 兼容旧配置：曾用 interval_minutes
    if "interval_minutes" in cfg and "interval_seconds" not in cfg:
        try:
            cfg["interval_seconds"] = int(cfg["interval_minutes"]) * 60
        except Exception:
            cfg["interval_seconds"] = DEFAULT_CONFIG["interval_seconds"]
        del cfg["interval_minutes"]
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


CONFIG = load_config()

# ---------------------------------------------------------------- 文案（附录 A）
QUIPS = [
    "屁股已经和椅子谈恋爱了，去分开它们五分钟吧～",
    "你的脊椎正在默默吐槽：我就没直起来过？",
    "再不动一动，椅子就要长在你身上了哦。",
    "起来！别让血液只在屁股那一块循环。",
    "颈椎发来消息：主人，我也想伸个懒腰。",
    "据说站起来的人，比坐着的人更接近健康。",
    "你的腿：主人，你还记得我有吗？",
    "久坐一时爽，起来才发现——原来腿还是自己的。",
    "给眼睛和屁股都放个假吧，站起来看看远方。",
    "警告：检测到人类已进化成蘑菇，请起身恢复人形。",
]

# ---------------------------------------------------------------- 计时状态
class TimerState:
    def __init__(self, seconds):
        self.interval = max(5, int(seconds))
        self.paused = False
        self._remaining = self.interval
        self._end = None
        self.reset()

    def reset(self):
        self._end = datetime.now() + timedelta(seconds=self.interval)
        self.paused = False

    def skip(self):
        self.reset()

    def pause(self):
        if not self.paused:
            self._remaining = max(0, (self._end - datetime.now()).total_seconds())
            self.paused = True

    def resume(self):
        if self.paused:
            self._end = datetime.now() + timedelta(seconds=self._remaining)
            self.paused = False

    def remaining(self):
        if self.paused:
            return int(self._remaining)
        return max(0, int((self._end - datetime.now()).total_seconds()))

    def set_interval(self, seconds):
        self.interval = max(5, int(seconds))
        self.reset()


# ---------------------------------------------------------------- 图片加载
def _hex_to_rgba(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def load_mascot(size=(150, 150)):
    """加载妮子形象。

    抠图阶段已做 defringe（边缘颜色=本体色）与羽化（渐变 alpha）。
    本体 alpha 强制二值化 + 先平滑 mask 再二值化，消除硬锯齿；
    阴影走半透明渐变（色键是浅色，混色不会发黑），blur 在显示分辨率做。
    """
    if not os.path.exists(MASCOT_PATH):
        return None
    try:
        from PIL import Image, ImageFilter, ImageTk
        src = Image.open(MASCOT_PATH).convert("RGBA")
        src = src.transpose(Image.FLIP_LEFT_RIGHT)  # 水平镜像（原图保持不动）
        # 1) 平滑 + 二值化的不透明 mask（边缘无毛刺、无半透明）
        mask = src.split()[3].point(lambda a: 255 if a > 128 else 0)
        mask = mask.filter(ImageFilter.GaussianBlur(1.5)).point(
            lambda a: 255 if a > 128 else 0)
        # 2) RGB 与 mask 同步缩放到目标尺寸，保证对齐
        src_s = src.resize(size, Image.LANCZOS)
        mask_s = mask.resize(size, Image.LANCZOS).point(
            lambda a: 255 if a > 128 else 0)
        cat = Image.new("RGBA", size, (0, 0, 0, 0))
        cat.paste(src_s, (0, 0), mask_s)
        cat.putalpha(mask_s)  # 强制二值 alpha（源图渐变 alpha 会带来黑边）
        # 3) 柔边阴影：色键已换浅色，半透明像素向浅色混合不再发黑，
        #    可以做真羽化渐变阴影。
        #    blur 必须在最终显示分辨率上做——之前在 1920px 源图上模糊
        #    再缩到 150px，模糊量被缩小倍率吃掉（等效 <1px），阴影显硬。
        # 小尺寸 + 低透明度 + 强羽化：sigma 保持较大让边缘全是平滑渐变，
        # 靠「压低最大 alpha + 缩小偏移」把阴影整体缩小、变淡。
        sh_alpha = mask_s.filter(ImageFilter.GaussianBlur(2.2))
        sh_layer = Image.new("RGBA", size, (135, 130, 136, 80))  # 更淡的暖灰
        sh_img = Image.new("RGBA", size, (0, 0, 0, 0))
        sh_img.paste(sh_layer, (0, 0), sh_alpha)
        # 4) 合成到全透明底色；阴影向右下角偏移
        pad = 14
        W, H = size[0] + pad * 2, size[1] + pad * 2
        base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        base.paste(sh_img, (pad + 1, pad + 1), sh_img)  # 阴影偏右下
        base.paste(cat, (pad, pad), cat)
        return ImageTk.PhotoImage(base)
    except Exception:
        try:
            return tk.PhotoImage(file=MASCOT_PATH)
        except Exception:
            return None


# ---------------------------------------------------------------- 通用 UI 小部件（苹果极简风辅助）
def _round_rect_canvas(c, x0, y0, x1, y1, r, **kw):
    """在 Canvas 上画圆角矩形（Tk 无原生 round_rect）。"""
    c.create_arc(x0, y0, x0 + 2 * r, y0 + 2 * r, start=90, extent=90, style="pieslice", **kw)
    c.create_arc(x1 - 2 * r, y0, x1, y0 + 2 * r, start=0, extent=90, style="pieslice", **kw)
    c.create_arc(x1 - 2 * r, y1 - 2 * r, x1, y1, start=270, extent=90, style="pieslice", **kw)
    c.create_arc(x0, y1 - 2 * r, x0 + 2 * r, y1, start=180, extent=90, style="pieslice", **kw)
    c.create_rectangle(x0 + r, y0, x1 - r, y1, **kw)
    c.create_rectangle(x0, y0 + r, x1, y1 - r, **kw)


def _make_time_frames():
    """预生成 hover 倒计时小气泡的动画帧。

    深色紧凑胶囊（近黑底），无尾巴。
    深色小胶囊与白色提醒大卡形成「深浅两级」视觉层级：
    轻信息=深色悬浮，重要提醒=白卡。数字用等宽字体，跳秒不抖。
    动画 = 绕顶边中点锚点（靠妮子一侧）从 0.2 生长到 1.0
    （easeOutBack 带轻微回弹），与提醒大气泡同一套节奏。
    3x 超采样抗锯齿。PIL 缺失时返回 None。
    """
    try:
        from PIL import Image, ImageDraw, ImageTk
    except Exception:
        return None
    W, H = 150, 44
    bw, bh = 112, 30                    # 胶囊本体
    bx = (W - bw) // 2
    by = 7
    ax, ay = W / 2, by                  # 生长锚点 = 顶边中点（朝向妮子）
    SS = 3                              # 超采样倍数
    DARK = (30, 30, 34, 255)            # 近黑胶囊

    def ease_out_back(t):
        c1 = 1.70158
        return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2

    n = 14
    frames = []
    for i in range(n + 1):
        t = i / n
        s = min(max(0.2 + 0.8 * ease_out_back(t), 0.02), 1.08)
        img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def T(x, y):
            return ((ax + (x - ax) * s) * SS, (ay + (y - ay) * s) * SS)

        q0 = T(bx, by); q1 = T(bx + bw, by + bh)                    # 胶囊
        d.rounded_rectangle([q0[0], q0[1], q1[0], q1[1]], radius=bh / 2 * s * SS,
                            fill=DARK)
        frames.append(ImageTk.PhotoImage(img.resize((W, H), Image.LANCZOS)))
    return frames


# ---------------------------------------------------------------- 漫画气泡框
class BubbleWindow(tk.Toplevel):
    """提醒气泡：白色高级卡片 + 细尾巴（始终指向妮子）+ 生长过渡动画。

    设计语言（清晰 / 简洁 / 高级）：
    - 纯白卡面，无描边；阴影分两层（近层实、远层淡）营造悬浮感
    - 眉头小标签（灰色小字）+ 主文案 + 单个圆角主按钮，层级分明
    - 深色倒计时小胶囊与本白卡形成「深浅两级」视觉层级
    """

    ANIM_STEPS = 14   # 动画帧数
    ANIM_DELAY = 14   # 每帧间隔 ms（全程约 200ms）

    def __init__(self, parent, text, on_confirm):
        super().__init__(parent)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        try:
            self.wm_attributes("-transparentcolor", TRANS_KEY)
        except Exception:
            pass
        self.configure(bg=TRANS_KEY)
        self.on_confirm = on_confirm
        self.parent = parent
        self._drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0}

        self.w, self.h = w, h = 300, 184
        self.pad, self.tail, self.r = 16, 16, 14
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        cat_cx = px + pw // 2            # 妮子中心（尾巴指向目标）
        above = (py - h - 14) >= 0       # 上方空间够 → 气泡放上面，尾巴朝下
        self.above = above
        x = cat_cx - w // 2
        y = (py - h - 14) if above else (py + ph + 14)
        x = max(8, min(x, sw - w - 8))
        y = max(8, min(y, sh - h - 10))
        self.geometry(f"+{x}+{y}")

        # 尾巴尖（窗口内坐标）：x 始终对准妮子中心；被屏幕边缘 clamp 后
        # 仍把尾巴 x 收在气泡范围内，保证「箭头永远指着本体」。
        pad = self.pad
        tx = max(x + pad + 30, min(cat_cx, x + w - pad - 30)) - x
        ty = (h - pad) if above else pad
        self.anchor = (tx, ty)           # 动画生长锚点 = 尾巴尖

        # 气泡本体矩形（全尺寸）
        if above:
            self.body = (pad, pad, w - pad, h - pad - self.tail)
        else:
            self.body = (pad, pad + self.tail, w - pad, h - pad)

        self.canvas = tk.Canvas(self, width=w, height=h, bg=TRANS_KEY,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # 文案（动画结束后出现）
        self._label = tk.Label(self, text=text, bg="white", fg="#1d1d1f",
                               font=FONT_QUOTE, wraplength=w - 64, justify="center")

        self._anim_i = 0
        self._animate()

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.bind("<Escape>", lambda e: self.confirm())

    # ----- 出现动画：easeOutBack，从尾巴尖向气泡体生长 -----
    def _animate(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        i, n = self._anim_i, self.ANIM_STEPS
        t = i / n
        c1 = 1.70158
        e = 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2   # easeOutBack
        scale = 0.2 + 0.8 * e                                  # 0.2 → 1(轻微回弹)
        self._render(min(max(scale, 0.02), 1.08))
        if i >= n:
            self._show_widgets()
            return
        self._anim_i += 1
        self.after(self.ANIM_DELAY, self._animate)

    def _render(self, s, button=False):
        """按缩放系数 s（绕尾巴锚点）重绘气泡形状。"""
        c = self.canvas
        c.delete("all")
        ax, ay = self.anchor
        bx0, by0, bx1, by1 = self.body

        def T(p):
            return (ax + (p[0] - ax) * s, ay + (p[1] - ay) * s)

        # 阴影两层（远层大而淡 → 近层小而实），营造悬浮感
        p0 = T((bx0 + 6, by0 + 10)); p1 = T((bx1 + 6, by1 + 10))
        _round_rect_canvas(c, p0[0], p0[1], p1[0], p1[1], self.r * s,
                           fill="#f1f1f4", outline="#f1f1f4", width=1)
        p0 = T((bx0 + 2, by0 + 4)); p1 = T((bx1 + 2, by1 + 4))
        _round_rect_canvas(c, p0[0], p0[1], p1[0], p1[1], self.r * s,
                           fill="#e4e4e9", outline="#e4e4e9", width=1)
        # 纯白卡面（描边同色，无线）
        q0 = T((bx0, by0)); q1 = T((bx1, by1))
        _round_rect_canvas(c, q0[0], q0[1], q1[0], q1[1], self.r * s,
                           fill="white", outline="white", width=1)
        # 尾巴（略窄，更利落）：底边在气泡边缘，尖端固定在锚点
        if self.above:
            b1 = T((ax - 11, by1 - 1)); b2 = T((ax + 11, by1 - 1))
        else:
            b1 = T((ax - 11, by0 + 1)); b2 = T((ax + 11, by0 + 1))
        c.create_polygon(b1[0], b1[1], b2[0], b2[1], ax, ay,
                         fill="white", outline="white")
        if button:
            self._draw_button(c)

    def _draw_button(self, c):
        """自绘圆角主按钮（带 hover 反馈）。

        关键：hover 只允许 itemconfig 原地改色，绝不能 delete+重建——
        删掉指针下的图元会触发 <Leave>、新建的又触发 <Enter>，
        两者互相重绘形成事件风暴，事件循环直接卡死（已实测复现）。
        """
        w = self.w
        bx0, by0, bx1, by1 = self.body
        cy = by0 + 102                     # 按钮纵向中心
        bw, bh = 96, 28
        x0, x1 = w / 2 - bw / 2, w / 2 + bw / 2
        _round_rect_canvas(c, x0, cy, x1, cy + bh, bh / 2,
                           fill="#007aff", outline="#007aff", width=1,
                           tags=("btn", "btnshape"))
        c.create_text(w / 2, cy + bh / 2, text="知道了",
                      font=FONT_BTN, fill="white", tags=("btn", "btntext"))
        c.tag_bind("btn", "<Button-1>", lambda e: self.confirm())
        c.tag_bind("btn", "<Enter>", self._btn_enter)
        c.tag_bind("btn", "<Leave>", self._btn_leave)

    def _btn_enter(self, e):
        self._set_btn_color("#0066d6")

    def _btn_leave(self, e):
        self._set_btn_color("#007aff")

    def _set_btn_color(self, color):
        try:
            self.canvas.itemconfig("btnshape", fill=color, outline=color)
        except Exception:
            pass

    def _show_widgets(self):
        w = self.w
        bx0, by0, bx1, by1 = self.body
        # 卡面 + 按钮（_render 会清空画布，先画）
        self._render(1.0, button=True)
        # 眉头小标签（灰色小字）
        self.canvas.create_text(w / 2, by0 + 28, text="久 坐 提 醒",
                                font=FONT_TAG, fill="#8e8e93")
        # 标签下的细短线（居中 24px）
        self.canvas.create_line(w / 2 - 12, by0 + 42, w / 2 + 12, by0 + 42,
                                fill="#e8e8ec", width=2)
        # 主文案
        self._label.place(x=w / 2, y=by0 + 74, anchor="center")

    def _on_press(self, e):
        self._drag["sx"] = e.x_root
        self._drag["sy"] = e.y_root
        self._drag["wx"] = self.winfo_x()
        self._drag["wy"] = self.winfo_y()

    def _on_drag(self, e):
        dx = e.x_root - self._drag["sx"]
        dy = e.y_root - self._drag["sy"]
        self.geometry(f"+{self._drag['wx'] + dx}+{self._drag['wy'] + dy}")

    def confirm(self):
        if getattr(self, "_confirmed", False):
            return
        self._confirmed = True
        # Windows 上 <Button-1> 触发时窗口还持有隐式指针 grab，
        # 此时直接 destroy 会卡死整个事件循环。延迟到本轮事件结束后再销毁。
        self.after(80, self._do_confirm)

    def _do_confirm(self):
        try:
            if self.winfo_exists():
                self.destroy()
        except Exception:
            pass
        if self.on_confirm:
            self.on_confirm()


# ---------------------------------------------------------------- 关闭选择框
class ChoiceWindow(tk.Toplevel):
    def __init__(self, parent, on_exit, on_minimize):
        super().__init__(parent)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg="#fff7e6")
        self.geometry("250x140")
        self.update_idletasks()
        x = parent.winfo_rootx() + 20
        y = parent.winfo_rooty() + 20
        self.geometry(f"+{x}+{y}")

        tk.Label(self, text="要怎么关闭浮窗？",
                 bg="#fff7e6", font=("Microsoft YaHei", 11)).pack(pady=(14, 6))
        frm = tk.Frame(self, bg="#fff7e6")
        frm.pack()
        tk.Button(frm, text="退出程序", width=8,
                  command=lambda: (self.destroy(), on_exit())).pack(side="left", padx=4)
        tk.Button(frm, text="最小化到托盘", width=11,
                  command=lambda: (self.destroy(), on_minimize())).pack(side="left", padx=4)
        tk.Button(self, text="取消", width=8, command=self.destroy).pack(pady=8)


# ---------------------------------------------------------------- 设置窗口（原生系统窗口风格：标准标题栏/关闭/拖动）
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, cfg, app):
        super().__init__(parent)
        self.app = app
        self.title("设置 · 久坐提醒")
        self.configure(bg="#f0f0f0")
        self.resizable(False, False)
        F = ("Microsoft YaHei", 9)  # 小字号

        secs = int(cfg["interval_seconds"])
        is_min = (secs % 60 == 0 and secs >= 60)
        self.unit = tk.StringVar(value="分钟" if is_min else "秒")
        self.var = tk.StringVar(value=str(secs // 60 if is_min else secs))
        self.auto = tk.BooleanVar(value=bool(cfg["autostart"]))

        frm = tk.Frame(self, bg="#f0f0f0")
        frm.pack(fill="both", expand=True, padx=14, pady=10)

        row1 = tk.Frame(frm, bg="#f0f0f0")
        row1.pack(fill="x", pady=(0, 8))
        tk.Label(row1, text="提醒间隔", bg="#f0f0f0", font=F).pack(side="left")
        tk.Entry(row1, textvariable=self.var, width=6, justify="center",
                 font=F).pack(side="left", padx=(10, 4))
        om = tk.OptionMenu(row1, self.unit, "分钟", "秒")
        om.config(font=F)
        om.pack(side="left")

        tk.Checkbutton(frm, text="开机自动启动", variable=self.auto,
                       bg="#f0f0f0", font=F, anchor="w"
                       ).pack(fill="x", pady=(0, 10))

        row2 = tk.Frame(frm, bg="#f0f0f0")
        row2.pack(fill="x")
        tk.Button(row2, text="暂停/继续", command=self._toggle_pause,
                  font=F).pack(side="left", padx=(0, 6))
        tk.Button(row2, text="跳过本次", command=self._skip,
                  font=F).pack(side="left", padx=(0, 6))
        tk.Button(row2, text="保存", command=self.save,
                  font=F).pack(side="right")

        # 出现在浮窗右侧（被屏幕边缘 clamp）
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = parent.winfo_rootx() + parent.winfo_width() + 12
        y = parent.winfo_rooty()
        x = max(8, min(x, sw - w - 8))
        y = max(8, min(y, sh - h - 8))
        self.geometry(f"+{x}+{y}")

    def _toggle_pause(self):
        self.app.toggle_pause()

    def _skip(self):
        self.app.on_skip()

    def save(self):
        try:
            v = int(self.var.get())
        except ValueError:
            v = -1
        unit = self.unit.get()
        if unit == "分钟":
            if not (1 <= v <= 600):
                mb.showerror("输入错误", "请输入 1-600 之间的整数分钟")
                return
            secs = v * 60
        else:
            if not (5 <= v <= 36000):
                mb.showerror("输入错误", "请输入 5-36000 之间的整数秒（≥5）")
                return
            secs = v
        self.app.apply_settings(secs, self.auto.get())
        self.destroy()


# ---------------------------------------------------------------- 主应用
class App:
    def __init__(self):
        self.cfg = dict(CONFIG)
        self.timer = TimerState(self.cfg["interval_seconds"])
        self.root = tk.Tk()
        self.root.title("久坐提醒 · 妮子")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg=TRANS_KEY)
        # 透明色键：让 TRANS_KEY 区域透出桌面
        try:
            self.root.wm_attributes("-transparentcolor", TRANS_KEY)
        except Exception:
            pass
        self.root.geometry("210x214+40+40")

        self._drag = {"sx": 0, "sy": 0, "moved": False}
        self._bubble = None
        self._settings = None
        self.tray_icon = None
        self.hover = False

        self._build_ui()
        self._start_tray()
        self._tick()
        self.root.mainloop()

    # ----- UI：只留妮子 -----
    def _build_ui(self):
        self.mascot = load_mascot((150, 150))
        if self.mascot:
            self.img_label = tk.Label(self.root, image=self.mascot,
                                      bg=TRANS_KEY, bd=0, cursor="hand2")
        else:
            self.img_label = tk.Label(self.root, text="(妮子形象\n未找到)",
                                      bg=TRANS_KEY, fg="#999")
        self.img_label.place(relx=0.5, rely=0.46, anchor="center")

        # 倒计时小气泡（默认隐藏，hover 显示，生长动画）；place 绝对定位不挤压图片
        self.time_canvas = tk.Canvas(self.root, width=150, height=44,
                                     bg=TRANS_KEY, highlightthickness=0)
        self.time_canvas.place_forget()  # 初始隐藏
        self._time_frames = None         # 动画帧（首次 hover 懒加载）
        self._time_after = None          # 动画调度 id
        self._time_txt = ""
        self._time_text_id = None

        # 鼠标在猫和气泡间移动时保持显示
        for wgt in (self.img_label, self.time_canvas):
            wgt.bind("<Enter>", self._on_enter)
            wgt.bind("<Leave>", self._on_leave)
        self.img_label.bind("<ButtonPress-1>", self._on_press)
        self.img_label.bind("<B1-Motion>", self._on_drag)
        self.img_label.bind("<ButtonRelease-1>", self._on_release)
        self.img_label.bind("<Button-3>", self.on_close)  # 右键关闭菜单

    def _draw_time(self, txt):
        self._time_txt = txt
        if self._time_text_id is not None:
            try:
                self.time_canvas.itemconfig(self._time_text_id, text=txt)
            except Exception:
                pass

    # ----- 倒计时气泡的显示/隐藏动画 -----
    def _cancel_time_anim(self):
        if self._time_after is not None:
            try:
                self.root.after_cancel(self._time_after)
            except Exception:
                pass
            self._time_after = None

    def _on_enter(self, e):
        self.hover = True
        if self._time_frames is None:
            self._time_frames = _make_time_frames()
        if not self._time_frames:      # PIL 缺失：无动画，直接显示文字
            self._draw_time_fallback()
            return
        self._cancel_time_anim()
        if self.time_canvas.winfo_ismapped() and self._time_text_id is not None:
            return                     # 已完整显示，不重播动画
        self.time_canvas.place(relx=0.5, rely=1.0, anchor="s", y=-2)
        self._time_text_id = None
        self._show_time_frame(0)

    def _draw_time_fallback(self):
        """无 PIL 时的降级绘制：Canvas 矢量深色胶囊 + 白字。"""
        c = self.time_canvas
        c.delete("all")
        _round_rect_canvas(c, 19, 7, 131, 37, 15, fill="#1e1e22",
                           outline="#1e1e22", width=1)
        self._time_text_id = c.create_text(75, 22, text=self._time_txt,
                                           font=FONT_TIME, fill="#f5f5f7")
        c.place(relx=0.5, rely=1.0, anchor="s", y=-2)

    def _show_time_frame(self, i):
        frames = self._time_frames
        idx = min(i, len(frames) - 1)
        self.time_canvas.delete("all")
        self.time_canvas.create_image(0, 0, image=frames[idx], anchor="nw")
        if idx >= len(frames) - 1:     # 末帧：加文字（胶囊中心）
            self._time_text_id = self.time_canvas.create_text(
                75, 22, text=self._time_txt, font=FONT_TIME, fill="#f5f5f7")
            self._time_after = None
            return
        self._time_after = self.root.after(
            14, lambda: self._show_time_frame(i + 1))

    def _on_leave(self, e):
        self.hover = False
        self._cancel_time_anim()
        if not self._time_frames:
            self.time_canvas.place_forget()
            return
        # 延迟 60ms 再收起：鼠标在猫↔气泡间移动不闪烁
        self._time_after = self.root.after(60, self._hide_time_frame_start)

    def _hide_time_frame_start(self):
        if self.hover:                 # 期间又回到猫/气泡上
            self._time_after = None
            return
        self._time_text_id = None
        self._hide_time_frame(1)

    def _hide_time_frame(self, i):
        if self.hover:
            self._time_after = None
            return
        frames = self._time_frames
        idx = len(frames) - 1 - i
        if idx <= 0:
            self.time_canvas.delete("all")
            self.time_canvas.place_forget()
            self._time_after = None
            return
        self.time_canvas.delete("all")
        self.time_canvas.create_image(0, 0, image=frames[idx], anchor="nw")
        self._time_after = self.root.after(
            12, lambda: self._hide_time_frame(i + 1))

    def _on_press(self, e):
        # 记录鼠标起点 AND 窗口起点（关键：拖动时用窗口起点+累计位移，
        # 不能每次都用 winfo_x() 叠加，否则越拖越飞）
        self._drag["sx"] = e.x_root
        self._drag["sy"] = e.y_root
        self._drag["wx"] = self.root.winfo_x()
        self._drag["wy"] = self.root.winfo_y()
        self._drag["moved"] = False

    def _on_drag(self, e):
        dx = e.x_root - self._drag["sx"]
        dy = e.y_root - self._drag["sy"]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag["moved"] = True
        x = self._drag["wx"] + dx
        y = self._drag["wy"] + dy
        self.root.geometry(f"+{x}+{y}")

    def _on_release(self, e):
        # 没怎么移动 = 单击 → 打开设置
        if not self._drag["moved"]:
            self.open_settings()

    # ----- 计时循环 -----
    def _tick(self):
        if not self.timer.paused:
            rem = self.timer.remaining()
            m, s = divmod(rem, 60)
            txt = f"{m:02d}:{s:02d}"
            if rem <= 0:
                self.pop_bubble()
        else:
            m, s = divmod(self.timer.remaining(), 60)
            txt = f"{m:02d}:{s:02d} ⏸"
        if self.hover:
            self._draw_time(txt)
        self.root.after(250, self._tick)

    def pop_bubble(self):
        if self._bubble and self._bubble.winfo_exists():
            return
        self._bubble = BubbleWindow(self.root, random.choice(QUIPS), self.timer.reset)

    # ----- 控制 -----
    def toggle_pause(self):
        if self.timer.paused:
            self.timer.resume()
        else:
            self.timer.pause()

    def on_skip(self):
        self.timer.skip()

    def open_settings(self):
        # 已打开则聚焦，避免重复创建多个设置窗口
        if self._settings and self._settings.winfo_exists():
            self._settings.lift()
            self._settings.focus_force()
            return
        try:
            self._settings = SettingsWindow(self.root, self.cfg, self)
            self._settings.bind("<Destroy>", lambda e: self._clear_settings())
        except Exception as ex:
            import traceback
            traceback.print_exc()
            mb.showerror("打开设置失败", f"{type(ex).__name__}: {ex}")

    def _clear_settings(self):
        self._settings = None

    def apply_settings(self, interval_seconds, autostart):
        self.cfg["interval_seconds"] = interval_seconds
        self.cfg["autostart"] = autostart
        save_config(self.cfg)
        self.timer.set_interval(interval_seconds)
        # TODO: 开机自启各平台写入逻辑（Win 注册表 / macOS plist / Linux .desktop）后续实现

    # ----- 关闭 -----
    def on_close(self, event=None):
        ChoiceWindow(self.root, self.do_exit, self.do_minimize)

    def do_exit(self):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()

    def do_minimize(self):
        self.root.withdraw()

    # ----- 系统托盘（可选） -----
    def _start_tray(self):
        try:
            import pystray
            from PIL import Image
            if os.path.exists(MASCOT_PATH):
                icon_img = Image.open(MASCOT_PATH).convert("RGBA").resize((64, 64))
            else:
                icon_img = Image.new("RGBA", (64, 64), (255, 200, 0, 255))
            menu = pystray.Menu(
                pystray.MenuItem("显示浮窗", self._tray_show),
                pystray.MenuItem("暂停/继续", lambda i, e: self.toggle_pause()),
                pystray.MenuItem("跳过本次", lambda i, e: self.on_skip()),
                pystray.MenuItem("退出", self._tray_exit),
            )
            self.tray_icon = pystray.Icon("sit_reminder", icon_img, "久坐提醒·妮子", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception:
            self.tray_icon = None

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)

    def _tray_exit(self, icon=None, item=None):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)


if __name__ == "__main__":
    App()
