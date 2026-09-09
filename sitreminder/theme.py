"""视觉常量与缓动函数。

以前这些数字散落在 800 行主文件里，改个颜色要全文搜索；
集中到这里后，样式调整只改这一个文件。
"""

from __future__ import annotations

# 透明色键：淡粉。Tk 的 -transparentcolor 是 1-bit 透明（要么全透要么不透），
# 所以要挑一个绝不会出现在猫身和控件配色里的颜色当「挖空色」。
# 必须是浅色：半透明阴影像素会和色键混色，接近黑色的键会混出黑边，
# 浅色键混出来还是浅色，才能做出真正羽化的柔边阴影。
TRANS_KEY = "#f0e5e7"

FONT_FAMILY = "Microsoft YaHei"
FONT_QUOTE = (FONT_FAMILY, 11)      # 提醒主文案
FONT_TAG = (FONT_FAMILY, 9)         # 眉头小标签
FONT_BTN = (FONT_FAMILY, 9)         # 按钮文字
FONT_TIME = ("Consolas", 12)        # 倒计时：等宽字体，跳秒时数字不抖动

# 气泡配色
CARD_BG = "white"
CARD_TEXT = "#1d1d1f"
CARD_SUBTEXT = "#8e8e93"
CARD_RULE = "#e8e8ec"
SHADOW_FAR = "#f1f1f4"
SHADOW_NEAR = "#e4e4e9"
BTN_BLUE = "#007aff"
BTN_BLUE_HOVER = "#0066d6"
TIME_CAPSULE = (30, 30, 34, 255)    # hover 倒计时胶囊底色（近黑）
TIME_TEXT = "#f5f5f7"
FALLBACK_CAPSULE = "#1e1e22"

# 动画节奏（气泡与倒计时胶囊共用同一套，视觉才统一）
ANIM_STEPS = 14      # 帧数
ANIM_DELAY = 14      # 帧间隔 ms，全程约 200ms
ANIM_HIDE_DELAY = 12
HOVER_HIDE_DELAY = 60   # 鼠标移开后延迟收起，避免在猫↔气泡之间移动时闪烁


def ease_out_back(t: float) -> float:
    """easeOutBack：末尾轻微回弹，弹出动作更「有生命感」。"""
    c1 = 1.70158
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def grow_scale(t: float) -> float:
    """把 0→1 的进度映射成 0.2→1.0 的缩放系数（带轻微过冲）。"""
    return min(max(0.2 + 0.8 * ease_out_back(t), 0.02), 1.08)
