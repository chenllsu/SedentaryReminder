#!/usr/bin/env python3
"""抠图：把妮子从浅色背景中分离为透明 PNG（保留全部本体，只去背景）。

方法：边缘连通 flood-fill。
从图片四边出发，只把"与四角背景色接近(色差<tol)且与边缘连通"的像素判为背景。
猫的白色本体(白肚皮/脸)虽然亮，但被灰色猫身包围，flood 从边缘沿浅色路径走不进去，
因此不会被误删 —— 这是阈值法做不到的（阈值法会把白肚皮当背景）。
"""
import os
import numpy as np
from collections import deque
from PIL import Image
from scipy import ndimage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
SRC = os.path.join(BASE_DIR, "A_3D_rendered_cute_chibi_ish_s_2026-08-21T07-29-39.png")
OUT = os.path.join(ASSET_DIR, "nizi_clean.png")


def main():
    img = np.array(Image.open(SRC).convert("RGB")).astype(np.int32)
    H, W, _ = img.shape

    # 四角采样背景色
    corners = [img[3, 3], img[H - 4, 3], img[3, W - 4], img[H - 4, W - 4]]
    bg = np.mean(corners, axis=0)
    print("背景色(RGB):", [int(c) for c in bg])

    # 与背景的色差
    dist = np.abs(img - bg).sum(axis=2)

    # 自适应容差：背景很亮(浅色)时给窄一点，避免吃掉猫的浅灰边缘
    tol = 60
    print("flood-fill 容差 tol =", tol)

    bgmask = np.zeros((H, W), dtype=bool)
    # 多源 BFS，只走"接近背景且连通边缘"的像素
    seeds = []
    for x in range(W):
        seeds.append((x, 0)); seeds.append((x, H - 1))
    for y in range(H):
        seeds.append((0, y)); seeds.append((W - 1, y))
    q = deque(seeds)
    while q:
        x, y = q.popleft()
        if not (0 <= x < W and 0 <= y < H):
            continue
        if bgmask[y, x]:
            continue
        if dist[y, x] >= tol:   # 不是背景 → 停止扩散（猫身挡住 flood）
            continue
        bgmask[y, x] = True
        q.append((x + 1, y)); q.append((x - 1, y))
        q.append((x, y + 1)); q.append((x, y - 1))

    cat = ~bgmask
    # 填补猫身内部极小空洞（白肚皮若被误判为洞则补回）
    cat = ndimage.binary_fill_holes(cat)
    # 开运算去毛刺（先腐蚀后膨胀）：把轮廓上 1px 的细尖刺/凹坑抹掉，
    # 比直接 dilation 更平滑（之前 dilation(1) 会让边缘整体外凸产生毛边）
    cat = ndimage.binary_opening(cat, iterations=1)

    # 只保留最大连通块：把背景里"色差刚好越线"导致被误判为猫的小白点碎块全删掉
    labels, n = ndimage.label(cat)
    if n > 1:
        sizes = ndimage.sum(cat, labels, range(1, n + 1))
        big_label = int(np.argmax(sizes)) + 1
        removed = cat.sum() - int(sizes[big_label - 1])
        print(f"连通块共 {n} 个，仅保留最大块({int(sizes[big_label-1])} 像素)，"
              f"删掉 {removed} 个噪点像素")
        cat = labels == big_label

    # 羽化：对二值 mask 做高斯模糊，输出渐变 alpha。
    soft = ndimage.gaussian_filter(cat.astype(np.float32), sigma=2.5)
    alpha = (np.clip(soft * 255, 0, 255)).astype(np.uint8)

    # —— 去色晕 defringe ——
    # 源图边缘像素 = 本体色与浅背景的混合（RGB≈238，接近背景 243），是白色锯齿的来源。
    # 把猫身边缘带（非核心区）的每个像素颜色，替换为"距离它最近的核心本体像素"的颜色，
    # 让边缘颜色与本体一致，白色浅晕/锯齿彻底消失。
    rgb = img.astype(np.int32)
    # 核心 = 猫身腐蚀 2px 剩下的区域（颜色可信的本体内部）
    ero = ndimage.binary_erosion(cat, iterations=2)
    if ero.sum() > 0:
        # distance_transform 返回每个像素到最近核心像素的坐标索引
        _, idx = ndimage.distance_transform_edt(~ero, return_indices=True)
        iy, ix = idx[0], idx[1]
        # 先复制，保证猫身内部(核心区)颜色完全不变
        new_rgb = rgb.copy()
        edge = cat & ~ero  # 边缘带：颜色需要替换的像素
        new_rgb[edge] = rgb[iy[edge], ix[edge]]
        # 对替换后的边缘带做 1px 高斯平滑，避免不同位置核心色造成的跳变
        for c in range(3):
            ch = new_rgb[..., c].astype(np.float32)
            sm = ndimage.gaussian_filter(ch, sigma=0.8)
            new_rgb[edge, c] = sm[edge]
        rgb = new_rgb

    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = alpha

    Image.fromarray(out, "RGBA").save(OUT)

    print("输出尺寸:", W, "x", H,
          " 透明像素占比: %.1f%%" % (100 * (out[..., 3] == 0).mean()))
    ys, xs = np.where(out[..., 3] > 0)
    if len(xs):
        print("猫身包围盒 x[%d,%d] y[%d,%d]" % (xs.min(), xs.max(), ys.min(), ys.max()))
    # 中心核透明率（应接近 0，说明本体没被抠空）
    cy, cx = H // 2, W // 2
    core = out[cy - 150:cy + 150, cx - 150:cx + 150, 3]
    print("中心核(±150)透明率: %.1f%% (本体完好应接近0)" % (100 * (core == 0).mean()))


if __name__ == "__main__":
    main()
