"""Qt6 主浮窗「妮子」。

真透明窗口 + 猫图 alpha 蒙版裁剪的真羽化阴影 + 抗锯齿文本/图片。
对比 Tk 1-bit 色键，Qt 是真 alpha：猫边缘、阴影、胶囊全为渐变，无毛边。

v0.4 改造：
  - 阴影改为「猫图 alpha 蒙版 + 多圈半透明」自绘，自动贴猫毛、不再有矩形方框
  - 倒计时胶囊移到猫下方，进出有过渡动画（滑入+淡入 / 滑出+淡出）
"""
from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint
from PySide6.QtGui import (
    QPainter, QPainterPath, QPixmap, QImage, QColor, QPen, QRegion,
)
from PySide6.QtWidgets import QWidget, QMenu

from .. import paths
from . import qtheme
from .qtheme import make_time_font

log = logging.getLogger(__name__)

IMG_W, IMG_H = 150, 150
SHADOW_PAD = 16
# 窗口加高：上方留 16 放猫阴影，猫图占 16..166，下方额外留出独立的胶囊停靠带，
# 保证胶囊完整态顶部(≈164)落在猫身可视轮廓(≈155)之下、不再遮住妮子。
WIN_W, WIN_H = IMG_W + SHADOW_PAD * 2, 200

CAPSULE_W, CAPSULE_H = 150, 48
CAPSULE_BODY_W, CAPSULE_BODY_H = 116, 30
CAPSULE_BOTTOM_PAD = 6   # 完整态胶囊底边距窗口下缘的像素（避免底部被窗口裁切）

# 胶囊动画参数 —— 时间驱动补间，时长以毫秒计；easeOutCubic 缓出(出现)、easeInCubic 缓入(消失)
CAPSULE_ANIM_MS_IN = 220      # 出现动画时长
CAPSULE_ANIM_MS_OUT = 180     # 消失动画时长
CAPSULE_ANIM_INTERVAL_MS = 15


