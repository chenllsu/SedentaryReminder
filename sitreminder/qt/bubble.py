"""Qt6 提醒气泡：白卡 + 真羽化阴影 + 抗锯齿文字 + 尾巴自动指向妮子。

相比 Tk：阴影是真 alpha 渐变（无 1-bit 阶梯）、文字 QPainter 抗锯齿清晰、
卡片圆角由 QPainterPath 生成（无像素锯齿）。

v0.4 改造：
  - 位置策略：枚举四个方向（上下左右），优先放"贴猫且不出屏幕"的位置；
    尾巴方向跟随位置动态指向猫
  - 文字布局：QRectF 分层，间距用 qtheme 常量统一控制

v0.7 改造（「爪印贴纸」统一）：
  - 去掉「久坐提醒」标签行与分隔线，只留正文 + 琥珀「知道了」按钮
  - 白卡 → 奶米贴纸卡（白剪纸外沿 + 细描边），与倒计时贴纸/关闭弹窗同一套语言
  - 320×200 → 260×148，内边距与按钮同步收紧，阴影改暖棕调
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QFont, QFontMetrics,
)
from PySide6.QtWidgets import QWidget

from . import qtheme

log = logging.getLogger(__name__)

# 整窗尺寸（含透明边距，给阴影留空间）
# v0.7：去标签行只留正文+按钮，320×200 → 260×148，贴纸化配色
W = 260
H = 148
MARGIN = 20
RADIUS = 14
TAIL_LEN = qtheme.BUBBLE_TAIL_LEN
TAIL_HALF = qtheme.BUBBLE_TAIL_HALF

CARD_W = W - MARGIN * 2
CARD_H = H - MARGIN * 2

# 方向常量
DIR_UP = "up"      # 气泡在猫上方，尾巴向下指向猫
DIR_DOWN = "down"  # 气泡在猫下方，尾巴向上指向猫
DIR_LEFT = "left"  # 气泡在猫左侧，尾巴向右指向猫
DIR_RIGHT = "right"


class BubbleWindow(QWidget):
    """到点提醒气泡。提供 bubble_closed 信号（点按钮后发）。"""

    bubble_closed = Signal()

    ANIM_STEPS = 12
    ANIM_MS = 14

    def __init__(self, ctrl, text: str):
        super().__init__()
        self.ctrl = ctrl
        self.text = text
        self.setWindowTitle("久坐提醒")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(W, H)

        # 方向：初始由调用方（show_near）设置；缺省朝下
        self.tail = DIR_DOWN
        self._anim_step = 0
        self._scale = 0.2
        self._started = False
        self._hover_btn = False

        # 文字自动折行
        self._lines = self._wrap(text)

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._step_anim)
        self._anim.start(BubbleWindow.ANIM_MS)

    # ------------------------------------------------------------ 文字折行
    def _wrap(self, text: str):
        fm = QFontMetrics(make_font(qtheme.FONT_QUOTE))
        # 内宽 = 卡宽 - 左右 padding - 文字两侧留 4px 安全
        width = CARD_W - qtheme.BUBBLE_PAD_X * 2 - 8
        lines, cur = [], ""
        for ch in text:
            if fm.horizontalAdvance(cur + ch) > width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines

    # ------------------------------------------------------------ 位置
    def show_near(self, ref: QWidget):
        """把气泡放在妮子浮窗附近：四方向自适应 + 屏幕内 + 尾巴指向猫。

        策略：
          1) 取猫窗口中心 + 屏幕可用区
          2) 枚举四个方向（上/下/左/右），每个方向计算"完美对齐中心"的位置
          3) 计算该位置放入屏幕后"溢出量"（被裁掉的像素）
          4) 选溢出=0 且方向更"贴猫"（更靠近猫中心）的位置；若都不溢出选纵向最近；溢出都>0 选最少溢出的
          5) 同步设置尾巴方向
        """
        win = ref.window()
        # 猫在屏幕上的几何
        cg = win.frameGeometry()
        cat_cx = cg.center().x()
        cat_top = cg.top()
        cat_bot = cg.bottom()
        cat_left = cg.left()
        cat_right = cg.right()

        # 当前屏幕可用区（多屏时按猫所在屏幕）
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is None:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().availableGeometry()

        # 计算四个方向的候选位置（每个方向理想位置：贴猫边 + 对齐猫中心）
        candidates = []

        # 上方（气泡在猫头顶）：猫中心对齐
        x_top = cat_cx - W // 2
        y_top = cat_top - H + 4   # 略微重叠给尾巴"插入"猫身
        candidates.append((DIR_UP, x_top, y_top, W, H, "vert"))

        # 下方
        x_bot = cat_cx - W // 2
        y_bot = cat_bot + 6
        candidates.append((DIR_DOWN, x_bot, y_bot, W, H, "vert"))

        # 左侧（气泡在猫左边）：猫中心垂直对齐
        x_left = cat_left - W + 4
        y_left = cat_top + (cg.height() - H) // 2
        candidates.append((DIR_LEFT, x_left, y_left, W, H, "horz"))

        # 右侧
        x_right = cat_right + 6
        y_right = cat_top + (cg.height() - H) // 2
        candidates.append((DIR_RIGHT, x_right, y_right, W, H, "horz"))

        # 评分：负分=在屏幕内，溢出越多分越低
        sx0, sy0 = screen.x(), screen.y()
        sw, sh = screen.width(), screen.height()
        best = None
        for d, x, y, w, h, pri in candidates:
            overflow_x = max(0, sx0 - x) + max(0, (x + w) - (sx0 + sw))
            overflow_y = max(0, sy0 - y) + max(0, (y + h) - (sy0 + sh))
            overflow = overflow_x + overflow_y
            # 加垂直/水平偏好加成（让方向在都不溢出时仍能选择）
            pri_bonus = 0
            # 上方优于下方、左侧优于右侧（贴猫身方向优先级一致）
            if d == DIR_UP: pri_bonus = 0
            elif d == DIR_DOWN: pri_bonus = 1
            elif d == DIR_LEFT: pri_bonus = 2
            elif d == DIR_RIGHT: pri_bonus = 3
            score = (overflow, pri_bonus)
            if best is None or score < best[0]:
                best = (score, d, x, y, overflow)

        _, direction, fx, fy, _ = best
        self.tail = direction

        # 边界调整（溢出时尽量贴边裁剪）
        fx = max(sx0, min(fx, sx0 + sw - W))
        fy = max(sy0, min(fy, sy0 + sh - H))

        self.move(fx, fy)
        self.show()

    # ------------------------------------------------------------ 动画
    def _step_anim(self):
        # easeOutBack 生长
        from math import pi
        i, n = self._anim_step, BubbleWindow.ANIM_STEPS
        t = i / n
        c1 = 1.70158
        e = 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2
        self._scale = min(max(0.2 + 0.8 * e, 0.05), 1.08)
        if i >= n:
            self._anim.stop()
            self._started = True
        self._anim_step += 1
        self.update()

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        s = self._scale
        # 生长锚点 = 气泡卡片中心（让生长从中心放射，不影响相对位置感）
        cx, cy = W / 2, H / 2

        # 卡片矩形（按中心等比缩放）
        def sx_(v): return cx + (v - cx) * s
        def sy_(v): return cy + (v - cy) * s

        card = QRectF(sx_(MARGIN), sy_(MARGIN),
                      CARD_W * s, CARD_H * s)

        # 关键：把尾巴三角形并入卡片圆角路径，得到「卡片+尾巴」的单体外轮廓。
        # 一次性 fillPath 同一颜色 → 两者间绝无阴影/底色夹缝（此前尾巴与卡片是
        # 分两次 fill，中间会被右下偏移的投影切出一道线）。
        body = QPainterPath()
        body.addRoundedRect(card, RADIUS * s, RADIUS * s)
        body = self._merge_tail(body, card)

        # 阴影沿合并后的整体外轮廓绘制（含尾巴），再整体填奶米卡
        self._draw_shadow(p, body)
        # 贴纸语言：白色剪纸外沿（5px 白描边）+ 奶米内芯 + 内芯细描边
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(qtheme.STICKER_EDGE, 5))
        p.drawPath(body)
        p.fillPath(body, qtheme.STICKER_BG)
        inner = QPainterPath()
        inner.addRoundedRect(card.adjusted(1.5, 1.5, -1.5, -1.5),
                             RADIUS - 1.5, RADIUS - 1.5)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(qtheme.STICKER_BORDER, 1))
        p.drawPath(inner)

        if self._started:
            self._draw_content(p, card)

    def _draw_shadow(self, p, body):
        # 沿「卡片+尾巴」合并轮廓做多层偏移半透明描边 = 柔和投影。
        # 由于 body 先描边、再在下方整体填卡，内扩部分会被底色盖掉，
        # 只留下朝外扩散的羽化投影 → 不会在尾巴/卡片之间留下切缝。
        # v0.7：黑灰调改暖棕调，与奶咖贴纸色系融合。
        for dx, dy, w, col in (
            (5, 6, 14, QColor(90, 70, 54, 12)),
            (3, 4, 9,  QColor(90, 70, 54, 18)),
            (1, 2, 4,  QColor(90, 70, 54, 26)),
        ):
            shifted = QPainterPath(body)   # body 自画不可直接改，复制一份平移
            shifted.translate(dx, dy)
            p.setPen(QPen(col, w))
            p.drawPath(shifted)

    def _merge_tail(self, body, card):
        """把尾巴三角形与卡片做几何并集，返回「卡片+尾巴」单体外轮廓。"""
        if self.tail == DIR_DOWN:
            base_y = card.top()
            tip_y = base_y - TAIL_LEN
            mid_x = card.center().x()
            pts = [QPointF(mid_x - TAIL_HALF, base_y),
                   QPointF(mid_x + TAIL_HALF, base_y),
                   QPointF(mid_x, tip_y)]
        elif self.tail == DIR_UP:
            base_y = card.bottom()
            tip_y = base_y + TAIL_LEN
            mid_x = card.center().x()
            pts = [QPointF(mid_x - TAIL_HALF, base_y),
                   QPointF(mid_x + TAIL_HALF, base_y),
                   QPointF(mid_x, tip_y)]
        elif self.tail == DIR_LEFT:
            base_x = card.right()
            tip_x = base_x + TAIL_LEN
            mid_y = card.center().y()
            pts = [QPointF(base_x, mid_y - TAIL_HALF),
                   QPointF(base_x, mid_y + TAIL_HALF),
                   QPointF(tip_x, mid_y)]
        else:  # DIR_RIGHT
            base_x = card.left()
            tip_x = base_x - TAIL_LEN
            mid_y = card.center().y()
            pts = [QPointF(base_x, mid_y - TAIL_HALF),
                   QPointF(base_x, mid_y + TAIL_HALF),
                   QPointF(tip_x, mid_y)]
        tail = QPainterPath()
        tail.moveTo(pts[0])
        tail.lineTo(pts[1])
        tail.lineTo(pts[2])
        tail.closeSubpath()
        # 真正的几何并集：消掉卡片与尾巴之间的共享内边 → 干净无缝外轮廓
        return body.united(tail)

    def _draw_content(self, p, card):
        """分层布局：正文区 / 按钮区。

        v0.7 去掉「久坐提醒」标签行与分隔线（视觉重心交给正文与琥珀按钮），
        正文夹在卡片顶部与按钮之间、按实际行数垂直居中。
        """
        # ---- 按钮区（固定位置，卡片底部居中）
        btn_w = qtheme.BUBBLE_BTN_W
        btn_h = qtheme.BUBBLE_BTN_H
        btn_rect = QRectF(card.center().x() - btn_w / 2,
                           card.bottom() - qtheme.BUBBLE_PAD_BOT - btn_h,
                           btn_w, btn_h)

        # ---- 正文区（夹在卡片顶部与按钮之间）
        body_top = card.top() + qtheme.BUBBLE_PAD_TOP
        body_rect = QRectF(card.left() + qtheme.BUBBLE_PAD_X, body_top,
                           card.width() - qtheme.BUBBLE_PAD_X * 2,
                           btn_rect.top() - qtheme.BUBBLE_GAP_BODY_BTN - body_top)

        # 画正文（多行在 body_rect 内垂直居中）
        p.setPen(qtheme.STICKER_TEXT)
        p.setFont(make_font(qtheme.FONT_QUOTE))
        fm = p.fontMetrics()
        line_h = fm.lineSpacing()
        total_h = len(self._lines) * line_h
        first_y = body_rect.top() + (body_rect.height() - total_h) / 2
        for i, line in enumerate(self._lines):
            tw = fm.horizontalAdvance(line)
            lx = body_rect.center().x() - tw / 2
            p.drawText(QPointF(lx, first_y + (i + 1) * line_h - fm.descent()),
                       line)

        # 画按钮（hover 状态）：琥珀胶囊
        path = QPainterPath()
        path.addRoundedRect(btn_rect, btn_h / 2, btn_h / 2)
        col = (qtheme.STICKER_ACCENT_HOVER if self._hover_btn
               else qtheme.STICKER_ACCENT_BG)
        p.fillPath(path, col)
        p.setPen(QPen(qtheme.STICKER_ACCENT_BORDER, 1))
        p.drawPath(path)
        p.setPen(qtheme.STICKER_ACCENT_TEXT)
        p.setFont(make_font(qtheme.FONT_BTN, bold=True))
        p.drawText(btn_rect, Qt.AlignCenter, "知道了")
        self._btn_rect = btn_rect

    # ------------------------------------------------------------ 事件
    def mousePressEvent(self, e):
        if self._btn_rect is not None and self._btn_rect.contains(e.position()):
            self.close()

    def mouseMoveEvent(self, e):
        hover = self._btn_rect is not None and self._btn_rect.contains(e.position())
        if hover != self._hover_btn:
            self._hover_btn = hover
            self.update()

    def closeEvent(self, e):
        self.bubble_closed.emit()
        super().closeEvent(e)


def make_font(px: int, bold: bool = False, family: str = qtheme.FONT_FAMILY) -> QFont:
    f = QFont(family, px)
    f.setPixelSize(px)
    f.setBold(bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f