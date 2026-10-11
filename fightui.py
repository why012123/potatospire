"""战斗 UI（FightUI mixin）。

从 gui.py 拆出，供 GameApp 混入。后续所有战斗界面（单人 / 多人 PVE / PVP）
都以此为基。本文件只做「战斗场景的绘制与交互」，不持有自有状态，
所有状态挂在宿主 GameApp（self）上。

多玩家 / 多怪适配：
  - self._players() / self._enemies() 返回可迭代列表，单机时包成单元素列表；
  - 上下方向键切换 self._view_player_idx（未来 engine 支持多玩家后自动生效）；
  - 敌人 / 玩家面板按数量自动分列排布，意图、血条、状态一并绘制。
"""

from __future__ import annotations

import math
import os

import pygame

from game.card import Card, CardType
from game.enemy import get_upcoming_intents
from ui_common import (
    ACCENT,
    CARD_H,
    CARD_W,
    GREEN,
    HEIGHT,
    IMAGES_DIR,
    MUTED,
    PANEL,
    PANEL_EDGE,
    PHASE_NAMES,
    RED,
    ROOT,
    SLOT_ACTIVE_EDGE,
    SLOT_BG,
    SLOT_EDGE,
    TEXT,
    WIDTH,
    YELLOW,
    draw_image_fit,
    load_font,
    weight_color,
)

# 状态图标目录（sources/icon/buff）
ICON_BUFF_DIR = os.path.join(ROOT, "sources", "icon", "buff")

# 状态名 → 图标文件名映射（用户可能重命名图标文件）
_STATUS_ICON_ALIAS = {
    "缩小": "虚弱",  # shrink 图标文件名是「虚弱」
}


def _status_icon_path(name: str) -> str:
    """按状态名解析图标路径（尝试别名 + 多种扩展名）。"""
    base = _STATUS_ICON_ALIAS.get(name, name)
    for ext in (".png", ".webp", ".jpeg", ".jpg"):
        p = os.path.join(ICON_BUFF_DIR, base + ext)
        if os.path.exists(p):
            return p
    return ""


