#!/usr/bin/env python3
"""卡面生成脚本：仿照模板绘制卡牌卡面。

用法：
    python tools/generate_cards.py            # 生成全部已定义卡牌
    python tools/generate_cards.py strike     # 只生成指定卡牌 key

卡面保存到 sources/images/card/<卡名>/<卡名>.png，
后期卡牌升级时重新生成同名牌即可覆盖。

模板素材：
    sources/images/card/普卡模板.png   （稀有度 COMMON 用）
    sources/images/card/蓝卡模板.png   （稀有度 UNCOMMON 用）
    sources/images/card/金卡模板.png   （稀有度 RARE 用）
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont

from game.card import Rarity
from game.cards import CARD_DEFS, make_card

CARD_DIR = os.path.join(ROOT, "sources", "images", "card")
TEMPLATE_DIR = CARD_DIR

FONT_PATH = "/System/Library/Fonts/STHeiti Light.ttc"

# 模板尺寸
TMP_W, TMP_H = 1728, 2432

# 布局坐标（基于 1728×2432 模板）
NAME_CY = 232          # 卡名带文字中心 y
DESC_TOP = 1620        # 描述文字起始 y
DESC_BOTTOM = 2180     # 描述文字结束 y
DESC_LINE_SPACING = 100

# 重量圆（左上角，自己绘制）
COST_CX = 190
COST_CY = 200
COST_R = 120

TEMPLATE_BY_RARITY = {
    Rarity.COMMON: "普卡模板.png",
    Rarity.STARTER: "普卡模板.png",
    Rarity.SPECIAL: "普卡模板.png",
    Rarity.UNCOMMON: "蓝卡模板.png",
    Rarity.RARE: "金卡模板.png",
}


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """按像素宽度自动换行。"""
    lines: list[str] = []
    current = ""
    for ch in text:
        if draw.textlength(current + ch, font=font) > max_width:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)
    return lines


def draw_cost_badge(draw: ImageDraw.ImageDraw, weight: int, logic: bool = False) -> None:
    """在左上角绘制重量圆框；逻辑牌绘制「逻辑」标签。"""
    cx, cy, r = COST_CX, COST_CY, COST_R
    # 外圈金色描边
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=(175, 145, 70), width=8, fill=(250, 246, 230),
    )
    # 内圈深色描边装饰
    draw.ellipse(
        [cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14],
        outline=(120, 100, 55), width=4,
    )
    if logic:
        font = load_font(120)
        text = "逻辑"
    else:
        font = load_font(200)
        text = str(weight)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=6)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]),
        text, font=font, fill=(60, 50, 30), stroke_width=6, stroke_fill=(60, 50, 30),
    )


def generate_card(key: str) -> str:
    """生成单张卡面，返回保存路径。

    只绘制静态部分：模板背景 + 标题（加粗）+ 重量圆（逻辑牌画「逻辑」）。
    描述文字（含可变数值）由 GUI 动态渲染，不写入卡面。
    """
    card = make_card(key)
    template_name = TEMPLATE_BY_RARITY.get(card.rarity, "普卡模板.png")
    template_path = os.path.join(TEMPLATE_DIR, template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板不存在：{template_path}")

    im = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(im)

    # 重量圆（左上角）
    draw_cost_badge(draw, card.weight, logic=card.logic)

    # 卡名（卡名带居中，加粗加大）
    name_font = load_font(150)
    name_bbox = draw.textbbox((0, 0), card.name, font=name_font, stroke_width=8)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]
    draw.text(
        (TMP_W / 2 - name_w / 2 - name_bbox[0], NAME_CY - name_h / 2 - name_bbox[1]),
        card.name, font=name_font, fill=(45, 40, 28), stroke_width=8, stroke_fill=(45, 40, 28),
    )

    # 按卡名建文件夹保存
    out_dir = os.path.join(CARD_DIR, card.name)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{card.name}.png")
    im.save(out_path)
    return out_path


def main() -> int:
    keys = list(CARD_DEFS.keys())
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        keys = [k for k in args if k in CARD_DEFS]
        if not keys:
            print(f"未找到卡牌 key：{args}，可用：{list(CARD_DEFS.keys())}")
            return 1

    for key in keys:
        try:
            path = generate_card(key)
            print(f"已生成：{path}")
        except Exception as exc:  # noqa: BLE001
            print(f"生成 {key} 失败：{exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
