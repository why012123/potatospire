#!/usr/bin/env python3
"""对杀戮尖塔2卡牌图片做「去文字」处理，生成空卡牌模板。

原理：
  卡牌上的文字（卡名、能量数字、描述文字）都是接近白色的像素，
  而背景是彩色插画 / 深灰文字框 / 绿色能量圆。脚本检测出白色文字像素，
  再用其周围非文字像素的颜色做 inpainting 填充，从而抹掉文字。

用法：
  # 处理单张卡牌
  python edit_cards.py sourcecache/sts2/Abrasive.png

  # 处理整个目录（默认输出到 <输入目录>/_blank/）
  python edit_cards.py sourcecache/sts2

  # 指定输出目录
  python edit_cards.py sourcecache/sts2 --out sourcecache/sts2_blank

依赖：
  pip install pillow

版权与合规提示：
  素材版权归游戏厂商所有，本脚本仅供个人学习、研究参考，请勿用于分发或商业用途。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

# 白色文字判定：亮度阈值 + 饱和度上限（接近灰白）
WHITE_LUM = 190
WHITE_SAT = 45  # max(r,g,b) - min(r,g,b) 小于该值视为灰白

# 深灰文字框背景色（用于识别描述文字框与其中的彩色关键词）
GRAY_LO, GRAY_HI = 35, 100
GRAY_SAT = 30  # 深灰背景的饱和度上限

# inpainting 采样半径（像素）
RADIUS = 6

SCRIPT_DIR = Path(__file__).resolve().parent


def _lum(r: int, g: int, b: int) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _sat(r: int, g: int, b: int) -> int:
    return max(r, g, b) - min(r, g, b)


def is_white_text(r: int, g: int, b: int) -> bool:
    return _lum(r, g, b) > WHITE_LUM and _sat(r, g, b) < WHITE_SAT


def is_gray_bg(r: int, g: int, b: int) -> bool:
    """深灰文字框背景色。"""
    return (
        GRAY_LO <= r <= GRAY_HI
        and GRAY_LO <= g <= GRAY_HI
        and GRAY_LO <= b <= GRAY_HI
        and _sat(r, g, b) < GRAY_SAT
    )


def strip_text(img: Image.Image) -> Image.Image:
    """返回去掉文字后的图像副本。

    分两类文字处理：
    1. 白色文字（卡名/能量/描述白字）——全局检测，inpainting 填充。
    2. 深灰文字框内的彩色关键词——检测「周围以深灰背景为主」的
       高饱和彩色像素，填充为深灰背景。
    """
    w, h = img.size
    src = img.convert("RGBA")
    px = src.load()

    # 1) 白字 mask + 深灰背景 mask
    white_mask = [[False] * w for _ in range(h)]
    gray_mask = [[False] * w for _ in range(h)]
    white_pixels: list[tuple[int, int]] = []
    for y in range(h):
        wrow = white_mask[y]
        grow = gray_mask[y]
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 10:
                continue
            if is_white_text(r, g, b):
                wrow[x] = True
                white_pixels.append((x, y))
            elif is_gray_bg(r, g, b):
                grow[x] = True

    out = src.copy()
    opx = out.load()

    if not white_pixels and not any(any(r) for r in gray_mask):
        print("  未检测到文字像素，跳过")
        return out

    # 2) 白字 inpainting：用周围非白字像素的众数颜色填充
    for x, y in white_pixels:
        colors: dict[tuple[int, int, int], int] = {}
        for dy in range(-RADIUS, RADIUS + 1):
            yy = y + dy
            if yy < 0 or yy >= h:
                continue
            for dx in range(-RADIUS, RADIUS + 1):
                xx = x + dx
                if xx < 0 or xx >= w:
                    continue
                if white_mask[yy][xx]:
                    continue
                r, g, b, a = px[xx, yy]
                if a <= 10:
                    continue
                key = (r, g, b)
                colors[key] = colors.get(key, 0) + 1
        if colors:
            fill = max(colors.items(), key=lambda kv: kv[1])[0]
            opx[x, y] = (*fill, 255)

    # 3) 深灰文字框内的彩色关键词：像素高饱和且周围深灰背景占比高
    color_pixels: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 10 or white_mask[y][x] or gray_mask[y][x]:
                continue
            # 高饱和彩色（关键词通常是金色/绿色等纯色）
            if _sat(r, g, b) < 60:
                continue
            if _lum(r, g, b) < 90:
                continue
            # 周围深灰背景占比
            gray_cnt = 0
            total = 0
            for dy in range(-4, 5):
                yy = y + dy
                if yy < 0 or yy >= h:
                    continue
                for dx in range(-4, 5):
                    xx = x + dx
                    if xx < 0 or xx >= w:
                        continue
                    if xx == x and yy == y:
                        continue
                    if px[xx, yy][3] <= 10:
                        continue
                    total += 1
                    if gray_mask[yy][xx]:
                        gray_cnt += 1
            if total > 0 and gray_cnt / total >= 0.45:
                color_pixels.append((x, y))

    # 用深灰背景色填充彩色关键词
    for x, y in color_pixels:
        opx[x, y] = (64, 64, 64, 255)

    return out


def process_image(path: Path, out_path: Path) -> None:
    img = Image.open(path)
    result = strip_text(img)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    print(f"  已处理: {path.name} -> {out_path.name}")


def main() -> int:
    global RADIUS

    parser = argparse.ArgumentParser(description="去除杀戮尖塔2卡牌文字，生成空模板")
    parser.add_argument("target", help="输入图片文件或目录")
    parser.add_argument("--out", default=None, help="输出目录（默认 <输入目录>/_blank）")
    parser.add_argument("--radius", type=int, default=RADIUS, help=f"inpainting 半径（默认 {RADIUS}）")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"[错误] 路径不存在: {target}", file=sys.stderr)
        return 1

    RADIUS = args.radius

    if target.is_file():
        out_dir = Path(args.out) if args.out else target.parent / "_blank"
        process_image(target, out_dir / target.name)
    else:
        out_dir = Path(args.out) if args.out else target / "_blank"
        files = sorted(
            p for p in target.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )
        if not files:
            print("目录内没有图片文件。")
            return 0
        print(f"共 {len(files)} 张图片，输出到 {out_dir}")
        for f in files:
            process_image(f, out_dir / f.name)

    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
