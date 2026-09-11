"""Qt6 关闭选择框：退出程序 / 最小化到托盘。

v0.7「爪印贴纸」统一（方案 A）：
  - 奶米内芯 + 白色剪纸外沿 + 细描边，与倒计时贴纸/提醒气泡同一套设计语言
  - 260×132 → 208×88 紧凑尺寸；去掉底部「取消」按钮——本窗是 Qt.Popup，
    点弹窗外部任意位置即关闭（等效取消），右上角另留一个小 ✕
  - 按钮必须显式配色：半透明 + Qt.Popup 窗口上，Qt 的 windows11 风格会把
    默认 QPushButton 画成白底白字融进卡片（实测 PrintWindow 抓图证实），
    hover/pressed 也要一并定死。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QPushButton,
    QVBoxLayout, QWidget,
)

from . import qtheme


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont(qtheme.FONT_FAMILY, px)
    f.setPixelSize(px)
    f.setBold(bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def _draw_paw(p: QPainter, cx: float, cy: float, s: float, color: QColor):
    """小爪印：掌垫 + 三趾（与倒计时贴纸同一画法）。"""
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    pad = QPainterPath()
    pad.addEllipse(QPointF(cx, cy + s * 0.55), s, s * 0.78)
    p.drawPath(pad)
    for dx, dy, r in ((-s * 1.02, -s * 0.42, s * 0.40),
                      (0.0, -s * 0.78, s * 0.44),
                      (s * 1.02, -s * 0.42, s * 0.40)):
        toe = QPainterPath()
        toe.addEllipse(QPointF(cx + dx, cy + dy), r, r)
        p.drawPath(toe)
    p.setBrush(Qt.NoBrush)   # drawPath 会带 brush 填充，画完必须清掉


class _PawTitle(QWidget):
    """「爪印 + 标题」组合居中的自绘行（贴纸语言的点睛）。"""

    def __init__(self, text: str):
        super().__init__()
        self._text = text
        self.setFixedHeight(20)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(_font(12, bold=True))
        tw = p.fontMetrics().horizontalAdvance(self._text)
        paw_w, gap = 12.5, 5
        x0 = (self.width() - (paw_w + gap + tw)) / 2
        _draw_paw(p, x0 + paw_w / 2, self.height() / 2 + 1, 4.4,
                  qtheme.STICKER_PAW)
        p.setPen(qtheme.STICKER_TEXT)
        p.drawText(QRectF(x0 + paw_w + gap, 0, tw + 6, self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, self._text)


class ChoiceWindow(QWidget):
    """轻量小窗，置于妮子浮窗旁。"""
    action_chosen = Signal(str)   # "exit" | "minimize" | "cancel"

    def __init__(self, ctrl, on_exit, on_minimize):
        super().__init__()
        self.ctrl = ctrl
        self.on_exit = on_exit
        self.on_minimize = on_minimize
        self.setWindowTitle("关闭浮窗")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Popup | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(208, 88)

        # 白色剪纸外沿（外层卡）+ 奶米内芯（内层卡，带细描边）
        edge = QFrame(self)
        edge.setObjectName("card_edge")
        edge.setGeometry(0, 0, 208, 88)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 2)
        shadow.setColor(qtheme.STICKER_SHADOW)
        edge.setGraphicsEffect(shadow)

        card = QFrame(edge)
        card.setObjectName("card")
        card.setGeometry(2, 2, 204, 84)
        # ⚠️ 按钮必须显式指定颜色（见模块 docstring），hover/pressed 一并定死。
        card.setStyleSheet(
            "#card { background: #FDF6EC; border: 1px solid #D9C9B4;"
            " border-radius: 12px; }"
            "#card QPushButton { background: #ffffff; color: #5A4636;"
            " border: 1px solid #D9C9B4; border-radius: 13px;"
            " font-size: 11px; }"
            "#card QPushButton:hover { background: #F0DCB2;"
            " border-color: #B8863B; }"
            "#card QPushButton:pressed { background: #E8CFA0; }"
            "#card QPushButton#close { background: transparent;"
            " border: none; color: #8A6F56; font-size: 12px; }"
            "#card QPushButton#close:hover { color: #5A4636;"
            " background: transparent; }"
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.addWidget(_PawTitle("要怎么关闭浮窗？"))

        row = QHBoxLayout()
        row.setSpacing(8)
        b_exit = QPushButton("退出程序")
        b_min = QPushButton("最小化到托盘")
        for b in (b_exit, b_min):
            b.setFixedHeight(26)
            b.setCursor(Qt.PointingHandCursor)
        b_exit.clicked.connect(lambda: (self.close(), self.on_exit()))
        b_min.clicked.connect(lambda: (self.close(), self.on_minimize()))
        row.addWidget(b_exit)
        row.addWidget(b_min)
        lay.addLayout(row)

        # 右上角 ✕ = 关闭弹窗（等效取消：不执行退出/最小化）
        b_close = QPushButton("✕", card)
        b_close.setObjectName("close")
        b_close.setFixedSize(18, 18)
        b_close.setCursor(Qt.PointingHandCursor)
        b_close.move(card.width() - 22, 4)
        b_close.raise_()

    def show_beside(self, ref):
        """置于妮子浮窗旁（右下偏移 24），并保证完整落在屏幕可用区内。

        原先直接用「妮子坐标 + 24」定位。妮子是可以被拖到任意位置的，
        一旦拖到屏幕右缘/下缘，弹窗就会有一多半跑到屏幕外，按钮点不到。
        这里补上边界收敛：右侧放不下就翻到妮子左侧，上下超出则内收。
        """
        ref_win = ref.window()
        ref_geo = ref_win.frameGeometry()
        scr = ref_win.screen() or self.screen()
        avail = scr.availableGeometry()

        w, h = self.width(), self.height()
        x = ref_geo.x() + 24
        y = ref_geo.y() + 24
        # 右边放不下 → 翻到妮子左侧
        if x + w > avail.right():
            x = ref_geo.left() - 24 - w
        # 兜底：无论落在哪一侧，都不许越出屏幕可用区
        x = max(avail.left(), min(x, avail.right() - w))
        y = max(avail.top(), min(y, avail.bottom() - h))
        self.move(x, y)
        self.show()
