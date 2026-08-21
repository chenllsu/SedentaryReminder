#!/usr/bin/env python3
"""针对用户抠好的 3D 猫图（白底 JPG）精细化抠图 -> 透明 PNG。

流程：
1. 边缘连通 flood-fill 去白底（容差 tol，从四边出发只删与边缘连通且接近白底的区域）
2. 仅保留最大连通块（清掉右下角"豆包AI生成"水印、JPEG 杂点等小连通块）
3. 去色晕 defringe：把边缘带像素颜色替换为最近的核心本体色，消除白底残留的浅白边
4. 羽化：mask 高斯模糊输出渐变 alpha，边缘平滑过渡
"""
import os
import numpy as np
from collections import deque
from PIL import Image
from scipy import ndimage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
SRC = os.path.join(ASSET_DIR, "nizi_user_source.jpg")
OUT = os.path.join(ASSET_DIR, "nizi_clean.png")


def main():
    img = np.array(Image.open(SRC).convert("RGB")).astype(np.int32)
    H, W, _ = img.shape

    bg = np.array([255, 255, 255])  # 白底
    dist = np.abs(img - bg).sum(axis=2)

    tol = 30  # 略留余量，覆盖 JPEG 边缘杂色，又不漫入猫白肚皮
    print("flood-fill 容差 tol =", tol)

    bgmask = np.zeros((H, W), dtype=bool)
    q = deque([(x, 0) for x in range(W)] + [(x, H - 1) for x in range(W)] +
              [(0, y) for y in range(H)] + [(W - 1, y) for y in range(H)])
    while q:
        x, y = q.popleft()
        if not (0 <= x < W and 0 <= y < H):
            continue
        if bgmask[y, x]:
            continue
        if dist[y, x] >= tol:
            continue
        bgmask[y, x] = True
        q += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    cat = ~bgmask
    cat = ndimage.binary_fill_holes(cat)
    cat = ndimage.binary_opening(cat, iterations=1)

    # 仅保留最大连通块（删水印/杂点）
    labels, n = ndimage.label(cat)
    sizes = ndimage.sum(cat, labels, range(1, n + 1))
    big = int(np.argmax(sizes)) + 1
    removed = int(cat.sum() - sizes[big - 1])
    print(f"连通块 {n} 个，仅保留最大块({int(sizes[big-1])} 像素)，删 {removed} 噪点像素")
    cat = labels == big

    # 羽化渐变 alpha
    soft = ndimage.gaussian_filter(cat.astype(np.float32), sigma=2.5)
    alpha = (np.clip(soft * 255, 0, 255)).astype(np.uint8)

    # 去色晕：边缘带颜色替换为最近核心本体色
    rgb = img.copy()
    ero = ndimage.binary_erosion(cat, iterations=2)
    if ero.sum() > 0:
        _, idx = ndimage.distance_transform_edt(~ero, return_indices=True)
        iy, ix = idx[0], idx[1]
        edge = cat & ~ero
        rgb[edge] = img[iy[edge], ix[edge]]
        for c in range(3):
            ch = rgb[..., c].astype(np.float32)
            rgb[edge, c] = ndimage.gaussian_filter(ch, sigma=0.8)[edge]

    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[..., 3] = alpha
    Image.fromarray(out, "RGBA").save(OUT)

    print("输出尺寸:", W, "x", H, " 透明像素占比: %.1f%%" % (100 * (out[..., 3] == 0).mean()))
    ys, xs = np.where(out[..., 3] > 0)
    print("猫身包围盒 x[%d,%d] y[%d,%d]" % (xs.min(), xs.max(), ys.min(), ys.max()))
    cy, cx = H // 2, W // 2
    core = out[cy - 200:cy + 200, cx - 200:cx + 200, 3]
    print("中心核(±200)透明率: %.1f%% (本体完好应接近0)" % (100 * (core == 0).mean()))


if __name__ == "__main__":
    main()
