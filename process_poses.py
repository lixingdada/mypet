# -*- coding: utf-8 -*-
"""
姿势素材处理脚本
思路（与站立立绘共用同一比例，避免蹲/坐/趴被拉伸放大）：
  1. 洪水填充清除白底（含浅灰投影），得到透明 PNG
  2. 按 alpha 通道取角色包围盒
  3. 用【固定缩放系数】k = 512 / 站立基准高度，所有姿势一视同仁
  4. 底部对齐（脚/身体贴地面）+ 水平居中，贴到 512x512 画布
这样站姿仍是满高 512，而蹲/趴/躺会按真实身量变矮。
"""
import os
from collections import deque
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "assets", "2d", "poses")
OUT = os.path.join(BASE, "assets", "2d", "out")
os.makedirs(OUT, exist_ok=True)

CANVAS = 512
# 站立基准：base_idle 原始图中角色高度（像素），用于确定统一缩放系数
SCALE_REF_H = 1439
K = CANVAS / SCALE_REF_H

POSES = ["squat", "sit", "prone", "lie", "stretch", "eat"]
THRESH = 244          # 白底判定阈值（略高，顺带清掉浅灰投影）


def flood_remove_bg(img, thr=THRESH):
    """从四角洪水填充清除白/浅灰背景，返回带 alpha 的图。"""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    def is_bg(x, y):
        r, g, b, a = px[x, y]
        return r >= thr and g >= thr and b >= thr

    visited = bytearray(w * h)
    q = deque()
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


def main():
    for name in POSES:
        src = os.path.join(SRC, name + ".png")
        if not os.path.exists(src):
            print(f"[跳过] 缺少 {name}.png")
            continue
        img = flood_remove_bg(Image.open(src))
        bbox = img.getbbox()          # 基于 alpha 的包围盒
        if not bbox:
            print(f"[失败] {name} 抠图后为空")
            continue
        img = img.crop(bbox)
        w, h = img.size
        nw, nh = max(1, round(w * K)), max(1, round(h * K))
        img = img.resize((nw, nh), Image.LANCZOS)

        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        x = (CANVAS - nw) // 2
        y = CANVAS - nh                # 底部对齐（负值会自动裁掉溢出部分）
        canvas.paste(img, (x, y), img)
        canvas.save(os.path.join(OUT, name + ".png"))
        print(f"[完成] {name}: 原{bbox} → 输出 {nw}x{nh}, 顶部y={y}, 高度占比 {nh/CANVAS:.0%}")


if __name__ == "__main__":
    main()
