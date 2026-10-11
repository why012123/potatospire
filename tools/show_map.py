"""六边形探索地图可视化预览。

展示：中心起点 + 六角 Boss（对角同一 Boss，共 3 个）、普通战斗/事件/火堆/精英
按 30/30/20/20 占比随机分布、相邻危险度、迷雾与「侦查 → 移动」流程。

用法：
    python tools/show_map.py [radius] [seed]

按键：
    R / Enter  重新生成
    F          切换迷雾（隐藏未揭示房间）
    Q          切换危险度数字（中央红字 = 相邻 战斗+精英 数量，覆盖类型标签）
    S          进入/退出侦查模式（每回合最多侦查相邻 2 格）
    鼠标点击   侦查模式下：侦查点击的相邻格；普通模式：移动到相邻格
    ESC        退出
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game.map import (  # noqa: E402
    BOSS_COLORS,
    MAX_SCOUTS_PER_TURN,
    ROOM_COLORS,
    ROOM_LABELS,
    RoomType,
    generate_map,
    hex_centers,
    hex_vertices,
)

WIDTH, HEIGHT = 1100, 900
BG = (24, 26, 34)
PANEL = (38, 42, 56)
TEXT = (235, 235, 240)
MUTED = (148, 150, 160)
DANGER = (235, 70, 70)
LINK = (100, 106, 130)
FOG = (58, 60, 72)
FOG_EDGE = (80, 84, 98)
PLAYER_RING = (120, 210, 255)
MOVE_RING = (90, 230, 170)
SCOUT_RING = (240, 200, 80)

HEX_SIZE = 40
DEFAULT_RADIUS = 5


def load_font(size: int) -> pygame.font.Font:
    for name in (
        "PingFang SC", "Heiti SC", "Hiragino Sans GB", "STHeiti", "Songti SC",
        "Microsoft YaHei", "SimHei", "Arial Unicode MS", "Noto Sans CJK SC",
    ):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ):
        if os.path.exists(path):
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def layout(gmap) -> dict[int, tuple[int, int]]:
    """把地图坐标映射到屏幕像素（y 轴翻转：r 增大的方向朝上）。"""
    centers = hex_centers(gmap, HEX_SIZE)
    xs = [p[0] for p in centers.values()]
    ys = [p[1] for p in centers.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    top = 70
    bottom = HEIGHT - 120
    scale = min((WIDTH - 80) / (max_x - min_x), (bottom - top) / (max_y - min_y))
    scale = min(scale, 1.0)
    world_cx = (min_x + max_x) / 2
    world_cy = (min_y + max_y) / 2
    result = {}
    for rid, (x, y) in centers.items():
        sx = WIDTH / 2 + (x - world_cx) * scale
        sy = (top + bottom) / 2 - (y - world_cy) * scale  # 翻转
        result[rid] = (int(sx), int(sy))
    return result


def draw_map(screen, gmap, positions, font, font_small, fog_on: bool,
             show_danger: bool, scout_mode: bool) -> None:
    cur = gmap.current_room
    moves = {r.id for r in gmap.available_moves()}

    # 连线（只画双方都可见的边）
    for room in gmap.rooms.values():
        x1, y1 = positions[room.id]
        for nid in room.neighbors:
            if nid > room.id:
                x2, y2 = positions[nid]
                pygame.draw.line(screen, LINK, (x1, y1), (x2, y2), 3)

    # 六边形
    for room in gmap.rooms.values():
        x, y = positions[room.id]
        visible = (not fog_on) or room.revealed
        if not visible:
            # 迷雾：灰色 + 问号（危险度模式下仍只显示数字）
            pts = [(int(vx), int(vy)) for vx, vy in hex_vertices(x, y, HEX_SIZE)]
            pygame.draw.polygon(screen, FOG, pts)
            pygame.draw.polygon(screen, FOG_EDGE, pts, 2)
            if show_danger:
                danger = gmap.danger(room.id)
                dcolor = DANGER if danger > 0 else MUTED
                dsurf = font.render(str(danger), True, dcolor)
                screen.blit(dsurf, dsurf.get_rect(center=(x, y)))
            else:
                q = font_small.render("?", True, MUTED)
                screen.blit(q, q.get_rect(center=(x, y)))
            continue

        color = ROOM_COLORS[room.room_type]
        if room.room_type is RoomType.BOSS and room.boss_key:
            color = BOSS_COLORS[room.boss_key]
        pts = [(int(vx), int(vy)) for vx, vy in hex_vertices(x, y, HEX_SIZE)]
        pygame.draw.polygon(screen, color, pts)
        pygame.draw.polygon(screen, (50, 52, 64), pts, 2)

        # 中央内容：危险度数字 或 类型标签（二者互斥）
        if show_danger:
            danger = gmap.danger(room.id)
            dcolor = DANGER if danger > 0 else MUTED
            dsurf = font.render(str(danger), True, dcolor)
            screen.blit(dsurf, dsurf.get_rect(center=(x, y)))
        elif room.room_type is RoomType.BOSS and room.boss_key:
            label = {"boss_a": "Ⅰ", "boss_b": "Ⅱ", "boss_c": "Ⅲ"}[room.boss_key]
            surf = font.render(label, True, (255, 255, 255))
            screen.blit(surf, surf.get_rect(center=(x, y)))
        else:
            label = ROOM_LABELS[room.room_type]
            if label:
                surf = font.render(label, True, (30, 30, 38))
                screen.blit(surf, surf.get_rect(center=(x, y)))

    # 玩家当前位置高亮
    px, py = positions[cur.id]
    pygame.draw.circle(screen, PLAYER_RING, (px, py), HEX_SIZE + 5, 3)

    # 可移动 / 可侦查房间高亮（迷雾模式下）
    if fog_on:
        for mid in moves:
            mx, my = positions[mid]
            color = SCOUT_RING if scout_mode else MOVE_RING
            pygame.draw.circle(screen, color, (mx, my), HEX_SIZE + 3, 2)


def draw_hud(screen, font, gmap, fog_on: bool, show_danger: bool, scout_mode: bool) -> None:
    y = 34
    segs = [
        f"半径 {gmap.radius}",
        f"迷雾 {'开' if fog_on else '关'}(F)",
        f"危险度 {'开' if show_danger else '关'}(Q)",
        f"侦查 {'进行中' if scout_mode else '待命'}(S)",
        f"本回合已侦查 {gmap.scouts_this_turn}/{MAX_SCOUTS_PER_TURN}",
    ]
    text = "   |   ".join(segs)
    surf = font.render(text, True, TEXT)
    screen.blit(surf, surf.get_rect(midtop=(WIDTH // 2, 6)))


def draw_legend(screen, font) -> None:
    y = HEIGHT - 56
    items = [
        (ROOM_COLORS[RoomType.EVENT], "事件"),
        (ROOM_COLORS[RoomType.BATTLE], "战斗"),
        (ROOM_COLORS[RoomType.REST], "火堆"),
        (ROOM_COLORS[RoomType.ELITE], "精英"),
        (BOSS_COLORS["boss_a"], "Boss Ⅰ"),
        (BOSS_COLORS["boss_b"], "Boss Ⅱ"),
        (BOSS_COLORS["boss_c"], "Boss Ⅲ"),
    ]
    x = 24
    for color, name in items:
        pygame.draw.circle(screen, color, (x + 10, y + 8), 10)
        pygame.draw.circle(screen, (50, 52, 64), (x + 10, y + 8), 10, 2)
        surf = font.render(name, True, TEXT)
        screen.blit(surf, (x + 26, y))
        x += 26 + surf.get_width() + 22
    tip = font.render("Q 中央数字 = 相邻 战斗+精英 数量", True, MUTED)
    screen.blit(tip, tip.get_rect(midright=(WIDTH - 24, y + 8)))


def click_to_room(gmap, positions, pos) -> int | None:
    """把鼠标位置映射到最近的房间 id（距离 < 外接圆半径）。"""
    best, best_d = None, HEX_SIZE * 1.1
    for rid, (x, y) in positions.items():
        d = ((pos[0] - x) ** 2 + (pos[1] - y) ** 2) ** 0.5
        if d < best_d:
            best, best_d = rid, d
    return best


def main() -> None:
    radius = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RADIUS
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else None

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("土豆尖塔 · 六边形探索地图")
    clock = pygame.time.Clock()
    font = load_font(20)
    font_small = load_font(15)
    font_title = load_font(26)

    gmap = generate_map(radius=radius, seed=seed)
    positions = layout(gmap)
    fog_on = False
    show_danger = False
    scout_mode = False
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE,):
                    running = False
                elif event.key == pygame.K_q:
                    show_danger = not show_danger
                elif event.key in (pygame.K_r, pygame.K_RETURN):
                    gmap = generate_map(radius=radius)
                    positions = layout(gmap)
                    scout_mode = False
                elif event.key == pygame.K_f:
                    fog_on = not fog_on
                elif event.key == pygame.K_s:
                    scout_mode = not scout_mode
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                rid = click_to_room(gmap, positions, event.pos)
                if rid is None:
                    continue
                if scout_mode:
                    # 侦查模式：侦查点击的相邻格（每回合最多 2 格）
                    result = gmap.scout(rid)
                    if result is None and gmap.scouts_this_turn >= MAX_SCOUTS_PER_TURN:
                        scout_mode = False  # 侦查满 2 格自动退出
                else:
                    # 移动模式：移动到相邻格
                    if not fog_on or rid in {r.id for r in gmap.available_moves()}:
                        gmap.move_to(rid)
                        scout_mode = False

        screen.fill(BG)
        title = font_title.render("六边形探索地图", True, TEXT)
        screen.blit(title, title.get_rect(midtop=(WIDTH // 2, 18)))
        draw_hud(screen, font_small, gmap, fog_on, show_danger, scout_mode)
        draw_map(screen, gmap, positions, font, font_small, fog_on, show_danger, scout_mode)
        draw_legend(screen, font)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
