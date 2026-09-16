"""Qt6 主浮窗「妮子」。

真透明窗口 + 猫图 alpha 蒙版的真羽化阴影 + 抗锯齿文本/图片。
对比 Tk 1-bit 色键，Qt 是真 alpha：猫边缘、阴影、胶囊全为渐变，无毛边。

v0.4 改造：
  - 阴影改为「猫图 alpha 蒙版 + 多圈半透明」自绘，自动贴猫毛、不再有矩形方框
  - 倒计时胶囊移到猫下方

v0.5 改造：
  - 胶囊由「悬停才出现」改为「常驻显示」：平时半透明淡显（不抢视线），
    鼠标移入窗口即变为完全清晰；淡显↔清晰之间做平滑补间
  - 暂停时胶囊转琥珀底色 + 文字前带暂停标记，无需打开菜单就能看出是停着的

v1.1 改造（双姿态）：
  - 妮子有两张姿态图：计时中 = 坐姿，暂停 = 蜷起来睡觉
  - 两者之间**直接切换**，不做呼吸 / 伸懒腰 / 飘 Z 等动画
  - 唯一真相源仍是 ctrl.timer.is_paused，窗口只在状态变化时重绘一次

v1.2 改造（体验优化）：
  - 尺寸不再写死：从 config.MASCOT_SIZE_PRESETS 取三档（小/中/大），
    窗口宽高、素材物理像素、阴影底片全部由实例的边长推导（见 window_size_for）
  - 暂停时胶囊改显示「已暂停时长」（正计时）——暂停中剩余时间是冻住的，
    没有信息量；"停了多久"才是用户在意的（也便于判断还差多久自动恢复）

v1.3 改造（姿态过渡动画）：
  - 坐姿 ↔ 睡姿之间加过渡：**整层交叉淡化 + 轻微垂直位移**（见 _paint_mascot）
  - 刻意**不做逐帧形变**：两张素材轮廓差异大，硬插值必然生硬（9/15 试过两版被否）。
    交叉淡化不要求两图有任何对应关系，是这类素材唯一稳妥的过渡方式
"""
from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QPixmap, QImage, QColor, QPen, QRegion, QTransform,
)
from PySide6.QtWidgets import QWidget, QMenu

from .. import paths
from ..config import DEFAULT_MASCOT_SIZE, MASCOT_SIZE_PRESETS, sanitize_mascot_size
from . import qtheme
from .qtheme import make_time_font

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- 尺寸
# 妮子逻辑显示边长(px)。可选项见 config.MASCOT_SIZE_PRESETS（小 88 / 中 110 / 大 132），
# 110 = 龙哥 2026-09-10 从 150/130/120/110 对比图中选定，现作为默认中档。
# ⚠️ 要加档位只改 config.MASCOT_SIZE_PRESETS，本文件的几何会自动跟着走。
MASCOT_SIZE = DEFAULT_MASCOT_SIZE
IMG_W = IMG_H = MASCOT_SIZE
SHADOW_PAD = 16   # 四周留给投影的透明边距

# 妮子「可见底部」占图高的比例。素材 alpha 包围盒实测：内容底 480 / 画布 512 = 0.9375
# （猫图上沿约在 4% 处、脚下约在 93.7% 处，其余是透明留白）。
# 胶囊停靠位置由它推导，因此改尺寸时不必再手算窗口高度。
MASCOT_VISIBLE_BOTTOM_RATIO = 0.9375
CAPSULE_GAP_BELOW_CAT = 8   # 胶囊完整态顶部与猫脚之间的空隙

# v0.6「爪印贴纸」紧凑化：CAPSULE_BODY_* 指"内芯"尺寸，白色剪纸外框再外扩
# CAPSULE_STICKER_PAD。爪印图标 + 数字把内芯填满，不再有大段空白。
CAPSULE_BODY_W, CAPSULE_BODY_H = 72, 20
CAPSULE_STICKER_PAD = 3   # 白色剪纸外框厚度
CAPSULE_PAW_BOX = 11      # 爪印图标占位宽
CAPSULE_PAW_GAP = 4       # 爪印与数字的间距
CAPSULE_BOTTOM_PAD = 7   # 完整态贴纸外沿底边距窗口下缘的像素（避免底部被窗口裁切）

# 胶囊常驻显示（v0.5）：不再"悬停才出现"，而是长期挂在猫脚下。
# 平时用较低不透明度淡显（不抢视线），鼠标移入即恢复清晰。
# 暂停时强制清晰并转琥珀底色（见 _paint_capsule），确保"停着"一眼可辨。
CAPSULE_IDLE_ALPHA = 0.42    # 平时（未悬停、未暂停）的不透明度
CAPSULE_FULL_ALPHA = 1.0     # 悬停 / 暂停时的不透明度

