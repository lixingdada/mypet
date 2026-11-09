# -*- coding: utf-8 -*-
"""
边缘姿势素材处理脚本（贴屏幕四边专用）
=====================================
与站立/姿势素材共用同一套 512x512 画布约定，但**贴边方式不同**：

  · 站立/普通姿势：底部对齐 + 水平居中
  · 边缘姿势：把内容贴到画布对应的一条边上
        peek_side  → 贴【左】边（脚仍在画布底部）
        peek_top   → 贴【上】边（水平居中）
        peek_bottom→ 贴【下】边（水平居中）

这样 pet.py 只需把画布贴到窗口对应的那条边，画面里的"裁切断口"就正好落在
屏幕（工作区）边缘上，形成"她藏在屏幕边后面"的错觉。

生成图里 AI 会画一道"墙沿"细线来表现遮挡，必须清掉，否则会变成桌面上
一条悬空的横线/竖线。判定办法：**又长又薄**（连续长度 > 画面 45%，
且垂直/水平厚度 <= 9px）才判为线，逐像素清除——手、裙子等粗结构不会误伤。
"""
import os
from collections import deque
import numpy as np
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "assets", "2d", "edges", "src")
OUT = os.path.join(BASE, "assets", "2d", "out")
os.makedirs(OUT, exist_ok=True)

CANVAS = 512
THRESH = 244          # 白底阈值（与 process_poses.py 一致）
A_ON = 40             # alpha 判定为"实心"的阈值

# 每个姿势：缩放系数 / 贴边位置 / 可选裁切
#   scale 按【头部大小】对齐站立立绘，保证贴边时人物大小不跳变
#   ay：top 贴画布顶 / middle 垂直居中 / bottom 贴画布底
#   cut_x：先丢掉 x < cut_x 的像素再做包围盒（用于"她躲在那道屏幕边后面"）
CFG = {
    # 左右「躲边探头」：她双手扒着屏幕边缘、探出上半身偷看（当前使用）
    #   ay="top" 让她的身体一直向下延伸到画布之外被裁掉，
    #   看上去就是"身体还在屏幕外、只有上半身探进来"，而不是被一刀切断
    "peek_l":      dict(scale=0.485,  ax="left",   ay="top",    cut_x=236),
    # 贴上/下：同样只看得到头+手，跟着贴左的头部尺寸一起放大（否则四边大小不一致）
    "peek_top":    dict(scale=0.4070, ax="center", ay="top"),
    "peek_bottom": dict(scale=0.3560, ax="center", ay="bottom"),
    # 备选（旧素材，整身竖切一半，pet.py 已不引用，随时可切回）
    "peek_side":   dict(scale=0.3558, ax="left",   ay="bottom"),
    "peek_side2":  dict(scale=0.3558, ax="left",   ay="bottom", drop_left_of_line=True),
}


