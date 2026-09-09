"""Qt6 主题常量与样式工具。

Qt 用 QColor/QFont/QPen，与 tk 的字符串色值不同。这里集中定义。
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

TRANS_PARENT = QColor(0, 0, 0, 0)     # 完全透明
CARD_BG = QColor("#ffffff")           # 气泡白卡
CARD_TEXT = QColor("#1d1d1f")         # 主文案
CARD_SUBTEXT = QColor("#8e8e93")      # 眉头标签灰
CARD_RULE = QColor("#e8e8ec")         # 分隔线
BTN_BLUE = QColor("#007aff")          # 主按钮
BTN_BLUE_HOVER = QColor("#0066d6")
SHADOW_NEAR = QColor(30, 30, 34, 22)  # 近层阴影（真半透明）
SHADOW_FAR = QColor(30, 30, 34, 10)   # 远层淡阴影
CAPSULE_BG = QColor(30, 30, 34, 255)  # hover 胶囊底
CAPSULE_TEXT = QColor("#f5f5f7")
MASCOT_SHADOW_30 = QColor(20, 18, 24, 30)
MASCOT_SHADOW_20 = QColor(20, 18, 24, 20)
MASCOT_SHADOW_10 = QColor(20, 18, 24, 10)
CHOICE_BG = QColor("#fff7e6")
WINDOW_BG = QColor("#f0f0f0")

# 间距 / 布局常量（Qt 版独立于此模块外引用）
SP_XS = 4
SP_SM = 8
SP_MD = 14
SP_LG = 22

# 气泡布局参数
BUBBLE_PAD_X = 24
BUBBLE_PAD_TOP = 18
BUBBLE_PAD_BOT = 16
BUBBLE_GAP_LABEL_RULE = 8
BUBBLE_GAP_RULE_BODY = 14
BUBBLE_GAP_BODY_BTN = 18
BUBBLE_BTN_W = 104
BUBBLE_BTN_H = 32
BUBBLE_RULE_W = 24
BUBBLE_TAIL_LEN = 18
BUBBLE_TAIL_HALF = 12

# 主浮窗胶囊参数
CAPSULE_OFFSET_FROM_CAT = 18  # 胶囊与猫身外沿的像素距离

FONT_FAMILY = "Microsoft YaHei"
FONT_QUOTE = 15     # 提醒主文案
FONT_TAG = 11       # 眉头标签
FONT_BTN = 10
FONT_TIME = 14      # 倒计时等宽


def make_font(px: int, bold: bool = False, family: str = FONT_FAMILY) -> QFont:
    f = QFont(family, px)
    f.setPixelSize(px)
    f.setBold(bold)
    f.setStyleStrategy(QFont.PreferAntialias)   # 强制抗锯齿
    return f


def make_time_font(px: int = FONT_TIME) -> QFont:
    # 等宽数字字体，避免跳秒抖动
    f = QFont("Consolas", px)
    f.setPixelSize(px)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def rgba(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c
