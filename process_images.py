# -*- coding: utf-8 -*-
"""
抠图脚本 v2：用洪水填充法清除白底（从四角开始），只清除与边缘连通的白色，
不影响角色内部的浅色区域。输出统一 512x512 透明 PNG。
"""
import os
import sys
from collections import deque
from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "2d")
OUT = os.path.join(SRC, "out")
os.makedirs(OUT, exist_ok=True)

NAMES = ["base_idle", "happy", "moe", "surprised", "sleepy", "angry", "walk", "dragged", "wave"]
TARGET = 512
# 判定"接近白色"的阈值（RGB 各通道最低值）
THRESH = 235


def flood_remove_bg(img):
    """从四角洪水填充清除白色背景。"""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    def is_bg(x, y):
        r, g, b, a = px[x, y]
        return r >= THRESH and g >= THRESH and b >= THRESH

    visited = bytearray(w * h)
    q = deque()
    # 四个角 + 四条边中点作为种子
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for x, y in seeds:
        if is_bg(x, y) and not visited[y * w + x]:
            visited[y * w + x] = 1
            q.append((x, y))

    while q:
        x, y = q.popleft()
        px[x, y] = (255, 255, 255, 0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx] and is_bg(nx, ny):
                visited[ny * w + nx] = 1
                q.append((nx, ny))
    return img


def crop_and_pad(img):
    bbox = img.getbbox()
    if not bbox:
        return img
    img = img.crop(bbox)
    w, h = img.size
    scale = min(TARGET / w, TARGET / h)
    nw, nh = int(w * scale), int(h * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (TARGET, TARGET), (0, 0, 0, 0))
    canvas.paste(img, ((TARGET - nw) // 2, (TARGET - nh) // 2), img)
    return canvas


def main():
    ok = True
    for name in NAMES:
        src_path = os.path.join(SRC, name + ".png")
        if not os.path.exists(src_path):
            print(f"[跳过] {src_path}")
            continue
        img = Image.open(src_path)
        img = flood_remove_bg(img)
        img = crop_and_pad(img)
        img.save(os.path.join(OUT, name + ".png"))
        print(f"[完成] {name}.png")
    print("全部完成" if ok else "有跳过")


if __name__ == "__main__":
    main()
