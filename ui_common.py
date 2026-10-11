"""UI 共享常量与工具：供 gui.py 与 fightui.py 共用。

只放「两个模块都要用」的常量 / 函数，避免循环 import。
"""

from __future__ import annotations

import os
import sys

import pygame

from game.state import Phase


def _resource_path(relative: str) -> str:
    """解析资源路径，兼容 PyInstaller 打包（资源被解包到 sys._MEIPASS）。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = _resource_path(os.path.join("sources", "images"))

WIDTH, HEIGHT = 1280, 800
FPS = 60

BG = (24, 26, 34)
PANEL = (38, 42, 56)
PANEL_EDGE = (60, 66, 86)
CARD_BG = (246, 243, 234)
CARD_TEXT = (40, 42, 50)
SLOT_BG = (30, 33, 44)
SLOT_EDGE = (70, 76, 96)
SLOT_ACTIVE_EDGE = (92, 156, 255)
TEXT = (235, 235, 240)
MUTED = (148, 150, 160)
ACCENT = (92, 156, 255)
GREEN = (88, 180, 120)
RED = (220, 90, 90)
YELLOW = (240, 200, 80)

CARD_W, CARD_H = 160, 224
SLOT_W, SLOT_H = 170, 240

VERSION = "R1.01"

# 结算动画帧数
STACK_FRAMES = 40
FLY_FRAMES = 24
EFFECT_FRAMES = 55
EFFECT_HOLD_FRAMES = 85  # 单机出牌后停留帧数（比 PVP 效果文字停留更久，给飘字看）
MONSTER_ANIM_FRAMES = 40  # 怪物攻击动画帧数
HOLD_FRAMES = 30          # PVP 牌飞行到中间后的停留帧数

PHASE_NAMES = {
    Phase.TURN_START: "回合开始",
    Phase.PLAYER_ACTION: "玩家行动",
    Phase.CLEAR_HAND: "弃置手牌",
    Phase.STATUS: "状态判定",
    Phase.RESOLVE_PILE: "结算牌堆",
    Phase.MONSTER: "怪物回合",
    Phase.TURN_END: "回合结束",
}


def load_font(size: int) -> pygame.font.Font:
    # 字体缓存：避免每帧重复 match_font 遍历（性能）
    cached = _FONT_CACHE.get(size)
    if cached is not None:
        return cached
    font = _load_font_uncached(size)
    _FONT_CACHE[size] = font
    return font


_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _load_font_uncached(size: int) -> pygame.font.Font:
    for name in (
        # macOS
        "PingFang SC",
        "Heiti SC",
        "Hiragino Sans GB",
        "STHeiti",
        "Songti SC",
        # Windows
        "Microsoft YaHei",
        "Microsoft YaHei UI",
        "SimHei",
        "SimSun",
        "Microsoft JhengHei",
        # 通用
        "Arial Unicode MS",
        "Noto Sans CJK SC",
        "WenQuanYi Micro Hei",
    ):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",     # 黑体
        "C:/Windows/Fonts/simsun.ttc",     # 宋体
        "C:/Windows/Fonts/msjh.ttc",       # 微软正黑体
    ):
        if os.path.exists(path):
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def weight_color(w: int) -> tuple[int, int, int]:
    """重量 1..10 从绿色渐变到红色。"""
    t = max(0.0, min(10.0, float(w)) - 1.0) / 9.0
    r = int(GREEN[0] + (RED[0] - GREEN[0]) * t)
    g = int(GREEN[1] + (RED[1] - GREEN[1]) * t)
    b = int(GREEN[2] + (RED[2] - GREEN[2]) * t)
    return (r, g, b)


def draw_image_fit(
    surface: pygame.Surface, path: str, area: pygame.Rect, flip: bool = False
) -> None:
    if not path or not os.path.isfile(path):
        return
    key = (path, flip)
    img = _IMAGE_CACHE.get(key)
    if img is None:
        try:
            img = pygame.image.load(path).convert_alpha()
        except pygame.error:
            return
        if flip:
            img = pygame.transform.flip(img, True, False)
        _IMAGE_CACHE[key] = img
    scale = min(area.width / img.get_width(), area.height / img.get_height())
    w, h = int(img.get_width() * scale), int(img.get_height() * scale)
    scaled = pygame.transform.smoothscale(img, (w, h))
    surface.blit(scaled, scaled.get_rect(center=area.center))


_IMAGE_CACHE: dict[tuple[str, bool], pygame.Surface] = {}