def flood_remove_bg(img, thr=THRESH):
    """从四角洪水填充清除白/浅灰背景。"""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    def is_bg(x, y):
        r, g, b, a = px[x, y]
        return r >= thr and g >= thr and b >= thr

    visited = bytearray(w * h)
    q = deque()
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
             (w // 4, h // 2), (w * 3 // 4, h // 2)]
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


def _runs_h(mask):
    """每个像素所在的【水平连续段】长度。"""
    h, w = mask.shape
    idx = np.arange(w, dtype=np.int32)[None, :]
    last_false = np.maximum.accumulate(np.where(mask, -1, idx), axis=1)
    left = idx - last_false
    rev = np.arange(w - 1, -1, -1, dtype=np.int32)[None, :]
    next_false = np.minimum.accumulate(np.where(mask, w, rev), axis=1)
    right = next_false - rev
    return left + right - 1


def _runs_v(mask):
    """每个像素所在的【垂直连续段】长度。"""
    h, w = mask.shape
    up = np.zeros((h, w), np.int32)
    cur = np.zeros(w, np.int32)
    for y in range(h):
        cur = np.where(mask[y], cur + 1, 0)
        up[y] = cur
    down = np.zeros((h, w), np.int32)
    cur = np.zeros(w, np.int32)
    for y in range(h - 1, -1, -1):
        cur = np.where(mask[y], cur + 1, 0)
        down[y] = cur
    return up + down - 1


def remove_thin_lines(img, min_run_ratio=0.45, max_thick=9):
    """清除"又长又薄"的墙线：贯穿画面 45% 以上、厚度 <= 9px 的结构。

    逐像素判定，所以手、裙子等粗结构不会被误伤。
    返回 (img, 清除像素数, 竖线x列表, 横线y列表)。
    """
    w, h = img.size
    a = np.frombuffer(img.getchannel("A").tobytes(), np.uint8).reshape(h, w)
    mask = a > A_ON
    if not mask.any():
        return img, 0, [], []
    run_h = _runs_h(mask)      # 水平段长
    run_v = _runs_v(mask)      # 垂直段长（也就是垂直厚度）
    line_v = (run_v > h * min_run_ratio) & (run_h <= max_thick)   # 竖线
    line_h = (run_h > w * min_run_ratio) & (run_v <= max_thick)   # 横线
    line = line_v | line_h
    n = int(line.sum())
    if n:
        a2 = a.copy()
        a2[line] = 0
        img.putalpha(Image.frombytes("L", (w, h), a2.tobytes()))
    vx = sorted(set(np.where(line_v)[1].tolist()))
    hy = sorted(set(np.where(line_h)[0].tolist()))
    return img, n, vx, hy


def robust_bbox(img, thr=A_ON, min_cov=0.02):
    """稳健包围盒：取"显著内容"的最长连续行/列区间。

    不能用 img.getbbox()：抠图后背景是 (255,255,255,0)，RGB 非零会撑满整图；
    也不能只看"有任意像素"——画面底部/边缘常残留一道极淡的细线或淡影，
    会把包围盒撑到图片边缘，导致贴边时留出一道空隙。
    """
    a = np.asarray(img.getchannel("A"))
    m = a > thr
    h, w = m.shape
    row_cov = m.sum(axis=1) / float(w)
    col_cov = m.sum(axis=0) / float(h)

    def longest(prof):
        best, cur = (0, 0), None
        for i, v in enumerate(prof):
            if v > min_cov:
                if cur is None:
                    cur = i
            elif cur is not None:
                if i - cur > best[1] - best[0]:
                    best = (cur, i)
                cur = None
        if cur is not None:
            if len(prof) - cur > best[1] - best[0]:
                best = (cur, len(prof))
        return best

    y0, y1 = longest(row_cov)
    x0, x1 = longest(col_cov)
    if y1 <= y0 or x1 <= x0:
        return None
    return (x0, y0, x1, y1)


def make(name):
    cfg = CFG[name]
    path = os.path.join(SRC, name + ".png")
    if not os.path.exists(path):
        print("[跳过] 缺少", path)
        return None
    src = Image.open(path)
    img = flood_remove_bg(src)
    img, nline, vx, hy = remove_thin_lines(img)
    cut_x = cfg.get("cut_x")
    if cut_x:
        # 她扒着的"屏幕边缘"及其左侧全部丢掉：那片属于"屏幕外"，
        # 留着她被挡住的那半边只会让她看起来像被竖着切成两半
        a = np.array(img.getchannel("A"))
        a[:, :cut_x] = 0
        img.putalpha(Image.frombytes("L", img.size, a.tobytes()))
    if cfg.get("drop_left_of_line") and vx:
        # 墙沿左侧属于"被挡住的那半边"，全部丢掉落（否则左边的马尾会露在屏幕外）
        cut = vx[0]
        a = np.array(img.getchannel("A"))
        a[:, :cut] = 0
        img.putalpha(Image.frombytes("L", img.size, a.tobytes()))
        print("       └ 丢弃墙沿左侧 0..%d" % cut)
    bbox = robust_bbox(img)
    if not bbox:
        print("[失败] %s 抠图后为空" % name)
        return None
    if cut_x:
        # 左边界按 cut_x 对齐（内容紧贴她扒着的那道边缘）
        bbox = (min(bbox[0], cut_x), bbox[1], bbox[2], bbox[3])
    img = img.crop(bbox)
    w, h = img.size
    k = cfg["scale"]
    nw, nh2 = max(1, round(w * k)), max(1, round(h * k))
    img = img.resize((nw, nh2), Image.LANCZOS)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    x = 0 if cfg["ax"] == "left" else (CANVAS - nw) // 2
    if cfg["ay"] == "top":
        y = 0
    elif cfg["ay"] == "middle":
        y = (CANVAS - nh2) // 2
    else:
        y = CANVAS - nh2
    canvas.paste(img, (x, y), img)      # paste 会自动裁掉超出画布的部分
    canvas.save(os.path.join(OUT, "edge_" + name + ".png"))
    print("[完成] %-12s 清线%dpx 原%s → 输出 %dx%d 贴(%s,%s)"
          % (name, nline, bbox, nw, nh2, cfg["ax"], cfg["ay"]))
    return canvas


def main():
    made = {}
    for name in CFG:
        c = make(name)
        if c:
            made[name] = c
    for name, c in list(made.items()):
        if "side" in name or name.endswith("_l"):
            c.transpose(Image.FLIP_LEFT_RIGHT).save(
                os.path.join(OUT, "edge_%s_r.png" % name))
            print("[完成] %-12s 水平镜像（用于屏幕右边）" % (name + "_r"))
    print("全部完成")


if __name__ == "__main__":
    main()