# 形象朝向：True = 水平翻转（左右对调，等价于绕竖直轴转 180°）。
# 主浮窗与托盘图标共用 load_mascot_pixmap()，改这一处两边同步生效。
# 2026-09-10 龙哥要求：妮子卡通形象 + 系统托盘图标统一水平翻转。
MASCOT_MIRROR = True

# 胶囊不透明度补间参数 —— 时长以毫秒计；
# 变清晰用 easeOutCubic(缓出)、变淡用 easeInCubic(缓入)
CAPSULE_ANIM_MS_IN = 220      # 淡显 → 清晰 的时长
CAPSULE_ANIM_MS_OUT = 180     # 清晰 → 淡显 的时长
CAPSULE_ANIM_INTERVAL_MS = 15

# ---------------------------------------------------------------- 姿态过渡（v1.3）
# 坐姿 ↔ 睡姿之间怎么"换"。
#
# ⚠️ 只用「交叉淡化 + 小位移」，**不做逐帧形变**。
# 理由：两张素材是各自独立画的（一张端坐、一张蜷成一团），轮廓之间没有对应点，
# 逐帧插值只能靠外部运动模型硬掰，必然生硬——9/15 已经试过两版（Catmull-Rom
# 样条 + 预备动作）都被否掉。交叉淡化不要求两图有任何对应关系，天然平滑。
#
# 位移的作用：打破"纯透明度变化"的平淡，给一点点方向感 ——
# 换出的姿态微微下沉淡出、换入的姿态自上方落到位置（幅度很小，别喧宾夺主）。
POSE_SWAP_MS = 340            # 一次姿态切换的时长（比胶囊的 220ms 长：主体动作该慢些）
# 换出者下沉 / 换入者下落的总位移。8px 是实测过的值：再小两张轮廓会叠在同一处
# （中途看起来"糊成一团"），再大就变成明显的"跳一下"了。
POSE_SWAP_DY = 12
# 淡化曲线的指数：坐姿不透明度 = (1-e)^k，睡姿 = 1 - 坐姿。
#  k = 1 就是标准的对称交叉淡化，中途两张各占一半 —— 谁都不占主导，
#  于是两边轮廓同等清晰地叠着，看起来"糊成一团"（第一版就是这个问题）。
#  k > 1 让坐姿退得更快、睡姿更快占主导；两者**互补**所以总不透明度恒定，
#  不会出现"换到一半整只猫忽明忽暗"。2.2 是照着渲染帧比的：
#  e=0.5 时坐姿只剩 22%（k=1 时是 50%），中间帧已经是"睡姿 + 一点旧影"。
POSE_SWAP_CURVE = 2.2
# 换出者在淡出的同时缩到多小。只靠淡化压不住重影：中间帧两张轮廓同等清晰地叠着，
# 看起来"糊"；让它稍微缩小、沉下去，观感就变成"旧的那只退到后面去了"，
# 跟新姿态不再是同一层次的东西，叠加就不再打架。
POSE_SWAP_SCALE = 0.94
POSE_ANIM_INTERVAL_MS = 15


def window_size_for(mascot_size: int) -> tuple:
    """按妮子显示边长推出窗口尺寸 (宽, 高)。

    高 = 上留白 + 猫脚位置 + 空隙 + 胶囊高 + 下留白。
    这样胶囊永远落在猫脚之下（不遮妮子），且不留多余空白；
    换档位时高度自动跟着走，不用手算。
    """
    win_w = mascot_size + SHADOW_PAD * 2
    win_h = int(round(
        SHADOW_PAD
        + mascot_size * MASCOT_VISIBLE_BOTTOM_RATIO
        + CAPSULE_GAP_BELOW_CAT
        + CAPSULE_BODY_H
        + CAPSULE_BOTTOM_PAD
    ))
    return win_w, win_h


# 默认档的窗口尺寸（保留给单测 / 旧引用；实例内部一律用 self._win_w / self._win_h）
WIN_W, WIN_H = window_size_for(MASCOT_SIZE)