def _load_scaled_mascot() -> QPixmap | None:
    # 优先用去色晕版（Qt 真透明下保留这个版本的边缘 alpha，不再有"白边鬼影"）
    for path in (paths.MASCOT_PATH_QT, paths.MASCOT_PATH):
        if not os.path.exists(path):
            continue
        img = QImage(path)
        if img.isNull():
            continue
        # 朝向约定：以素材原始方向为准（= 用户选定的 B 朝向），不再镜像。
        # 主浮窗与托盘图标共用该方向，保持一致。
        pm = QPixmap.fromImage(img)
        return pm.scaled(IMG_W, IMG_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    log.warning("形象资源缺失（%s / %s）", paths.MASCOT_PATH_QT, paths.MASCOT_PATH)
    return None


class SitReminderWindow(QWidget):
    """主浮窗：妮子（原生透明 PNG）+ 悬停胶囊（下方，带动画）+ 拖拽 / 菜单。"""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.setWindowTitle("久坐提醒 · 妮子")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # WA_TranslucentBackground + WA_NoSystemBackground：Qt 文档明确这俩要一起设才"真透明"
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFixedSize(WIN_W, WIN_H)

        self._mascot = _load_scaled_mascot()
        # 真 alpha 阴影层：保留猫的 alpha 轮廓，仅把 RGB 换成深色。
        # 用它逐层偏移叠加 → 得到贴猫轮廓的真羽化投影（无 1-bit 二值硬边，
        # 浅色桌面上不会再生出"灰白描边/锯齿边"）。
        self._shadow_layer = self._make_shadow_layer()
        # 胶囊动画进度：0.0 = 完全隐藏，1.0 = 完全显示
        # 时间驱动补间：_cap_anim_t0 = 动画开始时的单调时钟(ms)
        self._cap_progress = 0.0
        self._cap_target = 0.0   # 0.0 收起 / 1.0 显示
        self._cap_anim_t0 = 0.0
        self._cap_anim_from = 0.0  # 本次动画起始进度
        self._cap_anim = QTimer(self)
        self._cap_anim.setInterval(CAPSULE_ANIM_INTERVAL_MS)
        self._cap_anim.timeout.connect(self._step_capsule_anim)
        self._hover = False
        self._time_text = ""

        self._press_global: QPoint | None = None
        self._press_win: QPoint | None = None
        self._dragging = False

        self._build_menu()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(250)

    # ------------------------------------------------------------ 菜单
    def _build_menu(self):
        self.menu = QMenu(self)
        self.menu.addAction("显示主窗口", self.ctrl.show_main)
        self.menu.addAction("设置", self.ctrl.open_settings)
        self.act_pause = self.menu.addAction("暂停/继续", self.ctrl.toggle_pause)
        self.menu.addAction("跳过本次", self.ctrl.on_skip)
        self.menu.addSeparator()
        self.menu.addAction("关闭…", self.ctrl.open_close_choice)

    def set_paused(self, paused: bool):
        self.act_pause.setText("继续计时" if paused else "暂停计时")

    # ------------------------------------------------------------ 计时
    def _on_tick(self):
        if self._hover and self._cap_progress > 0:
            t = self.ctrl.timer
            m, s = divmod(t.remaining(), 60)
            suffix = " ⏸" if t.is_paused else ""
            text = f"{m:02d}:{s:02d}{suffix}"
            if text != self._time_text:
                self._time_text = text
                self.update()
        if self.ctrl.timer.is_due():
            self.ctrl.on_due()

    # ------------------------------------------------------------ 胶囊动画
    def _start_capsule_anim(self):
        # 记录本次动画的起点(当前进度)与开始时间，做一次「时间驱动补间」。
        # 若动画已在跑，允许从当前进度平滑改向（例如鼠标反复进出）。
        self._cap_anim_from = self._cap_progress
        self._cap_anim_t0 = time.monotonic()
        if not self._cap_anim.isActive():
            self._cap_anim.start()

    @staticmethod
    def _ease_out_cubic(t: float) -> float:
        return 1 - (1 - t) ** 3

    @staticmethod
    def _ease_in_cubic(t: float) -> float:
        return t ** 3

    def _step_capsule_anim(self):
        """按单调时钟线性推进时间 t，再对 t 做缓动映射。

        相比旧的「对当前 progress 递归 ease + step*1.5」算法，
        这里 progress 是 t 的平滑函数，全程无跳变，动画更丝滑。
        """
        entering = self._cap_target > self._cap_progress
        duration = CAPSULE_ANIM_MS_IN if entering else CAPSULE_ANIM_MS_OUT
        t_raw = (time.monotonic() - self._cap_anim_t0) * 1000.0 / duration
        t = max(0.0, min(1.0, t_raw))
        # 曲线：出现用缓出(先快后慢)，消失用缓入(先慢后快)
        eased = self._ease_out_cubic(t) if entering else self._ease_in_cubic(t)
        # 从本次动画起点 _cap_anim_from 平滑逼近目标，避免改向时跳变
        self._cap_progress = self._cap_anim_from + (self._cap_target - self._cap_anim_from) * eased
        if t_raw >= 1.0:
            self._cap_progress = self._cap_target
            self._cap_anim.stop()
        self.update()

    def _capsule_rect_animated(self) -> QRectF:
        """计算胶囊本次绘制的矩形。

        完整态(progress=1)底部固定对齐窗口下缘内侧留 pad；高度随 progress 增长。
        底部 y 恒定(始终在窗口内、不会被裁)，胶囊像从停靠带原地长高，姿态稳定。
        由于窗口已加高到 200，完整态顶部落在猫身可视轮廓之下，不再遮住妮子。
        """
        cx = WIN_W / 2.0
        h = CAPSULE_BODY_H * self._cap_progress
        # 胶囊完整态底部固定：窗口下缘向上留 CAPSULE_BOTTOM_PAD
        bottom = WIN_H - CAPSULE_BOTTOM_PAD
        # 滑入感：进度低时胶囊略靠下，随进度上移到停靠位（幅度小、平滑）
        y = bottom - h - (1 - self._cap_progress) * 8
        return QRectF(cx - CAPSULE_BODY_W / 2, y,
                      CAPSULE_BODY_W, h)

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        if self._mascot is not None:
            # 阴影：把猫图 alpha 作为剪贴区，偏移+多圈半透明画 → 真羽化
            self._paint_drop_shadow(p)
            p.drawPixmap(SHADOW_PAD, SHADOW_PAD, self._mascot)

        # 胶囊：悬停时绘制，根据 _cap_progress 控制位置/大小/透明度
        if self._cap_progress > 0.01 and self._time_text:
            self._paint_capsule(p)

    def _make_shadow_layer(self):
        """由彩色猫图生成一张「深色 + 保留 alpha」的阴影底片。

        阴影绘制时用 setOpacity 压层即可得到多层羽化；因为 alpha 是逐像素
        真渐变（不是 createHeuristicMask 的 1-bit 二值），外圈随猫 alpha 自然
        淡出，不会在浅色桌面上形成硬边描边。
        """
        if self._mascot is None:
            return None
        img = self._mascot.toImage().convertToFormat(QImage.Format_ARGB32)
        w, h = img.width(), img.height()
        for y in range(h):
            for x in range(w):
                c = img.pixelColor(x, y)
                a = c.alpha()
                if a:
                    img.setPixelColor(x, y, QColor(20, 18, 24, a))
        return QPixmap.fromImage(img)

    def _paint_drop_shadow(self, p: QPainter):
        """真 alpha 羽化投影：把深色猫影往右下逐层偏移、降透明度叠加。

        相比旧的「createHeuristicMask(True) 二值 mask + fillRect 剪贴」，
        这里不用 1-bit 硬剪贴区，阴影外轮廓跟随猫的真实 alpha 渐变淡出，
        消除浅色桌面上贴着猫身的那圈灰白硬边/锯齿感。
        """
        if self._shadow_layer is None:
            return
        # 方案 C：最近一圈偏移从 1 起步提到 2，避免阴影贴猫太近显得像描边。
        # 层序：内圈偏移小透明度高(贴近立体感) → 外圈偏移大透明度低(羽化淡出)。
        for dx, dy, op in ((2, 3, 0.16), (4, 5, 0.10), (7, 8, 0.05)):
            p.save()
            p.setOpacity(op)
            p.drawPixmap(SHADOW_PAD + dx, SHADOW_PAD + dy, self._shadow_layer)
            p.restore()

    def _paint_capsule(self, p: QPainter):
        rect = self._capsule_rect_animated()
        # 透明度由胶囊颜色 alpha 表达
        alpha = max(0, min(255, int(self._cap_progress * 255)))
        bg = qtheme.CAPSULE_BG
        bg.setAlpha(alpha)
        text_col = QColor(qtheme.CAPSULE_TEXT)
        text_col.setAlpha(alpha)
        border_col = QColor(255, 255, 255, int(26 * self._cap_progress))

        path = QPainterPath()
        # 圆角 = 半高（胶囊型）
        radius = CAPSULE_BODY_H * self._cap_progress / 2
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, bg)
        p.setPen(QPen(border_col, 1))
        p.drawPath(path)
        # 文字：胶囊 progress 太低时不画（< 0.3）避免模糊
        if self._cap_progress > 0.3 and self._time_text:
            p.setPen(text_col)
            f = make_time_font()
            p.setFont(f)
            p.drawText(rect, Qt.AlignCenter, self._time_text)

    # ------------------------------------------------------------ 交互
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._press_win = self.pos()
            self._dragging = False
        elif e.button() == Qt.RightButton:
            self.menu.exec(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._press_global is None:
            return
        delta = e.globalPosition().toPoint() - self._press_global
        if not self._dragging and (abs(delta.x()) > 3 or abs(delta.y()) > 3):
            self._dragging = True
        if self._dragging:
            self.move(self._press_win + delta)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and not self._dragging:
            self.ctrl.open_settings()
        self._press_global = None
        self._dragging = False

    def enterEvent(self, e):
        self._hover = True
        # 触发胶囊出现动画
        if not self._time_text:
            t = self.ctrl.timer
            m, s = divmod(t.remaining(), 60)
            suffix = " ⏸" if t.is_paused else ""
            self._time_text = f"{m:02d}:{s:02d}{suffix}"
        self._cap_target = 1.0
        self._start_capsule_anim()
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        # 触发胶囊消失动画
        self._cap_target = 0.0
        self._start_capsule_anim()
        self.update()