class FightUI:
    """战斗场景绘制 / 交互（混入 GameApp）。"""

    # ---------- 多玩家 / 多怪兼容层 ----------
    def _players(self) -> list:
        """返回本场所有玩家。单机时只有 state.player。"""
        st = self.engine.state
        if getattr(st, "players", None):
            return list(st.players)
        return [st.player]

    def _enemies(self) -> list:
        """返回本场所有敌人。单机时只有 state.enemy（可能为 None）。"""
        st = self.engine.state
        if getattr(st, "enemies", None):
            return [e for e in st.enemies if e is not None]
        if st.enemy is not None:
            return [st.enemy]
        return []

    def _active_player(self):
        """当前查看/操作的玩家。"""
        players = self._players()
        if not players:
            return self.engine.state.player
        idx = getattr(self, "_view_player_idx", 0) % len(players)
        return players[idx]

    # ---------- 战斗场景主绘制 ----------
    def _draw_battle(self) -> None:
        st = self.engine.state
        player = self._active_player()
        # 每帧重置状态/意图图标点击区
        self.status_icon_rects = []
        self.intent_icon_rects = []

        # 敌人（多怪自动分列）
        self._draw_enemy_side()

        # 我方玩家（多玩家自动分列）
        self._draw_player_side()

        # 牌堆槽位（先画，渲染优先级低于顶部栏，收起时被顶栏挡住）
        for i, rect in enumerate(self.slot_rects):
            active = i < st.active_slots
            self._draw_slot(rect, i, active, hovered=(i == self.hover_slot))

        # 顶部 HUD（最后画在牌堆之上，遮住收起的牌堆）
        pygame.draw.rect(self.screen, PANEL, (0, 0, WIDTH, 92))
        pygame.draw.line(self.screen, PANEL_EDGE, (0, 92), (WIDTH, 92), 1)
        # 左侧：当前角色小头像（加大，可点击）
        icon_rect = self.hero_icon_btn
        if player.icon:
            draw_image_fit(
                self.screen, os.path.join(IMAGES_DIR, player.icon), icon_rect
            )
        else:
            pygame.draw.rect(self.screen, SLOT_BG, icon_rect, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT, icon_rect, 2, border_radius=8)
        hud = (
            f"回合 {st.turn}  |  活跃牌堆 {st.active_slots}/{player.max_slots}"
            f"  |  消耗 {len(player.exhaust_pile)}"
            f"  |  阶段：{PHASE_NAMES.get(st.phase, st.phase.name)}"
        )
        # 多人提示
        players = self._players()
        if len(players) > 1:
            idx = getattr(self, "_view_player_idx", 0) % len(players)
            hud += f"  |  [↑↓] 玩家 {idx + 1}/{len(players)}（{player.name}）"
        self.screen.blit(self.font.render(hud, True, TEXT), (70, 20))

        self._draw_button(self.skip_btn, "结束回合", ACCENT)
        if self.mode == "rogue":
            self._draw_button(self.map_key_btn, "地图", PANEL_EDGE)
            self._draw_button(self.potion_btn, f"药水×{len(player.potions)}", (110, 210, 130))
        self._draw_button(self.quit_btn, "设置", RED)

        # 遗物栏（肉鸽模式，HUD 第二行）
        if self.mode == "rogue":
            self._draw_relic_bar()

        # 日志
        self._draw_log()

        # 抽牌堆 / 弃牌堆按钮（左右下角）
        self._draw_deck_buttons()

        # 手牌（折叠条带，悬停展开）
        self.layout_hand()
        for i, rect in enumerate(self.hand_rects):
            if i == self.dragging:
                self._draw_card_placeholder(rect)
                continue
            card = player.hand[i]
            if i == self.hand_hover:
                full = pygame.Rect(rect.x, rect.bottom - CARD_H, CARD_W, CARD_H)
                self._draw_card(full, card, selected=False)
            else:
                self._draw_folded_card(rect, card)

        if not self.hand_rects:
            msg = self.font.render("（手牌为空，点击「跳过回合」）", True, MUTED)
            self.screen.blit(msg, msg.get_rect(center=(WIDTH // 2, HEIGHT - 80)))

        # 拖拽中的牌
        if self.dragging is not None and self.dragging < len(player.hand):
            card = player.hand[self.dragging]
            drag_rect = pygame.Rect(0, 0, CARD_W, CARD_H)
            drag_rect.center = self.drag_pos
            self._draw_card(drag_rect, card, selected=True)

        # 牌堆查看浮层
        if self.viewing_pile is not None:
            self._draw_pile_viewer(self.viewing_pile)
        # 抽牌堆 / 弃牌堆查看浮层
        if getattr(self, "viewing_deck", None) is not None:
            self._draw_deck_viewer()

        # 操作提示
        tip = "操作：按住手牌拖动到牌堆放下 | 点击牌堆查看内容 | S 结束回合 | ESC 关闭/退出"
        self.screen.blit(self.font_small.render(tip, True, MUTED), (20, HEIGHT - 24))

        # 浮层
        if self.customizing is not None:
            self._draw_weight_popup()
        if self.settings_active:
            self._draw_settings()
        if self.hero_info_active:
            self._draw_hero_info()
        if getattr(self, "status_detail", None) is not None:
            self._draw_status_detail()
        if getattr(self, "intent_detail", None) is not None:
            self._draw_intent_detail()

    # ---------- 敌方 / 我方渲染（无框立绘 + 血条 + 状态栏） ----------
    def _enemy_disp(self, i: int, enemy) -> tuple[float, float]:
        """返回第 i 个敌人的血条/格挡动画显示值。"""
        dhp = self.disp_hp.get(f"enemy{i}", self.disp_hp.get("enemy", float(enemy.hp)))
        dbk = self.disp_block.get(f"enemy{i}", self.disp_block.get("enemy", float(enemy.block)))
        return dhp, dbk

    def _focused_enemy_idx(self, n: int) -> int:
        """当前聚焦的敌人索引（多怪时用左右键切换）。"""
        idx = getattr(self, "_view_enemy_idx", 0) % max(1, n)
        return idx

    def _combatant_status_items(self, char) -> list[dict]:
        """返回某个战斗单位的所有「状态项」（含力量被动），供状态栏渲染。

        每项：{"name", "stacks", "value", "desc"}。诅咒的 value 为红色伤害数字。
        """
        items: list[dict] = []
        for s in char.active_statuses():
            items.append({
                "name": s.name,
                "stacks": s.stacks,
                "value": getattr(s, "value", 0),
                "desc": s.description,
            })
        strength = char.strength + getattr(char, "temp_strength", 0)
        if strength > 0:
            items.append({"name": "力量", "stacks": strength, "value": 0, "desc": "每点使攻击 +1"})
        # 蒸蛋「目标」效果：显示当前目标层数
        if getattr(char, "has_target", False):
            items.append({
                "name": "目标",
                "stacks": getattr(char, "target_level", 1),
                "value": 0,
                "desc": "精准卡牌打出时重量等于目标层数则效果 ×2；每回合 +1，到 10 回 1",
            })
        return items

    def _draw_fan_card(self, rect: pygame.Rect, card, angle: float) -> None:
        """绘制扇形手牌：有卡面图则旋转 + 重量徽章烘焙进卡面，避免错位。"""
        img = self._card_image(card)
        if img is not None:
            # 先烘焙重量徽章到卡面左上角，再整体旋转
            baked = img.copy()
            scale = rect.w / baked.get_width()
            cx = int(baked.get_width() * 0.13)
            cy = int(baked.get_height() * 0.13)
            rad = max(14, int(baked.get_width() * 0.11))
            pygame.draw.circle(baked, (250, 246, 230), (cx, cy), rad)
            pygame.draw.circle(baked, (175, 145, 70), (cx, cy), rad, max(2, rad // 5))
            txt = "逻辑" if card.logic else str(card.weight)
            font = load_font(max(16, int(baked.get_width() * 0.15)))
            badge = font.render(txt, True, (60, 50, 30))
            baked.blit(badge, badge.get_rect(center=(cx, cy)))
            rot = pygame.transform.rotozoom(baked, angle, scale)
            r = rot.get_rect(center=rect.center)
            self.screen.blit(rot, r)
            return
        self._draw_card(rect, card, selected=False)

    def _draw_status_bar(self, char, area: pygame.Rect) -> None:
        """在 area 内横向绘制状态图标（有图用图，无图用首汉字），记录可点击矩形。"""
        items = self._combatant_status_items(char)
        if not items:
            return
        size = 34
        gap = 6
        x = area.x
        y = area.y
        for it in items:
            if x + size > area.right:
                break
            r = pygame.Rect(x, y, size, size)
            icon_path = _status_icon_path(it["name"])
            if icon_path:
                # 有图标
                draw_image_fit(self.screen, icon_path, r)
            else:
                # 无图标：深色底 + 首汉字（大号加粗）
                pygame.draw.rect(self.screen, (40, 44, 58), r, border_radius=8)
                pygame.draw.rect(self.screen, PANEL_EDGE, r, 1, border_radius=8)
                ch = it["name"][0] if it["name"] else "?"
                big = load_font(26)
                ch_surf = big.render(ch, True, TEXT)
                self.screen.blit(ch_surf, ch_surf.get_rect(center=r.center))
            # 角标数字
            if it["name"] == "诅咒" and it.get("value", 0) > 0:
                # 诅咒：左下角蓝色数字（层数），右下角红色数字（伤害）
                blue = load_font(14).render(str(it["stacks"]), True, (255, 255, 255))
                blue_rect = blue.get_rect(bottomleft=(r.left + 2, r.bottom - 2))
                pygame.draw.rect(self.screen, (60, 100, 220), blue_rect.inflate(6, 4), border_radius=8)
                self.screen.blit(blue, blue_rect)
                red = load_font(14).render(str(it["value"]), True, (255, 255, 255))
                red_rect = red.get_rect(bottomright=(r.right - 2, r.bottom - 2))
                pygame.draw.rect(self.screen, (200, 60, 60), red_rect.inflate(6, 4), border_radius=8)
                self.screen.blit(red, red_rect)
            elif it["stacks"] > 1:
                cnt = load_font(14).render(str(it["stacks"]), True, (255, 255, 255))
                cnt_rect = cnt.get_rect(bottomright=(r.right - 2, r.bottom - 2))
                bg = cnt_rect.inflate(6, 4)
                pygame.draw.rect(self.screen, (200, 60, 60), bg, border_radius=8)
                self.screen.blit(cnt, cnt_rect)
            # 记录可点击矩形
            self.status_icon_rects.append((it, r))
            x += size + gap

    def _sprite_top(self, char, area: pygame.Rect) -> int:
        """返回立绘实际绘制的顶部 y（按宽度缩放后的真实高度）。"""
        img_path = os.path.join(IMAGES_DIR, char.image) if char.image else ""
        if not img_path or not os.path.isfile(img_path):
            return area.top + 22
        img = self._load_combat_img(img_path, False)
        if img is None:
            return area.top + 22
        h = int(img.get_height() * (area.width / img.get_width()))
        bar_top = area.bottom - 54
        return bar_top - h

    def _draw_combatant(
        self, char, area: pygame.Rect, is_enemy: bool,
        disp_hp: float | None, disp_block: float | None,
    ) -> int:
        """绘制单个战斗单位：无框立绘 + 名字 + 血条 + 状态栏。返回立绘顶部 y。"""
        bar_top = area.bottom - 54
        sprite_top = self._sprite_top(char, area)
        # 名字：紧贴立绘顶部上方
        name_surf = self.font_small.render(char.name, True, TEXT)
        self.screen.blit(name_surf, name_surf.get_rect(midbottom=(area.centerx, sprite_top - 2)))
        # 立绘（无框，底部对齐血条）
        sprite_area = pygame.Rect(area.x, sprite_top, area.width, bar_top - sprite_top)
        img_path = os.path.join(IMAGES_DIR, char.image) if char.image else ""
        self._draw_sprite_bottom(img_path, sprite_area, flip=is_enemy)
        # 血条（含格挡），紧贴立绘底部
        bar = pygame.Rect(area.x, bar_top, area.width, 18)
        self._draw_hp_bar(bar, char.hp, char.max_hp, char.block, disp_hp, disp_block)
        # 状态栏
        sb = pygame.Rect(area.x, area.bottom - 32, area.width, 30)
        self._draw_status_bar(char, sb)
        return sprite_top

    def _load_combat_img(self, path: str, flip: bool = False):
        key = (path, flip)
        img = self._combat_img_cache.get(key)
        if img is None:
            try:
                img = pygame.image.load(path).convert_alpha()
            except pygame.error:
                return None
            if flip:
                img = pygame.transform.flip(img, True, False)
            self._combat_img_cache[key] = img
        return img

    def _draw_sprite_bottom(self, path: str, area: pygame.Rect, flip: bool = False) -> None:
        """底部对齐绘制立绘（贴住 area 底边）。"""
        if not path or not os.path.isfile(path):
            return
        img = self._load_combat_img(path, flip)
        if img is None:
            return
        scale = area.width / img.get_width()
        w = area.width
        h = int(img.get_height() * scale)
        scaled = pygame.transform.smoothscale(img, (w, h))
        self.screen.blit(scaled, (area.x, area.bottom - h))

    def _draw_enemy_side(self) -> None:
        enemies = self._enemies()
        if not enemies:
            return
        n = len(enemies)
        if n == 1:
            top = self._draw_combatant(
                enemies[0], self.enemy_area, True,
                self.disp_hp.get("enemy0", self.disp_hp.get("enemy")),
                self.disp_block.get("enemy0", self.disp_block.get("enemy")),
            )
            if enemies[0].is_alive:
                self._draw_enemy_intents(enemies[0], self.enemy_area, top)
            return
        # 多怪：错开站立，全部显示，每个都画意图
        for i, e in enumerate(enemies):
            area = self._enemy_slot_area(i, n, 0)
            dhp, dbk = self._enemy_disp(i, e)
            top = self._draw_combatant(e, area, True, dhp, dbk)
            if e.is_alive:
                self._draw_enemy_intents(e, area, top)

    def _enemy_slot_area(self, i: int, n: int, focus: int) -> pygame.Rect:
        """多怪错开站立：大嗓门靠左（不被边界挡），练家子站到接近中间。"""
        base = self.enemy_area
        w = base.width
        h = base.height
        if n == 2:
            # 第 0 个靠左，第 1 个站到屏幕近中间
            if i == 0:
                x = base.x
                off_y = -10
            else:
                x = WIDTH * 0.42 - w // 2
                off_y = 10
            return pygame.Rect(int(x), base.y + off_y, w, h)
        # 超过 2 个：从 base 起点向右排开
        spread = 70 * (n - 1)
        x = base.x + (i * spread)
        off_y = -12 if i % 2 == 0 else 12
        return pygame.Rect(int(x), base.y + off_y, w, h)

    def _draw_player_side(self) -> None:
        players = self._players()
        for i, p in enumerate(players):
            area = self._side_area(self.player_area, i, len(players))
            self._draw_combatant(
                p, area, False,
                self.disp_hp["self"], self.disp_block["self"],
            )

    def _side_area(self, base: pygame.Rect, i: int, n: int) -> pygame.Rect:
        """把一个大面板区域按数量 n 切成第 i 个竖列。"""
        if n <= 1:
            return base
        w = base.width // n
        return pygame.Rect(base.x + w * i, base.y, w - 4, base.height)

    # ---------- 状态详情浮层 ----------
    def _draw_status_detail(self) -> None:
        """点击状态图标后弹出的状态详情浮层。"""
        info = self.status_detail
        if info is None:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 220, HEIGHT // 2 - 140, 440, 280)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=16)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=16)
        name = self.font_big.render(info.get("name", ""), True, YELLOW)
        self.screen.blit(name, name.get_rect(midtop=(box.centerx, box.y + 24)))
        if info.get("name") == "诅咒" and info.get("value", 0) > 0:
            stacks = self.font.render(
                f"层数 ×{info.get('stacks', 1)}  伤害 ×{info.get('value', 0)}",
                True, TEXT,
            )
        else:
            stacks = self.font.render(f"层数 ×{info.get('stacks', 1)}", True, TEXT)
        self.screen.blit(stacks, stacks.get_rect(midtop=(box.centerx, box.y + 72)))
        desc = info.get("desc", "")
        y = box.y + 120
        for line in self._wrap_text(desc, box.width - 60):
            surf = self.font_small.render(line, True, TEXT)
            self.screen.blit(surf, surf.get_rect(midtop=(box.centerx, y)))
            y += 24
        tip = self.font_small.render("点击任意处关闭", True, MUTED)
        self.screen.blit(tip, tip.get_rect(midbottom=(box.centerx, box.bottom - 12)))

    # ---------- 抽牌堆 / 弃牌堆按钮 ----------
    _DEEP_PURPLE = (110, 60, 150)

    def _draw_deck_buttons(self) -> None:
        """页面左右下角：弃牌堆（左下，下三角）+ 抽牌堆（右下，方块+上三角）。"""
        player = self._active_player()
        # 弃牌堆（左下角，深紫下三角）
        d = self.discard_pile_btn
        tri = [(d.centerx, d.bottom - 5), (d.left + 6, d.top + 5), (d.right - 6, d.top + 5)]
        pygame.draw.polygon(self.screen, self._DEEP_PURPLE, tri)
        pygame.draw.polygon(self.screen, PANEL_EDGE, tri, 2)
        cnt = self.font_small.render(str(len(player.discard_pile)), True, (255, 255, 255))
        self.screen.blit(cnt, cnt.get_rect(center=(d.centerx, d.centery + 10)))

        # 抽牌堆（右下角，方块 + 上三角）
        d = self.draw_pile_btn
        pygame.draw.rect(self.screen, self._DEEP_PURPLE, d, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_EDGE, d, 2, border_radius=8)
        up = [(d.centerx, d.top + 5), (d.left + 6, d.bottom - 5), (d.right - 6, d.bottom - 5)]
        pygame.draw.polygon(self.screen, (150, 90, 200), up)
        cnt = self.font_small.render(str(len(player.draw_pile)), True, (255, 255, 255))
        self.screen.blit(cnt, cnt.get_rect(center=(d.centerx, d.centery + 10)))

    def _draw_deck_viewer(self) -> None:
        """查看抽牌堆 / 弃牌堆的卡牌浮层。"""
        kind = self.viewing_deck
        player = self._active_player()
        cards = player.draw_pile if kind == "draw" else player.discard_pile
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 320, 90, 640, 600)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=14)
        title = self.font.render(
            f"{'抽牌堆' if kind == 'draw' else '弃牌堆'}（共 {len(cards)} 张）",
            True, TEXT,
        )
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 14)))
        hint = self.font_small.render("点击卡牌查看整卡 · 点击外部关闭", True, MUTED)
        self.screen.blit(hint, hint.get_rect(midtop=(box.centerx, box.y + 44)))

        self.deck_viewer_card_rects = []
        if not cards:
            msg = self.font.render("（空）", True, MUTED)
            self.screen.blit(msg, msg.get_rect(center=box.center))
        else:
            cw, ch = 110, 154
            per_row = 5
            gap = 14
            start_x = box.x + (box.width - (cw * per_row + gap * (per_row - 1))) // 2
            y = box.y + 80
            for i, card in enumerate(cards[:20]):
                row = i // per_row
                col = i % per_row
                r = pygame.Rect(start_x + col * (cw + gap), y + row * (ch + 12), cw, ch)
                self._draw_compact_card(r, card, i)
                self.deck_viewer_card_rects.append((card, r))
            if len(cards) > 20:
                more = self.font_small.render(f"…还有 {len(cards) - 20} 张", True, MUTED)
                self.screen.blit(more, more.get_rect(midtop=(box.centerx, box.bottom - 30)))

        if self.deck_viewer_selected is not None:
            self._draw_full_card(self.deck_viewer_selected)

    def _handle_deck_viewer_click(self, pos: tuple[int, int]) -> None:
        """抽/弃牌堆查看浮层内的点击。"""
        if self.deck_viewer_selected is not None:
            self.deck_viewer_selected = None
            return
        for card, r in self.deck_viewer_card_rects:
            if r.collidepoint(pos):
                self.deck_viewer_selected = card
                return
        if not self._view_popup_rect().collidepoint(pos):
            self.viewing_deck = None