# ---------------------------------------------------------------- 双姿态（v1.1，v1.3 加过渡）
# 妮子有两张姿态图：计时中 = 坐姿，暂停 = 蜷起来睡觉。
#
# 设计要点：
#  1. **唯一真相源 = ctrl.timer.is_paused**。窗口不缓存「睡没睡着」——
#     _pose_target 每拍都由真相源同步（_sync_pose_anim 在 tick 里兜底），
#     _pose_progress 只是「过渡走到哪了」这个动画量，不是状态本身。
#     这样即使某条路径只改了计时器没通知窗口，下一拍也会自愈。
#  2. **过渡 = 交叉淡化 + 小位移**（v1.3 起；此前是硬切）。为什么不用逐帧形变，
#     见文件上方 POSE_SWAP_* 的说明。
#  3. 两张素材的底边、宽度、水平中心都已对齐（实测底边均为画布的
#     MASCOT_VISIBLE_BOTTOM_RATIO），所以换图时**猫脚不会挪位**。


def pose_blend(e: float) -> tuple:
    """按过渡进度 e 算出两个姿态各自的绘制参数。

    e = 0 → 纯坐姿，e = 1 → 纯睡姿，中间是交叉淡化。返回
    ((坐姿不透明度, 坐姿下沉量, 坐姿缩放), (睡姿不透明度, 睡姿位移, 睡姿缩放))。

    抽成纯函数是为了能单测 —— 这里有两个"改坏了也看不出来"的地方：
      · 两层不透明度必须**互补**（相加为 1），否则过渡中途整只猫会忽明忽暗；
      · 坐姿的淡化指数必须 > 1，否则中途两张同等清晰、叠起来"糊成一团"。
    """
    e = max(0.0, min(1.0, float(e)))
    a_sit = (1.0 - e) ** POSE_SWAP_CURVE
    shrink = 1.0 - POSE_SWAP_SCALE
    return (
        (a_sit, POSE_SWAP_DY * e, 1.0 - shrink * e),
        (1.0 - a_sit, -POSE_SWAP_DY * (1.0 - e), POSE_SWAP_SCALE + shrink * e),
    )


def _mascot_source_image(pose: str = "sit") -> QImage | None:
    """按优先级取妮子原图（都是高分辨率，供按需缩放）。

    pose="sit"（默认）：优先去色晕的 Qt 版（512px，透明区 RGB 已归零），
                        降级用 1920 通用版。
    pose="sleep"：      v1.1 睡姿专属图；**取不到时返回 None**（不能拿坐姿顶替，
                        否则暂停时看不出任何变化）。
    """
    if pose == "sleep":
        p = paths.MASCOT_SLEEP_PATH_QT
        if os.path.exists(p):
            img = QImage(p)
            if not img.isNull():
                return img
        log.warning("睡姿素材缺失：%s（将一直显示坐姿）", p)
        return None

    for path in (paths.MASCOT_PATH_QT, paths.MASCOT_PATH):
        if not os.path.exists(path):
            continue
        img = QImage(path)
        if not img.isNull():
            return img
    log.warning("形象资源缺失（%s / %s）", paths.MASCOT_PATH_QT, paths.MASCOT_PATH)
    return None


