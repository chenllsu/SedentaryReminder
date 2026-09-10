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

# ---------------------------------------------------------------- 尺寸
# 妮子逻辑显示边长(px)。调小 = 形象更小巧、更不打扰；窗口尺寸随之联动。
# 110 = 龙哥 2026-09-10 从 150/130/120/110 对比图中选定。
MASCOT_SIZE = 110
IMG_W = IMG_H = MASCOT_SIZE
SHADOW_PAD = 16   # 四周留给投影的透明边距

# 妮子「可见底部」占图高的比例。素材 alpha 包围盒实测：内容底 480 / 画布 512 = 0.9375
# （猫图上沿约在 4% 处、脚下约在 93.7% 处，其余是透明留白）。
# 胶囊停靠位置由它推导，因此改 MASCOT_SIZE 时不必再手算窗口高度。
MASCOT_VISIBLE_BOTTOM_RATIO = 0.9375
CAPSULE_GAP_BELOW_CAT = 8   # 胶囊完整态顶部与猫脚之间的空隙

CAPSULE_BODY_W, CAPSULE_BODY_H = 116, 30
CAPSULE_BOTTOM_PAD = 6   # 完整态胶囊底边距窗口下缘的像素（避免底部被窗口裁切）

# 窗口高度 = 上留白 + 猫脚位置 + 空隙 + 胶囊高 + 下留白。
# 这样胶囊永远落在猫脚之下（不遮妮子），且不留多余空白。
WIN_W = IMG_W + SHADOW_PAD * 2
WIN_H = int(round(
    SHADOW_PAD
    + IMG_H * MASCOT_VISIBLE_BOTTOM_RATIO
    + CAPSULE_GAP_BELOW_CAT
    + CAPSULE_BODY_H
    + CAPSULE_BOTTOM_PAD
))

# 胶囊动画参数 —— 时间驱动补间，时长以毫秒计；easeOutCubic 缓出(出现)、easeInCubic 缓入(消失)
CAPSULE_ANIM_MS_IN = 220      # 出现动画时长
CAPSULE_ANIM_MS_OUT = 180     # 消失动画时长
CAPSULE_ANIM_INTERVAL_MS = 15


def _mascot_source_image() -> QImage | None:
    """按优先级取妮子原图（都是高分辨率，供按需缩放）。

    优先去色晕的 Qt 版（512px，透明区 RGB 已归零），降级用 1920 通用版。
    """
    for path in (paths.MASCOT_PATH_QT, paths.MASCOT_PATH):
        if not os.path.exists(path):
            continue
        img = QImage(path)
        if not img.isNull():
            return img
    log.warning("形象资源缺失（%s / %s）", paths.MASCOT_PATH_QT, paths.MASCOT_PATH)
    return None


def load_mascot_pixmap(logical_size: int, dpr: float = 1.0) -> QPixmap | None:
    """生成妮子位图：按「逻辑尺寸 × 屏幕缩放」取物理像素，并标注 devicePixelRatio。

    为什么必须这样做（原本发虚的根因）：
      屏幕 125% 缩放时，Qt 要把 150 逻辑像素的绘制栅格化成 187.5 物理像素。
      若位图只有 150 物理像素，等于被放大 1.25 倍 → 边缘发虚。
      这里改为直接产出 187 物理像素、并 setDevicePixelRatio(1.25) 告知 Qt，
      Qt 绘制到 150 逻辑矩形时正好 1:1，不再缩放 → 清晰。
    """
    img = _mascot_source_image()
    if img is None:
        return None
    dpr = max(1.0, float(dpr))
    phys = max(1, int(round(logical_size * dpr)))
    src = QPixmap.fromImage(img)
    # 高清源 → 物理像素：这是"缩小"，用平滑插值；配合预乘 alpha 素材不会渗白边。
    pm = src.scaled(phys, phys, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm


def _load_scaled_mascot() -> QPixmap | None:
    """主浮窗用：按当前主屏缩放比例加载妮子位图。"""
    return load_mascot_pixmap(IMG_W, current_device_pixel_ratio())


def current_device_pixel_ratio(widget=None) -> float:
    """取屏幕缩放比例（如 Windows 125% → 1.25）。取不到时按 1.0 处理。"""
    from PySide6.QtWidgets import QApplication
    scr = None
    if widget is not None:
        try:
            scr = widget.screen()
        except Exception:
            scr = None
    if scr is None:
        scr = QApplication.primaryScreen()
    if scr is None:
        return 1.0
    try:
        return float(scr.devicePixelRatio()) or 1.0
    except Exception:
        return 1.0


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

        self._mascot = None
        self._shadow_layer = None
        self._dpr = current_device_pixel_ratio(self)
        self._reload_mascot()
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

    # ------------------------------------------------------------ 素材（高 DPI）
    def _reload_mascot(self):
        """按当前 DPR 重新生成妮子位图与阴影底片。"""
        self._mascot = load_mascot_pixmap(IMG_W, self._dpr)
        # 真 alpha 阴影层：保留猫的 alpha 轮廓，仅把 RGB 换成深色。
        # 逐层偏移叠加即得贴猫轮廓的真羽化投影（无 1-bit 二值硬边）。
        self._shadow_layer = self._make_shadow_layer()

    def showEvent(self, e):
        # 窗口首次上屏 / 跨屏移动后，若屏幕缩放比例变了，按新 DPR 重载素材，
        # 保证任何显示器上都是 1:1 物理像素（否则在 150% 屏上又会发虚）。
        super().showEvent(e)
        dpr = current_device_pixel_ratio(self)
        if abs(dpr - self._dpr) > 1e-6:
            self._dpr = dpr
            self._reload_mascot()
            self.update()

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
        """由妮子位图生成一张「深色 + 保留 alpha」的阴影底片。

        阴影绘制时用 setOpacity 压层即可得到多层羽化；因为 alpha 是逐像素
        真渐变（不是 createHeuristicMask 的 1-bit 二值），外圈随猫 alpha 自然
        淡出，不会在浅色桌面上形成硬边描边。

        用字节级改写代替逐像素 pixelColor/setPixelColor：Format_ARGB32 每像素
        4 字节（小端序下为 B,G,R,A），只覆盖 BGR、保留 A，速度快一个量级。
        """
        if self._mascot is None:
            return None
        img = self._mascot.toImage().convertToFormat(QImage.Format_ARGB32)
        w, h = img.width(), img.height()
        mv = img.bits()             # 可写内存视图，长度 = w*h*4
        # 阴影色 (20, 18, 24) 的 B,G,R 字节
        b_sh, g_sh, r_sh = 24, 18, 20
        for i in range(0, w * h * 4, 4):
            mv[i] = b_sh
            mv[i + 1] = g_sh
            mv[i + 2] = r_sh
            # mv[i + 3] 是 alpha，保持原样
        pm = QPixmap.fromImage(img)
        # 关键：阴影底片必须与猫图同 DPR，否则 drawPixmap 会按 1:1 画 → 错位。
        pm.setDevicePixelRatio(self._mascot.devicePixelRatio())
        return pm

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