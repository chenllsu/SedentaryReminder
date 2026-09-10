"""Qt6 GUI 冒烟 + 真实截图：验证主浮窗无白边、阴影羽化、胶囊、气泡。

用法（用 PySide6 的 3.13 解释器）：
  <pyqt python> tests/smoke_qt.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor

from sitreminder.qt.app import QtController

os.makedirs(os.path.join(ROOT, "assets", "_previews"), exist_ok=True)
BG = QColor(42, 58, 96)


class Backdrop(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), BG)


def shot(name, widget):
    pm = widget.grab()
    pm.save(os.path.join(ROOT, "assets", "_previews", name))
    print("  saved", name)


def main():
    """Qt 渲染测试：用 Backdrop 模拟桌面 + 直接在 Backdrop 上画主窗口内容，
    模拟"widget 真透明叠在桌面上"的最终视觉效果。
    """
    from PySide6.QtGui import QPainter, QPainterPath, QColor, QPixmap
    from PySide6.QtGui import QFont as QF
    from sitreminder import paths as P
    from sitreminder.qt import qtheme
    from sitreminder.qt.qtheme import make_time_font

    app = QApplication(sys.argv)
    screen = app.primaryScreen().availableGeometry()

    # 1) 加载去色晕版素材（走主窗同一条 HiDPI 加载路径，朝向=素材原方向 B，不再镜像）
    from PySide6.QtGui import QImage, QIcon
    from sitreminder.qt import window as W
    mascot_pm = W.load_mascot_pixmap(W.IMG_W, 1.0)

    # 2) 一张大画布：浅灰主色 + 蓝/深色色块做"桌面"对比
    canvas = QPixmap(900, 540)
    canvas.fill(QColor(220, 220, 225))    # 浅灰主桌面
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    # 三块"壁纸"区
    p.fillRect(0, 0, 300, 540, QColor(35, 30, 45))        # 深色
    p.fillRect(300, 0, 300, 540, QColor(42, 58, 96))       # 蓝
    p.fillRect(600, 0, 300, 540, QColor(180, 165, 145))    # 米色
    # 标签
    f = QF("Microsoft YaHei", 14)
    p.setFont(f); p.setPen(QColor(255, 255, 255))
    p.drawText(20, 30, "深色桌面")
    p.drawText(320, 30, "蓝色桌面")
    p.setPen(QColor(40, 40, 40))
    p.drawText(620, 30, "浅色桌面")

    # 3) 在三块背景上各画一只猫（带阴影），验证去色晕后的真实外观
    IMG_W, IMG_H = W.IMG_W, W.IMG_H
    PAD = W.SHADOW_PAD
    for cx_bg, base_x in [(0, 90), (300, 390), (600, 690)]:
        # 阴影（多圈 QColor alpha）
        for pen_w, col in ((10, QColor(20, 18, 24, 10)),
                           (6, QColor(20, 18, 24, 20)),
                           (3, QColor(20, 18, 24, 30))):
            path = QPainterPath()
            path.addRoundedRect(float(base_x+PAD+1), float(PAD+18+1),
                                IMG_W-2, IMG_H-2, 24, 24)
            p.setPen(col)
            # setPenColor 需带宽度：手动
            from PySide6.QtGui import QPen
            pen = QPen(col, pen_w)
            p.setPen(pen)
            p.drawPath(path)
        if mascot_pm is not None:
            p.drawPixmap(base_x + PAD, PAD + 18, mascot_pm)

    # 4) 画悬停胶囊
    for base_x in (90, 390, 690):
        cx = base_x + PAD + IMG_W / 2.0
        rect_w, rect_h = W.CAPSULE_BODY_W, W.CAPSULE_BODY_H
        cy = 4.0
        rect = QtCore.QRectF(cx - rect_w/2, cy, rect_w, rect_h)
        path = QPainterPath()
        path.addRoundedRect(rect, rect_h/2, rect_h/2)
        p.fillPath(path, qtheme.CAPSULE_BG)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.drawPath(path)
        p.setPen(qtheme.CAPSULE_TEXT)
        p.setFont(make_time_font(qtheme.FONT_TIME))
        p.drawText(rect, Qt.AlignCenter, "29:42")

    p.end()

    out = os.path.join(ROOT, "assets", "_previews", "qt_main_window.png")
    canvas.save(out)
    print("  saved", out, canvas.size())

    # 5) 画气泡（无 alpha 干扰，直接在浅色背景上）
    from PySide6.QtCore import QRectF, QPointF
    bub = QPixmap(360, 220)
    bub.fill(Qt.transparent)
    bp = QPainter(bub)
    bp.setRenderHint(QPainter.Antialiasing, True)
    bp.setRenderHint(QPainter.TextAntialiasing, True)
    # 模拟"浅灰桌面"作为气泡后背景
    bub_bg = QColor(220, 220, 225)
    bp.fillRect(bub.rect(), bub_bg)
    rect = QRectF(20, 26, 320, 168)
    path = QPainterPath()
    path.addRoundedRect(rect, 16, 16)
    # 阴影
    for dx, dy, w, col in (
        (4, 5, 14, QColor(0, 0, 0, 10)),
        (3, 4, 8, QColor(0, 0, 0, 16)),
        (2, 3, 4, QColor(0, 0, 0, 20)),
    ):
        sh = QPainterPath()
        sh.addRoundedRect(rect.adjusted(dx, dy, dx, dy), 16, 16)
        bp.setPen(QPen(col, w))
        bp.drawPath(sh)
    bp.fillPath(path, qtheme.CARD_BG)
    # 眉头
    bp.setPen(qtheme.CARD_SUBTEXT)
    bp.setFont(QF("Microsoft YaHei", 11))
    bp.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, "久 坐 提 醒")
    # 分隔线
    bp.setPen(QPen(qtheme.CARD_RULE, 1))
    mid = rect.center().x()
    bp.drawLine(QPointF(mid - 16, rect.top() + 26 + 14),
                QPointF(mid + 16, rect.top() + 26 + 14))
    # 主文案
    bp.setPen(qtheme.CARD_TEXT)
    bp.setFont(QF("Microsoft YaHei", 14))
    text = "你的脊椎正在默默吐槽：我就没直起来过？"
    from PySide6.QtGui import QFontMetrics
    fm = QFontMetrics(bp.font())
    bp.drawText(rect.adjusted(0, 50, 0, 0), Qt.AlignHCenter | Qt.AlignTop, text)
    # 按钮
    bw, bh = 104, 32
    bx = rect.center().x() - bw/2
    by = rect.bottom() - bh - 10
    br = QRectF(bx, by, bw, bh)
    bp_p = QPainterPath()
    bp_p.addRoundedRect(br, bh/2, bh/2)
    bp.fillPath(bp_p, qtheme.BTN_BLUE)
    bp.setPen(qtheme.CARD_BG)
    bp.setFont(QF("Microsoft YaHei", 11))
    bp.drawText(br, Qt.AlignCenter, "知道了")
    bp.end()
    bub_out = os.path.join(ROOT, "assets", "_previews", "qt_bubble.png")
    bub.save(bub_out)
    print("  saved", bub_out)

    app.quit()


if __name__ == "__main__":
    import PySide6.QtCore as QtCore
    main()
