# -*- coding: utf-8 -*-
"""生成桌宠的图标：assets/icon.ico（多尺寸）+ icon_preview.png（各尺寸效果预览）。

桌面快捷方式 / 启动文件夹里的那条 .lnk 都指向 pythonw.exe，图标会退化成
Python 的"文档+蟒蛇"（缩到 48px 像只黄鸭子）。这里拿她的立绘抠一张头像，
做成粉底圆徽章，48px 下也认得出是她。

用法：python make_icon.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "assets", "2d", "out", "base_idle.png")
OUT_ICO = os.path.join(BASE, "assets", "icon.ico")
OUT_PNG = os.path.join(BASE, "assets", "icon.png")
OUT_PREVIEW = os.path.join(BASE, "icon_preview.png")

MASTER = 1024                     # 先在大画布上画，再缩下来（超采样，边缘才干净）
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

# 立绘里"她的头"那一块（512x512 画布坐标）：耳朵顶端到下巴，左右留一点头发
CROP = (140, 0, 384, 244)
C_PINK_DK = (238, 120, 158, 255)
C_PINK_LT = (255, 246, 250, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build_master():
    """粉底圆徽章 + 她的脸（圆内裁切）+ 一点高光。"""
    img = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 底：竖向渐变（上浅下稍深），裁成圆
    grad = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(MASTER):
        t = y / MASTER
        gd.line([(0, y), (MASTER, y)], fill=lerp(C_PINK_LT[:3], (255, 214, 231), t) + (255,))
    mask = Image.new("L", (MASTER, MASTER), 0)
    ImageDraw.Draw(mask).ellipse((8, 8, MASTER - 8, MASTER - 8), fill=255)
    img.paste(grad, (0, 0), mask)

    # 她：从立绘裁头像 → 缩到圆内
    src = Image.open(SRC).convert("RGBA").crop(CROP).resize((MASTER - 40, MASTER - 40),
                                                           Image.LANCZOS)
    face = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    face.paste(src, (20, 14), src)
    fmask = Image.new("L", (MASTER, MASTER), 0)
    ImageDraw.Draw(fmask).ellipse((26, 22, MASTER - 26, MASTER - 22), fill=255)
    img.paste(face, (0, 0), fmask)

    # 顶部一层柔和高光，看着有点玻璃感
    gloss = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse((-140, -360, MASTER + 140, int(MASTER * 0.58)),
                                  fill=(255, 255, 255, 58))
    gloss = gloss.filter(ImageFilter.GaussianBlur(28))
    img.alpha_composite(Image.composite(gloss, Image.new("RGBA", img.size, (0, 0, 0, 0)), mask))

    # 描边：外面一圈深粉，里面一圈白，缩到 16px 也还是个"徽章"
    d.ellipse((8, 8, MASTER - 8, MASTER - 8), outline=C_PINK_DK, width=26)
    d.ellipse((40, 40, MASTER - 40, MASTER - 40), outline=(255, 255, 255, 235), width=14)
    return img


def main():
    master = build_master()
    master.resize((256, 256), Image.LANCZOS).save(OUT_PNG)
    master.save(OUT_ICO, sizes=[(s, s) for s in SIZES])
    print("已生成 %s（%s）" % (os.path.basename(OUT_ICO),
                          " / ".join("%dpx" % s for s in SIZES)))

    # 预览：浅色 + 深色背景各来一排，尺寸从小到大
    pad, gap, label_h = 16, 14, 18
    row_w = sum(SIZES) + gap * (len(SIZES) - 1)
    cell_h = 256 + label_h + 12
    out = Image.new("RGB", (pad * 2 + row_w, pad * 2 + cell_h * 2 + 30), (247, 243, 246))
    d = ImageDraw.Draw(out)
    try:
        f = lambda n: __import__("PIL").ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", n)
        f13 = f(13)
    except Exception:
        f13 = None
    for i, (bg, name) in enumerate([((255, 255, 255), "浅色壁纸"), ((44, 48, 62), "深色壁纸")]):
        y0 = pad + i * (cell_h + 8)
        d.rectangle((pad, y0, pad + row_w, y0 + cell_h), fill=bg)
        x = pad
        for s in SIZES:
            ic = master.resize((s, s), Image.LANCZOS)
            out.paste(ic, (x + (s - s) // 2, y0 + 256 - s + 8), ic)
            if f13:
                t = "%d" % s
                d.text((x + s // 2 - 6, y0 + 256 + 12), t, font=f13,
                       fill=(120, 110, 118) if i == 0 else (210, 205, 215))
            x += s + gap
    out.save(OUT_PREVIEW)
    print("已生成 %s %s" % (os.path.basename(OUT_PREVIEW), out.size))


if __name__ == "__main__":
    main()
