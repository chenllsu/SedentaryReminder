"""Canvas 绘图辅助（Tk 没有原生圆角矩形）。"""

from __future__ import annotations


def round_rect(canvas, x0, y0, x1, y1, radius, **kw):
    """在 Canvas 上画圆角矩形。

    半径会自动收敛到「不超过短边的一半」：生长动画的前几帧矩形很小，
    若还按原始半径画，四个角会互相穿透，出现畸形色块。
    """
    width, height = x1 - x0, y1 - y0
    radius = max(0.0, min(float(radius), width / 2.0, height / 2.0))

    if radius <= 0:
        canvas.create_rectangle(x0, y0, x1, y1, **kw)
        return

    canvas.create_arc(x0, y0, x0 + 2 * radius, y0 + 2 * radius,
                      start=90, extent=90, style="pieslice", **kw)
    canvas.create_arc(x1 - 2 * radius, y0, x1, y0 + 2 * radius,
                      start=0, extent=90, style="pieslice", **kw)
    canvas.create_arc(x1 - 2 * radius, y1 - 2 * radius, x1, y1,
                      start=270, extent=90, style="pieslice", **kw)
    canvas.create_arc(x0, y1 - 2 * radius, x0 + 2 * radius, y1,
                      start=180, extent=90, style="pieslice", **kw)
    canvas.create_rectangle(x0 + radius, y0, x1 - radius, y1, **kw)
    canvas.create_rectangle(x0, y0 + radius, x1, y1 - radius, **kw)
