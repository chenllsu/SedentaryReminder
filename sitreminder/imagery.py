"""位图资源生成：妮子形象、hover 倒计时胶囊动画帧。

PIL 是可选依赖：缺失时全部降级（形象退化为纯色/文字，胶囊改用 Canvas 矢量绘制），
保证「没有 Pillow 也能跑」，只是没那么好看。
"""

from __future__ import annotations

import logging
import os
import tkinter as tk
from typing import List, Optional

from . import paths, theme

log = logging.getLogger(__name__)

MASCOT_SIZE = (150, 150)
TIME_CAPSULE_SIZE = (150, 44)
_TIME_TEXT_POS = (75, 22)     # 胶囊内文字中心（与画布尺寸配套）


def _resample():
    """兼容新旧 Pillow：10.0 之后 LANCZOS 挪到了 Image.Resampling 下。"""
    from PIL import Image
    return getattr(Image, "LANCZOS", Image.BICUBIC)


def load_mascot(size=MASCOT_SIZE):
    """加载妮子形象，返回 PhotoImage；失败返回 None。

    抠图阶段已做过 defringe（边缘颜色取本体色）与羽化；这里再补两件事：
    1) 本体 alpha 强制二值化 —— 源图的渐变 alpha 在 Tk 上会晕出黑边；
    2) 阴影的 blur 必须在「最终显示分辨率」上做 —— 在 1920px 源图上模糊
       再缩到 150px，模糊量会被缩放倍率吃掉，阴影就会发硬。
    """
    if not os.path.exists(paths.MASCOT_PATH):
        log.warning("未找到形象资源：%s", paths.MASCOT_PATH)
        return None
    try:
        from PIL import Image, ImageFilter, ImageTk
    except ImportError:
        log.info("Pillow 未安装，尝试使用 Tk 原生解码 PNG")
        try:
            return tk.PhotoImage(file=paths.MASCOT_PATH)
        except tk.TclError as exc:
            log.warning("Tk 无法解码形象资源：%s", exc)
            return None

    try:
        src = Image.open(paths.MASCOT_PATH).convert("RGBA")
        src = src.transpose(Image.FLIP_LEFT_RIGHT)  # 水平镜像，原图文件保持不动

        # 1) 平滑 + 二值化的不透明 mask：边缘无毛刺、无半透明像素
        mask = src.split()[3].point(lambda a: 255 if a > 128 else 0)
        mask = mask.filter(ImageFilter.GaussianBlur(1.5)).point(
            lambda a: 255 if a > 128 else 0)

        # 2) RGB 与 mask 同步缩放，保证两者像素级对齐
        resample = _resample()
        src_s = src.resize(size, resample)
        mask_s = mask.resize(size, resample).point(lambda a: 255 if a > 128 else 0)

        cat = Image.new("RGBA", size, (0, 0, 0, 0))
        cat.paste(src_s, (0, 0), mask_s)
        cat.putalpha(mask_s)  # 强制二值 alpha

        # 3) 柔边阴影：色键是浅色，半透明像素向浅色混合不会发黑，
        #    所以可以放心做羽化渐变。压低最大 alpha + 缩小偏移 → 淡而贴身。
        sh_alpha = mask_s.filter(ImageFilter.GaussianBlur(2.2))
        sh_layer = Image.new("RGBA", size, (135, 130, 136, 80))  # 更淡的暖灰
        sh_img = Image.new("RGBA", size, (0, 0, 0, 0))
        sh_img.paste(sh_layer, (0, 0), sh_alpha)

        # 4) 合成：阴影向右下偏移 1px
        pad = 14
        width, height = size[0] + pad * 2, size[1] + pad * 2
        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        base.paste(sh_img, (pad + 1, pad + 1), sh_img)
        base.paste(cat, (pad, pad), cat)
        return ImageTk.PhotoImage(base)
    except Exception:
        log.exception("形象加载失败")
        return None


def make_time_frames() -> Optional[List[object]]:
    """预生成 hover 倒计时胶囊的生长动画帧（PIL 缺失时返回 None）。

    深色紧凑胶囊、无尾巴：与白色提醒卡形成「深浅两级」层级——
    轻信息用深色悬浮，重要提醒用白卡。3x 超采样抗锯齿。
    """
    try:
        from PIL import Image, ImageDraw, ImageTk
    except ImportError:
        return None

    width, height = TIME_CAPSULE_SIZE
    body_w, body_h = 112, 30
    body_x = (width - body_w) // 2
    body_y = 7
    anchor_x, anchor_y = width / 2, body_y      # 生长锚点=顶边中点（朝向妮子一侧）
    SS = 3                                      # 超采样倍数

    frames = []
    for i in range(theme.ANIM_STEPS + 1):
        scale = theme.grow_scale(i / theme.ANIM_STEPS)
        img = Image.new("RGBA", (width * SS, height * SS), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        def transform(x, y, s=scale):
            return ((anchor_x + (x - anchor_x) * s) * SS,
                    (anchor_y + (y - anchor_y) * s) * SS)

        p0 = transform(body_x, body_y)
        p1 = transform(body_x + body_w, body_y + body_h)
        draw.rounded_rectangle(
            [p0[0], p0[1], p1[0], p1[1]],
            radius=body_h / 2 * scale * SS,
            fill=theme.TIME_CAPSULE,
        )
        frames.append(ImageTk.PhotoImage(img.resize((width, height), _resample())))
    return frames


def time_text_pos():
    return _TIME_TEXT_POS
