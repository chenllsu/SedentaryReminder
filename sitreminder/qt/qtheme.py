"""Qt6 主题常量与样式工具。

Qt 用 QColor/QFont/QPen，与 tk 的字符串色值不同。这里集中定义。
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont

TRANS_PARENT = QColor(0, 0, 0, 0)     # 完全透明
CARD_BG = QColor("#ffffff")           # （旧）气泡白卡，smoke_qt.py 仍引用
CARD_TEXT = QColor("#1d1d1f")         # （旧）主文案
CARD_SUBTEXT = QColor("#8e8e93")      # （旧）眉头标签灰
CARD_RULE = QColor("#e8e8ec")         # （旧）分隔线
BTN_BLUE = QColor("#007aff")          # （旧）主按钮
BTN_BLUE_HOVER = QColor("#0066d6")

# 贴纸设计语言（v0.7 统一：倒计时贴纸 / 关闭弹窗 / 提醒气泡共用）
STICKER_EDGE = QColor("#ffffff")           # 白色剪纸外沿
STICKER_BG = QColor("#FDF6EC")             # 奶米内芯
STICKER_BORDER = QColor("#D9C9B4")         # 内芯细描边
STICKER_TEXT = QColor("#5A4636")           # 深棕文字
STICKER_PAW = QColor("#8A6F56")            # 爪印棕
STICKER_BTN_BG = QColor("#ffffff")         # 次级按钮：白底
STICKER_BTN_HOVER = QColor("#F0DCB2")      # 次级按钮 hover
STICKER_ACCENT_BG = QColor("#F6C87E")      # 主按钮：琥珀（与暂停色同源）
STICKER_ACCENT_HOVER = QColor("#EFB25A")   # 主按钮 hover
STICKER_ACCENT_BORDER = QColor("#B8863B")  # 主按钮描边
STICKER_ACCENT_TEXT = QColor("#7A5217")    # 主按钮文字
STICKER_SHADOW = QColor(90, 70, 54, 70)    # 暖棕柔和阴影

# 倒计时胶囊（v0.6「爪印贴纸」）——配色取自妮子本体的奶咖色系
CAPSULE_STICKER_EDGE = QColor("#ffffff")   # 白色剪纸外描边（贴纸感）
CAPSULE_CREAM_BG = QColor("#FDF6EC")       # 平时：奶米底
CAPSULE_CREAM_BORDER = QColor("#D9C9B4")   # 平时：内芯细描边
CAPSULE_TEXT_BROWN = QColor("#5A4636")     # 平时：文字深棕
CAPSULE_PAW = QColor("#8A6F56")            # 平时：爪印
CAPSULE_PAUSED_BG = QColor("#F6C87E")      # 暂停：琥珀底（常亮）
CAPSULE_PAUSED_BORDER = QColor("#B8863B")  # 暂停：内芯描边
CAPSULE_PAUSED_TEXT = QColor("#7A5217")    # 暂停：文字与爪印
MASCOT_SHADOW_30 = QColor(20, 18, 24, 30)
MASCOT_SHADOW_20 = QColor(20, 18, 24, 20)
MASCOT_SHADOW_10 = QColor(20, 18, 24, 10)
WINDOW_BG = QColor("#f0f0f0")

# 间距 / 布局常量（Qt 版独立于此模块外引用）
SP_XS = 4
SP_SM = 8
SP_MD = 14
SP_LG = 22

# 气泡布局参数（v0.7：去标签行，只留正文 + 按钮，整体紧凑化）
BUBBLE_PAD_X = 18
BUBBLE_PAD_TOP = 14
BUBBLE_PAD_BOT = 12
BUBBLE_GAP_BODY_BTN = 12
BUBBLE_BTN_W = 84
BUBBLE_BTN_H = 26
BUBBLE_TAIL_LEN = 14
BUBBLE_TAIL_HALF = 10

# 主浮窗胶囊参数
CAPSULE_OFFSET_FROM_CAT = 18  # 胶囊与猫身外沿的像素距离

FONT_FAMILY = "Microsoft YaHei"
FONT_QUOTE = 13     # 提醒主文案（v0.7 由 15 收窄，v0.7.1 龙哥要求再小一档）
FONT_TAG = 11       # 眉头标签（旧样式保留，smoke_qt.py 引用）
FONT_BTN = 10
FONT_TIME = 12      # 倒计时等宽


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