def load_mascot_pixmap(logical_size: int, dpr: float = 1.0,
                       pose: str = "sit") -> QPixmap | None:
    """生成妮子位图：按「逻辑尺寸 × 屏幕缩放」取物理像素，并标注 devicePixelRatio。

    为什么必须这样做（原本发虚的根因）：
      屏幕 125% 缩放时，Qt 要把 150 逻辑像素的绘制栅格化成 187.5 物理像素。
      若位图只有 150 物理像素，等于被放大 1.25 倍 → 边缘发虚。
      这里改为直接产出 187 物理像素、并 setDevicePixelRatio(1.25) 告知 Qt，
      Qt 绘制到 150 逻辑矩形时正好 1:1，不再缩放 → 清晰。

    pose: "sit"（默认，托盘图标等沿用）/ "sleep"（v1.1 蜷缩睡觉）。
    """
    img = _mascot_source_image(pose)
    if img is None:
        return None
    # 朝向：水平翻转（左右对调）。放在缩放之前，变换与等比缩放互不影响。
    # 主窗与托盘图标都经过本函数，因此镜像一次即两处同步。
    if MASCOT_MIRROR:
        img = img.transformed(QTransform().scale(-1, 1))
    dpr = max(1.0, float(dpr))
    phys = max(1, int(round(logical_size * dpr)))
    src = QPixmap.fromImage(img)
    # 高清源 → 物理像素：这是"缩小"，用平滑插值；配合预乘 alpha 素材不会渗白边。
    pm = src.scaled(phys, phys, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm


def _load_scaled_mascot() -> QPixmap | None:
    """主浮窗用：按当前主屏缩放比例加载妮子位图（默认档）。"""
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

    def __init__(self, ctrl, mascot_size: int = DEFAULT_MASCOT_SIZE):
        super().__init__()
        self.ctrl = ctrl
        self.setWindowTitle("久坐提醒 · 妮子")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # WA_TranslucentBackground + WA_NoSystemBackground：Qt 文档明确这俩要一起设才"真透明"
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        # 妮子尺寸（三档，设置窗可切）。非法值在 sanitize 里收敛到最近档。
        # 窗口宽高、素材物理像素、阴影底片三件事全部由这个边长推导。
        self._mascot_size = sanitize_mascot_size(mascot_size)
        self._img_w = self._img_h = self._mascot_size
        self._win_w, self._win_h = window_size_for(self._mascot_size)
        self.setFixedSize(self._win_w, self._win_h)

        self._mascot = None
        self._mascot_sleep = None      # 睡姿图；素材缺失时为 None（自动降级）
        self._shadow_layer = None
        self._shadow_sleep = None
        self._dpr = current_device_pixel_ratio(self)
        self._reload_mascot()
        # 胶囊不透明度补间：_cap_progress = 当前不透明度，_cap_target = 目标值。
        # v0.5 起胶囊**常驻**（不再有"收起"状态），这里只负责「淡显 ↔ 清晰」的
        # 平滑过渡，不再控制出现/消失。
        # 时间驱动补间：_cap_anim_t0 = 动画开始时的单调时钟(秒)
        self._cap_progress = 0.0
        self._cap_target = CAPSULE_IDLE_ALPHA
        self._cap_anim_t0 = 0.0
        self._cap_anim_from = 0.0  # 本次动画起始不透明度
        self._cap_anim = QTimer(self)
        self._cap_anim.setInterval(CAPSULE_ANIM_INTERVAL_MS)
        self._cap_anim.timeout.connect(self._step_capsule_anim)
        self._hover = False
        # 贴纸显示模式：True = 常驻淡显（默认）；False = 悬停/暂停才出现。
        # 由控制器按配置在构建后调 set_capsule_always() 注入。
        self._capsule_always = True
        self._time_text = ""

        # ---- 姿态状态（v1.1；v1.3 起带过渡动画）----
        # _pose_progress：当前画到哪了。0 = 全是坐姿、1 = 全是睡姿，过渡中小数。
        # _pose_target  ：目标值，每拍从 ctrl.timer.is_paused 同步（唯一真相源）。
        # 启动时直接把进度设到目标、**不播动画** —— 程序刚起来不该看到妮子换姿势。
        self._pose_progress = 1.0 if self.ctrl.timer.is_paused else 0.0
        self._pose_target = self._pose_progress
        self._pose_anim_t0 = 0.0
        self._pose_anim_from = self._pose_progress
        self._pose_anim = QTimer(self)
        self._pose_anim.setInterval(POSE_ANIM_INTERVAL_MS)
        self._pose_anim.timeout.connect(self._step_pose_anim)

        self._press_global: QPoint | None = None
        self._press_win: QPoint | None = None
        self._dragging = False

        self._build_menu()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(250)

        # 常驻胶囊：入口先把文字填好（否则首帧是空胶囊），
        # 再启动一次补间，让它从全透明淡入到"平时"的淡显不透明度。
        self._refresh_time_text()
        self._start_capsule_anim()

    # ------------------------------------------------------------ 素材（高 DPI）
    def _reload_mascot(self):
        """按当前 DPR 重新生成「坐姿 + 睡姿」两套位图与阴影底片。

        睡姿素材缺失时 self._mascot_sleep 为 None，绘制端会自动退化成
        「一直显示坐姿」（见 _paint_mascot），不会崩。
        """
        self._mascot = load_mascot_pixmap(self._img_w, self._dpr)
        self._mascot_sleep = load_mascot_pixmap(self._img_w, self._dpr, pose="sleep")
        # 真 alpha 阴影层：保留猫的 alpha 轮廓，仅把 RGB 换成深色。
        # 逐层偏移叠加即得贴猫轮廓的真羽化投影（无 1-bit 二值硬边）。
        self._shadow_layer = self._make_shadow_layer(self._mascot)
        self._shadow_sleep = self._make_shadow_layer(self._mascot_sleep)

    def set_mascot_size(self, size: int) -> bool:
        """切换妮子大小（小 / 中 / 大）。返回**是否真的发生了变化**。

        调用方据此决定要不要顺手存一次窗口位置（见 qt/app.apply_settings）。

        保持**窗口中心不动**：换档后妮子仍在原来那块地方，不会"跳"走。
        窗口左上角坐标因此会变，所以换档后必须补存位置。
        """
        size = sanitize_mascot_size(size)
        if size == self._mascot_size:
            return False
        center = self.frameGeometry().center()
        self._mascot_size = self._img_w = self._img_h = size
        self._win_w, self._win_h = window_size_for(size)
        self.setFixedSize(self._win_w, self._win_h)
        # 尺寸变了，重新取一次 DPR 并按新边长重载素材与阴影底片
        self._dpr = current_device_pixel_ratio(self)
        self._reload_mascot()
        self.move(center.x() - self._win_w // 2, center.y() - self._win_h // 2)
        self.update()
        return True

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
        # 「显示主窗口」已移除：妮子常驻桌面时它是摆设；最小化隐藏后
        # 由托盘兜底找回（托盘菜单「显示」调 show_main）。
        self.menu.addAction("设置", self.ctrl.open_settings)
        self.act_pause = self.menu.addAction("暂停计时", self.ctrl.toggle_pause)
        self.menu.addAction("跳过本次", self.ctrl.on_skip)
        self.menu.addSeparator()
        self.menu.addAction("关闭…", self.ctrl.open_close_choice)
        # 暂停项文字里带「已停多久」，是个活值 —— 每次弹出前刷新一次，
        # 保证菜单一打开显示的就是当下准确的时长（托盘菜单同理由控制器刷新）。
        self.menu.aboutToShow.connect(self._refresh_pause_label)

    def _pause_label(self, paused: bool) -> str:
        """暂停菜单项文字。

        文案统一由控制器提供（ctrl.pause_label）——它与托盘菜单共用同一份逻辑，
        避免两处各写一套、改了一处忘了另一处。
        """
        return self.ctrl.pause_label(paused)

    def _refresh_pause_label(self):
        self.act_pause.setText(self._pause_label(self.ctrl.timer.is_paused))

    def set_paused(self, paused: bool):
        self.act_pause.setText(self._pause_label(paused))
        # 暂停时贴纸必须清晰可见（琥珀底 + 爪印变色），不能被"平时淡显"压暗。
        self._sync_capsule_alpha()
        # 姿态：暂停 → 睡姿，继续 → 坐姿。这里只负责"起过渡"，
        # 具体怎么画由 _paint_mascot 按 _pose_progress 决定。
        self._sync_pose_anim()

    def set_capsule_always(self, always: bool):
        """切换贴纸显示模式（设置窗保存后由控制器调用）。

        常驻 = 平时淡显挂着；非常驻 = 平时完全隐藏，仅悬停/暂停时出现。
        暂停态在两种模式下都会现身（重要的状态提示不该被藏掉）。
        """
        always = bool(always)
        if always == self._capsule_always:
            return
        self._capsule_always = always
        self._sync_capsule_alpha()

    def _alpha_target(self) -> float:
        """胶囊目标不透明度。

        暂停中或鼠标悬停 → 清晰（两种模式一致）；
        其余情况：常驻模式淡显，非常驻模式完全隐藏。
        暂停状态一律以计时器为准（唯一真相源）。窗口若自己再缓存一份，
        一旦某条路径只改了计时器没通知窗口，就会出现"底色变了但淡显没跟上"
        或反过来的精神分裂现象。
        """
        if self.ctrl.timer.is_paused or self._hover:
            return CAPSULE_FULL_ALPHA
        return CAPSULE_IDLE_ALPHA if self._capsule_always else 0.0

    def _sync_capsule_alpha(self):
        """按当前状态更新胶囊目标不透明度；确有变化才启动补间。"""
        target = self._alpha_target()
        if abs(target - self._cap_target) < 1e-9:
            return
        self._cap_target = target
        self._start_capsule_anim()

    # ------------------------------------------------------------ 计时
    def _refresh_time_text(self):
        """按当前状态刷新胶囊文字。

        计时中 → 剩余时间倒计时；
        暂停中 → **已暂停时长**（正计时）。暂停时剩余时间是冻住的、没有信息量，
        「已经停了多久」才是有用的信息（配合暂停超时自动恢复，
        还能看出还差多久会被自动继续）。
        """
        t = self.ctrl.timer
        if t.is_paused:
            m, s = divmod(t.paused_seconds(), 60)
        else:
            m, s = divmod(t.remaining(), 60)
        self._time_text = f"{m:02d}:{s:02d}"

    def _on_tick(self):
        # 常驻显示：不再要求"正在悬停"，每次 tick 都刷新
        old = self._time_text
        self._refresh_time_text()
        # 兜底：暂停状态可能由别处改变（托盘/菜单/气泡），这里顺带校准一次
        # 胶囊不透明度，保证底色与淡显始终一致。
        self._sync_capsule_alpha()
        # 同理兜底姿态：状态翻转了就起过渡（_sync_pose_anim 自己读计时器，
        # 窗口不多存一份"睡没睡着"）。过渡期间的重绘由 _step_pose_anim 驱动，
        # 所以这里不需要因为姿态而 set dirty。
        dirty = self._time_text != old
        self._sync_pose_anim()
        if dirty:
            self.update()
        # 暂停超时自动恢复：暂停会不会被"自动解冻"只有控制器知道，
        # 借这拍 250ms 的心跳问一次（放在这里是因为它已经在稳定地跑）。
        self.ctrl.check_pause_timeout()
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
        entering = self._cap_target > self._cap_progress   # True = 正在变清晰
        duration = CAPSULE_ANIM_MS_IN if entering else CAPSULE_ANIM_MS_OUT
        t_raw = (time.monotonic() - self._cap_anim_t0) * 1000.0 / duration
        t = max(0.0, min(1.0, t_raw))
        # 曲线：变清晰用缓出(先快后慢)，变淡用缓入(先慢后快)
        eased = self._ease_out_cubic(t) if entering else self._ease_in_cubic(t)
        # 从本次动画起点 _cap_anim_from 平滑逼近目标，避免改向时跳变
        self._cap_progress = self._cap_anim_from + (self._cap_target - self._cap_anim_from) * eased
        if t_raw >= 1.0:
            self._cap_progress = self._cap_target
            self._cap_anim.stop()
        self.update()

    # ------------------------------------------------------------ 姿态过渡动画
    @staticmethod
    def _ease_in_out_cubic(t: float) -> float:
        """两端慢、中间快。交叉淡化用它最自然：起点 / 终点不会突然"咔"一下。"""
        if t < 0.5:
            return 4.0 * t * t * t
        return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0

    def _sync_pose_anim(self):
        """把「该显示哪个姿态」与计时器对齐，需要就往目标起一次过渡。

        幂等：目标没变就原地返回 —— tick 每 250ms 调它一次，
        若每次都重置动画时间轴，过渡永远走不完。
        """
        want = 1.0 if self.ctrl.timer.is_paused else 0.0
        if abs(want - self._pose_target) < 1e-9:
            return
        self._pose_target = want
        if self._mascot_sleep is None:
            # 没有睡姿素材就无从过渡，直接到位（省得空跑 340ms 动画）。
            self._pose_progress = want
            self.update()
            return
        self._pose_anim_from = self._pose_progress
        self._pose_anim_t0 = time.monotonic()
        if not self._pose_anim.isActive():
            self._pose_anim.start()

    def _step_pose_anim(self):
        """按单调时钟推进过渡进度（与胶囊补间同一套"时间驱动"写法）。

        从 _pose_anim_from 平滑逼近 _pose_target，因此中途反向
        （过渡没走完就又切回来）也不会跳变。
        """
        t_raw = (time.monotonic() - self._pose_anim_t0) * 1000.0 / POSE_SWAP_MS
        t = max(0.0, min(1.0, t_raw))
        e = self._ease_in_out_cubic(t)
        self._pose_progress = self._pose_anim_from + (self._pose_target - self._pose_anim_from) * e
        if t_raw >= 1.0:
            self._pose_progress = self._pose_target
            self._pose_anim.stop()
        self.update()

    def _paint_mascot(self, p: QPainter):
        """绘制妮子本体，按 _pose_progress 表现坐姿 ↔ 睡姿的过渡。

        e = 0 → 只画坐姿；e = 1 → 只画睡姿；0 < e < 1 → 两张交叉淡化，
        各自的淡化 / 位移 / 缩放由 pose_blend() 给出（三者的方向都相反：
        一沉一升、一缩一放），所以重叠期两张不会挤在同一层次上。
        睡姿素材缺失时永远只画坐姿（不会崩，也不会白跑一趟动画）。
        """
        if self._mascot is None:
            return
        e = self._pose_progress
        if self._mascot_sleep is None or e <= 0.001:
            self._draw_pose(p, self._mascot, self._shadow_layer)
            return
        if e >= 0.999:
            self._draw_pose(p, self._mascot_sleep, self._shadow_sleep)
            return
        (a_sit, dy_sit, sc_sit), (a_sleep, dy_sleep, sc_sleep) = pose_blend(e)
        self._draw_pose(p, self._mascot, self._shadow_layer,
                        opacity=a_sit, dy=dy_sit, scale=sc_sit)
        self._draw_pose(p, self._mascot_sleep, self._shadow_sleep,
                        opacity=a_sleep, dy=dy_sleep, scale=sc_sleep)

    def _draw_pose(self, p: QPainter, mascot: QPixmap, shadow: QPixmap | None,
                   opacity: float = 1.0, dy: float = 0.0, scale: float = 1.0):
        """画一个姿态（含它的真羽化投影）。

        阴影走「猫图 alpha 蒙版 + 多圈半透明偏移叠加」：外圈随猫真实 alpha
        自然淡出，不用 1-bit 硬剪贴，浅色桌面上不会有一圈灰白硬边。

        opacity / dy / scale 供姿态过渡使用：**整层一起淡化、平移、缩放**
        （猫和它的影子共用同一套参数），否则会出现"猫在动、影子不动"的分离感。
        ⚠️ QPainter.setOpacity() 是**替换**语义而非累乘，所以每层都要手动乘 opacity。
        ⚠️ 坐标一律取整：非整数像素绘制会让高清素材重新采样、边缘发虚。
        """
        if opacity <= 0.001:
            return
        p.save()
        if abs(scale - 1.0) > 1e-6:
            # 缩放锚点取「猫身可见中心」而不是窗口中心 —— 窗口下方还有胶囊区，
            # 用窗口中心缩放会让猫看起来一边缩一边往下掉。
            cx = SHADOW_PAD + self._img_w / 2.0
            cy = SHADOW_PAD + self._img_h / 2.0
            p.translate(cx, cy)
            p.scale(scale, scale)
            p.translate(-cx, -cy)
        x = SHADOW_PAD
        y = SHADOW_PAD + dy
        if shadow is not None:
            # 层序：内圈偏移小透明度高（贴身立体感）→ 外圈偏移大透明度低（羽化）
            for dx, dy2, op in ((2, 3, 0.16), (4, 5, 0.10), (7, 8, 0.05)):
                p.save()
                p.setOpacity(op * opacity)
                p.drawPixmap(int(round(x + dx)), int(round(y + dy2)), shadow)
                p.restore()
        p.setOpacity(opacity)
        p.drawPixmap(int(round(x)), int(round(y)), mascot)
        p.restore()

    def _capsule_rect(self) -> QRectF:
        """胶囊矩形（常驻完整态，尺寸与位置恒定）。

        v0.5 起胶囊不再"长大/收起"，因此这里与不透明度无关：水平居中、
        底部对齐窗口下缘内侧留 pad。窗口高度本就是按「猫脚 + 空隙 + 胶囊高」
        推导出来的，所以胶囊始终完整落在猫身下方，既不遮妮子也不被裁切。
        坐标基于实例的 self._win_w / self._win_h —— 换档时胶囊自动跟着走。
        """
        cx = self._win_w / 2.0
        bottom = self._win_h - CAPSULE_BOTTOM_PAD
        return QRectF(cx - CAPSULE_BODY_W / 2, bottom - CAPSULE_BODY_H,
                      CAPSULE_BODY_W, CAPSULE_BODY_H)

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        self._paint_mascot(p)

        # 胶囊：常驻绘制；_cap_progress 即其当前不透明度
        # （平时淡显 / 悬停与暂停时清晰），淡入过程中会从 0 平滑上升。
        if self._time_text and self._cap_progress > 0.01:
            self._paint_capsule(p)

    def _make_shadow_layer(self, mascot: QPixmap | None):
        """由妮子位图生成一张「深色 + 保留 alpha」的阴影底片。

        阴影绘制时用 setOpacity 压层即可得到多层羽化；因为 alpha 是逐像素
        真渐变（不是 createHeuristicMask 的 1-bit 二值），外圈随猫 alpha 自然
        淡出，不会在浅色桌面上形成硬边描边。

        用字节级改写代替逐像素 pixelColor/setPixelColor：Format_ARGB32 每像素
        4 字节（小端序下为 B,G,R,A），只覆盖 BGR、保留 A，速度快一个量级。
        """
        if mascot is None:
            return None
        img = mascot.toImage().convertToFormat(QImage.Format_ARGB32)
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
        pm.setDevicePixelRatio(mascot.devicePixelRatio())
        return pm

    def _paint_capsule(self, p: QPainter):
        """绘制常驻倒计时贴纸（v0.6「爪印贴纸」）。

        不透明度由 _cap_progress 表达：平时淡显、悬停与暂停时清晰。
        结构：白色剪纸外框（贴纸感）→ 内芯（奶米/琥珀）→ 爪印图标 + 数字。
        暂停时内芯转琥珀、爪印与文字转深琥珀，"停着"一眼可辨。
        """
        inner = self._capsule_rect()
        alpha = max(0, min(255, int(self._cap_progress * 255)))
        paused = self.ctrl.timer.is_paused

        # 全部颜色先拷贝再改 alpha：qtheme 里的 QColor 是模块级共享对象，
        # 直接 setAlpha 会污染其他使用方。
        edge = QColor(qtheme.CAPSULE_STICKER_EDGE)
        bg = QColor(qtheme.CAPSULE_PAUSED_BG if paused else qtheme.CAPSULE_CREAM_BG)
        border = QColor(qtheme.CAPSULE_PAUSED_BORDER if paused
                        else qtheme.CAPSULE_CREAM_BORDER)
        text_col = QColor(qtheme.CAPSULE_PAUSED_TEXT if paused
                          else qtheme.CAPSULE_TEXT_BROWN)
        paw_col = QColor(qtheme.CAPSULE_PAUSED_TEXT if paused
                         else qtheme.CAPSULE_PAW)
        for c in (edge, bg, border, text_col, paw_col):
            c.setAlpha(alpha)

        # 白色剪纸外框：内芯四周外扩 CAPSULE_STICKER_PAD，圆角随外框高度
        outer = inner.adjusted(-CAPSULE_STICKER_PAD, -CAPSULE_STICKER_PAD,
                               CAPSULE_STICKER_PAD, CAPSULE_STICKER_PAD)
        outer_path = QPainterPath()
        outer_path.addRoundedRect(outer, outer.height() / 2, outer.height() / 2)
        p.fillPath(outer_path, edge)

        # 内芯
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner, inner.height() / 2, inner.height() / 2)
        p.fillPath(inner_path, bg)
        p.setPen(QPen(border, 1))
        p.drawPath(inner_path)

        if self._cap_progress > 0.3 and self._time_text:
            # 爪印图标：垂直居中、贴左
            self._paint_paw(p, paw_col,
                            inner.left() + 4.0 + CAPSULE_PAW_BOX / 2,
                            inner.center().y())
            # 数字：爪印右侧剩余区域居中
            text_rect = inner.adjusted(CAPSULE_PAW_BOX + CAPSULE_PAW_GAP, 0, 0, 0)
            p.setPen(text_col)
            p.setFont(make_time_font())
            p.drawText(text_rect, Qt.AlignCenter, self._time_text)

    def _paint_paw(self, p: QPainter, color: QColor, cx: float, cy: float):
        """以 (cx, cy) 为中心画一枚约 11×11 的猫爪印（主肉垫 + 四趾）。"""
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        s = CAPSULE_PAW_BOX / 11.0
        # 主肉垫
        p.drawEllipse(QPointF(cx, cy + 2.2 * s), 3.6 * s, 2.9 * s)
        # 四趾：左 → 右
        p.drawEllipse(QPointF(cx - 4.2 * s, cy - 2.6 * s), 1.5 * s, 1.5 * s)
        p.drawEllipse(QPointF(cx - 1.4 * s, cy - 3.9 * s), 1.5 * s, 1.5 * s)
        p.drawEllipse(QPointF(cx + 1.6 * s, cy - 3.7 * s), 1.5 * s, 1.5 * s)
        p.drawEllipse(QPointF(cx + 4.3 * s, cy - 2.0 * s), 1.4 * s, 1.4 * s)
        p.restore()

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
        # 左键「单击」不再做任何事（原先会弹设置窗，容易误触）。
        # 设置窗改由右键菜单或托盘菜单打开；左键只用于拖动，松手时记下位置。
        if e.button() == Qt.LeftButton and self._dragging:
            self.ctrl.save_window_pos(self.pos())
        self._press_global = None
        self._dragging = False

    def enterEvent(self, e):
        self._hover = True
        # 每次进入都重算：若沿用上次缓存，会先显示旧数字，
        # 最长要等 250ms 的下一次 tick 才刷新 —— 看上去就是"闪一下旧时间"。
        self._refresh_time_text()
        # 悬停 → 胶囊由淡显转为完全清晰
        self._sync_capsule_alpha()
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        # 胶囊不消失，只回落成"淡显"（暂停中则维持清晰）
        self._sync_capsule_alpha()
        self.update()
