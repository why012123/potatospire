from __future__ import annotations

import os
import random
import sys

import pygame

from game.card import Card, CardType, Rarity
from game.cards import (
    build_deck,
    make_card,
    cards_for_hero,
    public_card_keys,
    hero_card_keys,
    get_card_def,
)
from game.engine import Engine
from game.enemy import enemy_names, get_upcoming_intents, make_enemy
from game.events import GameEvent, get_event, random_event_key
from game.heroes import HEROES, HeroDef, char_image_path, get_hero
from game.map import (
    BOSS_COLORS,
    MAX_SCOUTS_PER_TURN,
    ROOM_COLORS,
    ROOM_LABELS,
    RoomType,
    generate_map,
    hex_centers,
    hex_vertices,
)
from game.player import Player
from game.potions import Potion, make_potion, random_potion_key
from game.relics import Relic, make_relic, tick_relics
from game.reward import (
    roll_elite_gold,
    roll_elite_relic,
    roll_reward_cards,
    roll_reward_gold,
    roll_reward_relic,
)
from game.shop import generate_offers, remove_service_price
from game.state import GameState, Phase
from game.net import cards_to_list
from ui_common import (
    ACCENT,
    BG,
    CARD_BG,
    CARD_H,
    CARD_TEXT,
    CARD_W,
    EFFECT_FRAMES,
    EFFECT_HOLD_FRAMES,
    FLY_FRAMES,
    FPS,
    GREEN,
    HEIGHT,
    HOLD_FRAMES,
    IMAGES_DIR,
    MONSTER_ANIM_FRAMES,
    MUTED,
    PANEL,
    PANEL_EDGE,
    PHASE_NAMES,
    RED,
    ROOT,
    SLOT_ACTIVE_EDGE,
    SLOT_BG,
    SLOT_EDGE,
    SLOT_H,
    SLOT_W,
    STACK_FRAMES,
    TEXT,
    VERSION,
    WIDTH,
    YELLOW,
    draw_image_fit,
    load_font,
    weight_color,
)
from fightui import FightUI

# 地图渲染颜色
LINK = (100, 106, 130)
FOG = (58, 60, 72)
FOG_EDGE = (80, 84, 98)
PLAYER_RING = (120, 210, 255)
MOVE_RING = (90, 230, 170)
SCOUT_RING = (240, 200, 80)
DANGER = (235, 70, 70)

# 画笔标记颜色（按索引循环）
MARK_COLORS = [
    (235, 70, 70),    # 红
    (92, 156, 255),   # 蓝
    (88, 180, 120),   # 绿
    (240, 200, 80),   # 黄
]
MARK_COLORS_COUNT = len(MARK_COLORS)

class GameApp(FightUI):
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("土豆尖塔 Potatospire")
        self.clock = pygame.time.Clock()
        self.font = load_font(20)
        self.font_small = load_font(16)
        self.font_big = load_font(30)
        self.font_card = load_font(24)
        self.font_title = load_font(56)

        # 场景状态机：menu -> select -> battle
        self.scene = "menu"
        self.engine: Engine | None = None
        self.hero: HeroDef | None = None

        # 拖拽状态
        self.dragging: int | None = None   # 正在拖拽的手牌索引
        self.drag_pos = (0, 0)             # 当前鼠标位置
        self.hover_slot: int | None = None  # 拖拽时悬停的槽位索引
        # 手牌悬停（扇形折叠展开用）
        self.hand_hover: int | None = None
        # 选择模式（逻辑牌需要选择目标：hand_1 / hand_2 / hand_same / pile）
        self.select_mode: str = ""
        self.select_card: Card | None = None
        self.selected_hand: list[int] = []
        self.selected_piles: list[int] = []
        self.select_confirm_btn = pygame.Rect(0, 0, 200, 52)
        self.select_cancel_btn = pygame.Rect(0, 0, 200, 52)
        self.select_full_hand_rects: list[pygame.Rect] = []
        self.select_deck_rects: list[pygame.Rect] = []  # 恰如其分选牌（牌组）
        # 卡面图片缓存：card.name -> 原始卡面 Surface
        self.card_image_cache: dict[str, pygame.Surface] = {}
        # 战斗单位立绘缓存（底部对齐用）
        self._combat_img_cache: dict[tuple, pygame.Surface] = {}
        # 查看牌堆状态
        self.viewer_card_rects: list[tuple[Card, pygame.Rect]] = []
        self.viewer_selected_card: Card | None = None
        self.viewing_pile: int | None = None
        # 自定义重量浮层
        self.customizing: Card | None = None
        self.pending_hand_index: int | None = None
        self.pending_slot: int | None = None
        self.custom_weight: int = 1
        # 设置菜单 / 头像详情浮层
        self.settings_active: bool = False
        self.hero_info_active: bool = False
        self.settings_back_btn = pygame.Rect(0, 0, 260, 56)
        self.settings_exit_btn = pygame.Rect(0, 0, 260, 56)
        self.hero_info_card_rects: list[tuple[Card, pygame.Rect]] = []
        self.hero_info_selected_card: Card | None = None
        # 血条/格挡动画（显示值平滑过渡到真实值）
        self.disp_hp = {"self": 0.0, "enemy": 0.0}
        self.disp_block = {"self": 0.0, "enemy": 0.0}
        # 结算动画状态
        self.resolve_anim: str | None = None  # None/"stack"/"await_target"/"fly"/"effect"
        self.resolve_cards: list[Card] = []
        self.resolve_index: int = 0
        self.resolve_current: Card | None = None
        self.resolve_target: str | None = None
        self.anim_t: float = 0.0
        self.effect_text: str = ""
        self.effect_timer: int = 0
        self.target_btn_rects: dict[str, pygame.Rect] = {}
        # 怪物攻击动画
        self.monster_anim_timer: int = 0
        self.monster_effect_text: str = ""
        self.monster_pierced: bool = False  # 本回合怪物攻击是否穿透格挡造成掉血
        # 伤害飘字动画：{x, y, text, timer}
        self.float_texts: list[dict] = []
        # 胜负结算
        self.game_result: str | None = None  # None/"victory"/"defeat"
        self.result_ok_btn = pygame.Rect(WIDTH // 2 - 120, 470, 240, 56)
        # 调试控制台
        self.console_active: bool = False
        self.console_input: str = ""
        self.console_log: list[str] = []

        # 菜单 / 选角色按钮
        self.menu_start_btn = pygame.Rect(WIDTH // 2 - 120, 320, 240, 60)
        self.menu_pvp_btn = pygame.Rect(WIDTH // 2 - 120, 400, 240, 60)
        self.menu_quit_btn = pygame.Rect(WIDTH // 2 - 120, 480, 240, 60)
        self.select_back_btn = pygame.Rect(40, 30, 120, 40)
        self.hero_card_rects: list[tuple[HeroDef, pygame.Rect]] = []
        # 牌组编辑
        self.deck_edit: dict[str, int] = {}
        self.deck_card_rects: list[tuple[str, pygame.Rect, pygame.Rect]] = []  # (key, 卡面rect, +/-按钮)
        self.deck_start_btn = pygame.Rect(WIDTH - 220, HEIGHT - 70, 200, 50)
        self.deck_back_btn = pygame.Rect(40, 30, 120, 40)
        self.deck_scroll: int = 0  # 牌组编辑页滚动偏移（负值向上滚）
        # 滚动条几何（用于拖拽）
        self.deck_scroll_track = pygame.Rect(0, 0, 0, 0)
        self.deck_scroll_thumb = pygame.Rect(0, 0, 0, 0)
        self.deck_scroll_max: int = 0
        self.dragging_scrollbar: bool = False

        # 自定义重量浮层按钮
        self.weight_minus_btn = pygame.Rect(0, 0, 44, 44)
        self.weight_plus_btn = pygame.Rect(0, 0, 44, 44)
        self.weight_ok_btn = pygame.Rect(0, 0, 120, 44)
        self.weight_cancel_btn = pygame.Rect(0, 0, 120, 44)

        # 战斗布局
        self.skip_btn = pygame.Rect(WIDTH - 330, 14, 90, 36)
        self.map_key_btn = pygame.Rect(WIDTH - 220, 14, 90, 36)
        self.potion_btn = pygame.Rect(WIDTH - 440, 14, 90, 36)
        self.quit_btn = pygame.Rect(WIDTH - 120, 14, 90, 36)
        # 左上角角色头像（加大，可点击）
        self.hero_icon_btn = pygame.Rect(8, 8, 52, 52)

        # 模式选择：None / "sim"(战斗模拟) / "rogue"(肉鸽)
        self.mode: str | None = None
        self.mode_sim_btn = pygame.Rect(WIDTH // 2 - 200, 300, 400, 70)
        self.mode_rogue_btn = pygame.Rect(WIDTH // 2 - 200, 400, 400, 70)
        self.mode_pve_btn = pygame.Rect(WIDTH // 2 - 200, 500, 400, 70)
        self.mode_back_btn = pygame.Rect(40, 30, 120, 40)

        # PVP 模式状态
        self.pvp_role: str = ""              # "" / "host" / "guest"
        self.pvp_session = None              # PvpSession 实例
        self.pvp_hp_mult: float = 1.0        # 血量乘数 X
        self.pvp_deck_min: int = 8           # 配牌数量下限
        self.pvp_deck_max: int = 20          # 配牌数量上限
        self.pvp_peer_hero: str = ""         # 对手角色名
        self.pvp_my_hero: HeroDef | None = None
        self.pvp_deck: dict[str, int] = {}
        self.pvp_ready: bool = False         # 本回合是否已结束
        self.pvp_peer_ready: bool = False
        self.pvp_last_order: list[int] = []  # 上回合先手顺序
        self.pvp_winner: int | None = None   # 胜者 0/1/2
        # PVP 结算动画
        self.pvp_anims: list[dict] = []      # 待播放的结算动画序列
        self.pvp_anim_index: int = 0         # 当前播放到的动画索引
        self.pvp_anim_t: float = 0.0         # 当前动画进度
        self.pvp_anim_phase: str = "fly1"    # "fly1" / "hold" / "fly2" / "effect"
        self.pvp_effect_timer: int = 0       # 效果文字持续帧数
        self.pvp_hold_timer: int = 0         # 中间停留帧数
        self.pvp_resolving: bool = False     # 是否正在播放结算动画
        self.pvp_subprocess = None           # 本地双窗口的访客子进程
        self.pvp_port: int = 0
        self.pvp_setup_back_btn = pygame.Rect(40, 30, 120, 40)
        self.pvp_host_btn = pygame.Rect(WIDTH // 2 - 200, 360, 400, 60)
        self.pvp_host_lan_btn = pygame.Rect(WIDTH // 2 - 200, 430, 400, 60)
        self.pvp_join_btn = pygame.Rect(WIDTH // 2 - 200, 500, 400, 60)
        self.pvp_mult_minus = pygame.Rect(WIDTH // 2 - 120, 220, 44, 44)
        self.pvp_mult_plus = pygame.Rect(WIDTH // 2 + 76, 220, 44, 44)
        self.pvp_deckmin_minus = pygame.Rect(WIDTH // 2 - 120, 290, 40, 40)
        self.pvp_deckmin_plus = pygame.Rect(WIDTH // 2 + 40, 290, 40, 40)
        self.pvp_deckmax_minus = pygame.Rect(WIDTH // 2 - 120, 330, 40, 40)
        self.pvp_deckmax_plus = pygame.Rect(WIDTH // 2 + 40, 330, 40, 40)
        # 局域网联机
        self.pvp_local_ip: str = ""          # 本机局域网 IP
        self.pvp_join_ip: str = ""           # 访客输入的房主 IP
        self.pvp_join_port: int = 7777       # 固定端口
        self.pvp_join_back_btn = pygame.Rect(40, 30, 120, 40)
        self.pvp_join_confirm_btn = pygame.Rect(WIDTH // 2 - 150, 360, 300, 56)
        self.pvp_join_input_rect = pygame.Rect(WIDTH // 2 - 250, 260, 500, 56)

        # 多人 PVE 模式状态
        self.pve_role: str = ""              # "" / "host" / "guest"
        self.pve_session = None              # PveSession 实例
        self.pve_my_hero: HeroDef | None = None
        self.pve_deck: dict[str, int] = {}
        self.pve_ready: bool = False         # 本回合是否已结束
        self.pve_port: int = 0               # 端口（房主 0=自动分配，开赛后写入实际端口）
        self.pve_local_ip: str = ""
        self.pve_join_ip: str = ""           # 访客输入，支持 "ip" 或 "ip:端口"
        self.pve_enemy_names: list[str] = ["拳击构造体"]
        self.pve_enemy_pick_rects: list[tuple[str, pygame.Rect]] = []
        self.pve_setup_back_btn = pygame.Rect(40, 30, 120, 40)
        self.pve_host_btn = pygame.Rect(WIDTH // 2 - 200, 300, 400, 60)
        self.pve_join_btn = pygame.Rect(WIDTH // 2 - 200, 380, 400, 60)
        self.pve_start_btn = pygame.Rect(WIDTH // 2 - 150, HEIGHT - 120, 300, 60)
        self.pve_enemy_prev_btn = pygame.Rect(WIDTH // 2 - 180, 420, 44, 44)
        self.pve_enemy_next_btn = pygame.Rect(WIDTH // 2 + 136, 420, 44, 44)
        self.pve_join_back_btn = pygame.Rect(40, 30, 120, 40)
        self.pve_join_confirm_btn = pygame.Rect(WIDTH // 2 - 150, 360, 300, 56)
        self.pve_join_input_rect = pygame.Rect(WIDTH // 2 - 250, 260, 500, 56)
        self.pve_waiting: bool = False

        # 战斗模拟：敌方自选
        self.enemy_select_rects: list[tuple[str, pygame.Rect]] = []
        self.enemy_select_back_btn = pygame.Rect(40, 30, 120, 40)

        # 肉鸽模式状态
        self.gmap = None
        self.current_floor: int = 1
        self.map_radius: int = 5
        self.map_hex_size: int = 40
        self.rogue_hp: int = 0
        self.rogue_deck: list[Card] = []
        self.rogue_hero: HeroDef | None = None
        self.map_mode: str = "select"          # "select"(选择路线) / "room"(房间内容)
        self.map_room_overlay: str | None = None  # "start"/"event"/"rest"
        self.scout_mode: bool = False          # 侦查模式开关
        self.show_danger: bool = False         # Q 切换危险度数字
        self.paint_mode: bool = False          # 画笔模式开关（标记房间）
        self.room_marks: dict[int, int] = {}   # 房间标记：room_id -> 颜色索引
        self.paint_color: int = 0              # 当前画笔颜色索引
        self.battle_context: str = "sim"       # "sim"/"rogue_normal"/"rogue_elite"/"rogue_boss"
        self.map_view_active: bool = False     # 战斗中打开的地图查看浮层
        self.map_positions: dict[int, tuple[int, int]] = {}
        self.map_close_btn = pygame.Rect(WIDTH // 2 - 120, HEIGHT - 80, 240, 56)
        self.map_continue_btn = pygame.Rect(WIDTH - 260, HEIGHT - 90, 220, 56)
        self.map_avatar_btn = pygame.Rect(14, 10, 46, 46)  # 地图页左上角头像
        # 事件系统
        self.current_event: str | None = None  # 当前事件 key
        self.event_stage: str = "choose"       # "choose"/"delete_card"/"done"
        self.event_result_text: str = ""       # 选项结果文案
        self.event_option_rects: list[tuple[str, pygame.Rect]] = []  # (选项key, 按钮rect)
        self.event_delete_rects: list[tuple[str, pygame.Rect]] = []  # 删除牌界面 (key, rect)
        self.event_delete_back_btn = pygame.Rect(WIDTH // 2 - 300, 180, 100, 36)
        # 遗物 / 诅咒牌倒计时
        self.rogue_relics: list[Relic] = []        # 当前持有的遗物
        self.rogue_guilt_timers: list[int] = []    # 每张愧疚卡的剩余战斗数
        # 遗物附魔选牌浮层（泡泡机 / 劣质胶水获得时指定两张牌）
        self.enchant_pick_active: bool = False
        self.enchant_pick_enchant: str = ""        # 要施加的永久附魔 key
        self.enchant_pick_selected: list[int] = []  # 已选的 rogue_deck 索引
        self.enchant_pick_rects: list[tuple[int, pygame.Rect]] = []
        self.enchant_pick_confirm_btn = pygame.Rect(0, 0, 200, 52)
        self.enchant_pick_cancel_btn = pygame.Rect(0, 0, 200, 52)
        # 金币 / 商店
        self.rogue_gold: int = 60                  # 当前金币
        self.rogue_remove_count: int = 0           # 已删除牌数（决定删牌服务价格）
        self.shop_offers: list[tuple[str, int, bool]] = []  # (key, 价格, 是否特价)
        self.shop_stage: str = "buy"               # "buy"/"remove_card"
        self.shop_free_items: int = 0              # 老板娘的怀表：本商店免费次数
        self.shop_offer_rects: list[tuple[int, pygame.Rect]] = []  # (offer索引, 按钮rect)
        self.shop_remove_rects: list[tuple[str, pygame.Rect]] = []  # (key, rect)
        self.shop_remove_btn = pygame.Rect(0, 0, 420, 46)
        self.shop_relic_btn = pygame.Rect(0, 0, 200, 46)
        self.shop_potion_btn = pygame.Rect(0, 0, 200, 46)
        self.shop_remove_back_btn = pygame.Rect(0, 0, 100, 36)
        self.shop_hint: str = ""                      # 商店提示文字
        self.chest_result: str = ""                   # 宝箱开启结果
        # 战斗奖励（普通战斗后）
        self.reward_gold: int = 0                     # 本次奖励金币
        self.reward_relic: str | None = None          # 本次奖励遗物 key
        self.reward_cards: list[str] = []             # 卡牌三选一 key 列表
        self.reward_chosen: bool = False              # 是否已选卡
        self.reward_chosen_key: str | None = None     # 已选卡牌 key
        self.reward_card_rects: list[tuple[str, pygame.Rect]] = []  # (key, rect)
        self.reward_continue_btn = pygame.Rect(0, 0, 240, 56)
        self.reward_potion: str | None = None         # 本次奖励药水 key（精英）
        self.reward_stage: str = "loot"               # "loot"（战利品弹窗）/ "cards"（选卡）
        self.reward_card_pick_btn = pygame.Rect(0, 0, 260, 50)  # 弹窗「选择卡牌」按钮
        self.reward_skip_btn = pygame.Rect(0, 0, 160, 48)       # 选卡页「跳过」按钮
        # 药水槽
        self.rogue_potions: list[Potion] = []         # 持有的药水
        self.potion_use_rects: list[tuple[Potion, pygame.Rect]] = []  # (药水, 按钮rect)
        self.potion_popup_active: bool = False        # 药水使用浮层开关
        # 事件「趁机购物」选卡
        self.event_pick_cards: list[str] = []       # 三张随机蓝色以上卡
        self.event_pick_rects: list[tuple[str, pygame.Rect]] = []  # (key, rect)

        self.enemy_area = pygame.Rect(45, 240, 250, 400)
        self.player_area = pygame.Rect(WIDTH - 235, 160, 200, 400)
        # 状态图标点击（敌我共用）：记录可点图标矩形，点击弹出详情
        self.status_icon_rects: list[tuple[object, pygame.Rect]] = []  # (Status实例, rect)
        self.status_detail: object | None = None  # 当前查看详情的 Status 实例
        # 阿兰娜被动：回合开始选择诅咒目标
        self.curse_select: bool = False
        self.curse_target_rects: list[tuple[int, pygame.Rect]] = []  # (敌人索引, rect)
        # 意图图标点击：记录可点图标矩形，点击弹出详情
        self.intent_icon_rects: list[tuple[str, pygame.Rect]] = []  # (描述, rect)
        self.intent_detail: str | None = None
        # 日志蒙版开关（D 键，全屏半透明覆盖层）
        self.log_visible: bool = False
        # 日志滚动与滚动条状态
        self.log_scroll: int = 0
        self.log_scroll_max: int = 0
        self.log_scroll_track = pygame.Rect(0, 0, 0, 0)
        self.log_scroll_thumb = pygame.Rect(0, 0, 0, 0)
        self.dragging_log_scrollbar: bool = False
        self.log_close_btn = pygame.Rect(0, 0, 0, 0)
        # 牌堆滑出动画（0=隐藏上半部分到顶栏，1=完全展开「迎接」牌）
        self._slot_slide: float = 1.0
        # 抽牌堆 / 弃牌堆按钮（页面左右下角，缩小）
        self.draw_pile_btn = pygame.Rect(WIDTH - 88, HEIGHT - 88, 70, 70)
        self.discard_pile_btn = pygame.Rect(18, HEIGHT - 88, 70, 70)
        self.viewing_deck: str | None = None       # "draw" / "discard"
        self.deck_viewer_card_rects: list[tuple[Card, pygame.Rect]] = []
        self.deck_viewer_selected: Card | None = None

        slot_y = 100
        gap = 16
        total_w = SLOT_W * 4 + gap * 3
        start_x = (WIDTH - total_w) // 2
        self.slot_rects = [
            pygame.Rect(start_x + i * (SLOT_W + gap), slot_y, SLOT_W, SLOT_H)
            for i in range(4)
        ]

        self.log_area = pygame.Rect(start_x, slot_y + SLOT_H + 24, total_w, 130)
        self.hand_rects: list[pygame.Rect] = []
        self.hand_angles: list[float] = []

        # 多玩家查看索引（FightUI 用，上下方向键切换）
        self._view_player_idx: int = 0
        # 多怪堆叠：当前聚焦的敌人索引（左右方向键切换）
        self._view_enemy_idx: int = 0
        self._enemy_switch_anim: float = 1.0  # 切换动画进度（1.0=完成）

    def _reset_battle_ui(self) -> None:
        """重置战斗场景的各类 UI 状态。"""
        self._end_drag()
        self.viewing_pile = None
        self.viewer_selected_card = None
        self.customizing = None
        self.resolve_anim = None
        self.resolve_cards = []
        self.settings_active = False
        self.hero_info_active = False
        self.map_view_active = False
        self.log_visible = False
        self.log_scroll = 0
        self.log_scroll_max = 0
        self.dragging_log_scrollbar = False
        self.viewing_deck = None
        self.deck_viewer_selected = None
        self._slot_slide = 1.0

    def _start_battle(self, hero: HeroDef, enemy_name: str | None = None) -> None:
        """按选中的角色定义构建一局战斗（战斗模拟模式，单怪）。"""
        if enemy_name is None:
            enemy_name = random.choice(enemy_names())
        self._start_battle_enemies(hero, [enemy_name])

    def _start_battle_enemies(self, hero: HeroDef, enemy_names: list[str]) -> None:
        """战斗模拟模式：构建一局（可能多怪）战斗。"""
        rng = random.Random(42)
        # 按编辑后的牌组构建卡组
        cards = build_deck(self.deck_edit) if self.deck_edit else build_deck(hero.deck)
        rng.shuffle(cards)
        player = Player(
            name=hero.name,
            max_hp=hero.max_hp,
            image=char_image_path(hero.name, "小人"),
            icon=char_image_path(hero.name, "小头像"),
            extra_draw=hero.extra_draw,
            mark_on_attack=hero.mark_on_attack,
            keep_block=hero.keep_block,
            gain_resilience_on_hit=hero.gain_resilience_on_hit,
            curse_on_turn=hero.curse_on_turn,
            curse_mult=hero.curse_mult,
            draw_pile=cards,
        )
        enemies = [make_enemy(n) for n in enemy_names]
        self._ensure_warden_guard(enemies)
        state = GameState(player=player, enemies=enemies)
        engine = Engine(state, rng=rng)
        engine.start_turn()
        # 出场自带状态（鼠鼠：1 层韧性）
        for sid, stacks in hero.start_statuses.items():
            player.add_status(sid, stacks)
        self.engine = engine
        self.hero = hero
        self.battle_context = "sim"
        self.scene = "battle"
        self._reset_battle_ui()
        # 初始化显示值
        self.disp_hp = {"self": float(player.hp)}
        self.disp_block = {"self": float(player.block)}
        for i, e in enumerate(enemies):
            self.disp_hp[f"enemy{i}"] = float(e.hp)
            self.disp_block[f"enemy{i}"] = float(e.block)
        # 阿兰娜被动：第一回合开始也触发诅咒
        self._maybe_trigger_curse_passive()

    # ---------- 肉鸽模式 ----------
    def _start_rogue_run(self) -> None:
        """进入肉鸽模式：初始化三层探索的持久状态，从第 1 层起点开始。"""
        self.rogue_hero = self.hero
        # 肉鸽模式不可自定义牌库：固定使用角色默认牌组
        self.rogue_deck = build_deck(dict(self.hero.deck))
        self.rogue_hp = self.hero.max_hp
        self.rogue_relics = []
        self.rogue_guilt_timers = []
        self.rogue_potions = []
        self.rogue_gold = 100
        self.rogue_remove_count = 0
        self.current_floor = 1
        self._enter_next_floor()

    def _build_rogue_player(self) -> Player:
        """用持久牌组 + 当前血量重建玩家（每场战斗新建，血量跨战斗保留）。"""
        import copy
        hero = self.rogue_hero
        cards = [copy.deepcopy(c) for c in self.rogue_deck]
        rng = random.Random()
        rng.shuffle(cards)
        player = Player(
            name=hero.name,
            max_hp=hero.max_hp,
            hp=self.rogue_hp,
            image=char_image_path(hero.name, "小人"),
            icon=char_image_path(hero.name, "小头像"),
            extra_draw=hero.extra_draw,
            mark_on_attack=hero.mark_on_attack,
            keep_block=hero.keep_block,
            gain_resilience_on_hit=hero.gain_resilience_on_hit,
            curse_on_turn=hero.curse_on_turn,
            curse_mult=hero.curse_mult,
            draw_pile=cards,
            potions=list(self.rogue_potions),
            dilute_serum=self._has_relic("dilute_serum"),
        )
        for sid, stacks in hero.start_statuses.items():
            player.add_status(sid, stacks)
        return player

    def _start_rogue_battle(self, enemy_name: str, context: str) -> None:
        """肉鸽模式：用当前血量与牌组开启一场单怪战斗。"""
        self._start_rogue_battle_enemies([enemy_name], context)

    def _start_rogue_battle_enemies(self, enemy_names: list[str], context: str) -> None:
        """肉鸽模式：用当前血量与牌组开启一场（可能多怪）战斗。"""
        rng = random.Random()
        player = self._build_rogue_player()
        enemies = [make_enemy(n) for n in enemy_names]
        self._ensure_warden_guard(enemies)
        state = GameState(player=player, enemies=enemies)
        engine = Engine(state, rng=rng)
        engine.start_turn()
        # 遗物效果：战斗开始时自带 5 层中毒（吃剩的毒外卖）
        for relic in self.rogue_relics:
            if relic.relic_id == "leftover_poison_takeout":
                player.add_status("poison", 5)
                break
        self.engine = engine
        self.hero = self.rogue_hero
        self.battle_context = context
        self.scene = "battle"
        self._reset_battle_ui()
        self.disp_hp = {"self": float(player.hp)}
        self.disp_block = {"self": float(player.block)}
        for i, e in enumerate(enemies):
            self.disp_hp[f"enemy{i}"] = float(e.hp)
            self.disp_block[f"enemy{i}"] = float(e.block)
        # 阿兰娜被动：第一回合开始也触发诅咒
        self._maybe_trigger_curse_passive()

    def _enter_next_floor(self) -> None:
        """生成新一层地图，玩家回到中心起点，进入起点房间。"""
        self.gmap = generate_map(radius=self.map_radius)
        self._compute_map_positions()
        self.scene = "map"
        self.map_mode = "room"
        self.map_room_overlay = "start"
        self.scout_mode = False
        self.show_danger = False
        self.paint_mode = False
        self.room_marks = {}
        self.current_event = None
        self.event_stage = "choose"
        self.event_result_text = ""

    def _compute_map_positions(self) -> None:
        """把地图六边形坐标映射到屏幕像素。"""
        centers = hex_centers(self.gmap, self.map_hex_size)
        xs = [p[0] for p in centers.values()]
        ys = [p[1] for p in centers.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        top = 90
        bottom = HEIGHT - 130
        scale = min((WIDTH - 120) / (max_x - min_x), (bottom - top) / (max_y - min_y))
        scale = min(scale, 1.0)
        world_cx = (min_x + max_x) / 2
        world_cy = (min_y + max_y) / 2
        self.map_positions = {}
        for rid, (x, y) in centers.items():
            sx = WIDTH / 2 + (x - world_cx) * scale
            sy = (top + bottom) / 2 - (y - world_cy) * scale  # 翻转
            self.map_positions[rid] = (int(sx), int(sy))

    def _room_at(self, pos: tuple[int, int]) -> int | None:
        """把鼠标位置映射到最近的房间 id。"""
        best, best_d = None, self.map_hex_size * 1.15
        for rid, (x, y) in self.map_positions.items():
            d = ((pos[0] - x) ** 2 + (pos[1] - y) ** 2) ** 0.5
            if d < best_d:
                best, best_d = rid, d
        return best

    def _enter_room(self, room_id: int) -> None:
        """移动到相邻房间，并按类型触发对应内容。"""
        room = self.gmap.rooms[room_id]
        self.gmap.move_to(room_id)
        rtype = room.room_type
        if rtype is RoomType.BATTLE:
            self._start_rogue_battle(random.choice(self.rogue_normal_pool()), "rogue_normal")
        elif rtype is RoomType.ELITE:
            if self.current_floor >= 3:
                # 三层精英：大嗓门 + 练家子 同时出现
                self._start_rogue_battle_enemies(["大嗓门", "练家子"], "rogue_elite")
            else:
                self._start_rogue_battle(random.choice(self.rogue_elite_pool()), "rogue_elite")
        elif rtype is RoomType.BOSS:
            self._start_rogue_battle_enemies(
                self.rogue_boss_enemies(getattr(room, "boss_key", None)), "rogue_boss"
            )
        elif rtype is RoomType.REST:
            # 火堆：回 30% 血
            heal = int(self.rogue_hero.max_hp * 0.30)
            self.rogue_hp = min(self.rogue_hero.max_hp, self.rogue_hp + heal)
            self.map_mode = "room"
            self.map_room_overlay = "rest"
        elif rtype is RoomType.EVENT:
            self.map_mode = "room"
            self.map_room_overlay = "event"
            self.current_event = random_event_key(self.current_floor)
            self.event_stage = "choose"
            self.event_result_text = ""
        elif rtype is RoomType.SHOP:
            self.map_mode = "room"
            self.map_room_overlay = "shop"
            self._setup_shop()
        elif rtype is RoomType.CHEST:
            self.map_mode = "room"
            self.map_room_overlay = "chest"
            self._open_chest()
        else:  # START
            self.map_mode = "room"
            self.map_room_overlay = "start"

    def _open_chest(self) -> None:
        """打开宝箱：获得不少金币 + 一个随机遗物（占位符）。"""
        gold = random.randint(50, 100)
        self.rogue_gold += gold
        # 随机遗物：当前仅占位遗物
        self.rogue_relics.append(make_relic("mystery_relic"))
        self.chest_result = f"你打开了宝箱，获得 {gold} 金币和一个「神秘遗物」。"

    # ---------- 肉鸽敌人池 ----------
    def rogue_normal_pool(self) -> list[str]:
        """普通战斗的随机敌人池（按层区分）。"""
        if self.current_floor == 2:
            return ["拳击构造体", "小啃兽", "缩小甲虫", "立柱构造体", "罪恶茶壶"]
        return ["拳击构造体", "小啃兽", "缩小甲虫", "立柱构造体"]

    def rogue_elite_pool(self) -> list[str]:
        """精英战斗的随机敌人池（按层区分）。"""
        if self.current_floor == 2:
            return ["劣人杀手", "多伦斯异鸟", "旧日雕像", "迎宾雁"]
        return ["劣人杀手", "多伦斯异鸟", "旧日雕像"]

    def rogue_boss_enemies(self, boss_key: str | None = None) -> list[str]:
        """当前层 Boss 敌人列表。

        一层三个 boss 角（boss_a/boss_b/boss_c）分别对应：墨影幻灵 / 海盗王噶呜 / 科学怪呜；
        二层：典狱长 + 看守；三层暂用墨影幻灵（蒸蛋待做）。
        """
        if self.current_floor == 2:
            return ["典狱长", "看守"]
        if self.current_floor == 1:
            mapping = {
                "boss_a": ["墨影幻灵"],
                "boss_b": ["海盗王噶呜"],
                "boss_c": ["科学怪呜"],
            }
            return mapping.get(boss_key, ["墨影幻灵"])
        return ["墨影幻灵"]

    def _rogue_battle_won(self) -> None:
        """肉鸽战斗胜利：保存血量，推进遗物/诅咒牌倒计时，分发后续。"""
        p = self.engine.state.player
        self.rogue_hp = p.hp
        # 药水在战斗中使用后会从 player.potions 移除，回写持久药水槽
        self.rogue_potions = list(p.potions)
        # 稀释血清：本场触发过则消耗遗物
        if p.dilute_serum_used:
            self.rogue_relics = [r for r in self.rogue_relics if r.relic_id != "dilute_serum"]
        self.engine = None
        # 每场战斗结束：遗物与愧疚卡倒计时推进
        self.rogue_relics = tick_relics(self.rogue_relics)
        self._tick_guilt()
        if self.battle_context == "rogue_boss":
            if self.current_floor >= 3:
                self.game_result = "victory"
                self.scene = "result"
            else:
                self.current_floor += 1
                self._enter_next_floor()
        elif self.battle_context == "rogue_normal":
            # 普通战斗：进入奖励界面
            self._setup_reward()
        elif self.battle_context == "rogue_elite":
            # 精英战斗：金币 70~90 + 药水 + 50% 遗物 + 卡牌奖励
            self._setup_elite_reward()
        elif self.battle_context == "rogue_event_child13":
            # 十三号孩子：获胜获得遗物「稀释血清」
            self.rogue_relics.append(make_relic("dilute_serum"))
            self.scene = "map"
            self.map_mode = "select"
            self.scout_mode = False
            self.resolve_anim = None
            self.monster_anim_timer = 0
        else:
            # 兜底：直接回地图
            self.scene = "map"
            self.map_mode = "select"
            self.scout_mode = False
            self.resolve_anim = None
            self.monster_anim_timer = 0

    def _setup_reward(self) -> None:
        """生成普通战斗奖励并进入奖励弹窗（战利品待玩家领取）。"""
        self.reward_gold = roll_reward_gold()
        self.reward_relic = roll_reward_relic()
        self.reward_cards = roll_reward_cards(self.rogue_hero.key)
        self.reward_potion = None
        self.reward_chosen = False
        self.reward_chosen_key = None
        self.reward_stage = "loot"
        self.scene = "reward"

    def _setup_elite_reward(self) -> None:
        """生成精英战斗奖励并进入奖励弹窗（战利品待玩家领取）。"""
        self.reward_gold = roll_elite_gold()
        self.reward_relic = roll_elite_relic()
        self.reward_cards = roll_reward_cards(self.rogue_hero.key)
        self.reward_potion = random_potion_key()
        self.reward_chosen = False
        self.reward_chosen_key = None
        self.reward_stage = "loot"
        self.scene = "reward"

    def _grant_relic(self, key: str) -> None:
        """获得遗物；泡泡机 / 劣质胶水先弹出选牌浮层。"""
        self.rogue_relics.append(make_relic(key))
        if key == "bubble_machine":
            self._start_enchant_pick("bubble")
        elif key == "bad_glue":
            self._start_enchant_pick("sticky")

    def _finish_reward(self) -> None:
        """结算战利品：金币/遗物/药水入账，已选卡入牌组，然后进地图。"""
        self.rogue_gold += self.reward_gold
        if self.reward_relic is not None:
            self._grant_relic(self.reward_relic)
        if self.reward_potion is not None:
            self.rogue_potions.append(make_potion(self.reward_potion))
        if self.reward_chosen_key is not None:
            self.rogue_deck.append(make_card(self.reward_chosen_key))
        self.reward_relic = None
        self.reward_potion = None
        self.reward_chosen_key = None
        # 泡泡机/劣质胶水弹了选牌浮层：先完成选牌再进地图
        if self.enchant_pick_active:
            return
        self._enter_map_after_reward()

    def _enter_map_after_reward(self) -> None:
        """奖励结算完成后回到地图。"""
        self.scene = "map"
        self.map_mode = "select"
        self.scout_mode = False
        self.resolve_anim = None
        self.monster_anim_timer = 0

    def _maybe_leave_reward(self) -> None:
        """遗物选牌浮层完成后，若仍处于奖励场景则回到地图。"""
        if self.scene == "reward" and not self.enchant_pick_active:
            self._enter_map_after_reward()

    def _start_enchant_pick(self, enchant_key: str) -> None:
        """开启永久附魔选牌浮层（至少两张无永久附魔的牌才触发）。"""
        candidates = [i for i, c in enumerate(self.rogue_deck) if not c.perm_enchant]
        if len(candidates) < 2:
            return
        self.enchant_pick_active = True
        self.enchant_pick_enchant = enchant_key
        self.enchant_pick_selected = []
        self.enchant_pick_rects = []

    def _confirm_enchant_pick(self) -> None:
        """确认选牌：给选中卡施加永久附魔。"""
        if len(self.enchant_pick_selected) != 2:
            return
        for i in self.enchant_pick_selected:
            self.rogue_deck[i].perm_enchant = self.enchant_pick_enchant
        self.enchant_pick_active = False
        self.enchant_pick_enchant = ""
        self.enchant_pick_selected = []
        self._maybe_leave_reward()

    def _handle_enchant_pick_click(self, pos: tuple[int, int]) -> None:
        """选牌浮层内的点击。"""
        if self.enchant_pick_cancel_btn.collidepoint(pos):
            self.enchant_pick_active = False
            self.enchant_pick_enchant = ""
            self.enchant_pick_selected = []
            self._maybe_leave_reward()
            return
        if self.enchant_pick_confirm_btn.collidepoint(pos):
            self._confirm_enchant_pick()
            return
        for i, row in self.enchant_pick_rects:
            if row.collidepoint(pos):
                if i in self.enchant_pick_selected:
                    self.enchant_pick_selected.remove(i)
                elif len(self.enchant_pick_selected) < 2:
                    self.enchant_pick_selected.append(i)
                return

    def _draw_enchant_pick(self) -> None:
        """绘制永久附魔选牌浮层。"""
        from game.enchants import get_enchant_def
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 320, 80, 640, 640)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=14)
        d = get_enchant_def(self.enchant_pick_enchant)
        ename = d.name if d else self.enchant_pick_enchant
        title = self.font_big.render(f"选择两张牌附加永久「{ename}」", True, YELLOW)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 16)))
        hint = self.font_small.render(f"已选 {len(self.enchant_pick_selected)}/2", True, MUTED)
        self.screen.blit(hint, hint.get_rect(midtop=(box.centerx, box.y + 54)))
        self.enchant_pick_rects = []
        y = box.y + 90
        for i, c in enumerate(self.rogue_deck):
            if c.perm_enchant:
                continue
            row = pygame.Rect(box.x + 60, y, box.width - 120, 34)
            pygame.draw.rect(self.screen, PANEL_EDGE, row, border_radius=6)
            selected = i in self.enchant_pick_selected
            color = GREEN if selected else TEXT
            label = self.font_small.render(f"{c.name}（重量 {c.weight}）", True, color)
            self.screen.blit(label, label.get_rect(midleft=(row.x + 12, row.centery)))
            if selected:
                pygame.draw.rect(self.screen, GREEN, row, 2, border_radius=6)
            self.enchant_pick_rects.append((i, row))
            y += 38
        cx = WIDTH // 2
        self.enchant_pick_confirm_btn.midtop = (cx - 130, box.bottom - 58)
        self.enchant_pick_cancel_btn.midtop = (cx + 130, box.bottom - 58)
        if len(self.enchant_pick_selected) == 2:
            self._draw_button(self.enchant_pick_confirm_btn, "确认", GREEN)
        self._draw_button(self.enchant_pick_cancel_btn, "取消", RED)

    def _handle_reward_click(self, pos: tuple[int, int]) -> None:
        """奖励界面点击：战利品弹窗 / 卡牌选择子页面。"""
        if self.enchant_pick_active:
            self._handle_enchant_pick_click(pos)
            return
        if self.reward_stage == "cards":
            # 卡牌选择子页面：三选一 或 跳过
            if self.reward_skip_btn.collidepoint(pos):
                self.reward_stage = "loot"
                return
            for key, rect in self.reward_card_rects:
                if rect.collidepoint(pos):
                    self.reward_chosen = True
                    self.reward_chosen_key = key
                    self.reward_stage = "loot"
                    return
            return
        # 战利品弹窗
        if self.reward_card_pick_btn.collidepoint(pos):
            self.reward_stage = "cards"
            return
        if self.reward_continue_btn.collidepoint(pos):
            self._finish_reward()
            return

    def _tick_guilt(self) -> None:
        """推进愧疚卡倒计时：到期的从牌组移除一张愧疚。"""
        survivors: list[int] = []
        for t in self.rogue_guilt_timers:
            t -= 1
            if t > 0:
                survivors.append(t)
            else:
                self._remove_card_from_deck("guilt")
        self.rogue_guilt_timers = survivors

    def _handle_map_click(self, pos: tuple[int, int]) -> None:
        """地图场景内的点击：头像详情 / 设置菜单 / 房间内容 / 选择路线。"""
        if self.hero_info_active:
            self._handle_hero_info_click(pos)
            return
        if self.settings_active:
            self._handle_settings_click(pos)
            return
        if self.map_mode == "select" and self.map_avatar_btn.collidepoint(pos):
            self.hero_info_active = True
            self.hero_info_selected_card = None
            return
        if self.map_mode == "room":
            self._handle_room_click(pos)
            return
        # 选择路线：侦查 / 移动 / 画笔
        rid = self._room_at(pos)
        if rid is None:
            return
        # 画笔模式：点击房间循环切换标记颜色
        if self.paint_mode:
            if rid in self.room_marks:
                self.room_marks[rid] = (self.room_marks[rid] + 1) % MARK_COLORS_COUNT
            else:
                self.room_marks[rid] = 0
            return
        cur = self.gmap.current_room
        if rid not in cur.neighbors:
            return
        if self.scout_mode:
            result = self.gmap.scout(rid)
            if result is None and self.gmap.scouts_this_turn >= MAX_SCOUTS_PER_TURN:
                self.scout_mode = False  # 侦查满 2 格自动退出
        else:
            self._enter_room(rid)

    def _handle_room_click(self, pos: tuple[int, int]) -> None:
        """房间内容覆盖层内的点击：按房间类型分发。"""
        if self.map_room_overlay == "event":
            self._handle_event_click(pos)
            return
        if self.map_room_overlay == "shop":
            self._handle_shop_click(pos)
            return
        # 起点 / 火堆：直接「继续前进」
        if self.map_continue_btn.collidepoint(pos):
            self.map_mode = "select"
            self.scout_mode = False

    def _handle_event_click(self, pos: tuple[int, int]) -> None:
        """事件房间内的点击：选项 / 删除牌 / 选卡 / 结果。"""
        if self.event_stage == "choose":
            for opt_key, rect in self.event_option_rects:
                if rect.collidepoint(pos):
                    if opt_key == "decline":
                        self.event_stage = "delete_card"
                    elif opt_key == "shop":
                        # 趁机购物：扣金币后进入选卡
                        self._apply_event_option(opt_key)
                        self._setup_event_card_pick()
                        self.event_stage = "pick_card"
                    elif opt_key == "fight":
                        # 事件分支「打」：进入战斗
                        self._start_event_battle()
                    else:
                        self._apply_event_option(opt_key)
                        self.event_stage = "done"
                    return
            return
        if self.event_stage == "delete_card":
            if self.event_delete_back_btn.collidepoint(pos):
                self.event_stage = "choose"
                return
            for key, rect in self.event_delete_rects:
                if rect.collidepoint(pos):
                    self._remove_card_from_deck(key)
                    self._apply_event_option("decline")
                    self.event_stage = "done"
                    return
            return
        if self.event_stage == "pick_card":
            for key, rect in self.event_pick_rects:
                if rect.collidepoint(pos):
                    self.rogue_deck.append(make_card(key))
                    self.event_stage = "done"
                    return
            return
        # done：等待「继续前进」
        if self.map_continue_btn.collidepoint(pos):
            self.map_mode = "select"
            self.scout_mode = False

    def _start_event_battle(self) -> None:
        """事件分支「打」：进入「十三号孩子」战斗。"""
        self._start_rogue_battle("十三号孩子", "rogue_event_child13")

    def _apply_event_option(self, option_key: str) -> None:
        """应用事件选项效果，并记录结果文案。"""
        ev = get_event(self.current_event) if self.current_event else None
        if ev is None:
            return
        for opt in ev.options:
            if opt.key == option_key:
                self.event_result_text = opt.result_text
        if option_key == "devour":
            # 大吃特吃：回 15 血 + 获得遗物「吃剩的毒外卖」
            self.rogue_hp = min(self.rogue_hero.max_hp, self.rogue_hp + 15)
            self.rogue_relics.append(make_relic("leftover_poison_takeout"))
        elif option_key == "decline":
            # 好言拒绝：获得一张愧疚（诅咒牌，三场后移出）
            self.rogue_deck.append(make_card("guilt"))
            self.rogue_guilt_timers.append(3)
        elif option_key == "advertise":
            # 帮忙宣传：获得遗物「老板娘的怀表」（不重复获得）
            if not self._has_relic("boss_watch"):
                self.rogue_relics.append(make_relic("boss_watch"))
        elif option_key == "shop":
            # 趁机购物：失去 50 金币（不足 50 则失去所有）
            lost = min(50, self.rogue_gold)
            self.rogue_gold -= lost
            self.event_result_text += f"（失去 {lost} 金币）"

    def _shop_spend(self, price: int) -> bool:
        """尝试消费金币；本商店还有免费次数时优先免费。返回是否成功。"""
        if self.shop_free_items > 0:
            self.shop_free_items -= 1
            return True
        if self.rogue_gold >= price:
            self.rogue_gold -= price
            return True
        return False

    def _handle_shop_click(self, pos: tuple[int, int]) -> None:
        """商店内的点击：购买卡牌 / 删牌服务 / 占位 / 离开。"""
        if self.shop_stage == "remove_card":
            if self.shop_remove_back_btn.collidepoint(pos):
                self.shop_stage = "buy"
                return
            for key, rect in self.shop_remove_rects:
                if rect.collidepoint(pos):
                    self._shop_remove_card(key)
                    return
            return
        # buy 阶段
        for i, rect in self.shop_offer_rects:
            if rect.collidepoint(pos):
                self._shop_buy_card(i)
                return
        if self.shop_remove_btn.collidepoint(pos):
            if self.shop_free_items > 0 or self.rogue_gold >= remove_service_price(self.rogue_remove_count):
                self.shop_stage = "remove_card"
            return
        if self.shop_relic_btn.collidepoint(pos):
            self.shop_hint = "遗物：敬请期待"
            return
        if self.shop_potion_btn.collidepoint(pos):
            self.shop_hint = "药水：敬请期待"
            return
        if self.map_continue_btn.collidepoint(pos):
            self.map_mode = "select"
            self.scout_mode = False

    def _shop_buy_card(self, i: int) -> None:
        """购买商店里第 i 张卡牌。"""
        if i >= len(self.shop_offers):
            return
        key, price, _ = self.shop_offers[i]
        if self._shop_spend(price):
            self.rogue_deck.append(make_card(key))
            self.shop_offers.pop(i)
        else:
            self.shop_hint = "金币不足！"

    def _shop_remove_card(self, key: str) -> None:
        """付费删除一张牌。"""
        price = remove_service_price(self.rogue_remove_count)
        if self._shop_spend(price):
            self._remove_card_from_deck(key)
            self.rogue_remove_count += 1
            self.shop_stage = "buy"
        else:
            self.shop_hint = "金币不足！"

    def _remove_card_from_deck(self, key: str) -> None:
        """从肉鸽牌组删除一张指定 key（或卡名）的牌。"""
        d = get_card_def(key)
        target = d.name if d else key
        for i, c in enumerate(self.rogue_deck):
            if c.name == target:
                self.rogue_deck.pop(i)
                return

    def _rogue_deck_counts(self) -> dict[str, int]:
        """返回肉鸽牌组按卡名计数的字典。"""
        from collections import Counter
        return Counter(c.name for c in self.rogue_deck)

    def _rogue_deck_rows(self) -> list[tuple[str, str, int]]:
        """返回肉鸽牌组分组行：(卡名, 永久附魔名, 数量)。

        有永久附魔的卡按附魔单独分列（同名卡中无附魔的仍归一行）。
        """
        from collections import Counter
        from game.enchants import get_enchant_def
        rows: dict[tuple[str, str], int] = {}
        for c in self.rogue_deck:
            pe = c.perm_enchant
            d = get_enchant_def(pe) if pe else None
            pe_name = d.name if d else (pe or "")
            key = (c.name, pe_name)
            rows[key] = rows.get(key, 0) + 1
        return [(name, pe, rows[(name, pe)]) for name, pe in sorted(rows)]

    def _rogue_deck_card(self, name: str, pe_name: str) -> Card:
        """返回牌组中某 (卡名, 永久附魔名) 的一个实例（供放大查看）。"""
        from game.enchants import get_enchant_def
        for c in self.rogue_deck:
            pe = c.perm_enchant
            d = get_enchant_def(pe) if pe else None
            pn = d.name if d else (pe or "")
            if c.name == name and pn == pe_name:
                return c
        return make_card(name)

    def _has_relic(self, key: str) -> bool:
        """是否持有某遗物。"""
        return any(r.relic_id == key for r in self.rogue_relics)

    def _setup_shop(self) -> None:
        """进入商店：生成商品，计算免费次数（老板娘的怀表）。"""
        self.shop_offers = generate_offers(self.rogue_hero.key)
        self.shop_stage = "buy"
        self.shop_free_items = 2 if self._has_relic("boss_watch") else 0
        self.shop_hint = ""

    def _setup_event_card_pick(self) -> None:
        """事件「趁机购物」：生成三张随机蓝色以上品质卡供选择（不串池）。"""
        pool = [
            k for k in public_card_keys() + hero_card_keys(self.rogue_hero.key)
            if get_card_def(k).rarity in (Rarity.UNCOMMON, Rarity.RARE)
        ]
        rng = random.Random()
        self.event_pick_cards = rng.sample(pool, min(3, len(pool)))

    # ---------- 布局：手牌（折叠条带） ----------
    HAND_FOLD_H = 60  # 折叠时露出的高度（顶部条带）

    def layout_hand(self) -> None:
        n = len(self._active_player().hand)
        if n == 0:
            self.hand_rects = []
            return
        gap = 12
        max_w = WIDTH - 40
        total_w = CARD_W * n + gap * (n - 1)
        if total_w > max_w and n > 1:
            gap = max(-40, (max_w - CARD_W * n) / (n - 1))
            total_w = CARD_W * n + gap * (n - 1)
        start_x = (WIDTH - total_w) // 2
        bottom = HEIGHT - 20
        self.hand_rects = [
            pygame.Rect(int(start_x + i * (CARD_W + gap)), bottom - self.HAND_FOLD_H, CARD_W, self.HAND_FOLD_H)
            for i in range(n)
        ]

    def _hand_index_at(self, pos: tuple[int, int]) -> int | None:
        """返回鼠标悬停的手牌索引（考虑悬停展开的完整卡区域）。"""
        for i, rect in enumerate(self.hand_rects):
            if i == self.hand_hover:
                full = pygame.Rect(rect.x, rect.bottom - CARD_H, CARD_W, CARD_H)
                if full.collidepoint(pos):
                    return i
            elif rect.collidepoint(pos):
                return i
        return None

    # ---------- 事件 ----------
    def _handle_log_click(self, pos: tuple[int, int]) -> None:
        """日志界面内的点击：仅处理关闭与滚动条拖拽，屏蔽其它所有点击。"""
        if self.log_close_btn.collidepoint(pos):
            self.log_visible = False
            return
        # 滚动条：thumb 或轨道
        if self.log_scroll_track.collidepoint(pos):
            self._log_scrollbar_set_by_pos(pos)
            self.dragging_log_scrollbar = True
            return
        # 面板外的覆盖层空白区域：点击关闭
        box = pygame.Rect(WIDTH // 2 - 420, 60, 840, 680)
        if not box.collidepoint(pos):
            self.log_visible = False

    def _log_scrollbar_set_by_pos(self, pos: tuple[int, int]) -> None:
        """根据鼠标 y 位置设置日志滚动偏移。"""
        track = self.log_scroll_track
        if track.height <= 0 or self.log_scroll_max <= 0:
            return
        thumb_h = self.log_scroll_thumb.height
        view_h = track.height
        if view_h - thumb_h <= 0:
            self.log_scroll = 0
            return
        ratio = (pos[1] - track.y - thumb_h / 2) / (view_h - thumb_h)
        ratio = max(0.0, min(1.0, ratio))
        self.log_scroll = int(self.log_scroll_max * ratio)

    def handle_mouse_down(self, pos: tuple[int, int]) -> None:
        # 日志界面打开：屏蔽所有其它点击，只处理关闭/滚动
        if self.log_visible:
            self._handle_log_click(pos)
            return
        # 阿兰娜诅咒目标选择：优先处理
        if getattr(self, "curse_select", False):
            self._handle_curse_select_click(pos)
            return
        # 状态详情浮层打开：点击任意处关闭
        if getattr(self, "status_detail", None) is not None:
            self.status_detail = None
            return
        # 意图详情浮层打开：点击任意处关闭
        if getattr(self, "intent_detail", None) is not None:
            self.intent_detail = None
            return
        # 抽牌堆 / 弃牌堆查看浮层打开：处理内部点击
        if getattr(self, "viewing_deck", None) is not None:
            self._handle_deck_viewer_click(pos)
            return
        # 结算动画进行中：屏蔽其它点击，只处理目标选择
        if self.resolve_anim is not None:
            self._handle_resolution_click(pos)
            return
        # 选择模式：处理手牌 / 牌堆选择
        if self.select_mode:
            self._handle_select_click(pos)
            return
        # 地图查看浮层打开：只处理关闭
        if self.map_view_active:
            if self.map_close_btn.collidepoint(pos):
                self.map_view_active = False
            return
        # 设置菜单打开：只处理菜单内部
        if self.settings_active:
            self._handle_settings_click(pos)
            return
        # 头像详情打开：处理卡牌放大/关闭
        if self.hero_info_active:
            self._handle_hero_info_click(pos)
            return
        # 自定义重量浮层打开时优先处理，屏蔽其它点击
        if self.customizing is not None:
            self._handle_weight_popup_click(pos)
            return
        # 浮层打开时：屏蔽所有浮层范围内的点击响应，只处理浮层内部
        if self.viewing_pile is not None:
            self._handle_viewer_click(pos)
            return
        # 药水浮层打开：只处理内部
        if self.potion_popup_active:
            self._handle_potion_click(pos)
            return

        if self.quit_btn.collidepoint(pos):
            self.settings_active = True
            return
        if self.mode == "rogue" and self.map_key_btn.collidepoint(pos):
            self.map_view_active = True
            return
        if self.mode == "rogue" and self.potion_btn.collidepoint(pos):
            self.potion_popup_active = True
            return
        if self.skip_btn.collidepoint(pos):
            if self.mode == "pve":
                self._pve_end_turn()
            else:
                self._start_resolution()
            return
        if self.hero_icon_btn.collidepoint(pos):
            self.hero_info_active = True
            return

        # 抽牌堆 / 弃牌堆按钮
        if self.draw_pile_btn.collidepoint(pos):
            self.viewing_deck = "draw"
            self.deck_viewer_selected = None
            return
        if self.discard_pile_btn.collidepoint(pos):
            self.viewing_deck = "discard"
            self.deck_viewer_selected = None
            return

        # 点击状态图标：弹出状态详情
        for info, rect in getattr(self, "status_icon_rects", []):
            if rect.collidepoint(pos):
                self.status_detail = info
                return

        # 点击意图图标：弹出意图详情
        for desc, rect in getattr(self, "intent_icon_rects", []):
            if rect.collidepoint(pos):
                self.intent_detail = desc
                return

        # 点击牌堆：查看牌堆内容（点同一个可收起）
        for slot_idx, rect in enumerate(self.slot_rects):
            if rect.collidepoint(pos):
                self.viewing_pile = slot_idx
                self.viewer_selected_card = None
                return

        # 点击手牌：开始拖拽
        hand_idx = self._hand_index_at(pos)
        if hand_idx is not None:
            self.dragging = hand_idx
            self.hand_hover = None
            self.drag_pos = pos
            self.hover_slot = self._slot_at(pos)
            return

    # ---------- 药水 ----------
    def _use_potion(self, potion: Potion) -> None:
        """使用一瓶药水，应用效果并从玩家药水槽移除。"""
        from game.potions import get_potion_def
        d = get_potion_def(potion.potion_id)
        if d is None or self.engine is None:
            return
        player = self._active_player()
        effect, value = d.effect, d.value
        if effect == "heal":
            healed = player.heal(value)
            self.engine.log(f"使用药水：回复 {healed} 点生命")
        elif effect == "strength":
            player.strength += value
            self.engine.log(f"使用药水：力量 +{value}（当前力量 {player.strength}）")
        elif effect == "block":
            player.gain_block(value)
            self.engine.log(f"使用药水：获得 {value} 点格挡")
        elif effect == "draw":
            drawn = self.engine.draw_cards(value)
            self.engine.log(f"使用药水：抽取 {len(drawn)} 张牌")
        # 从玩家药水槽移除
        if potion in player.potions:
            player.potions.remove(potion)
        self.rogue_potions = list(player.potions)
        if not player.potions:
            self.potion_popup_active = False

    def _handle_potion_click(self, pos: tuple[int, int]) -> None:
        """药水浮层内的点击：使用药水 / 关闭。"""
        if self.engine is None:
            self.potion_popup_active = False
            return
        for potion, rect in self.potion_use_rects:
            if rect.collidepoint(pos):
                self._use_potion(potion)
                return
        # 点击浮层外关闭
        box = self._potion_popup_rect()
        if not box.collidepoint(pos):
            self.potion_popup_active = False

    def _potion_popup_rect(self) -> pygame.Rect:
        return pygame.Rect(WIDTH // 2 - 260, 180, 520, 360)

    def _draw_potion_popup(self) -> None:
        """绘制药水使用浮层。"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        box = self._potion_popup_rect()
        pygame.draw.rect(self.screen, PANEL, box, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=14)
        title = self.font_big.render("药水", True, (110, 210, 130))
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 16)))
        if self.engine is None:
            return
        player = self._active_player()
        self.potion_use_rects = []
        y = box.y + 70
        for potion in player.potions:
            rect = pygame.Rect(box.x + 40, y, box.width - 80, 56)
            pygame.draw.rect(self.screen, PANEL_EDGE, rect, border_radius=8)
            name = self.font.render(potion.name, True, TEXT)
            self.screen.blit(name, name.get_rect(midleft=(rect.x + 14, rect.y + 16)))
            desc = self.font_small.render(potion.description, True, MUTED)
            self.screen.blit(desc, desc.get_rect(midleft=(rect.x + 14, rect.y + 38)))
            self.potion_use_rects.append((potion, rect))
            y += 66
        if not player.potions:
            empty = self.font.render("（没有药水）", True, MUTED)
            self.screen.blit(empty, empty.get_rect(center=box.center))
        hint = self.font_small.render("点击药水使用 · 点击外部关闭", True, MUTED)
        self.screen.blit(hint, hint.get_rect(midbottom=(box.centerx, box.bottom - 10)))

    def _handle_settings_click(self, pos: tuple[int, int]) -> None:
        """设置菜单内的点击：返回主菜单 / 退出游戏。"""
        self._layout_settings_buttons()
        if self.settings_back_btn.collidepoint(pos):
            self.settings_active = False
            self.scene = "menu"
            self.game_result = None
        elif self.settings_exit_btn.collidepoint(pos):
            self.running = False
        else:
            self.settings_active = False

    def _layout_settings_buttons(self) -> None:
        cx = WIDTH // 2
        cy = HEIGHT // 2
        self.settings_back_btn.center = (cx, cy - 40)
        self.settings_exit_btn.center = (cx, cy + 30)

    def _handle_hero_info_click(self, pos: tuple[int, int]) -> None:
        """头像详情内的点击：点击卡牌放大查看描述，否则关闭。"""
        # 放大卡牌已打开：点击任意处关闭
        if self.hero_info_selected_card is not None:
            self.hero_info_selected_card = None
            return
        # 点击牌组中的卡牌 → 放大
        for card, rect in self.hero_info_card_rects:
            if rect.collidepoint(pos):
                self.hero_info_selected_card = card
                return
        # 点击其它地方关闭详情
        self.hero_info_active = False
        self.hero_info_selected_card = None

    def _handle_viewer_click(self, pos: tuple[int, int]) -> None:
        """浮层内的点击处理：翻页、查看整卡、关闭。"""
        prev_rect, next_rect = self._view_nav_rects()
        if prev_rect.collidepoint(pos):
            self.viewing_pile = (self.viewing_pile - 1) % len(self.slot_rects)
            self.viewer_selected_card = None
            return
        if next_rect.collidepoint(pos):
            self.viewing_pile = (self.viewing_pile + 1) % len(self.slot_rects)
            self.viewer_selected_card = None
            return

        # 整卡浮层打开时，点击任意处关闭整卡
        if self.viewer_selected_card is not None:
            self.viewer_selected_card = None
            return

        # 点击牌堆中的某张卡，显示整张卡面
        # 从底层（靠下的卡）往前判定，避免被上层卡矩形遮挡而点不到
        for card, rect in reversed(self.viewer_card_rects):
            if rect.collidepoint(pos):
                self.viewer_selected_card = card
                return

        # 点击浮层外关闭浮层
        if not self._view_popup_rect().collidepoint(pos):
            self.viewing_pile = None

    def handle_mouse_up(self, pos: tuple[int, int]) -> None:
        if self.dragging is None:
            return
        slot = self._slot_at(pos)
        hand_index = self.dragging
        player = self._active_player()
        if hand_index < len(player.hand):
            card = player.hand[hand_index]
            # 蒸蛋被动：可自定义重量的额外牌，放牌前先弹重量选择
            if slot is not None and card.customizable_weight:
                self.pending_hand_index = hand_index
                self.pending_slot = slot
                self.custom_weight = max(1, min(10, card.weight))
                self.customizing = card
                self._end_drag()
                return
        if slot is not None:
            # 需要选择的逻辑牌：进入选择模式
            if hand_index < len(player.hand):
                card = player.hand[hand_index]
                if card.select_mode:
                    player.hand.pop(hand_index)
                    self.select_mode = card.select_mode
                    self.select_card = card
                    self.selected_hand = []
                    self.selected_piles = []
                    self._end_drag()
                    return
            self.engine.add_card_to_pile(hand_index, slot)
        self._end_drag()

    def handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        self.drag_pos = pos
        if self.dragging_scrollbar:
            self._scrollbar_set_by_pos(pos)
            return
        if self.dragging_log_scrollbar:
            self._log_scrollbar_set_by_pos(pos)
            return
        if self.dragging is not None:
            self.hover_slot = self._slot_at(pos)
        else:
            self.hand_hover = self._hand_index_at(pos)

    def _end_drag(self) -> None:
        self.dragging = None
        self.hover_slot = None

    def _slot_at(self, pos: tuple[int, int]) -> int | None:
        for idx, rect in enumerate(self.slot_rects):
            if rect.collidepoint(pos):
                return idx
        return None

    # ---------- 逻辑牌选择 ----------
    def _full_hand_rects(self) -> list[pygame.Rect]:
        """展开的手牌完整卡区域（选择目标用）。"""
        self.layout_hand()
        rects = []
        for r in self.hand_rects:
            rects.append(pygame.Rect(r.x, r.bottom - CARD_H, CARD_W, CARD_H))
        self.select_full_hand_rects = rects
        return rects

    def _select_prompt(self) -> str:
        if self.select_mode == "hand_1":
            return "选择一张手牌，使其重量 +3"
        if self.select_mode == "hand_2":
            return f"选择两张手牌交换重量（已选 {len(self.selected_hand)}/2）"
        if self.select_mode == "hand_same":
            return f"选择至多三张重量相同的手牌（已选 {len(self.selected_hand)}/3）"
        if self.select_mode == "pile":
            if self.select_card is not None and self.select_card.invert_pile:
                return "选择要倒置的牌堆"
            return "选择要删除顶牌的牌堆"
        if self.select_mode == "deck_3":
            return f"从牌组选择三张卡附魔「精准」（已选 {len(self.selected_hand)}/3）"
        return ""

    def _handle_select_click(self, pos: tuple[int, int]) -> None:
        """处理逻辑牌选择模式下的点击。"""
        if self.select_cancel_btn.collidepoint(pos):
            self._cancel_selection()
            return
        if self.select_confirm_btn.collidepoint(pos):
            self._confirm_selection()
            return

        if self.select_mode in ("hand_1", "hand_2", "hand_same"):
            rects = self._full_hand_rects()
            player = self._active_player()
            for i, r in enumerate(rects):
                if r.collidepoint(pos) and i < len(player.hand):
                    if self.select_mode == "hand_1":
                        self.selected_hand = [i]
                        self._confirm_selection()
                    elif self.select_mode == "hand_2":
                        if i in self.selected_hand:
                            self.selected_hand.remove(i)
                        elif len(self.selected_hand) < 2:
                            self.selected_hand.append(i)
                    elif self.select_mode == "hand_same":
                        if i in self.selected_hand:
                            self.selected_hand.remove(i)
                        else:
                            if not self.selected_hand:
                                self.selected_hand = [i]
                            elif len(self.selected_hand) < 3:
                                w = player.hand[self.selected_hand[0]].weight
                                if player.hand[i].weight == w:
                                    self.selected_hand.append(i)
                    return
        elif self.select_mode == "pile":
            for idx, rect in enumerate(self.slot_rects):
                if rect.collidepoint(pos):
                    self.selected_piles = [idx]
                    self._confirm_selection()
                    return
        elif self.select_mode == "deck_3":
            for i, r in enumerate(self.select_deck_rects):
                if r.collidepoint(pos):
                    if i in self.selected_hand:
                        self.selected_hand.remove(i)
                    elif len(self.selected_hand) < 3:
                        self.selected_hand.append(i)
                    return

    def _confirm_selection(self) -> None:
        """确认选择，应用逻辑牌效果。"""
        card = self.select_card
        if card is None or self.engine is None:
            self._clear_selection()
            return
        valid = False
        if self.select_mode == "hand_1":
            valid = len(self.selected_hand) == 1
        elif self.select_mode == "hand_2":
            valid = len(self.selected_hand) == 2
        elif self.select_mode == "hand_same":
            valid = len(self.selected_hand) >= 2
        elif self.select_mode == "pile":
            valid = len(self.selected_piles) == 1
        elif self.select_mode == "deck_3":
            valid = len(self.selected_hand) == 3
        if not valid:
            return
        self.engine.play_select_card(card, self.selected_hand, self.selected_piles)
        self._clear_selection()

    def _cancel_selection(self) -> None:
        """取消选择，把手牌放回。"""
        if self.select_card is not None and self.engine is not None:
            self._active_player().hand.append(self.select_card)
        self._clear_selection()

    def _clear_selection(self) -> None:
        self.select_mode = ""
        self.select_card = None
        self.selected_hand = []
        self.selected_piles = []
        self.select_full_hand_rects = []
        self.select_deck_rects = []

    def _draw_select_overlay(self) -> None:
        """绘制逻辑牌选择目标浮层。"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        prompt = self.font_big.render(self._select_prompt(), True, YELLOW)
        self.screen.blit(prompt, prompt.get_rect(midtop=(WIDTH // 2, 80)))

        player = self._active_player()
        if self.select_mode in ("hand_1", "hand_2", "hand_same"):
            rects = self._full_hand_rects()
            for i, r in enumerate(rects):
                if i >= len(player.hand):
                    continue
                card = player.hand[i]
                selected = i in self.selected_hand
                self._draw_card(r, card, selected=selected)
                if selected:
                    pygame.draw.rect(self.screen, GREEN, r, 4, border_radius=10)
        elif self.select_mode == "pile":
            for idx, rect in enumerate(self.slot_rects):
                pygame.draw.rect(self.screen, SLOT_BG, rect, border_radius=10)
                pygame.draw.rect(
                    self.screen, GREEN if idx in self.selected_piles else SLOT_ACTIVE_EDGE,
                    rect, 3, border_radius=10,
                )
                label = self.font.render(f"牌堆 {idx + 1}", True, TEXT)
                self.screen.blit(label, label.get_rect(center=rect.center))
                pile = player.pile_slots[idx]
                cnt = self.font_small.render(f"{len(pile.cards)} 张", True, MUTED)
                self.screen.blit(cnt, cnt.get_rect(midtop=(rect.centerx, rect.bottom - 30)))
        elif self.select_mode == "deck_3":
            deck = self.engine._deck_cards()
            self.select_deck_rects = []
            cw, ch = 110, 154
            per_row = 6
            gap = 12
            start_x = (WIDTH - (cw * per_row + gap * (per_row - 1))) // 2
            y = 160
            for i, card in enumerate(deck):
                row = i // per_row
                col = i % per_row
                r = pygame.Rect(start_x + col * (cw + gap), y + row * (ch + 14), cw, ch)
                selected = i in self.selected_hand
                self._draw_card(r, card, selected=selected)
                if selected:
                    pygame.draw.rect(self.screen, GREEN, r, 4, border_radius=10)
                self.select_deck_rects.append(r)

        # 确认 / 取消按钮
        cx = WIDTH // 2
        self.select_confirm_btn.midtop = (cx - 130, HEIGHT - 90)
        self.select_cancel_btn.midtop = (cx + 130, HEIGHT - 90)
        can_confirm = {
            "hand_1": len(self.selected_hand) == 1,
            "hand_2": len(self.selected_hand) == 2,
            "hand_same": len(self.selected_hand) >= 2,
            "pile": len(self.selected_piles) == 1,
            "deck_3": len(self.selected_hand) == 3,
        }.get(self.select_mode, False)
        if can_confirm:
            self._draw_button(self.select_confirm_btn, "确认", GREEN)
        self._draw_button(self.select_cancel_btn, "取消", RED)

    # ---------- 结算动画 ----------
    def _start_resolution(self) -> None:
        """进入回合结束结算动画流程。"""
        if self.engine is None or self.engine.state.phase != Phase.PLAYER_ACTION:
            return
        self._end_drag()
        self.viewing_pile = None
        self.viewer_selected_card = None
        self.engine.clear_hand_to_discard()
        self.engine.status_phase()
        # 冰冻：玩家本回合牌堆不向前推进，直接进入怪物回合
        frozen = self.engine.state.player.get_stacks("frozen")
        if frozen > 0:
            self.engine.state.player.set_stacks("frozen", frozen - 1)
            self.engine.log(f"玩家被冰冻，牌堆不向前推进（冰冻 {frozen} -> {frozen - 1}）")
            self._after_resolution()
            return
        self.engine.begin_resolution()
        self.resolve_cards = list(self.engine.resolution_queue)
        self.resolve_index = 0
        self.resolve_current = None
        self.resolve_target = None
        self.anim_t = 0.0
        self.effect_text = ""
        if self.resolve_cards:
            self.resolve_anim = "stack"
        else:
            self._finish_resolution()

    def _finish_resolution(self) -> None:
        """结算动画结束，进入怪物回合，检查胜负。"""
        self.engine.end_resolution()
        self._after_resolution()

    def _after_resolution(self) -> None:
        """怪物回合 + 胜负判定 + 回合推进（结算之后）。"""
        hp_before = self.engine.state.player.hp
        self.engine.monster_phase()
        hp_after = self.engine.state.player.hp
        self.monster_pierced = hp_after < hp_before  # 是否穿透格挡掉血
        result = self.engine.check_game_over()
        self.resolve_anim = None
        self.resolve_cards = []
        self.resolve_current = None
        if result == "victory" and self.mode == "rogue":
            self._rogue_battle_won()
        elif result:
            self.game_result = result
            self.scene = "result"
        else:
            # 怪物攻击动画
            self.monster_anim_timer = MONSTER_ANIM_FRAMES
            self.resolve_anim = "monster_attack"

    def _maybe_trigger_curse_passive(self) -> None:
        """阿兰娜被动：回合开始时触发诅咒选择（多怪弹选择，单怪自动施）。"""
        if self.engine is None:
            return
        player = self.engine.state.player
        if not getattr(player, "curse_on_turn", False):
            return
        enemies = self._enemies()
        alive = [e for e in enemies if e.is_alive]
        if not alive:
            return
        if len(alive) == 1:
            self.engine.apply_curse_passive(alive[0])
        else:
            self.curse_select = True
            self.curse_target_rects = []
            # 布局选择按钮
            cx = WIDTH // 2
            y = HEIGHT // 2 + 130
            for i, e in enumerate(enemies):
                if not e.is_alive:
                    continue
                rect = pygame.Rect(cx - 75 + (i - len(enemies) / 2) * 170, y, 150, 48)
                self.curse_target_rects.append((i, rect))

    def _handle_curse_select_click(self, pos: tuple[int, int]) -> None:
        """处理阿兰娜诅咒目标选择。"""
        for i, rect in self.curse_target_rects:
            if rect.collidepoint(pos):
                enemies = self._enemies()
                if 0 <= i < len(enemies) and enemies[i].is_alive:
                    self.engine.apply_curse_passive(enemies[i])
                self.curse_select = False
                return

    def _draw_curse_select(self) -> None:
        """绘制阿兰娜诅咒目标选择浮层。"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        prompt = self.font_big.render("选择诅咒目标", True, YELLOW)
        self.screen.blit(prompt, prompt.get_rect(midtop=(WIDTH // 2, 80)))
        enemies = self._enemies()
        self.curse_target_rects = []
        cx = WIDTH // 2
        y = HEIGHT // 2 + 130
        for i, e in enumerate(enemies):
            if not e.is_alive:
                continue
            rect = pygame.Rect(cx - 75 + (i - (len(enemies) - 1) / 2) * 170, y, 150, 48)
            self.curse_target_rects.append((i, rect))
            self._draw_button(rect, e.name, RED)

    def _begin_next_card(self) -> None:
        """准备打出下一张牌。"""
        if self.resolve_index >= len(self.resolve_cards):
            self._finish_resolution()
            return
        card = self.resolve_cards[self.resolve_index]
        self.resolve_current = card
        if card.needs_target:
            self.resolve_target = None
            self.resolve_anim = "await_target"
            self._layout_target_buttons()
        else:
            self.resolve_target = None
            self.resolve_anim = "fly"
            self.anim_t = 0.0

    def _layout_target_buttons(self) -> None:
        cx = WIDTH // 2
        y = HEIGHT // 2 + 130
        card = self.resolve_current
        enemies = self._enemies()
        only_enemy = card is not None and card.apply_mark
        # 嘲讽：存活敌人中有嘲讽时，只能选它（不显示 self）
        taunt_idx = next(
            (i for i, e in enumerate(enemies) if e.is_alive and e.get_stacks("taunt") > 0),
            None,
        )
        if taunt_idx is not None:
            enemy_targets = [f"enemy{taunt_idx}"]
        else:
            enemy_targets = [f"enemy{i}" for i, e in enumerate(enemies) if e.is_alive]
        if not enemy_targets:
            enemy_targets = ["enemy0"]
        btn_w = 150
        gap = 16
        n = len(enemy_targets) + (0 if (only_enemy or taunt_idx is not None) else 1)
        total_w = btn_w * n + gap * (n - 1)
        x = cx - total_w // 2
        rects: dict[str, pygame.Rect] = {}
        for t in enemy_targets:
            rects[t] = pygame.Rect(x, y, btn_w, 48)
            x += btn_w + gap
        if not only_enemy and taunt_idx is None:
            rects["self"] = pygame.Rect(x, y, btn_w, 48)
        self.target_btn_rects = rects

    def _target_pos(self, target: str) -> tuple[int, int]:
        if target == "self":
            return self.player_area.center
        enemies = self._enemies()
        if target and target.startswith("enemy"):
            idx = int(target[5:]) if target[5:].isdigit() else 0
            area = self._side_area(self.enemy_area, idx, max(1, len(enemies)))
            return area.center
        return self.enemy_area.center

    def _play_current_card(self) -> None:
        """执行当前牌效果（不展示效果文字，日志仍记录），并停留片刻展示飘字。"""
        self.engine.step_resolution(self.resolve_target)
        self.effect_text = ""
        self.effect_timer = EFFECT_HOLD_FRAMES
        self.resolve_anim = "effect"
        self.resolve_index += 1
        self.resolve_current = None

    def _handle_resolution_click(self, pos: tuple[int, int]) -> None:
        """结算动画期间的点击：仅处理目标选择。"""
        if self.resolve_anim == "await_target":
            for target, rect in self.target_btn_rects.items():
                if rect.collidepoint(pos):
                    self.resolve_target = target
                    self.resolve_anim = "fly"
                    self.anim_t = 0.0
                    return

    def _update_resolution(self) -> None:
        """每帧推进结算动画。"""
        if self.resolve_anim == "stack":
            self.anim_t += 1.0 / STACK_FRAMES
            if self.anim_t >= 1.0:
                self._begin_next_card()
        elif self.resolve_anim == "fly":
            self.anim_t += 1.0 / FLY_FRAMES
            if self.anim_t >= 1.0:
                self._play_current_card()
        elif self.resolve_anim == "effect":
            self.effect_timer -= 1
            if self.effect_timer <= 0:
                self._begin_next_card()
        elif self.resolve_anim == "monster_attack":
            self.monster_anim_timer -= 1
            if self.monster_anim_timer <= 0:
                self.resolve_anim = None
                self.engine.start_turn()
                self._maybe_trigger_curse_passive()
        # await_target：等待点击，不自动推进

    # ---------- 场景分发 ----------
    def _dispatch_mouse_down(self, pos: tuple[int, int]) -> None:
        if self.scene == "menu":
            if self.menu_start_btn.collidepoint(pos):
                self.scene = "mode_select"
            elif self.menu_pvp_btn.collidepoint(pos):
                self.scene = "pvp_setup"
            elif self.menu_quit_btn.collidepoint(pos):
                self.running = False
        elif self.scene == "pvp_setup":
            if self.pvp_setup_back_btn.collidepoint(pos):
                self.scene = "menu"
            elif self.pvp_mult_minus.collidepoint(pos):
                self.pvp_hp_mult = max(0.5, round(self.pvp_hp_mult - 0.5, 1))
            elif self.pvp_mult_plus.collidepoint(pos):
                self.pvp_hp_mult = round(self.pvp_hp_mult + 0.5, 1)
            elif self.pvp_deckmin_minus.collidepoint(pos):
                self.pvp_deck_min = max(4, self.pvp_deck_min - 1)
            elif self.pvp_deckmin_plus.collidepoint(pos):
                self.pvp_deck_min = min(self.pvp_deck_min + 1, self.pvp_deck_max)
            elif self.pvp_deckmax_minus.collidepoint(pos):
                self.pvp_deck_max = max(self.pvp_deck_min, self.pvp_deck_max - 1)
            elif self.pvp_deckmax_plus.collidepoint(pos):
                self.pvp_deck_max = min(40, self.pvp_deck_max + 1)
            elif self.pvp_host_btn.collidepoint(pos):
                self._pvp_host_create(lan=False)
            elif self.pvp_host_lan_btn.collidepoint(pos):
                self._pvp_host_create(lan=True)
            elif self.pvp_join_btn.collidepoint(pos):
                self.scene = "pvp_join_setup"
        elif self.scene == "pvp_join_setup":
            if self.pvp_join_back_btn.collidepoint(pos):
                self.scene = "pvp_setup"
            elif self.pvp_join_confirm_btn.collidepoint(pos) and self.pvp_join_ip:
                self._pvp_guest_join(self.pvp_join_port, host=self.pvp_join_ip.strip())
        elif self.scene == "mode_select":
            if self.mode_back_btn.collidepoint(pos):
                self.scene = "menu"
            elif self.mode_sim_btn.collidepoint(pos):
                self.mode = "sim"
                self.scene = "select"
            elif self.mode_rogue_btn.collidepoint(pos):
                self.mode = "rogue"
                self.scene = "select"
            elif self.mode_pve_btn.collidepoint(pos):
                self.mode = "pve"
                self.scene = "pve_setup"
        elif self.scene == "pve_setup":
            self._handle_pve_setup_click(pos)
        elif self.scene == "pve_join_setup":
            self._handle_pve_join_click(pos)
        elif self.scene == "pve_wait":
            if self.pve_start_btn.collidepoint(pos):
                self._pve_host_start()
            elif self.pve_setup_back_btn.collidepoint(pos):
                self._pve_cleanup()
                self.scene = "pve_setup"
        elif self.scene == "select":
            if self.select_back_btn.collidepoint(pos):
                if self.mode == "pvp":
                    self.scene = "pvp_setup"
                elif self.mode == "pve":
                    self.scene = "pve_setup"
                else:
                    self.scene = "mode_select"
                return
            for hero, rect in self.hero_card_rects:
                if rect.collidepoint(pos):
                    self.hero = hero
                    if self.mode == "rogue":
                        # 肉鸽模式：不能自定义牌库，直接开跑
                        self._start_rogue_run()
                    elif self.mode == "pve":
                        # 多人 PVE：选定角色后进入等待
                        self._pve_pick_hero(hero)
                    else:
                        self.deck_edit = dict(hero.deck)
                        self.scene = "deck_edit"
                    return
        elif self.scene == "deck_edit":
            self._handle_deck_edit_click(pos)
        elif self.scene == "enemy_select":
            if self.enemy_select_back_btn.collidepoint(pos):
                self.scene = "deck_edit"
                return
            for name, rect in self.enemy_select_rects:
                if rect.collidepoint(pos):
                    if name == self._DUO_LABEL:
                        self._start_battle_enemies(self.hero, list(self._DUO_ENEMIES))
                    else:
                        self._start_battle(self.hero, name)
                    return
        elif self.scene == "map":
            self._handle_map_click(pos)
        elif self.scene == "battle":
            self.handle_mouse_down(pos)
        elif self.scene == "pvp_battle":
            self._handle_pvp_mouse_down(pos)
        elif self.scene == "reward":
            self._handle_reward_click(pos)
        elif self.scene == "result":
            self.scene = "menu"
            self.game_result = None
            self.mode = None
            self._pve_cleanup()

    # ---------- 牌组编辑 ----------
    def _handle_deck_edit_click(self, pos: tuple[int, int]) -> None:
        if self.deck_back_btn.collidepoint(pos):
            self.scene = "select"
            return
        if self.deck_start_btn.collidepoint(pos):
            if self.mode == "rogue":
                self._start_rogue_run()
            elif self.mode == "pvp":
                self._pvp_finalize_deck()
            else:
                self.scene = "enemy_select"
            return
        # 滚动条拖拽优先
        if self.deck_scroll_thumb.height > 0 and self._scrollbar_click(pos):
            return
        for key, minus_rect, plus_rect in self.deck_card_rects:
            if plus_rect.collidepoint(pos):
                # PVP 模式受配牌数量上限约束
                if self.mode == "pvp":
                    total = sum(self.deck_edit.values())
                    if total >= self.pvp_deck_max:
                        return
                self.deck_edit[key] = self.deck_edit.get(key, 0) + 1
                return
            if minus_rect.collidepoint(pos):
                if self.deck_edit.get(key, 0) > 0:
                    self.deck_edit[key] -= 1
                    if self.deck_edit[key] == 0:
                        del self.deck_edit[key]
                return

    # ---------- 自定义重量浮层 ----------
    def _weight_popup_rect(self) -> pygame.Rect:
        return pygame.Rect(WIDTH // 2 - 200, HEIGHT // 2 - 120, 400, 240)

    def _layout_weight_buttons(self) -> None:
        popup = self._weight_popup_rect()
        cy = popup.y + 130
        self.weight_minus_btn.midright = (popup.centerx - 60, cy)
        self.weight_plus_btn.midleft = (popup.centerx + 60, cy)
        self.weight_ok_btn.topleft = (popup.x + 40, popup.y + 180)
        self.weight_cancel_btn.topright = (popup.right - 40, popup.y + 180)

    def _handle_weight_popup_click(self, pos: tuple[int, int]) -> None:
        self._layout_weight_buttons()
        if self.weight_minus_btn.collidepoint(pos):
            self.custom_weight = max(1, self.custom_weight - 1)
        elif self.weight_plus_btn.collidepoint(pos):
            self.custom_weight = min(10, self.custom_weight + 1)
        elif self.weight_ok_btn.collidepoint(pos):
            self._confirm_custom_weight()
        elif self.weight_cancel_btn.collidepoint(pos):
            self.customizing = None
            self.pending_hand_index = None
            self.pending_slot = None

    def _confirm_custom_weight(self) -> None:
        if (
            self.customizing is None
            or self.pending_hand_index is None
            or self.pending_slot is None
        ):
            self.customizing = None
            return
        self.customizing.weight = self.custom_weight
        self.engine.add_card_to_pile(self.pending_hand_index, self.pending_slot)
        self.customizing = None
        self.pending_hand_index = None
        self.pending_slot = None

    def _view_popup_rect(self) -> pygame.Rect:
        """牌堆查看浮层的矩形。"""
        return pygame.Rect(WIDTH // 2 - 260, 110, 520, 560)

    def _view_nav_rects(self) -> tuple[pygame.Rect, pygame.Rect]:
        """浮层两侧的上一张/下一张三角形按钮区域。"""
        popup = self._view_popup_rect()
        size = 40
        prev = pygame.Rect(0, 0, size, size)
        prev.midright = (popup.left - 20, popup.centery)
        nxt = pygame.Rect(0, 0, size, size)
        nxt.midleft = (popup.right + 20, popup.centery)
        return prev, nxt

    def _viewer_card_layout(self, idx: int) -> list[tuple[Card, pygame.Rect]]:
        """浮层内牌堆各卡（从上到下）的矩形布局。"""
        pile = self._active_player().pile_slots[idx]
        cards = pile.snapshot_top_to_bottom()
        if not cards:
            return []
        popup = self._view_popup_rect()
        card_w, card_h = 110, 154
        max_display = 6
        start = min(len(cards), max_display)
        offset = 34
        total_h = card_h + (start - 1) * offset
        top = popup.centery - total_h // 2
        result = []
        for i in range(start):
            r = pygame.Rect(0, 0, card_w, card_h)
            r.center = (popup.centerx, top + card_h // 2 + i * offset)
            result.append((cards[i], r))
        return result

    # ---------- 渲染 ----------
    def draw(self) -> None:
        self.screen.fill(BG)
        if self.scene == "menu":
            self._draw_menu()
        elif self.scene == "mode_select":
            self._draw_mode_select()
        elif self.scene == "pvp_setup":
            self._draw_pvp_setup()
        elif self.scene == "pvp_join_setup":
            self._draw_pvp_join_setup()
        elif self.scene == "pvp_wait" or self.scene == "pvp_wait_config":
            self._draw_pvp_wait()
        elif self.scene == "pve_setup":
            self._draw_pve_setup()
        elif self.scene == "pve_join_setup":
            self._draw_pve_join_setup()
        elif self.scene == "pve_wait":
            self._draw_pve_wait()
        elif self.scene == "select":
            self._draw_char_select()
        elif self.scene == "deck_edit":
            self._draw_deck_edit()
        elif self.scene == "enemy_select":
            self._draw_enemy_select()
        elif self.scene == "map":
            self._draw_map_scene()
        elif self.scene == "battle":
            self._draw_battle()
            self._draw_float_texts()
            if self.resolve_anim is not None:
                self._draw_resolution_overlay()
            if self.map_view_active:
                self._draw_map_overlay()
            if self.select_mode:
                self._draw_select_overlay()
            if self.potion_popup_active:
                self._draw_potion_popup()
            if getattr(self, "curse_select", False):
                self._draw_curse_select()
        elif self.scene == "pvp_battle":
            self._draw_pvp_battle()
            if self.pvp_resolving:
                self._draw_pvp_anim_overlay()
            if self.customizing is not None:
                self._draw_weight_popup()
            if self.settings_active:
                self._draw_settings()
        elif self.scene == "reward":
            self._draw_reward()
            if self.enchant_pick_active:
                self._draw_enchant_pick()
        elif self.scene == "result":
            self._draw_result()
        # 控制台覆盖在最上层
        if self.console_active:
            self._draw_console()
        pygame.display.flip()

    # ---------- 遗物栏 ----------
    def _draw_relic_bar(self) -> None:
        """在战斗 HUD 第二行绘制遗物图标栏（含倒计时）。"""
        from game.relics import get_relic_def
        x = 70
        y = 50
        for relic in self.rogue_relics:
            d = get_relic_def(relic.relic_id)
            icon_rect = pygame.Rect(x, y, 32, 32)
            img_path = os.path.join(IMAGES_DIR, d.image) if d and d.image else ""
            if d and d.image and os.path.exists(img_path):
                draw_image_fit(self.screen, img_path, icon_rect)
            else:
                pygame.draw.rect(self.screen, (168, 118, 218), icon_rect, border_radius=6)
                pygame.draw.rect(self.screen, PANEL_EDGE, icon_rect, 1, border_radius=6)
            label = relic.name
            if relic.is_expiring():
                label += f"（剩 {relic.remaining_battles} 场）"
            text = self.font_small.render(label, True, (168, 118, 218))
            self.screen.blit(text, text.get_rect(midleft=(icon_rect.right + 6, icon_rect.centery)))
            x = icon_rect.right + 6 + text.get_width() + 22

    # ---------- 设置菜单 / 头像详情 ----------
    def _draw_settings(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 160, HEIGHT // 2 - 110, 320, 220)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=14)
        title = self.font.render("设置", True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 18)))
        self._layout_settings_buttons()
        self._draw_button(self.settings_back_btn, "返回主菜单", ACCENT)
        self._draw_button(self.settings_exit_btn, "退出游戏", RED)

    def _deck_snapshot(self):
        """返回 (unique: {name->Card}, counter: Counter)，兼容战斗与地图场景。"""
        from collections import Counter
        if self.scene == "battle" and self.engine is not None:
            player = self._active_player()
            all_cards = player.hand + player.draw_pile + player.discard_pile
            for p in player.pile_slots:
                all_cards += p.cards
        else:
            all_cards = list(self.rogue_deck)
        unique: dict[str, Card] = {}
        counter: Counter = Counter()
        for c in all_cards:
            counter[c.name] += 1
            unique[c.name] = c
        return unique, counter

    def _draw_hero_info(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 300, 90, 600, 620)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=14)
        hero = self.hero
        title = self.font_big.render(hero.name, True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 16)))
        # 被动
        passive = self.font_small.render(f"被动：{hero.passive_name}", True, YELLOW)
        self.screen.blit(passive, passive.get_rect(midtop=(box.centerx, box.y + 56)))
        lines = self._wrap_text(hero.passive_desc, box.width - 40)
        y = box.y + 82
        for line in lines:
            surf = self.font_small.render(line, True, TEXT)
            self.screen.blit(surf, surf.get_rect(midtop=(box.centerx, y)))
            y += 20
        # 金币（肉鸽模式）
        if self.mode == "rogue":
            gold = self.font_small.render(f"金币 {self.rogue_gold}", True, YELLOW)
            self.screen.blit(gold, gold.get_rect(midtop=(box.centerx, y)))
            y += 22
        # 遗物列表（肉鸽模式）
        if self.mode == "rogue" and self.rogue_relics:
            y += 6
            relic_title = self.font_small.render("遗物", True, YELLOW)
            self.screen.blit(relic_title, relic_title.get_rect(midtop=(box.centerx, y)))
            y += 22
            for relic in self.rogue_relics:
                count = f"（剩余 {relic.remaining_battles} 场战斗）" if relic.is_expiring() else ""
                line_text = f"{relic.name}{count}"
                surf = self.font_small.render(line_text, True, (168, 118, 218))
                self.screen.blit(surf, surf.get_rect(midtop=(box.centerx, y)))
                y += 20
                for dl in self._wrap_text(relic.description, box.width - 40)[:1]:
                    ds = self.font_small.render(dl, True, MUTED)
                    self.screen.blit(ds, ds.get_rect(midtop=(box.centerx, y)))
                    y += 18
        # 当前牌组（可点击放大）
        deck_title = self.font_small.render("当前牌组（点击卡牌查看描述）", True, MUTED)
        self.screen.blit(deck_title, deck_title.get_rect(midtop=(box.centerx, y + 8)))
        y += 36
        self.hero_info_card_rects = []
        if self.mode == "rogue":
            for name, pe_name, n in self._rogue_deck_rows():
                row_rect = pygame.Rect(box.x + 20, y, box.width - 40, 24)
                color = RED if pe_name else TEXT
                label = f"{name} × {n}" + (f"（{pe_name}）" if pe_name else "")
                row = self.font_small.render(label, True, color)
                self.screen.blit(row, row.get_rect(midleft=(row_rect.x + 6, row_rect.centery)))
                self.hero_info_card_rects.append((self._rogue_deck_card(name, pe_name), row_rect))
                y += 26
        else:
            unique, counter = self._deck_snapshot()
            for name in sorted(counter):
                n = counter[name]
                row_rect = pygame.Rect(box.x + 20, y, box.width - 40, 24)
                row = self.font_small.render(f"{name} × {n}", True, TEXT)
                self.screen.blit(row, row.get_rect(midleft=(row_rect.x + 6, row_rect.centery)))
                self.hero_info_card_rects.append((unique[name], row_rect))
                y += 26
        hint = self.font_small.render("点击卡牌放大查看，点击空白处关闭", True, MUTED)
        self.screen.blit(hint, hint.get_rect(midbottom=(box.centerx, box.bottom - 12)))

        # 放大查看卡牌（当前数值描述）
        if self.hero_info_selected_card is not None:
            self._draw_full_card(self.hero_info_selected_card)

    # ---------- 牌组编辑 ----------
    def _draw_deck_edit(self) -> None:
        hero = self.hero
        title = self.font_big.render(f"{hero.name} 的牌组编辑", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 36)))
        self._draw_button(self.deck_back_btn, "返回", PANEL_EDGE)

        keys = cards_for_hero(hero.key)
        public = set(public_card_keys())

        # 文字列表布局（不显示卡面图）
        cell_w = 560
        cell_h = 88
        gap_x, gap_y = 20, 12
        per_row = 2
        total_w = cell_w * per_row + gap_x * (per_row - 1)
        start_x = (WIDTH - total_w) // 2
        base_y = 80
        row_h = cell_h + gap_y
        rows = (len(keys) + per_row - 1) // per_row
        content_bottom = base_y + rows * row_h
        view_top = base_y
        view_bottom = HEIGHT - 90  # 底部按钮上方
        # 限制滚动范围（内容不滚动出可视区）
        max_scroll = view_bottom - content_bottom
        if max_scroll > 0:
            max_scroll = 0
        self.deck_scroll_max = max_scroll
        self.deck_scroll = max(max_scroll, min(0, self.deck_scroll))
        scroll = self.deck_scroll
        start_y = base_y + scroll

        # 裁剪区域：滚动内容只绘制在可视区内，避免遮住顶部标题/返回键与底部按钮
        clip = pygame.Rect(0, view_top, WIDTH, view_bottom - view_top)
        self.screen.set_clip(clip)

        self.deck_card_rects = []
        for i, key in enumerate(keys):
            row = i // per_row
            col = i % per_row
            x = start_x + col * (cell_w + gap_x)
            y = start_y + row * row_h
            # 跳过完全不可见的行
            if y + cell_h < view_top or y > view_bottom:
                continue
            card = make_card(key)
            count = self.deck_edit.get(key, 0)
            cell = pygame.Rect(x, y, cell_w, cell_h - 16)
            pygame.draw.rect(self.screen, PANEL, cell, border_radius=8)
            pygame.draw.rect(self.screen, PANEL_EDGE, cell, 1, border_radius=8)

            # 卡名（特有卡附角色小头像）
            name = self.font.render(card.name, True, TEXT)
            self.screen.blit(name, name.get_rect(topleft=(x + 12, y + 8)))
            if key not in public:
                owner = get_card_def(key).hero
                owner_hero = get_hero(owner)
                if owner_hero:
                    icon_rect = pygame.Rect(x + cell_w - 34, y + 6, 24, 24)
                    draw_image_fit(
                        self.screen,
                        os.path.join(IMAGES_DIR, char_image_path(owner, "小头像")),
                        icon_rect,
                    )
            # 描述
            desc_lines = self._wrap_text(card.rendered_description, cell_w - 100)
            dy = y + 34
            for line in desc_lines[:1]:
                desc = self.font_small.render(line, True, MUTED)
                self.screen.blit(desc, desc.get_rect(topleft=(x + 12, dy)))
            # 数量 + 按钮
            minus = pygame.Rect(x + cell_w - 90, y + 44, 30, 30)
            plus = pygame.Rect(x + cell_w - 34, y + 44, 30, 30)
            num = self.font.render(str(count), True, TEXT if count > 0 else MUTED)
            self.screen.blit(num, num.get_rect(midright=(minus.left - 8, y + 59)))
            self._draw_button(minus, "-", PANEL_EDGE)
            self._draw_button(plus, "+", ACCENT)
            self.deck_card_rects.append((key, minus, plus))

        self.screen.set_clip(None)

        # 滚动条
        if content_bottom > view_bottom:
            self._draw_scrollbar(view_top, view_bottom, content_bottom)

        # 底部：总数 + 开始按钮
        total = sum(self.deck_edit.values())
        total_surf = self.font.render(f"牌组总数：{total}", True, YELLOW)
        self.screen.blit(total_surf, total_surf.get_rect(midright=(WIDTH - 240, HEIGHT - 45)))
        self._draw_button(self.deck_start_btn, "开始战斗", GREEN)

    def _draw_scrollbar(self, view_top: int, view_bottom: int, content_bottom: int) -> None:
        """在右侧绘制滚动条，并记录几何信息供拖拽。"""
        track = pygame.Rect(WIDTH - 24, view_top, 10, view_bottom - view_top)
        pygame.draw.rect(self.screen, PANEL, track, border_radius=5)
        total_h = content_bottom - view_top
        view_h = view_bottom - view_top
        thumb_h = max(30, int(view_h * view_h / total_h))
        max_scroll = view_bottom - content_bottom
        ratio = self.deck_scroll / max_scroll if max_scroll != 0 else 0.0
        thumb_y = view_top + int((view_h - thumb_h) * ratio)
        thumb = pygame.Rect(WIDTH - 24, thumb_y, 10, thumb_h)
        pygame.draw.rect(self.screen, ACCENT, thumb, border_radius=5)
        # 记录供拖拽命中检测
        self.deck_scroll_track = track
        self.deck_scroll_thumb = thumb

    def _scrollbar_click(self, pos: tuple[int, int]) -> bool:
        """检测是否点中滚动条 thumb，是则开始拖拽并返回 True。"""
        if self.deck_scroll_thumb.collidepoint(pos):
            self.dragging_scrollbar = True
            return True
        # 点轨道：跳到对应位置
        if self.deck_scroll_track.collidepoint(pos):
            self._scrollbar_set_by_pos(pos)
            self.dragging_scrollbar = True
            return True
        return False

    def _scrollbar_set_by_pos(self, pos: tuple[int, int]) -> None:
        """根据鼠标 y 位置设置滚动偏移（点轨道 / 拖拽共用）。"""
        track = self.deck_scroll_track
        if track.height <= 0:
            return
        view_h = track.height
        thumb_h = self.deck_scroll_thumb.height
        if view_h - thumb_h <= 0:
            self.deck_scroll = 0
            return
        ratio = (pos[1] - track.y - thumb_h / 2) / (view_h - thumb_h)
        ratio = max(0.0, min(1.0, ratio))
        self.deck_scroll = int(self.deck_scroll_max * ratio)

    # ---------- 主菜单 / 选角色 ----------
    def _draw_menu(self) -> None:
        title = self.font_title.render("土豆尖塔", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 200)))
        subtitle = self.font_small.render("Potatospire", True, MUTED)
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 264)))
        self._draw_button(self.menu_start_btn, "开始游戏", ACCENT)
        self._draw_button(self.menu_pvp_btn, "PVP 模式", (168, 118, 218))
        self._draw_button(self.menu_quit_btn, "退出", RED)
        # 底部版本号
        ver = self.font_small.render(f"版本 {VERSION}", True, MUTED)
        self.screen.blit(ver, ver.get_rect(midbottom=(WIDTH // 2, HEIGHT - 12)))

    def _draw_result(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, (0, 0))
        if self.game_result == "victory":
            title = self.font_title.render("通关！" if self.mode == "rogue" else "胜利！", True, GREEN)
            img_kind = "成功"
        else:
            title = self.font_title.render("失败…", True, RED)
            img_kind = "失败"
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))
        # 角色结算图片（成功/失败）
        if self.hero is not None:
            img_path = os.path.join(IMAGES_DIR, char_image_path(self.hero.name, img_kind))
            img_area = pygame.Rect(WIDTH // 2 - 200, 180, 400, 320)
            draw_image_fit(self.screen, img_path, img_area)
        self._draw_button(self.result_ok_btn, "返回主菜单", ACCENT)
        hint = self.font_small.render("点击返回主菜单", True, MUTED)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 545)))

    # ---------- 战斗奖励 ----------
    def _draw_reward(self) -> None:
        """战斗奖励：战利品弹窗（金币/遗物/药水/卡牌），点击继续才领取。"""
        self.screen.fill(BG)
        if self.reward_stage == "cards":
            self._draw_reward_cards()
            return
        # 中间战利品弹窗
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 320, 100, 640, 600)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=16)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=16)
        title = self.font_big.render("战斗奖励", True, YELLOW)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 24)))
        # 战利品条目
        y = box.y + 96
        entries = [f"金币 × {self.reward_gold}"]
        if self.reward_relic is not None:
            entries.append(f"遗物「{make_relic(self.reward_relic).name}」")
        if self.reward_potion is not None:
            entries.append(f"药水「{make_potion(self.reward_potion).name}」")
        if self.reward_chosen_key is not None:
            entries.append(f"卡牌「{make_card(self.reward_chosen_key).name}」")
        for line in entries:
            surf = self.font.render(line, True, TEXT)
            self.screen.blit(surf, surf.get_rect(midtop=(box.centerx, y)))
            y += 40
        # 选择卡牌入口
        self.reward_card_pick_btn.center = (box.centerx, y + 26)
        if self.reward_chosen_key is None:
            self._draw_button(self.reward_card_pick_btn, "选择一张卡牌", ACCENT)
        else:
            chosen = self.font_small.render("已选择卡牌", True, GREEN)
            self.screen.blit(chosen, chosen.get_rect(center=(box.centerx, y + 26)))
        # 继续键（弹窗右下角）
        self.reward_continue_btn.midbottom = (box.centerx, box.bottom - 24)
        self._draw_button(self.reward_continue_btn, "继续", GREEN)

    def _draw_reward_cards(self) -> None:
        """卡牌三选一子页面（含跳过键）。"""
        self.screen.fill(BG)
        title = self.font.render("选择一张卡牌加入牌组", True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(WIDTH // 2, 70)))
        self.reward_card_rects = []
        cw, ch = 200, 280
        gap = 40
        total = cw * len(self.reward_cards) + gap * (len(self.reward_cards) - 1)
        x = (WIDTH - total) // 2
        cy = 150
        for key in self.reward_cards:
            card = make_card(key)
            rect = pygame.Rect(x, cy, cw, ch)
            self._draw_card(rect, card, selected=False)
            self.reward_card_rects.append((key, rect))
            x += cw + gap
        self.reward_skip_btn.midtop = (WIDTH // 2, cy + ch + 40)
        self._draw_button(self.reward_skip_btn, "跳过", RED)

    # ---------- 模式选择 / 敌方自选 ----------
    def _draw_mode_select(self) -> None:
        title = self.font_big.render("选择模式", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))
        self._draw_button(self.mode_back_btn, "返回", PANEL_EDGE)
        self._draw_button(self.mode_sim_btn, "战斗模拟", ACCENT)
        sim_hint = self.font_small.render("自由选择角色与敌人，单局对战", True, MUTED)
        self.screen.blit(sim_hint, sim_hint.get_rect(midtop=(WIDTH // 2, self.mode_sim_btn.bottom + 6)))
        self._draw_button(self.mode_rogue_btn, "肉鸽模式", (168, 118, 218))
        rogue_hint = self.font_small.render("三层地图探索，侦查路线，挑战 Boss", True, MUTED)
        self.screen.blit(rogue_hint, rogue_hint.get_rect(midtop=(WIDTH // 2, self.mode_rogue_btn.bottom + 6)))
        self._draw_button(self.mode_pve_btn, "多人 PVE", (110, 200, 150))
        pve_hint = self.font_small.render("局域网合作打怪，最多 4 人", True, MUTED)
        self.screen.blit(pve_hint, pve_hint.get_rect(midtop=(WIDTH // 2, self.mode_pve_btn.bottom + 6)))

    # ---------- PVP 设置 ----------
    def _draw_pvp_setup(self) -> None:
        title = self.font_big.render("PVP 模式", True, (168, 118, 218))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 90)))
        self._draw_button(self.pvp_setup_back_btn, "返回", PANEL_EDGE)

        # 血量乘数
        mult_label = self.font.render("角色最大生命值乘数 X", True, TEXT)
        self.screen.blit(mult_label, mult_label.get_rect(center=(WIDTH // 2, 200)))
        self._draw_button(self.pvp_mult_minus, "-", PANEL_EDGE)
        self._draw_button(self.pvp_mult_plus, "+", PANEL_EDGE)
        mult_val = self.font_big.render(f"{self.pvp_hp_mult:.1f}", True, YELLOW)
        self.screen.blit(mult_val, mult_val.get_rect(center=(WIDTH // 2, 242)))

        # 配牌数量范围
        deckmin_label = self.font.render("配牌数量下限", True, TEXT)
        self.screen.blit(deckmin_label, deckmin_label.get_rect(center=(WIDTH // 2 - 90, 290)))
        self._draw_button(self.pvp_deckmin_minus, "-", PANEL_EDGE)
        self._draw_button(self.pvp_deckmin_plus, "+", PANEL_EDGE)
        deckmin_val = self.font_big.render(str(self.pvp_deck_min), True, TEXT)
        self.screen.blit(deckmin_val, deckmin_val.get_rect(center=(WIDTH // 2 + 90, 290)))

        deckmax_label = self.font.render("配牌数量上限", True, TEXT)
        self.screen.blit(deckmax_label, deckmax_label.get_rect(center=(WIDTH // 2 - 90, 330)))
        self._draw_button(self.pvp_deckmax_minus, "-", PANEL_EDGE)
        self._draw_button(self.pvp_deckmax_plus, "+", PANEL_EDGE)
        deckmax_val = self.font_big.render(str(self.pvp_deck_max), True, TEXT)
        self.screen.blit(deckmax_val, deckmax_val.get_rect(center=(WIDTH // 2 + 90, 330)))

        # 创建房间（本地 / 局域网）/ 加入
        self._draw_button(self.pvp_host_btn, "本地联机（创建房间）", GREEN)
        self._draw_button(self.pvp_host_lan_btn, "局域网联机（创建房间）", (90, 150, 220))
        self._draw_button(self.pvp_join_btn, "加入局域网房间", (168, 118, 218))

    def _draw_pvp_join_setup(self) -> None:
        """访客输入房主 IP 的界面。"""
        self.screen.fill(BG)
        title = self.font_big.render("加入局域网房间", True, (168, 118, 218))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))
        self._draw_button(self.pvp_join_back_btn, "返回", PANEL_EDGE)
        hint = self.font.render("输入房主 IP 地址", True, TEXT)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 210)))
        # 输入框
        pygame.draw.rect(self.screen, (24, 26, 34), self.pvp_join_input_rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_EDGE, self.pvp_join_input_rect, 2, border_radius=8)
        ip_text = self.pvp_join_ip if self.pvp_join_ip else "（例如 192.168.1.100）"
        color = TEXT if self.pvp_join_ip else MUTED
        surf = self.font_big.render(ip_text, True, color)
        self.screen.blit(surf, surf.get_rect(midleft=(self.pvp_join_input_rect.x + 16, self.pvp_join_input_rect.centery)))
        port_label = self.font.render(f"端口 {self.pvp_join_port}", True, MUTED)
        self.screen.blit(port_label, port_label.get_rect(center=(WIDTH // 2, 330)))
        self._draw_button(self.pvp_join_confirm_btn, "连接", GREEN)

    def _draw_pvp_wait(self) -> None:
        """PVP 等待界面：等待对手配牌 / 就绪。"""
        self.screen.fill(BG)
        title = self.font_big.render("PVP 对战", True, (168, 118, 218))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 300)))
        hint = self.font.render("等待对手完成配牌…", True, TEXT)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 380)))
        if self.pvp_role == "host":
            if self.pvp_subprocess is not None:
                sub = self.font_small.render(
                    f"本地房间已开放（访客窗口已启动）", True, MUTED
                )
            else:
                sub = self.font_small.render(
                    f"局域网房间已开放：{self.pvp_local_ip}:{self.pvp_join_port}", True, YELLOW
                )
            self.screen.blit(sub, sub.get_rect(center=(WIDTH // 2, 420)))

    # ---------- 多人 PVE 流程 ----------
    def _handle_pve_setup_click(self, pos: tuple[int, int]) -> None:
        if self.pve_setup_back_btn.collidepoint(pos):
            self.scene = "mode_select"
            self.mode = None
            return
        if self.pve_host_btn.collidepoint(pos):
            self._pve_host_create()
            return
        if self.pve_join_btn.collidepoint(pos):
            self.scene = "pve_join_setup"
            return
        # 房主选敌人（host 模式下显示）
        if self.pve_enemy_prev_btn.collidepoint(pos):
            idx = self._pve_enemy_idx()
            idx = (idx - 1) % len(self._pve_enemy_pool())
            self.pve_enemy_names = [self._pve_enemy_pool()[idx]]
        elif self.pve_enemy_next_btn.collidepoint(pos):
            idx = self._pve_enemy_idx()
            idx = (idx + 1) % len(self._pve_enemy_pool())
            self.pve_enemy_names = [self._pve_enemy_pool()[idx]]

    def _handle_pve_join_click(self, pos: tuple[int, int]) -> None:
        if self.pve_join_back_btn.collidepoint(pos):
            self.scene = "pve_setup"
            return
        if self.pve_join_confirm_btn.collidepoint(pos) and self.pve_join_ip:
            self._pve_guest_join(self.pve_join_ip.strip())

    def _pve_enemy_pool(self) -> list[str]:
        from game.enemy import enemy_names
        return enemy_names()

    def _pve_enemy_idx(self) -> int:
        pool = self._pve_enemy_pool()
        name = self.pve_enemy_names[0] if self.pve_enemy_names else ""
        if name in pool:
            return pool.index(name)
        return 0

    def _pve_host_create(self) -> None:
        from game.net import get_local_ip
        from game.pve_net import PveSession

        session = PveSession(role="host", enemy_names=list(self.pve_enemy_names))
        self.pve_session = session
        # 端口自动分配（0 = 系统分配空闲端口）
        self.pve_port = session.host_listen(0)
        self.pve_role = "host"
        self.pve_local_ip = get_local_ip()
        self.pve_my_hero = None
        self.scene = "select"

    def _pve_guest_join(self, host_input: str) -> None:
        from game.pve_net import PveSession

        host = host_input.strip()
        port = 0
        if ":" in host:
            host, port_s = host.rsplit(":", 1)
            try:
                port = int(port_s)
            except ValueError:
                port = 0
        session = PveSession(role="client")
        self.pve_session = session
        self.pve_role = "guest"
        if session.client_connect(host, port):
            self.pve_my_hero = None
            self.scene = "select"
        else:
            self.scene = "pve_join_setup"

    def _pve_pick_hero(self, hero: HeroDef) -> None:
        self.pve_my_hero = hero
        self.pve_deck = dict(hero.deck)
        if self.pve_role == "host":
            self.scene = "pve_wait"
        else:
            self.pve_session.client_send_join(hero.key, dict(hero.deck))
            self.scene = "pve_wait"

    def _pve_host_start(self) -> None:
        session = self.pve_session
        if session is None or self.pve_my_hero is None:
            return
        match = session.host_start_match(self.pve_my_hero.key, self.pve_deck)
        self._pve_enter_battle()

    def _pve_enter_battle(self) -> None:
        session = self.pve_session
        my_idx = session.my_index
        engine = session.match.engines[my_idx]
        self.engine = engine
        self.hero = self.pve_my_hero or get_hero(session.match.players[my_idx].name)
        self.battle_context = "pve"
        self.scene = "battle"
        self._reset_battle_ui()
        self.disp_hp = {"self": float(engine.state.player.hp)}
        self.disp_block = {"self": float(engine.state.player.block)}
        for i, e in enumerate(session.match.enemies):
            self.disp_hp[f"enemy{i}"] = float(e.hp)
            self.disp_block[f"enemy{i}"] = float(e.block)

    def _pve_end_turn(self) -> None:
        session = self.pve_session
        if session is None or session.match is None:
            return
        my_idx = session.my_index
        player = session.match.players[my_idx]
        player.discard_pile.extend(player.hand)
        player.hand.clear()
        if self.pve_role == "host":
            session.match.ready_flags[my_idx] = True
        else:
            session.client_send_action([cards_to_list(p.cards) for p in player.pile_slots])

    def _pve_poll(self) -> None:
        if self.pve_session is None:
            return
        events = self.pve_session.handle_messages()
        for ev in events:
            t = ev.get("type")
            if t == "config":
                pass
            elif t == "start":
                if self.scene == "pve_wait" or self.pve_role == "guest":
                    self._pve_enter_battle()
            elif t == "join":
                pass
            elif t == "state":
                pass
        # 房主：全员就绪后结算并广播
        session = self.pve_session
        if session.role == "host" and session.match_started and session.match is not None:
            if session.match.all_ready() and session.match.winner is None:
                session.match.resolve_round()
                session.host_broadcast_state()
        # 胜负显示（房主结算后 / 访客收到 state 后）
        if session.match is not None and session.match.winner is not None:
            if self.scene == "battle":
                self.game_result = "victory" if session.match.winner else "defeat"
                self.scene = "result"

    def _pve_cleanup(self) -> None:
        if self.pve_session is not None:
            self.pve_session.close()
            self.pve_session = None
        self.pve_role = ""
        self.pve_my_hero = None
        self.pve_ready = False

    def _draw_pve_setup(self) -> None:
        self.screen.fill(BG)
        title = self.font_big.render("多人 PVE", True, (110, 200, 150))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 100)))
        self._draw_button(self.pve_setup_back_btn, "返回", PANEL_EDGE)
        self._draw_button(self.pve_host_btn, "创建房间（房主）", (110, 200, 150))
        self._draw_button(self.pve_join_btn, "加入局域网房间", (110, 160, 210))
        # 敌人选择（房主配置）
        enemy_label = self.font.render("敌人（房主选定）：", True, TEXT)
        self.screen.blit(enemy_label, enemy_label.get_rect(center=(WIDTH // 2, 400)))
        name = self.pve_enemy_names[0] if self.pve_enemy_names else ""
        enemy_name = self.font_big.render(name, True, YELLOW)
        self.screen.blit(enemy_name, enemy_name.get_rect(center=(WIDTH // 2, 442)))
        self._draw_button(self.pve_enemy_prev_btn, "‹", PANEL_EDGE)
        self._draw_button(self.pve_enemy_next_btn, "›", PANEL_EDGE)

    def _draw_pve_join_setup(self) -> None:
        self.screen.fill(BG)
        title = self.font_big.render("加入 PVE 房间", True, (110, 160, 210))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))
        self._draw_button(self.pve_join_back_btn, "返回", PANEL_EDGE)
        hint = self.font.render("输入房主地址（IP 或 IP:端口）", True, TEXT)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 210)))
        pygame.draw.rect(self.screen, (24, 26, 34), self.pve_join_input_rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_EDGE, self.pve_join_input_rect, 2, border_radius=8)
        ip_text = self.pve_join_ip if self.pve_join_ip else "（例如 192.168.1.100:5000）"
        color = TEXT if self.pve_join_ip else MUTED
        surf = self.font_big.render(ip_text, True, color)
        self.screen.blit(surf, surf.get_rect(midleft=(self.pve_join_input_rect.x + 16, self.pve_join_input_rect.centery)))
        self._draw_button(self.pve_join_confirm_btn, "连接", (110, 200, 150))

    def _draw_pve_wait(self) -> None:
        self.screen.fill(BG)
        title = self.font_big.render("多人 PVE", True, (110, 200, 150))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 300)))
        if self.pve_role == "host":
            session = self.pve_session
            n = len(session.server.framings) + 1 if session and session.server else 1
            hint = self.font.render(
                f"等待玩家加入（当前 {n}/4）… 房间 {self.pve_local_ip}:{self.pve_port}",
                True, TEXT,
            )
            self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 380)))
            if self.pve_my_hero is not None:
                self._draw_button(self.pve_start_btn, "开始游戏", (110, 200, 150))
        else:
            hint = self.font.render("已连接，等待房主开始…", True, TEXT)
            self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 380)))
        self._draw_button(self.pve_setup_back_btn, "返回", PANEL_EDGE)

    # ---------- PVP 流程 ----------
    def _pvp_host_create(self, lan: bool = False) -> None:
        """房主：创建房间并（可选）启动访客子进程。"""
        import subprocess
        import sys
        from game.net import get_local_ip
        from game.pvp_net import PvpSession

        session = PvpSession(role="host", hp_multiplier=self.pvp_hp_mult,
                             deck_min=self.pvp_deck_min, deck_max=self.pvp_deck_max)
        self.pvp_session = session
        self.pvp_port = session.host_listen(self.pvp_join_port)
        self.pvp_role = "host"
        self.mode = "pvp"
        if lan:
            # 局域网：不启动本地访客，显示本机 IP
            self.pvp_local_ip = get_local_ip()
            self.pvp_subprocess = None
        else:
            # 本地：启动访客子进程（第二个窗口）
            self.pvp_subprocess = subprocess.Popen(
                [sys.executable, os.path.join(ROOT, "main.py"), "--pvp-guest", str(self.pvp_port)],
                cwd=ROOT,
            )
        # 自己进入选角色
        self.scene = "select"

    def _pvp_guest_join(self, port: int, host: str = "127.0.0.1") -> None:
        """访客：连接房主，等待配置。"""
        from game.pvp_net import PvpSession

        session = PvpSession(role="client")
        self.pvp_session = session
        self.pvp_role = "guest"
        self.mode = "pvp"
        if session.client_connect(host, port):
            self.scene = "pvp_wait_config"
        else:
            self.scene = "menu"

    def _pvp_finalize_deck(self) -> None:
        """选好角色与牌组后，上报并进入等待。"""
        from game.pvp_net import PvpSession

        session: PvpSession = self.pvp_session
        hero_key = self.hero.key
        deck = dict(self.deck_edit)
        self.pvp_my_hero = self.hero
        self.pvp_deck = deck
        if session.role == "host":
            # 房主本地存自己的牌组，等访客 deck_ready
            session.my_ready = True
            # 房主自己的牌组暂存在 session 里
            session._host_hero_key = hero_key
            session._host_deck = deck
            self.scene = "pvp_wait"
        else:
            session.client_send_deck(hero_key, deck)
            self.scene = "pvp_wait"

    def _pvp_poll(self) -> None:
        """每帧轮询网络消息，推进 PVP 状态机。"""
        if self.pvp_session is None:
            return
        from game.pvp_net import PvpSession
        session: PvpSession = self.pvp_session

        # 房主：接受访客连接
        if session.role == "host" and session.net_server and not session.match_started:
            if session.net_server.conn is None:
                session.host_accept(timeout=0)
                if session.net_server.conn is not None:
                    session.host_send_config()

        events = session.handle_messages()

        for ev in events:
            t = ev.get("type")
            if t == "config":
                self.pvp_hp_mult = session.hp_multiplier
                self.pvp_deck_min = session.deck_min
                self.pvp_deck_max = session.deck_max
                if self.scene == "pvp_wait_config":
                    self.scene = "select"
            elif t == "deck_ready":
                self.pvp_peer_hero = ev.get("hero_key", "")
            elif t == "match_start":
                self._pvp_enter_battle()
            elif t == "action":
                self.pvp_peer_ready = True

        # 房主：双方牌组都就绪后开赛（不依赖消息到达顺序，避免双方互相等待）
        if (
            session.role == "host"
            and not session.match_started
            and getattr(session, "_host_deck", None) is not None
            and session.peer_deck is not None
        ):
            session.host_start_match(getattr(session, "_host_hero_key"), session._host_deck)
            self._pvp_enter_battle()

        # 双方都就绪后，各自在本地结算（确定性，结果一致，无需广播）
        if self.pvp_ready and self.pvp_peer_ready:
            self._pvp_resolve_local()

    def _pvp_enter_battle(self) -> None:
        """进入 PVP 战斗场景。"""
        session = self.pvp_session
        self.scene = "pvp_battle"
        # 指向自己的 engine（复用现有拖拽/绘制逻辑）
        my_idx = session.my_index
        my_engine = session.match.engine(my_idx)
        self.engine = my_engine
        self.hero = self.pvp_my_hero or get_hero(session.match.player(my_idx).name)
        self._reset_battle_ui()
        # 重置回合就绪标志（配牌阶段的 peer_ready 不能带进战斗）
        self.pvp_ready = False
        self.pvp_peer_ready = False
        session.my_ready = False
        session.peer_ready = False
        self.disp_hp = {
            "self": float(my_engine.state.player.hp),
            "enemy": float(my_engine.state.enemy.hp),
        }
        self.disp_block = {
            "self": float(my_engine.state.player.block),
            "enemy": float(my_engine.state.enemy.block),
        }

    def _pvp_resolve_local(self) -> None:
        """双方各自在本地结算整回合（确定性），并启动结算动画。"""
        session = self.pvp_session
        if session is None or session.match is None:
            return
        session.resolve_local()
        # 更新本地状态
        self.pvp_last_order = list(session.match.order)
        self.pvp_winner = session.match.winner
        self.pvp_ready = False
        self.pvp_peer_ready = False
        my_idx = session.my_index
        self.engine = session.match.engine(my_idx)
        p = session.match.player(my_idx)
        opp = session.match.player(3 - my_idx)
        self.disp_hp = {"self": float(p.hp), "enemy": float(opp.hp)}
        self.disp_block = {"self": float(p.block), "enemy": float(opp.block)}
        # 启动结算动画（从本地 match.last_animations 读取）
        if session.match.last_animations:
            self._pvp_start_animations(session.match.last_animations)

    def _pvp_start_animations(self, anims: list[dict]) -> None:
        """启动结算动画序列。"""
        self.pvp_anims = anims
        self.pvp_anim_index = 0
        self.pvp_anim_t = 0.0
        self.pvp_anim_phase = "fly1"  # fly1（来源→中间）→ hold → fly2（中间→目标）→ effect
        self.pvp_effect_timer = 0
        self.pvp_hold_timer = 0
        self.pvp_resolving = bool(anims)

    def _pvp_update_anim(self) -> None:
        """每帧推进 PVP 结算动画。"""
        if not self.pvp_resolving:
            return
        if self.pvp_anim_index >= len(self.pvp_anims):
            self.pvp_resolving = False
            self.pvp_anims = []
            return
        if self.pvp_anim_phase == "fly1":
            self.pvp_anim_t += 1.0 / FLY_FRAMES
            if self.pvp_anim_t >= 1.0:
                self.pvp_anim_phase = "hold"
                self.pvp_hold_timer = HOLD_FRAMES
        elif self.pvp_anim_phase == "hold":
            self.pvp_hold_timer -= 1
            if self.pvp_hold_timer <= 0:
                self.pvp_anim_phase = "fly2"
                self.pvp_anim_t = 0.0
        elif self.pvp_anim_phase == "fly2":
            self.pvp_anim_t += 1.0 / FLY_FRAMES
            if self.pvp_anim_t >= 1.0:
                self.pvp_anim_phase = "effect"
                self.pvp_effect_timer = EFFECT_FRAMES
        elif self.pvp_anim_phase == "effect":
            self.pvp_effect_timer -= 1
            if self.pvp_effect_timer <= 0:
                self.pvp_anim_index += 1
                self.pvp_anim_t = 0.0
                self.pvp_anim_phase = "fly1"

    def _draw_pvp_anim_overlay(self) -> None:
        """绘制 PVP 结算动画（双方牌依次飞出 + 效果文字）。"""
        if not self.pvp_resolving or self.pvp_anim_index >= len(self.pvp_anims):
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        self.screen.blit(overlay, (0, 0))

        anim = self.pvp_anims[self.pvp_anim_index]
        card = anim["card"]
        source = anim["source"]
        my_idx = self.pvp_session.my_index
        # 来源/目标：source == my_idx（我方，右侧）→ 对手（左侧）；否则反向
        if source == my_idx:
            src = self.player_area.center
            dst = self.enemy_area.center
        else:
            src = self.enemy_area.center
            dst = self.player_area.center
        center = (WIDTH // 2, HEIGHT // 2)

        if self.pvp_anim_phase in ("fly1", "hold", "fly2"):
            if self.pvp_anim_phase == "fly1":
                t = self.pvp_anim_t
                x = src[0] + (center[0] - src[0]) * t
                y = src[1] + (center[1] - src[1]) * t
            elif self.pvp_anim_phase == "hold":
                x, y = center
            else:  # fly2
                t = self.pvp_anim_t
                x = center[0] + (dst[0] - center[0]) * t
                y = center[1] + (dst[1] - center[1]) * t
            r = pygame.Rect(0, 0, CARD_W, CARD_H)
            r.center = (int(x), int(y))
            self._draw_card(r, card, selected=True)
        elif self.pvp_anim_phase == "effect":
            text = anim["text"]
            if text:
                surf = self.font_big.render(text, True, YELLOW)
                bg = pygame.Surface(
                    (surf.get_width() + 40, surf.get_height() + 24), pygame.SRCALPHA
                )
                bg.fill((0, 0, 0, 190))
                self.screen.blit(bg, (center[0] - bg.get_width() // 2, center[1] - bg.get_height() // 2))
                self.screen.blit(surf, surf.get_rect(center=center))

    def _pvp_end_turn(self) -> None:
        """结束本回合：弃手牌、上报牌堆、标记就绪。"""
        session = self.pvp_session
        if session is None or session.match is None:
            return
        my_idx = session.my_index
        player = session.match.player(my_idx)
        # 弃掉剩余手牌
        player.discard_pile.extend(player.hand)
        player.hand.clear()
        # 上报牌堆布局
        piles = [pile.cards for pile in player.pile_slots]
        session.submit_piles(piles)
        self.pvp_ready = True

    # ---------- PVP 战斗绘制 ----------
    def _draw_pvp_battle(self) -> None:
        session = self.pvp_session
        if session is None or session.match is None:
            return
        my_idx = session.my_index
        me = session.match.player(my_idx)
        opp = session.match.player(3 - my_idx)

        # 顶部 HUD
        pygame.draw.rect(self.screen, PANEL, (0, 0, WIDTH, 64))
        pygame.draw.line(self.screen, PANEL_EDGE, (0, 64), (WIDTH, 64), 1)
        # 头像
        if me.icon:
            draw_image_fit(self.screen, os.path.join(IMAGES_DIR, me.icon), self.hero_icon_btn)
        else:
            pygame.draw.rect(self.screen, SLOT_BG, self.hero_icon_btn, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT, self.hero_icon_btn, 2, border_radius=8)
        # 先手顺序提示
        order_text = ""
        if self.pvp_last_order:
            names = {1: session.match.hero_name_1, 2: session.match.hero_name_2}
            order_text = "上回合先手：" + " → ".join(names[i] for i in self.pvp_last_order)
        ready_text = "已结束回合" if self.pvp_ready else "进行中"
        peer_text = "对手已结束" if self.pvp_peer_ready else "等待对手"
        hud = (
            f"回合 {session.match.turn}  |  我的负重 {sum(c.weight for p in me.pile_slots for c in p.cards)}"
            f"  |  {ready_text}  |  {peer_text}"
        )
        self.screen.blit(self.font.render(hud, True, TEXT), (70, 12))
        if order_text:
            self.screen.blit(self.font_small.render(order_text, True, YELLOW), (70, 40))
        self._draw_button(self.skip_btn, "结束回合", ACCENT)
        self._draw_button(self.quit_btn, "设置", RED)

        # 对手（左侧，镜像）
        self._draw_character_panel(
            self.enemy_area, opp.image, f"对手（{opp.name}）", RED,
            opp.hp, opp.max_hp, opp.active_statuses(), opp.block, flip=True,
            disp_hp=self.disp_hp["enemy"], disp_block=self.disp_block["enemy"],
        )
        # 我方（右侧）
        self._draw_character_panel(
            self.player_area, me.image, f"我方（{me.name}）", ACCENT,
            me.hp, me.max_hp, me.active_statuses(), me.block,
            disp_hp=self.disp_hp["self"], disp_block=self.disp_block["self"],
        )

        # 牌堆槽位
        for i, rect in enumerate(self.slot_rects):
            active = i < me.max_slots
            self._draw_slot(rect, i, active, hovered=(i == self.hover_slot))

        # 日志（先画，避免遮挡手牌）
        self._draw_log()

        # 手牌
        self.layout_hand()
        for i, rect in enumerate(self.hand_rects):
            if i == self.dragging:
                self._draw_card_placeholder(rect)
                continue
            card = me.hand[i]
            if i == self.hand_hover:
                full = pygame.Rect(rect.x, rect.bottom - CARD_H, CARD_W, CARD_H)
                self._draw_card(full, card, selected=False)
            else:
                self._draw_folded_card(rect, card)
        if not self.hand_rects:
            msg = self.font.render("（手牌为空，点击「结束回合」）", True, MUTED)
            self.screen.blit(msg, msg.get_rect(center=(WIDTH // 2, HEIGHT - 80)))
        if self.dragging is not None and self.dragging < len(me.hand):
            card = me.hand[self.dragging]
            drag_rect = pygame.Rect(0, 0, CARD_W, CARD_H)
            drag_rect.center = self.drag_pos
            self._draw_card(drag_rect, card, selected=True)

        # 牌堆查看浮层
        if self.viewing_pile is not None:
            self._draw_pile_viewer(self.viewing_pile)

        # 胜负
        if session.match.winner is not None:
            self._draw_pvp_result()

    def _draw_pvp_result(self) -> None:
        session = self.pvp_session
        w = session.match.winner
        my_idx = session.my_index
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        if w == 0:
            title = self.font_title.render("平局！", True, YELLOW)
        elif w == my_idx:
            title = self.font_title.render("胜利！", True, GREEN)
        else:
            title = self.font_title.render("失败…", True, RED)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40)))
        hint = self.font.render("点击返回主菜单", True, MUTED)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30)))

    def _handle_pvp_mouse_down(self, pos: tuple[int, int]) -> None:
        """PVP 战斗场景的鼠标按下。"""
        session = self.pvp_session
        if session is None or session.match is None:
            return
        # 结算动画播放中：屏蔽交互
        if self.pvp_resolving:
            return
        # 胜负界面：点击返回主菜单
        if session.match.winner is not None:
            self._pvp_cleanup()
            self.scene = "menu"
            self.mode = None
            return
        if self.settings_active:
            self._handle_settings_click(pos)
            return
        if self.customizing is not None:
            self._handle_weight_popup_click(pos)
            return
        if self.viewing_pile is not None:
            self._handle_viewer_click(pos)
            return
        if self.quit_btn.collidepoint(pos):
            self.settings_active = True
            return
        if self.skip_btn.collidepoint(pos):
            self._pvp_end_turn()
            return
        if self.hero_icon_btn.collidepoint(pos):
            self.hero_info_active = True
            return
        for slot_idx, rect in enumerate(self.slot_rects):
            if rect.collidepoint(pos):
                self.viewing_pile = slot_idx
                self.viewer_selected_card = None
                return
        hand_idx = self._hand_index_at(pos)
        if hand_idx is not None:
            self.dragging = hand_idx
            self.hand_hover = None
            self.drag_pos = pos
            self.hover_slot = self._slot_at(pos)
            return

    def _handle_pvp_mouse_up(self, pos: tuple[int, int]) -> None:
        if self.pvp_resolving:
            self._end_drag()
            return
        """PVP 战斗场景的鼠标释放（拖牌放牌）。"""
        if self.dragging is None:
            return
        slot = self._slot_at(pos)
        hand_index = self.dragging
        session = self.pvp_session
        player = session.match.player(session.my_index)
        if hand_index < len(player.hand):
            card = player.hand[hand_index]
            if slot is not None and card.customizable_weight:
                self.pending_hand_index = hand_index
                self.pending_slot = slot
                self.custom_weight = max(1, min(10, card.weight))
                self.customizing = card
                self._end_drag()
                return
        if slot is not None:
            self.engine.add_card_to_pile(hand_index, slot)
        self._end_drag()

    def _pvp_cleanup(self) -> None:
        """关闭 PVP 会话与访客子进程。"""
        if self.pvp_session is not None:
            self.pvp_session.close()
            self.pvp_session = None
        if self.pvp_subprocess is not None:
            try:
                self.pvp_subprocess.terminate()
            except Exception:
                pass
            self.pvp_subprocess = None
        self.pvp_role = ""
        self.pvp_ready = False
        self.pvp_peer_ready = False
        self.pvp_last_order = []
        self.pvp_winner = None

    # 必须同时出现的敌人组合（不能在自选中单独选）
    _DUO_ENEMIES = ("大嗓门", "练家子")
    _DUO_LABEL = "大嗓门 & 练家子"

    @staticmethod
    def _ensure_warden_guard(enemies) -> None:
        """典狱长出场时自带一个看守（若列表里还没有看守则补一个）。"""
        if any(e.name == "典狱长" for e in enemies) and not any(e.name == "看守" for e in enemies):
            enemies.append(make_enemy("看守"))

    # 自选界面分类：Boss 按层标注（I/II/III），精英怪用紫色底
    _BOSS_FLOORS = {
        "墨影幻灵": 1, "海盗王噶呜": 1, "科学怪呜": 1,
        "典狱长": 2, "看守": 2,
    }
    _ELITE_ENEMIES = {"劣人杀手", "多伦斯异鸟", "旧日雕像", "迎宾雁", "大嗓门 & 练家子"}

    def _enemy_select_entries(self) -> list[str]:
        """自选战斗的敌人条目：双人组合不可单独选，合并为一个组合项。"""
        names = [n for n in enemy_names() if n not in self._DUO_ENEMIES]
        names.append(self._DUO_LABEL)
        return names

    def _layout_enemy_select(self) -> None:
        names = self._enemy_select_entries()
        # 网格布局：3 列，适应更多敌人
        cw, ch = 360, 80
        gap_x, gap_y = 20, 16
        cols = 3
        start_y = 160
        total_w = cw * cols + gap_x * (cols - 1)
        start_x = (WIDTH - total_w) // 2
        self.enemy_select_rects = []
        for i, name in enumerate(names):
            row = i // cols
            col = i % cols
            x = start_x + col * (cw + gap_x)
            y = start_y + row * (ch + gap_y)
            rect = pygame.Rect(x, y, cw, ch)
            self.enemy_select_rects.append((name, rect))

    def _draw_enemy_select(self) -> None:
        title = self.font_big.render("选择敌人（战斗模拟）", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 100)))
        self._draw_button(self.enemy_select_back_btn, "返回", PANEL_EDGE)
        self._layout_enemy_select()
        roman = {1: "I", 2: "II", 3: "III"}
        for name, rect in self.enemy_select_rects:
            floor = self._BOSS_FLOORS.get(name)
            is_elite = name in self._ELITE_ENEMIES
            if floor is not None:
                bg, edge = (196, 60, 60), (240, 110, 110)      # Boss：红色
            elif is_elite:
                bg, edge = (150, 90, 200), (196, 140, 236)      # 精英：紫色
            else:
                bg, edge = PANEL, PANEL_EDGE
            pygame.draw.rect(self.screen, bg, rect, border_radius=12)
            pygame.draw.rect(self.screen, edge, rect, 2, border_radius=12)
            label = self.font.render(name, True, TEXT)
            self.screen.blit(label, label.get_rect(center=rect.center))
            if floor is not None:
                tag = self.font_small.render(roman.get(floor, ""), True, (255, 255, 255))
                self.screen.blit(tag, tag.get_rect(topleft=(rect.x + 8, rect.y + 6)))

    # ---------- 地图绘制 ----------
    def _draw_map_canvas(self, show_rings: bool) -> None:
        """绘制六边形地图本体（迷雾、危险度、玩家位置、移动/侦查圈）。"""
        gmap = self.gmap
        # 连线
        for room in gmap.rooms.values():
            x1, y1 = self.map_positions[room.id]
            for nid in room.neighbors:
                if nid > room.id:
                    x2, y2 = self.map_positions[nid]
                    pygame.draw.line(self.screen, LINK, (x1, y1), (x2, y2), 3)
        # 六边形
        cur = gmap.current_room
        moves = {r.id for r in gmap.available_moves()}
        for room in gmap.rooms.values():
            x, y = self.map_positions[room.id]
            pts = [(int(vx), int(vy)) for vx, vy in hex_vertices(x, y, self.map_hex_size)]
            if not room.revealed:
                pygame.draw.polygon(self.screen, FOG, pts)
                pygame.draw.polygon(self.screen, FOG_EDGE, pts, 2)
                if self.show_danger:
                    danger = gmap.danger(room.id)
                    dcolor = DANGER if danger > 0 else MUTED
                    dsurf = self.font.render(str(danger), True, dcolor)
                    self.screen.blit(dsurf, dsurf.get_rect(center=(x, y)))
                else:
                    q = self.font_small.render("?", True, MUTED)
                    self.screen.blit(q, q.get_rect(center=(x, y)))
                continue
            color = ROOM_COLORS[room.room_type]
            if room.room_type is RoomType.BOSS and room.boss_key:
                color = BOSS_COLORS[room.boss_key]
            pygame.draw.polygon(self.screen, color, pts)
            pygame.draw.polygon(self.screen, (50, 52, 64), pts, 2)
            if self.show_danger:
                danger = gmap.danger(room.id)
                dcolor = DANGER if danger > 0 else MUTED
                dsurf = self.font.render(str(danger), True, dcolor)
                self.screen.blit(dsurf, dsurf.get_rect(center=(x, y)))
            elif room.room_type is RoomType.BOSS and room.boss_key:
                label = {"boss_a": "Ⅰ", "boss_b": "Ⅱ", "boss_c": "Ⅲ"}[room.boss_key]
                surf = self.font.render(label, True, (255, 255, 255))
                self.screen.blit(surf, surf.get_rect(center=(x, y)))
            else:
                label = ROOM_LABELS[room.room_type]
                if label:
                    surf = self.font.render(label, True, (30, 30, 38))
                    self.screen.blit(surf, surf.get_rect(center=(x, y)))
            # 走过的房间：画大红叉
            if room.visited:
                r = self.map_hex_size * 0.6
                pygame.draw.line(self.screen, (235, 50, 50), (x - r, y - r), (x + r, y + r), 5)
                pygame.draw.line(self.screen, (235, 50, 50), (x + r, y - r), (x - r, y + r), 5)
            # 画笔标记：加粗着色边框
            if room.id in self.room_marks:
                mark_color = MARK_COLORS[self.room_marks[room.id]]
                pygame.draw.polygon(self.screen, mark_color, pts, 5)
        # 玩家位置
        px, py = self.map_positions[cur.id]
        pygame.draw.circle(self.screen, PLAYER_RING, (px, py), self.map_hex_size + 5, 3)
        # 可移动 / 可侦查圈
        if show_rings:
            for mid in moves:
                mx, my = self.map_positions[mid]
                color = SCOUT_RING if self.scout_mode else MOVE_RING
                pygame.draw.circle(self.screen, color, (mx, my), self.map_hex_size + 3, 2)

    def _draw_map_scene(self) -> None:
        """肉鸽地图探索主场景。"""
        gmap = self.gmap
        # 顶部 HUD
        pygame.draw.rect(self.screen, PANEL, (0, 0, WIDTH, 68))
        pygame.draw.line(self.screen, PANEL_EDGE, (0, 68), (WIDTH, 68), 1)
        self._draw_map_hud()

        # 地图本体
        self._draw_map_canvas(show_rings=(self.map_mode == "select"))

        # 底部操作提示
        if self.map_mode == "select":
            if self.paint_mode:
                tip = f"画笔模式：点击房间标记（当前颜色）| B 退出画笔"
            elif self.scout_mode:
                tip = "侦查模式：点击相邻房间侦查 | S 退出侦查"
            else:
                tip = "S 侦查（每回合 2 格）| 点击相邻房间移动 | Q 危险度 | B 画笔"
            self.screen.blit(self.font_small.render(tip, True, MUTED), (20, HEIGHT - 30))

        # 房间内容覆盖层
        if self.map_mode == "room":
            self._draw_room_overlay()

        # 设置菜单 / 头像详情
        if self.settings_active:
            self._draw_settings()
        if self.hero_info_active:
            self._draw_hero_info()

    def _draw_heart(self, cx: float, cy: float, size: int) -> None:
        """在 (cx, cy) 绘制一个红色爱心。"""
        r = max(2, size // 3)
        pygame.draw.circle(self.screen, RED, (int(cx - r), int(cy - r * 0.7)), r)
        pygame.draw.circle(self.screen, RED, (int(cx + r), int(cy - r * 0.7)), r)
        pygame.draw.polygon(self.screen, RED, [
            (int(cx - size // 2), int(cy)),
            (int(cx + size // 2), int(cy)),
            (int(cx), int(cy + size // 2)),
        ])

    def _draw_map_hud(self) -> None:
        """地图页顶部 HUD：头像 + 爱心血量 + 金币 + 遗物。"""
        hero = self.rogue_hero
        # 头像（可点击查看卡组）
        icon = char_image_path(hero.name, "小头像")
        draw_image_fit(self.screen, os.path.join(IMAGES_DIR, icon), self.map_avatar_btn)
        pygame.draw.rect(self.screen, ACCENT, self.map_avatar_btn, 2, border_radius=8)

        # 爱心 + 血量
        hx = self.map_avatar_btn.right + 22
        hy = self.map_avatar_btn.centery
        self._draw_heart(hx, hy, 26)
        hp_text = self.font.render(f"{self.rogue_hp}/{hero.max_hp}", True, TEXT)
        self.screen.blit(hp_text, hp_text.get_rect(midleft=(hx + 22, hy)))

        # 金币
        gx = hx + 22 + hp_text.get_width() + 30
        gold_text = self.font.render(f"金币 {self.rogue_gold}", True, YELLOW)
        self.screen.blit(gold_text, gold_text.get_rect(midleft=(gx, hy)))

        # 遗物（图标 + 名字）
        from game.relics import get_relic_def as _get_relic_def
        rx = gx + gold_text.get_width() + 30
        for relic in self.rogue_relics:
            d = _get_relic_def(relic.relic_id)
            icon_rect = pygame.Rect(rx, hy - 16, 32, 32)
            img_path = os.path.join(IMAGES_DIR, d.image) if d and d.image else ""
            if d and d.image and os.path.exists(img_path):
                draw_image_fit(self.screen, img_path, icon_rect)
            else:
                pygame.draw.rect(self.screen, (168, 118, 218), icon_rect, border_radius=6)
                pygame.draw.rect(self.screen, PANEL_EDGE, icon_rect, 1, border_radius=6)
            label = relic.name
            if relic.is_expiring():
                label += f"（剩 {relic.remaining_battles}）"
            t = self.font_small.render(label, True, (168, 118, 218))
            self.screen.blit(t, t.get_rect(midleft=(icon_rect.right + 6, hy)))
            rx = icon_rect.right + 6 + t.get_width() + 18

        # 右侧：楼层 + 模式
        if self.map_mode == "select":
            mode_text = f"第 {self.current_floor}/3 层 · 侦查 {self.gmap.scouts_this_turn}/{MAX_SCOUTS_PER_TURN}"
            if self.scout_mode:
                mode_text += "（侦查中）"
            hud = self.font.render(mode_text, True, YELLOW)
        else:
            hud = self.font.render(f"第 {self.current_floor}/3 层 · 房间", True, MUTED)
        self.screen.blit(hud, hud.get_rect(midright=(WIDTH - 20, 34)))

    def _draw_room_overlay(self) -> None:
        """房间内容覆盖层：起点 / 事件 / 火堆。"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 320, 160, 640, 460)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=16)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=16)

        if self.map_room_overlay == "start":
            title = self.font_big.render("起点", True, PLAYER_RING)
            self.screen.blit(title, title.get_rect(center=(box.centerx, box.y + 90)))
            lines = ["这是本层的起点。", "侦查相邻房间，规划路线，向 Boss 进发。"]
            y = box.y + 170
            for line in lines:
                surf = self.font.render(line, True, TEXT)
                self.screen.blit(surf, surf.get_rect(center=(box.centerx, y)))
                y += 40
        elif self.map_room_overlay == "rest":
            title = self.font_big.render("火堆", True, ROOM_COLORS[RoomType.REST])
            self.screen.blit(title, title.get_rect(center=(box.centerx, box.y + 90)))
            heal = int(self.rogue_hero.max_hp * 0.30)
            lines = [f"你休息了一会，回复 30% 生命（+{heal}）。", f"当前生命 {self.rogue_hp}/{self.rogue_hero.max_hp}。"]
            y = box.y + 170
            for line in lines:
                surf = self.font.render(line, True, TEXT)
                self.screen.blit(surf, surf.get_rect(center=(box.centerx, y)))
                y += 40
        elif self.map_room_overlay == "event":
            self._draw_event(box)
        elif self.map_room_overlay == "shop":
            self._draw_shop(box)
        elif self.map_room_overlay == "chest":
            title = self.font_big.render("宝箱", True, ROOM_COLORS[RoomType.CHEST])
            self.screen.blit(title, title.get_rect(center=(box.centerx, box.y + 90)))
            y = box.y + 170
            for line in self._wrap_text(self.chest_result, box.width - 120):
                surf = self.font.render(line, True, TEXT)
                self.screen.blit(surf, surf.get_rect(center=(box.centerx, y)))
                y += 34

        # 右下角「继续前进」：事件需先完成，起点/火堆/商店/宝箱直接可用
        resolvable = self.map_room_overlay != "event" or self.event_stage == "done"
        if resolvable:
            self._draw_button(self.map_continue_btn, "继续前进", GREEN)

    def _draw_event(self, box: pygame.Rect) -> None:
        """绘制事件房间：图片 + 标题 + 描述 + 选项/删除牌/结果。"""
        ev = get_event(self.current_event) if self.current_event else None
        if ev is None:
            return
        # 事件图片（若有）
        img_path = os.path.join(IMAGES_DIR, ev.image)
        if ev.image and os.path.exists(img_path):
            img_area = pygame.Rect(box.centerx - 140, box.y + 16, 280, 170)
            draw_image_fit(self.screen, img_path, img_area)
            title_y = box.y + 205
        else:
            title_y = box.y + 60
        # 标题
        title = self.font_big.render(ev.title, True, TEXT)
        self.screen.blit(title, title.get_rect(center=(box.centerx, title_y)))
        # 描述
        desc_y = title_y + 36
        for line in self._wrap_text(ev.description, box.width - 100):
            surf = self.font.render(line, True, TEXT)
            self.screen.blit(surf, surf.get_rect(center=(box.centerx, desc_y)))
            desc_y += 26

        if self.event_stage == "choose":
            self.event_option_rects = []
            by = box.bottom - 130
            for i, opt in enumerate(ev.options):
                rect = pygame.Rect(box.centerx - 210, by + i * 58, 420, 50)
                self._draw_button(rect, opt.label, ACCENT)
                self.event_option_rects.append((opt.key, rect))
        elif self.event_stage == "delete_card":
            self._draw_delete_card(box)
        elif self.event_stage == "pick_card":
            self._draw_event_pick_card(box)
        else:  # done
            yy = box.bottom - 130
            for line in self._wrap_text(self.event_result_text, box.width - 100):
                surf = self.font.render(line, True, GREEN)
                self.screen.blit(surf, surf.get_rect(center=(box.centerx, yy)))
                yy += 26

    def _draw_event_pick_card(self, box: pygame.Rect) -> None:
        """事件「趁机购物」：三张蓝色以上卡任选一张。"""
        title = self.font.render("从以下三张卡中任选一张", True, YELLOW)
        self.screen.blit(title, title.get_rect(center=(box.centerx, box.y + 240)))
        self.event_pick_rects = []
        cw, ch = 150, 200
        gap = 30
        total = cw * len(self.event_pick_cards) + gap * (len(self.event_pick_cards) - 1)
        x = box.centerx - total // 2
        y = box.y + 270
        for key in self.event_pick_cards:
            card = make_card(key)
            rect = pygame.Rect(x, y, cw, ch)
            self._draw_card(rect, card, selected=False)
            self.event_pick_rects.append((key, rect))
            x += cw + gap

    def _draw_delete_card(self, box: pygame.Rect) -> None:
        """绘制「删除一张牌」子界面：列出牌组，点击删除。"""
        title = self.font.render("选择要删除的一张牌", True, YELLOW)
        self.screen.blit(title, title.get_rect(center=(box.centerx, box.y + 240)))
        self._draw_button(self.event_delete_back_btn, "返回", PANEL_EDGE)
        self.event_delete_rects = []
        counts = self._rogue_deck_counts()
        y = box.y + 275
        for name in sorted(counts):
            n = counts[name]
            row = pygame.Rect(box.x + 70, y, box.width - 140, 34)
            pygame.draw.rect(self.screen, PANEL_EDGE, row, border_radius=6)
            label = self.font_small.render(f"{name} × {n}", True, TEXT)
            self.screen.blit(label, label.get_rect(midleft=(row.x + 12, row.centery)))
            self.event_delete_rects.append((name, row))
            y += 40

    # ---------- 商店 ----------
    _RARITY_LABELS = {
        Rarity.STARTER: "普",
        Rarity.COMMON: "普",
        Rarity.UNCOMMON: "蓝",
        Rarity.RARE: "金",
        Rarity.SPECIAL: "金",
        Rarity.CURSE: "咒",
    }

    def _draw_shop(self, box: pygame.Rect) -> None:
        """绘制商店：商品卡牌 + 删牌服务 + 遗物/药水占位。"""
        title = self.font_big.render("商店", True, ROOM_COLORS[RoomType.SHOP])
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 16)))
        gold = self.font.render(f"金币 {self.rogue_gold}", True, YELLOW)
        self.screen.blit(gold, gold.get_rect(midtop=(box.centerx, box.y + 54)))
        y = box.y + 90
        if self.shop_free_items > 0:
            hint = self.font_small.render(
                f"老板娘的怀表：本商店可免费 {self.shop_free_items} 次", True, (168, 118, 218)
            )
            self.screen.blit(hint, hint.get_rect(midtop=(box.centerx, y)))
            y += 24

        if self.shop_stage == "remove_card":
            self._draw_shop_remove(box)
            return

        # 商品卡牌列表
        self.shop_offer_rects = []
        for i, (key, price, discounted) in enumerate(self.shop_offers):
            card = make_card(key)
            row = pygame.Rect(box.x + 40, y, box.width - 80, 40)
            pygame.draw.rect(self.screen, PANEL, row, border_radius=6)
            pygame.draw.rect(self.screen, PANEL_EDGE, row, 1, border_radius=6)
            rlabel = self._RARITY_LABELS.get(card.rarity, "")
            name = self.font_small.render(f"{card.name}（{rlabel}）", True, TEXT)
            self.screen.blit(name, name.get_rect(midleft=(row.x + 12, row.centery)))
            price_color = RED if discounted else YELLOW
            price_label = self.font_small.render(f"{price} 金币", True, price_color)
            self.screen.blit(price_label, price_label.get_rect(midright=(row.right - 12, row.centery)))
            self.shop_offer_rects.append((i, row))
            y += 48

        y += 8
        # 删牌服务
        remove_price = remove_service_price(self.rogue_remove_count)
        self.shop_remove_btn = pygame.Rect(box.x + 40, y, box.width - 80, 40)
        self._draw_button(self.shop_remove_btn, f"删除一张牌（{remove_price} 金币）", (90, 120, 200))
        y += 48
        # 遗物 / 药水占位
        half = (box.width - 100) // 2
        self.shop_relic_btn = pygame.Rect(box.x + 40, y, half, 40)
        self.shop_potion_btn = pygame.Rect(box.x + 60 + half, y, half, 40)
        self._draw_button(self.shop_relic_btn, "遗物（敬请期待）", MUTED)
        self._draw_button(self.shop_potion_btn, "药水（敬请期待）", MUTED)
        y += 48
        if self.shop_hint:
            h = self.font_small.render(self.shop_hint, True, YELLOW)
            self.screen.blit(h, h.get_rect(midtop=(box.centerx, y)))

    def _draw_shop_remove(self, box: pygame.Rect) -> None:
        """绘制商店删牌子界面：列出牌组，点击删除。"""
        title = self.font.render("选择要删除的一张牌", True, YELLOW)
        self.screen.blit(title, title.get_rect(center=(box.centerx, box.y + 120)))
        self.shop_remove_back_btn.topleft = (box.x + 40, box.y + 20)
        self._draw_button(self.shop_remove_back_btn, "返回", PANEL_EDGE)
        self.shop_remove_rects = []
        counts = self._rogue_deck_counts()
        y = box.y + 160
        for name in sorted(counts):
            n = counts[name]
            row = pygame.Rect(box.x + 70, y, box.width - 140, 34)
            pygame.draw.rect(self.screen, PANEL_EDGE, row, border_radius=6)
            label = self.font_small.render(f"{name} × {n}", True, TEXT)
            self.screen.blit(label, label.get_rect(midleft=(row.x + 12, row.centery)))
            self.shop_remove_rects.append((name, row))
            y += 40

    def _draw_map_overlay(self) -> None:
        """战斗中的地图查看浮层（只读）。"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        self.screen.blit(overlay, (0, 0))
        title = self.font.render(f"第 {self.current_floor} / 3 层地图（Q 切换危险度）", True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(WIDTH // 2, 20)))
        self._draw_map_canvas(show_rings=False)
        self._draw_button(self.map_close_btn, "关闭地图", ACCENT)

    def layout_hero_cards(self) -> None:
        n = len(HEROES)
        cw, ch = 280, 440
        gap = 50
        total = cw * n + gap * (n - 1)
        x = (WIDTH - total) // 2
        y = 140
        self.hero_card_rects = [
            (HEROES[i], pygame.Rect(x + i * (cw + gap), y, cw, ch)) for i in range(n)
        ]

    def _draw_char_select(self) -> None:
        title = self.font_big.render("选择角色", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 70)))
        self._draw_button(self.select_back_btn, "返回", PANEL_EDGE)

        self.layout_hero_cards()
        for hero, rect in self.hero_card_rects:
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=14)
            pygame.draw.rect(self.screen, ACCENT, rect, 2, border_radius=14)
            name = self.font.render(hero.name, True, TEXT)
            self.screen.blit(name, name.get_rect(midtop=(rect.centerx, rect.y + 14)))
            sprite = pygame.Rect(rect.x + 12, rect.y + 48, rect.width - 24, rect.height - 160)
            draw_image_fit(self.screen, os.path.join(IMAGES_DIR, char_image_path(hero.name, "大头像")), sprite)
            hp = self.font_small.render(f"生命上限 {hero.max_hp}", True, GREEN)
            self.screen.blit(hp, hp.get_rect(midtop=(rect.centerx, rect.bottom - 92)))
            pn = self.font_small.render(f"被动：{hero.passive_name}", True, YELLOW)
            self.screen.blit(pn, pn.get_rect(midtop=(rect.centerx, rect.bottom - 68)))
            lines = self._wrap_text(hero.passive_desc, rect.width - 24)
            for i, line in enumerate(lines[:3]):
                surf = self.font_small.render(line, True, MUTED)
                self.screen.blit(surf, surf.get_rect(midtop=(rect.centerx, rect.bottom - 46 + i * 18)))

    def _wrap_text(self, text: str, max_width: int, font=None) -> list[str]:
        font = font or self.font_small
        lines = []
        current = ""
        for ch in text:
            if font.size(current + ch)[0] > max_width:
                lines.append(current)
                current = ch
            else:
                current += ch
        if current:
            lines.append(current)
        return lines

    def _draw_weight_popup(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        popup = self._weight_popup_rect()
        pygame.draw.rect(self.screen, PANEL, popup, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_EDGE, popup, 2, border_radius=14)
        title = self.font.render("设定这张牌的重量", True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(popup.centerx, popup.y + 20)))
        hint = self.font_small.render("范围 1 ~ 10", True, MUTED)
        self.screen.blit(hint, hint.get_rect(midtop=(popup.centerx, popup.y + 52)))

        self._layout_weight_buttons()
        self._draw_button(self.weight_minus_btn, "-", PANEL_EDGE)
        self._draw_button(self.weight_plus_btn, "+", PANEL_EDGE)
        num = self.font_big.render(str(self.custom_weight), True, YELLOW)
        self.screen.blit(num, num.get_rect(center=(popup.centerx, popup.y + 130)))
        self._draw_button(self.weight_ok_btn, "确定", ACCENT)
        self._draw_button(self.weight_cancel_btn, "取消", RED)

    def _draw_resolution_overlay(self) -> None:
        """回合结束结算动画。"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        self.screen.blit(overlay, (0, 0))

        center = (WIDTH // 2, HEIGHT // 2)
        if self.resolve_anim == "stack":
            src = self.slot_rects[0].center
            total = len(self.resolve_cards)
            for i, card in enumerate(self.resolve_cards):
                t = max(0.0, min(1.0, self.anim_t * (total + 2) - i * 0.6))
                x = src[0] + (center[0] - src[0]) * t
                y = src[1] + (center[1] - src[1]) * t
                r = pygame.Rect(0, 0, CARD_W, CARD_H)
                r.center = (int(x), int(y))
                self._draw_card(r, card, selected=False)
        elif self.resolve_anim in ("await_target", "fly"):
            if self.resolve_current is not None:
                r = pygame.Rect(0, 0, CARD_W, CARD_H)
                r.center = center
                if self.resolve_anim == "fly" and self.resolve_target is not None:
                    tp = self._target_pos(self.resolve_target)
                    x = center[0] + (tp[0] - center[0]) * self.anim_t
                    y = center[1] + (tp[1] - center[1]) * self.anim_t
                    r.center = (int(x), int(y))
                self._draw_card(r, self.resolve_current, selected=True)
            if self.resolve_anim == "await_target":
                self._draw_target_buttons()
        elif self.resolve_anim == "effect":
            if self.effect_text:
                surf = self.font_big.render(self.effect_text, True, YELLOW)
                bg = pygame.Surface(
                    (surf.get_width() + 40, surf.get_height() + 24), pygame.SRCALPHA
                )
                bg.fill((0, 0, 0, 190))
                self.screen.blit(bg, (center[0] - bg.get_width() // 2, center[1] - bg.get_height() // 2))
                self.screen.blit(surf, surf.get_rect(center=center))
        elif self.resolve_anim == "monster_attack":
            # 怪物晃动两下 + 角色红闪（掉血）或下晃（全挡）
            import math
            enemy = self.engine.state.enemy
            t = self.monster_anim_timer / MONSTER_ANIM_FRAMES  # 1.0 -> 0
            if enemy is not None:
                if t > 0.4:
                    # 前段：怪物左右晃动两下（红色描边左右偏移）
                    shake_phase = (1.0 - t) / 0.6 * 2 * math.pi * 2
                    shake_x = int(math.sin(shake_phase) * 10)
                    rect = self.enemy_area.move(shake_x, 0)
                    pygame.draw.rect(self.screen, (230, 80, 60), rect, 3, border_radius=12)
                    # 攻击瞬间敌人罩暖色
                    alpha = int(160 * (t - 0.55) / 0.45) if t > 0.55 else 0
                    if alpha > 0:
                        flash = pygame.Surface((self.enemy_area.w, self.enemy_area.h), pygame.SRCALPHA)
                        flash.fill((255, 190, 110, alpha))
                        self.screen.blit(flash, self.enemy_area.topleft)
                else:
                    # 后段：角色反应
                    react = (0.4 - t) / 0.4  # 0 -> 1
                    if self.monster_pierced:
                        # 掉血：角色红闪
                        alpha = int(200 * react)
                        flash = pygame.Surface((self.player_area.w, self.player_area.h), pygame.SRCALPHA)
                        flash.fill((220, 60, 60, alpha))
                        self.screen.blit(flash, self.player_area.topleft)
                    else:
                        # 全挡：角色面板轻微下沉 + 金色提示
                        dy = int(react * 10)
                        rect = self.player_area.move(0, dy)
                        pygame.draw.rect(self.screen, (212, 175, 55), rect, 3, border_radius=12)

    def _draw_target_buttons(self) -> None:
        cx = WIDTH // 2
        title = self.font.render("选择目标", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(cx, HEIGHT // 2 + 95)))
        enemies = self._enemies()
        multi = len(enemies) > 1
        for target, rect in self.target_btn_rects.items():
            if target == "self":
                label, color = "自己", ACCENT
            else:
                idx = int(target[5:]) if target[5:].isdigit() else 0
                name = enemies[idx].name if idx < len(enemies) else "敌方"
                label = f"{idx + 1}·{name}" if multi else name
                color = RED
            self._draw_button(rect, label, color)

    def _draw_button(self, rect: pygame.Rect, label: str, color) -> None:
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        text = self.font.render(label, True, (255, 255, 255))
        self.screen.blit(text, text.get_rect(center=rect.center))

    def _intent_color(self, intent) -> tuple[int, int, int]:
        if intent.kind in ("attack", "multi", "attack_block", "attack_strength"):
            return RED
        if intent.kind == "strength":
            return (200, 120, 220)  # 紫色
        if intent.kind == "buff":
            return (212, 175, 55)  # 金色
        if intent.kind in ("gain_counterattack", "gain_resilience", "heal_block", "summon_minion", "buff_minions_strength"):
            return (212, 175, 55)  # 金色（增益）
        if intent.kind == "shrink":
            return (200, 120, 220)  # 紫色（负面）
        if intent.kind == "sleep":
            return MUTED
        return MUTED

    def _intent_hit_damage(self, base: int, player) -> int:
        """计算意图对某玩家的最终伤害（含玩家自身的易伤/调查/标记增伤）。"""
        amount = base
        amount += player.get_stacks("investigate")
        amount += player.get_stacks("mark")
        if player.get_stacks("vulnerable") > 0:
            amount = int(amount * 1.5)
        return amount

    def _intent_actions(self, intent, strength: int = 0, player=None):
        """把单个意图拆成动作列表 [(标签, 数值)]，标签 ∈ {打, 防, 效}。

        打类数值为「对该玩家」的最终伤害（含玩家状态增伤）。
        """
        atk = intent.value + strength
        # 玩家隐匿：攻击被免疫，伤害显示为 0
        if player is not None and player.get_stacks("hide") > 0:
            atk = 0
        else:
            atk = self._intent_hit_damage(atk, player) if player is not None else atk
        k = intent.kind
        if k == "attack":
            return [("打", atk)]
        if k == "multi":
            return [("打", atk)]
        if k == "strength":
            return [("效", 0)]
        if k == "buff":
            acts = []
            if intent.block:
                acts.append(("防", intent.block))
            if intent.strength:
                acts.append(("效", 0))
            return acts or [("效", 0)]
        if k == "attack_block":
            return [("打", atk), ("防", intent.block)]
        if k == "attack_strength":
            return [("打", atk), ("效", 0)]
        if k == "shrink":
            return [("效", 0)]
        if k == "sleep":
            return [("效", 0)]
        if k in ("gain_counterattack", "gain_resilience", "heal_block", "summon_minion", "buff_minions_strength"):
            return [("效", 0)]
        return [("效", 0)]

    # 意图标签 → 图标文件名（general 目录）
    _INTENT_ICON = {"打": "意图-攻击", "防": "意图-防御", "效": "意图-效果"}
    _INTENT_DESC = {"打": "攻击", "防": "防御", "效": "效果"}

    def _intent_icon_path(self, label: str) -> str:
        base = self._INTENT_ICON.get(label, label)
        for ext in (".webp", ".png", ".jpeg", ".jpg"):
            p = os.path.join(ROOT, "sources", "icon", "general", base + ext)
            if os.path.exists(p):
                return p
        return ""

    def _draw_intent_icon(self, label: str, value: int, cx: int, cy: int, size: int) -> None:
        """绘制单个意图图标：有图用图，无图用字；打/防右下角显示红色带黑描边数字。"""
        icon_path = self._intent_icon_path(label)
        r = pygame.Rect(0, 0, size, size)
        r.center = (cx, cy)
        if icon_path:
            draw_image_fit(self.screen, icon_path, r)
        else:
            pygame.draw.circle(self.screen, (46, 50, 64), r.center, size // 2)
            pygame.draw.circle(self.screen, PANEL_EDGE, r.center, size // 2, 2)
            ch = self.font_big.render(label, True, TEXT)
            self.screen.blit(ch, ch.get_rect(center=r.center))
        # 打 / 防右下角显示红色带黑描边数字（无红底）
        if label in ("打", "防") and value > 0:
            num = self._render_outlined(str(value), load_font(16), RED, (20, 20, 20))
            self.screen.blit(num, num.get_rect(bottomright=(r.right, r.bottom)))

    def _draw_enemy_intents(self, enemy, area: pygame.Rect | None = None, sprite_top: int | None = None) -> None:
        """在怪左上方显示未来两回合意图：下回合在上、下下回合在下，多动作并排，可点击看详情。"""
        upcoming = get_upcoming_intents(enemy, 3)
        if not upcoming:
            return
        panel = area if area is not None else self.enemy_area
        # 本回合（index0）即将执行的行动 = 下回合；再下一个 = 下下回合
        rows = upcoming[0:2]
        if not rows:
            rows = upcoming[:1]
        size = 34
        gap = 6
        start_x = panel.left
        # 意图锚定在立绘顶部上方（视立绘高度决定）
        anchor = sprite_top if sprite_top is not None else panel.top
        start_y = anchor - size - 10
        for row_i, (intent, strength) in enumerate(rows):
            # 最终力量 = 永久力量 + 临时力量（震撼激励等）
            total_str = strength + getattr(enemy, "temp_strength", 0)
            # 意图数字按「当前查看的玩家」状态计算
            acts = self._intent_actions(intent, total_str, self._active_player())
            x = start_x
            y = start_y + row_i * (size + gap)
            turn_label = "下回合" if row_i == 0 else "下下回合"
            for label, value in acts:
                self._draw_intent_icon(label, value, x + size // 2, y + size // 2, size)
                # 记录可点击矩形
                desc = self._intent_desc(intent, total_str, turn_label)
                self.intent_icon_rects.append((desc, pygame.Rect(x, y, size, size)))
                x += size + gap

    def _intent_desc(self, intent, strength: int, turn_label: str) -> str:
        """生成意图详情文案。"""
        text = intent.describe(strength)
        return f"{turn_label}：{text}"

    def _draw_intent_detail(self) -> None:
        """点击意图图标后弹出的详情浮层。"""
        if self.intent_detail is None:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 220, HEIGHT // 2 - 100, 440, 200)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=16)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=16)
        title = self.font_big.render("意图", True, YELLOW)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 20)))
        y = box.y + 80
        for line in self._wrap_text(self.intent_detail, box.width - 60):
            surf = self.font.render(line, True, TEXT)
            self.screen.blit(surf, surf.get_rect(midtop=(box.centerx, y)))
            y += 30
        tip = self.font_small.render("点击任意处关闭", True, MUTED)
        self.screen.blit(tip, tip.get_rect(midbottom=(box.centerx, box.bottom - 12)))

    def _draw_character_panel(
        self, area: pygame.Rect, img_name: str, title: str, accent,
        hp: int, max_hp: int, statuses=None, block: int = 0, flip: bool = False,
        disp_hp: float | None = None, disp_block: float | None = None,
    ) -> None:
        pygame.draw.rect(self.screen, PANEL, area, border_radius=12)
        pygame.draw.rect(self.screen, accent, area, 2, border_radius=12)
        title_surf = self.font.render(title, True, TEXT)
        self.screen.blit(title_surf, title_surf.get_rect(midtop=(area.centerx, area.y + 12)))
        sprite_area = pygame.Rect(area.x + 10, area.y + 46, area.width - 20, area.height - 96)
        draw_image_fit(self.screen, os.path.join(IMAGES_DIR, img_name), sprite_area, flip=flip)
        # 血条 + 格挡条
        bar = pygame.Rect(area.x + 16, area.bottom - 44, area.width - 32, 22)
        self._draw_hp_bar(bar, hp, max_hp, block, disp_hp, disp_block)
        # 状态徽章（全部显示，实时层数与名称）
        if statuses:
            y = area.y + 12
            for s in statuses:
                badge = self.font_small.render(f"{s.name}×{s.stacks}", True, (20, 20, 26))
                w = badge.get_width() + 14
                rect = pygame.Rect(area.right - w - 8, y, w, 24)
                pygame.draw.rect(self.screen, YELLOW, rect, border_radius=12)
                self.screen.blit(badge, badge.get_rect(center=rect.center))
                y += 30

    def _draw_hp_bar(
        self, rect: pygame.Rect, hp: int, max_hp: int, block: int = 0,
        disp_hp: float | None = None, disp_block: float | None = None,
    ) -> None:
        # 动画显示值
        show_hp = hp if disp_hp is None else max(0.0, disp_hp)
        show_block = block if disp_block is None else max(0.0, disp_block)
        hp_ratio = max(0.0, min(1.0, show_hp / max_hp)) if max_hp > 0 else 0.0
        block_ratio = max(0.0, min(1.0, show_block / max_hp)) if max_hp > 0 else 0.0
        # 盾牌（血条左边）+ 白色描边格挡数字（无格挡不显示）
        if show_block > 0:
            shield_r = pygame.Rect(0, 0, 34, 34)
            shield_r.midright = (rect.left - 2, rect.centery)
            shield_path = os.path.join(ROOT, "sources", "icon", "general", "盾牌.jpeg")
            if os.path.exists(shield_path):
                draw_image_fit(self.screen, shield_path, shield_r)
            else:
                pygame.draw.circle(self.screen, (80, 140, 255), shield_r.center, 16)
                pygame.draw.circle(self.screen, PANEL_EDGE, shield_r.center, 16, 2)
            blk_num = self._render_outlined(
                str(int(round(show_block))), load_font(18), (255, 255, 255), (20, 20, 20)
            )
            self.screen.blit(blk_num, blk_num.get_rect(center=shield_r.center))
        # 底色
        pygame.draw.rect(self.screen, (40, 40, 50), rect, border_radius=6)
        # 血条填充
        fill = rect.copy()
        fill.width = int(rect.width * hp_ratio)
        color = GREEN if hp_ratio > 0.5 else (YELLOW if hp_ratio > 0.25 else RED)
        pygame.draw.rect(self.screen, color, fill, border_radius=6)
        # 格挡条（蓝色，与血条左对齐，长度按格挡/max_hp 比例）
        if block_ratio > 0:
            blk = rect.copy()
            blk.width = max(1, int(rect.width * block_ratio))
            pygame.draw.rect(self.screen, (80, 140, 255), blk, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_EDGE, rect, 2, border_radius=6)
        label = self.font_small.render(f"{hp}/{max_hp}", True, (255, 255, 255))
        self.screen.blit(label, label.get_rect(center=rect.center))

    def _draw_slot(
        self, rect: pygame.Rect, idx: int, active: bool, hovered: bool = False
    ) -> None:
        # 牌堆滑出动画：平时收起（仅露 10%），放牌时快速展开「迎接」
        offset = int((1.0 - self._slot_slide) * (SLOT_H * 0.9))
        rect = rect.move(0, -offset)
        edge = SLOT_ACTIVE_EDGE if active else SLOT_EDGE
        pygame.draw.rect(self.screen, SLOT_BG, rect, border_radius=10)
        pygame.draw.rect(self.screen, edge, rect, 3 if hovered else 2, border_radius=10)
        label = f"牌堆 {idx + 1}"
        if not active:
            label += "（锁定）"
        text = self.font_small.render(label, True, MUTED if not active else TEXT)
        self.screen.blit(text, text.get_rect(midtop=(rect.centerx, rect.y + 8)))

        pile = self._active_player().pile_slots[idx]
        if pile.is_empty():
            msg = self.font.render("（空）", True, MUTED)
            self.screen.blit(msg, msg.get_rect(center=rect.center))
        else:
            top = pile.top
            # 槽位内画一张小卡（仅缩略，不显示效果描述）
            mini = pygame.Rect(0, 0, CARD_W - 40, int((CARD_W - 40) * CARD_H / CARD_W))
            mini.center = (rect.centerx, rect.centery - 6)
            self._draw_card(mini, top, selected=False, compact=True)

        # 张数 + 本回合加牌进度
        capacity = self._active_player().max_slots - idx
        used = self._active_player().pile_turn_counts[idx]
        cnt = self.font_small.render(f"×{len(pile.cards)}", True, YELLOW)
        self.screen.blit(cnt, cnt.get_rect(midtop=(rect.centerx, rect.bottom - 34)))
        prog = self.font_small.render(f"本回合 {used}/{capacity}", True, MUTED)
        self.screen.blit(prog, prog.get_rect(midtop=(rect.centerx, rect.bottom - 18)))

    def _card_image(self, card: Card) -> pygame.Surface | None:
        """加载卡牌卡面图（缓存），无卡面则返回 None。"""
        if card.name in self.card_image_cache:
            return self.card_image_cache[card.name]
        path = os.path.join(IMAGES_DIR, "card", card.name, f"{card.name}.png")
        if not os.path.exists(path):
            return None
        try:
            img = pygame.image.load(path).convert_alpha()
        except pygame.error:
            return None
        self.card_image_cache[card.name] = img
        return img

    def _draw_card(self, rect: pygame.Rect, card: Card, selected: bool, compact: bool = False) -> None:
        img = self._card_image(card)
        if img is not None:
            # 有卡面图：贴图 + 动态重量覆盖 + 动态描述 + 边框
            scaled = pygame.transform.smoothscale(img, (rect.w, rect.h))
            self.screen.blit(scaled, rect.topleft)
            self._draw_weight_overlay(rect, card.weight, logic=card.logic)
            if not compact:
                self._draw_desc_on_card(rect, card)
            if selected:
                pygame.draw.rect(self.screen, ACCENT, rect, 3, border_radius=10)
            elif card.customizable_weight:
                pygame.draw.rect(self.screen, YELLOW, rect, 3, border_radius=10)
            return

        # 回退：程序化绘制（无卡面图时）
        color = weight_color(card.weight)
        is_curse = card.card_type is CardType.CURSE
        is_logic = card.logic
        if is_curse:
            color = (168, 118, 218)  # 紫色诅咒牌
        elif is_logic:
            color = (110, 210, 130)  # 绿色逻辑牌
        pygame.draw.rect(self.screen, CARD_BG, rect, border_radius=10)
        pygame.draw.rect(
            self.screen, ACCENT if selected else color, rect, 3, border_radius=10
        )
        name = self.font_small.render(card.name, True, CARD_TEXT)
        self.screen.blit(name, name.get_rect(midtop=(rect.centerx, rect.y + 8)))
        if is_curse:
            center_label = "诅咒"
        elif is_logic:
            center_label = "逻辑"
        else:
            center_label = str(card.weight)
        weight = self.font_card.render(center_label, True, color)
        self.screen.blit(weight, weight.get_rect(center=(rect.centerx, rect.centery - 6)))
        if compact:
            lbl_text = "诅咒" if is_curse else ("逻辑" if is_logic else "重量")
            lbl = self.font_small.render(lbl_text, True, CARD_TEXT)
            self.screen.blit(lbl, lbl.get_rect(midbottom=(rect.centerx, rect.bottom - 8)))
            return
        effect = card.effect_text
        if effect:
            lines = self._wrap_text(effect, rect.width - 12)
            y = rect.bottom - 12 - (min(len(lines), 2) - 1) * 16
            for line in lines[:2]:
                surf = self.font_small.render(line, True, CARD_TEXT)
                self.screen.blit(surf, surf.get_rect(midtop=(rect.centerx, y)))
                y += 16
        else:
            lbl_text = "诅咒" if is_curse else ("逻辑" if is_logic else "重量")
            lbl = self.font_small.render(lbl_text, True, CARD_TEXT)
            self.screen.blit(lbl, lbl.get_rect(midbottom=(rect.centerx, rect.bottom - 10)))
        if card.customizable_weight:
            badge = self.font_small.render("自定", True, YELLOW)
            self.screen.blit(badge, badge.get_rect(topleft=(rect.x + 4, rect.y + 4)))

    def _draw_weight_overlay(self, rect: pygame.Rect, weight: int, logic: bool = False) -> None:
        """在卡面左上角圆上覆盖绘制当前重量（保证数值可变）；逻辑牌显示「逻辑」。"""
        scale = rect.w / 1728.0
        cx = rect.x + int(190 * scale)
        cy = rect.y + int(200 * scale)
        r = max(8, int(120 * scale))
        pygame.draw.circle(self.screen, (250, 246, 230), (cx, cy), r)
        pygame.draw.circle(self.screen, (175, 145, 70), (cx, cy), r, max(2, int(6 * scale)))
        if logic:
            font = load_font(max(12, int(140 * scale)))
            text = font.render("逻辑", True, (60, 50, 30))
        else:
            font = load_font(max(16, int(200 * scale)))
            text = font.render(str(weight), True, (60, 50, 30))
        self.screen.blit(text, text.get_rect(center=(cx, cy)))

    def _render_outlined(self, text: str, font, fill: tuple, outline: tuple, width: int = 2) -> pygame.Surface:
        """渲染带描边的文字（白色填充 + 深色描边）。"""
        base = font.render(text, True, fill)
        o = font.render(text, True, outline)
        surf = pygame.Surface(
            (base.get_width() + width * 2, base.get_height() + width * 2), pygame.SRCALPHA
        )
        for dx in range(-width, width + 1):
            for dy in range(-width, width + 1):
                if dx or dy:
                    surf.blit(o, (width + dx, width + dy))
        surf.blit(base, (width, width))
        return surf

    def _draw_desc_on_card(self, rect: pygame.Rect, card: Card) -> None:
        """在卡面文字框内动态绘制描述（实时数值，按逗号断行）+ 附魔两行。"""
        desc = card.rendered_description
        perm = card.perm_enchant_text
        temp = card.temp_enchant_text
        has_enchant = bool(perm or temp)
        # 文字框区域（按模板比例）：有附魔时描述区收窄
        top = rect.y + int(rect.h * 0.60)
        bottom = rect.y + int(rect.h * (0.80 if has_enchant else 0.90))
        area_h = bottom - top
        # 白色文字 + 深色描边，字号减小
        font = load_font(max(11, int(rect.w * 0.095)))
        # 按逗号断行
        import re
        segments = [s for s in re.split(r"[，,]", desc) if s.strip()]
        lines: list[str] = []
        for seg in segments:
            lines.extend(self._wrap_text(seg, rect.width - 16, font))
        line_h = font.get_height() + 3
        total_h = len(lines) * line_h
        y = top + (area_h - total_h) / 2
        for line in lines:
            surf = self._render_outlined(line, font, (255, 255, 255), (30, 30, 30))
            self.screen.blit(surf, surf.get_rect(center=(rect.centerx, y + line_h / 2)))
            y += line_h
        # 附魔两行：上行永久（金色+黑描边），下行临时（紫色+白描边）
        if has_enchant:
            efont = load_font(max(10, int(rect.w * 0.075)))
            base_y = rect.y + int(rect.h * 0.82)
            if perm:
                psurf = self._render_outlined(f"永久：{perm}", efont, (255, 200, 40), (20, 20, 20))
                self.screen.blit(psurf, psurf.get_rect(midtop=(rect.centerx, base_y)))
                base_y += psurf.get_height() + 2
            if temp:
                tsurf = self._render_outlined(f"临时：{temp}", efont, (220, 170, 255), (255, 255, 255))
                self.screen.blit(tsurf, tsurf.get_rect(midtop=(rect.centerx, base_y)))

    def _draw_folded_card(self, rect: pygame.Rect, card: Card) -> None:
        """绘制折叠的手牌：只显示卡面顶部条带（名字 + 重量可见）。"""
        img = self._card_image(card)
        if img is None:
            # 回退：程序绘制折叠条
            is_curse = card.card_type is CardType.CURSE
            edge = (168, 118, 218) if is_curse else weight_color(card.weight)
            pygame.draw.rect(self.screen, CARD_BG, rect, border_radius=8)
            pygame.draw.rect(self.screen, edge, rect, 2, border_radius=8)
            name = self.font_small.render(card.name, True, CARD_TEXT)
            self.screen.blit(name, name.get_rect(midtop=(rect.centerx, rect.y + 4)))
            if is_curse:
                curse = self.font_small.render("咒", True, (168, 118, 218))
                self.screen.blit(curse, curse.get_rect(center=(rect.centerx, rect.centery)))
            elif card.logic:
                logic = self.font_small.render("逻辑", True, (60, 50, 30))
                self.screen.blit(logic, logic.get_rect(center=(rect.centerx, rect.centery)))
            else:
                self._draw_weight_overlay(rect, card.weight)
            return
        # 裁剪卡面顶部（按折叠高度比例）
        crop_h = int(img.get_height() * rect.h / CARD_H)
        top = img.subsurface((0, 0, img.get_width(), crop_h))
        scaled = pygame.transform.smoothscale(top, (rect.w, rect.h))
        self.screen.blit(scaled, rect.topleft)
        # 顶部条带底部加一条分隔线
        pygame.draw.line(self.screen, SLOT_EDGE, (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1), 2)
        # 重量覆盖（位置与完整卡一致）
        self._draw_weight_overlay(rect, card.weight, logic=card.logic)

    def _draw_card_placeholder(self, rect: pygame.Rect) -> None:
        """被拖走的牌在原位留下的虚线占位。"""
        pygame.draw.rect(self.screen, SLOT_EDGE, rect, 2, border_radius=10)
        dashes = [
            (rect.x, rect.y, rect.x + rect.w, rect.y),
            (rect.x, rect.y + rect.h, rect.x + rect.w, rect.y + rect.h),
            (rect.x, rect.y, rect.x, rect.y + rect.h),
            (rect.x + rect.w, rect.y, rect.x + rect.w, rect.y + rect.h),
        ]
        for x1, y1, x2, y2 in dashes:
            self._dashed_line((x1, y1), (x2, y2), SLOT_EDGE, dash=8, gap=6)

    def _dashed_line(
        self, a: tuple[int, int], b: tuple[int, int], color, dash: int, gap: int
    ) -> None:
        import math

        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return
        steps = int(length // (dash + gap)) + 1
        for i in range(steps):
            t0 = i * (dash + gap) / length
            t1 = min(1.0, t0 + dash / length)
            p0 = (int(a[0] + dx * t0), int(a[1] + dy * t0))
            p1 = (int(a[0] + dx * t1), int(a[1] + dy * t1))
            pygame.draw.line(self.screen, color, p0, p1, 2)

    def _draw_pile_viewer(self, idx: int) -> None:
        """浮层：按从上到下顺序展示某个牌堆的所有牌。"""
        popup = self._view_popup_rect()
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, PANEL, popup, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_EDGE, popup, 2, border_radius=14)

        pile = self._active_player().pile_slots[idx]
        title = self.font.render(f"牌堆 {idx + 1}（从上到下，共 {len(pile.cards)} 张）", True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(popup.centerx, popup.y + 14)))
        hint = self.font_small.render("点浮层外关闭 · 点卡查看整卡", True, MUTED)
        self.screen.blit(hint, hint.get_rect(midtop=(popup.centerx, popup.y + 44)))

        cards = pile.snapshot_top_to_bottom()
        self.viewer_card_rects = self._viewer_card_layout(idx)
        if not cards:
            msg = self.font.render("（空牌堆）", True, MUTED)
            self.screen.blit(msg, msg.get_rect(center=popup.center))
        else:
            for i, (card, r) in enumerate(self.viewer_card_rects):
                self._draw_compact_card(r, card, i)
                order = self.font_small.render(f"第{i + 1}张", True, YELLOW)
                self.screen.blit(order, order.get_rect(midleft=(r.right + 14, r.centery)))
            if len(cards) > 6:
                more = self.font_small.render(f"…还有 {len(cards) - 6} 张", True, MUTED)
                self.screen.blit(more, more.get_rect(midtop=(popup.centerx, popup.bottom - 40)))

        # 两侧翻页三角形按钮
        prev_rect, next_rect = self._view_nav_rects()
        self._draw_tri_button(prev_rect, left=True)
        self._draw_tri_button(next_rect, left=False)

        # 整卡查看
        if self.viewer_selected_card is not None:
            self._draw_full_card(self.viewer_selected_card)

    def _draw_tri_button(self, rect: pygame.Rect, left: bool) -> None:
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_EDGE, rect, 2, border_radius=8)
        cx, cy = rect.center
        r = 12
        if left:
            pts = [(cx + r, cy - r), (cx + r, cy + r), (cx - r, cy)]
        else:
            pts = [(cx - r, cy - r), (cx - r, cy + r), (cx + r, cy)]
        pygame.draw.polygon(self.screen, ACCENT, pts)

    def _draw_full_card(self, card: Card) -> None:
        """整卡浮层：显示完整卡面。"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        r = pygame.Rect(0, 0, CARD_W * 2, CARD_H * 2)
        r.center = (WIDTH // 2, HEIGHT // 2)
        self._draw_card(r, card, selected=True)
        tip = self.font_small.render("点击任意处返回", True, MUTED)
        self.screen.blit(tip, tip.get_rect(midtop=(WIDTH // 2, r.bottom + 14)))

    def _draw_compact_card(self, rect: pygame.Rect, card: Card, depth: int) -> None:
        img = self._card_image(card)
        if img is not None:
            scaled = pygame.transform.smoothscale(img, (rect.w, rect.h))
            self.screen.blit(scaled, rect.topleft)
            pygame.draw.rect(self.screen, PANEL_EDGE, rect, 1, border_radius=8)
            # 覆盖实时重量（卡面图不印数字，重量会随效果变化）
            self._draw_weight_overlay(rect, card.weight, logic=card.logic)
            return
        # 回退：程序绘制
        color = weight_color(card.weight)
        shade = max(0, 255 - depth * 28)
        bg = (shade, shade, shade)
        pygame.draw.rect(self.screen, bg, rect, border_radius=8)
        pygame.draw.rect(self.screen, color, rect, 2, border_radius=8)
        name = self.font_small.render(card.name, True, (30, 30, 38))
        self.screen.blit(name, name.get_rect(midtop=(rect.centerx, rect.y + 8)))
        weight = self.font_card.render(str(card.weight), True, color)
        self.screen.blit(weight, weight.get_rect(center=rect.center))
        lbl = self.font_small.render("重量", True, (30, 30, 38))
        self.screen.blit(lbl, lbl.get_rect(midbottom=(rect.centerx, rect.bottom - 6)))

    def _draw_log(self) -> None:
        # 日志界面：全屏半透明覆盖层，屏蔽所有其它交互
        if not self.log_visible:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        box = pygame.Rect(WIDTH // 2 - 420, 60, 840, 680)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=16)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=16)
        title = self.font_big.render("战斗日志", True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 22)))

        # 关闭按钮（右上角）
        self.log_close_btn = pygame.Rect(box.right - 46, box.y + 14, 32, 32)
        pygame.draw.rect(self.screen, (80, 70, 80), self.log_close_btn, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_EDGE, self.log_close_btn, 1, border_radius=8)
        xmark = self.font_small.render("×", True, (255, 255, 255))
        self.screen.blit(xmark, xmark.get_rect(center=self.log_close_btn.center))

        # 日志内容区（可滚动）
        content = pygame.Rect(box.x + 20, box.y + 66, box.width - 64, box.height - 96)
        log = self.engine.state.log
        line_h = self.font_small.get_height() + 4
        visible = max(1, content.height // line_h)
        total = len(log)
        self.log_scroll_max = max(0, total - visible)
        self.log_scroll = max(0, min(self.log_scroll, self.log_scroll_max))

        # 裁剪显示：超出内容区的行不绘制
        clip = self.screen.get_clip()
        self.screen.set_clip(content)
        y = content.y
        for line in log[self.log_scroll:self.log_scroll + visible]:
            surf = self.font_small.render(line, True, TEXT)
            self.screen.blit(surf, (content.x + 4, y))
            y += line_h
        self.screen.set_clip(clip)

        # 滚动条（右侧）
        if total > visible:
            track = pygame.Rect(content.right + 6, content.y, 12, content.height)
            self.log_scroll_track = track
            thumb_h = max(30, int(track.height * visible / total))
            ratio = self.log_scroll / self.log_scroll_max if self.log_scroll_max > 0 else 0
            thumb_y = track.y + int((track.height - thumb_h) * ratio)
            self.log_scroll_thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
            pygame.draw.rect(self.screen, (60, 64, 80), track, border_radius=6)
            pygame.draw.rect(self.screen, ACCENT, self.log_scroll_thumb, border_radius=6)
        else:
            self.log_scroll_track = pygame.Rect(0, 0, 0, 0)
            self.log_scroll_thumb = pygame.Rect(0, 0, 0, 0)

        tip = self.font_small.render("滚轮 / 拖拽滚动条浏览 · 点击外部或 × 关闭", True, MUTED)
        self.screen.blit(tip, tip.get_rect(midbottom=(box.centerx, box.bottom - 12)))

    # ---------- 调试控制台 ----------
    def _run_console_command(self, cmd: str) -> str:
        """执行控制台指令，返回反馈字符串。"""
        cmd = cmd.strip()
        if not cmd:
            return ""
        parts = cmd.split()
        head = parts[0].lower()

        # 地图迷雾控制（不依赖战斗引擎）
        if head == "unlock" and len(parts) >= 2 and parts[1].lower() == "all":
            if self.gmap is not None:
                for room in self.gmap.rooms.values():
                    room.revealed = True
            return "已解除迷雾（unlock all）"
        if head == "reset" and len(parts) >= 2 and parts[1].lower() == "fog":
            if self.gmap is not None:
                for room in self.gmap.rooms.values():
                    room.revealed = (room.id == self.gmap.player_pos)
            return "已重置迷雾（reset fog）"

        e = self.engine
        if e is None:
            return "错误：当前不在战斗中"

        def target_of(name: str):
            if name == "self":
                return e.state.player
            if name == "enemy":
                return e.state.enemy
            return None

        if head == "help":
            return "指令见 指令格式.txt；常用：status/hp/block/draw/give/endturn/win/lose/state/unlock all/reset fog"

        if head == "statuses":
            from game.status import STATUS_DEFS
            items = ", ".join(f"{k}({d.name})" for k, d in STATUS_DEFS.items())
            return f"可用状态：{items}"

        if head == "cards":
            from game.cards import CARD_DEFS
            items = ", ".join(f"{k}({d.name})" for k, d in CARD_DEFS.items())
            return f"可用卡牌：{items}"

        if head == "state":
            p = e.state.player
            en = e.state.enemy
            lines = [f"回合 {e.state.turn} | 玩家 hp {p.hp}/{p.max_hp} block {p.block}"]
            if en:
                lines.append(f"敌方 {en.name} hp {en.hp}/{en.max_hp} block {en.block}")
                lines.append("敌方状态: " + (", ".join(str(s) for s in en.active_statuses()) or "无"))
            lines.append("玩家状态: " + (", ".join(str(s) for s in p.active_statuses()) or "无"))
            return " | ".join(lines)

        if head == "status" and len(parts) >= 3:
            target = target_of(parts[1])
            if target is None:
                return f"错误：未知目标 {parts[1]}（self/enemy）"
            status = parts[2]
            stacks = int(parts[3]) if len(parts) >= 4 else 1
            target.add_status(status, stacks)
            return f"已给 {target.name} 施加 {status}×{stacks}（当前 {target.get_stacks(status)}）"

        if head == "hp" and len(parts) >= 3:
            target = target_of(parts[1])
            if target is None:
                return f"错误：未知目标 {parts[1]}"
            target.hp = max(0, min(int(parts[2]), target.max_hp))
            return f"{target.name} 生命设为 {target.hp}"

        if head == "block" and len(parts) >= 3:
            target = target_of(parts[1])
            if target is None:
                return f"错误：未知目标 {parts[1]}"
            target.block = max(0, int(parts[2]))
            return f"{target.name} 格挡设为 {target.block}"

        if head == "draw" and len(parts) >= 2:
            n = int(parts[1])
            drawn = e.draw_cards(n)
            return f"抽了 {len(drawn)} 张牌"

        if head == "give" and len(parts) >= 2:
            try:
                card = make_card(parts[1])
            except KeyError:
                return f"错误：未知卡牌 {parts[1]}"
            e.state.player.hand.append(card)
            return f"已将 {card.name} 加入手牌"

        if head == "endturn":
            if e.state.phase == Phase.PLAYER_ACTION:
                e.skip()
                e.start_turn()
                self.resolve_anim = None
                return "已结束回合"
            return "错误：当前不是玩家行动阶段"

        if head == "win":
            self.game_result = "victory"
            self.scene = "result"
            return "已触发胜利结算"

        if head == "lose":
            self.game_result = "defeat"
            self.scene = "result"
            return "已触发失败结算"

        return f"未知指令：{cmd}（输入 help 查看帮助）"

    def _handle_console_key(self, event) -> None:
        if event.key == pygame.K_BACKQUOTE or event.key == pygame.K_ESCAPE:
            self.console_active = False
            return
        if event.key == pygame.K_RETURN:
            result = self._run_console_command(self.console_input)
            if result:
                self.console_log.append("> " + self.console_input)
                self.console_log.append(result)
                self.console_log = self.console_log[-8:]
            self.console_input = ""
            return
        if event.key == pygame.K_BACKSPACE:
            self.console_input = self.console_input[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self.console_input += event.unicode

    def _draw_console(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 300, HEIGHT // 2 - 160, 600, 320)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=12)
        pygame.draw.rect(self.screen, PANEL_EDGE, box, 2, border_radius=12)
        title = self.font.render("调试控制台（` 关闭，回车执行）", True, TEXT)
        self.screen.blit(title, title.get_rect(topleft=(box.x + 16, box.y + 12)))
        # 日志区
        y = box.y + 48
        for line in self.console_log[-6:]:
            surf = self.font_small.render(line, True, YELLOW if line.startswith(">") else TEXT)
            self.screen.blit(surf, (box.x + 16, y))
            y += 22
        # 输入框
        input_rect = pygame.Rect(box.x + 16, box.bottom - 44, box.width - 32, 30)
        pygame.draw.rect(self.screen, (24, 26, 34), input_rect, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_EDGE, input_rect, 1, border_radius=6)
        prompt = self.font_small.render("> " + self.console_input, True, TEXT)
        self.screen.blit(prompt, prompt.get_rect(midleft=(input_rect.x + 8, input_rect.centery)))

    # ---------- 键盘分发 ----------
    def _dispatch_key(self, key: int) -> None:
        # 多怪堆叠：左右方向键切换聚焦的敌人
        if self.scene == "battle" and key in (pygame.K_LEFT, pygame.K_RIGHT):
            enemies = self._enemies()
            if len(enemies) > 1:
                delta = -1 if key == pygame.K_LEFT else 1
                self._view_enemy_idx = (self._view_enemy_idx + delta) % len(enemies)
                self._enemy_switch_anim = 0.0
            return
        # 多人 PVE：上下方向键切换查看的玩家卡槽组
        if self.scene == "battle" and key in (pygame.K_UP, pygame.K_DOWN):
            players = self._players()
            if len(players) > 1:
                delta = -1 if key == pygame.K_UP else 1
                self._view_player_idx = (self._view_player_idx + delta) % len(players)
            return
        if key == pygame.K_q:
            # 地图场景 / 战斗中的地图浮层：Q 切换危险度数字
            if self.scene == "map" or (self.scene == "battle" and self.map_view_active):
                self.show_danger = not self.show_danger
            elif self.scene == "reward":
                return
            else:
                self.running = False
            return
        if key == pygame.K_ESCAPE:
            if self.scene == "menu":
                self.running = False
            elif self.scene == "mode_select":
                self.scene = "menu"
            elif self.scene == "pvp_setup":
                self.scene = "menu"
            elif self.scene == "enemy_select":
                self.scene = "deck_edit"
            elif self.scene == "select":
                self.scene = "pvp_setup" if self.mode == "pvp" else "mode_select"
            elif self.scene == "deck_edit":
                self.scene = "select"
            elif self.scene == "map":
                # 先关闭头像详情 / 设置
                if self.hero_info_active:
                    self.hero_info_active = False
                    self.hero_info_selected_card = None
                elif self.settings_active:
                    self.settings_active = False
                elif self.map_mode == "room":
                    # 房间内容不可跳过
                    return
                else:
                    self.settings_active = True
            elif self.scene == "reward":
                # 奖励界面：选卡后才能继续；ESC 忽略
                return
            elif self.scene == "result":
                self.scene = "menu"
                self.game_result = None
                self.mode = None
            elif self.scene == "pvp_battle":
                if self.settings_active:
                    self.settings_active = False
                elif self.customizing is not None:
                    self.customizing = None
                    self.pending_hand_index = None
                    self.pending_slot = None
                elif self.viewing_pile is not None:
                    self.viewing_pile = None
            else:  # battle
                if self.map_view_active:
                    self.map_view_active = False
                elif self.settings_active:
                    self.settings_active = False
                elif self.hero_info_active:
                    self.hero_info_active = False
                elif self.customizing is not None:
                    self.customizing = None
                    self.pending_hand_index = None
                    self.pending_slot = None
                elif self.viewing_pile is not None:
                    self.viewing_pile = None
                elif getattr(self, "viewing_deck", None) is not None:
                    self.viewing_deck = None
                    self.deck_viewer_selected = None
                elif self.log_visible:
                    self.log_visible = False
                elif self.select_mode:
                    self._cancel_selection()
                else:
                    self.running = False
        elif key == pygame.K_s:
            if self.scene == "map" and self.map_mode == "select":
                self.scout_mode = not self.scout_mode
                self.paint_mode = False  # 侦查与画笔互斥
            elif self.scene == "pvp_battle" and self.customizing is None and not self.pvp_resolving:
                self._pvp_end_turn()
            elif self.scene == "battle" and self.mode == "pve" and self.customizing is None and not self.select_mode:
                self._pve_end_turn()
            elif self.scene == "battle" and self.customizing is None and not self.select_mode:
                self._start_resolution()
        elif key == pygame.K_b:
            if self.scene == "map" and self.map_mode == "select":
                self.paint_mode = not self.paint_mode
                self.scout_mode = False  # 画笔与侦查互斥
        elif key == pygame.K_d:
            if self.scene == "battle":
                self.log_visible = not self.log_visible

    def _handle_wheel(self, direction: int) -> None:
        """鼠标滚轮：牌组编辑页 / 战斗日志上下滚动。"""
        if self.scene == "deck_edit":
            self.deck_scroll += direction * 60
        elif self.scene == "battle" and self.log_visible:
            self.log_scroll = max(0, min(self.log_scroll_max, self.log_scroll - direction * 2))

    def _handle_pvp_join_key(self, event) -> None:
        """访客 IP 输入框的键盘处理。"""
        if event.key == pygame.K_RETURN:
            if self.pvp_join_ip:
                self._pvp_guest_join(self.pvp_join_port, host=self.pvp_join_ip.strip())
            return
        if event.key == pygame.K_BACKSPACE:
            self.pvp_join_ip = self.pvp_join_ip[:-1]
            return
        if event.key == pygame.K_ESCAPE:
            self.scene = "pvp_setup"
            return
        if event.unicode and (event.unicode.isdigit() or event.unicode == "."):
            if len(self.pvp_join_ip) < 15:
                self.pvp_join_ip += event.unicode

    def _handle_pve_join_key(self, event) -> None:
        """PVE 访客地址输入框的键盘处理（支持 "ip:端口"）。"""
        if event.key == pygame.K_RETURN:
            if self.pve_join_ip:
                self._pve_guest_join(self.pve_join_ip.strip())
            return
        if event.key == pygame.K_BACKSPACE:
            self.pve_join_ip = self.pve_join_ip[:-1]
            return
        if event.key == pygame.K_ESCAPE:
            self.scene = "pve_setup"
            return
        if event.unicode and (event.unicode.isdigit() or event.unicode == "." or event.unicode == ":"):
            if len(self.pve_join_ip) < 21:
                self.pve_join_ip += event.unicode

    # ---------- 主循环 ----------
    def run(self, smoke: bool = False) -> None:
        self.running = True
        if smoke:
            # 冒烟测试直接进入战斗场景，覆盖最复杂的渲染路径
            self._start_battle(HEROES[0])
        frames = 0
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if self.scene == "pvp_join_setup":
                        self._handle_pvp_join_key(event)
                    elif self.scene == "pve_join_setup":
                        self._handle_pve_join_key(event)
                    elif self.console_active:
                        self._handle_console_key(event)
                    elif event.key == pygame.K_BACKQUOTE:
                        self.console_active = True
                    else:
                        self._dispatch_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._dispatch_mouse_down(event.pos)
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_mouse_motion(event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.dragging_scrollbar = False
                    self.dragging_log_scrollbar = False
                    if self.scene == "battle":
                        self.handle_mouse_up(event.pos)
                    elif self.scene == "pvp_battle":
                        self._handle_pvp_mouse_up(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    self._handle_wheel(event.y)

            self._pvp_poll()
            self._pvp_update_anim()
            self._pve_poll()
            self._update_resolution()
            self._update_hp_anim()
            self._spawn_damage_floats()
            self._update_float_texts()
            self.draw()
            self.clock.tick(FPS)
            frames += 1
            if smoke and frames >= 5:
                self.running = False

        self._pvp_cleanup()
        self._pve_cleanup()
        pygame.quit()

    def _update_hp_anim(self) -> None:
        """血条/格挡显示值平滑过渡到真实值（扣血扣格挡动画）。"""
        # 牌堆滑出动画：拖拽放牌时快速展开，平时收起（速度更快）
        target = 1.0 if self.dragging is not None else 0.0
        self._slot_slide += (target - self._slot_slide) * 0.6
        if abs(target - self._slot_slide) < 0.01:
            self._slot_slide = target
        # 多怪切换动画进度推进
        if getattr(self, "_enemy_switch_anim", 1.0) < 1.0:
            self._enemy_switch_anim = min(1.0, self._enemy_switch_anim + 0.12)
        if self.engine is None:
            return
        p = self.engine.state.player
        targets = {"self": (float(p.hp), float(p.block))}
        for i, e in enumerate(self.engine.state.enemies):
            targets[f"enemy{i}"] = (float(e.hp), float(e.block))
        for key, (thp, tblock) in targets.items():
            if key not in self.disp_hp:
                self.disp_hp[key] = float(thp)
                self.disp_block[key] = float(tblock)
            # 血量向目标靠近（快速）
            self.disp_hp[key] += (thp - self.disp_hp[key]) * 0.2
            if abs(thp - self.disp_hp[key]) < 0.5:
                self.disp_hp[key] = thp
            # 格挡向目标靠近
            self.disp_block[key] += (tblock - self.disp_block[key]) * 0.2
            if abs(tblock - self.disp_block[key]) < 0.5:
                self.disp_block[key] = tblock

    # ---------- 伤害飘字动画 ----------
    _FLOAT_LIFETIME = 40

    def _float_pos(self, target) -> tuple[int, int]:
        """返回某个受伤目标的飘字起始位置。"""
        if any(p is target for p in self._players()):
            return (self.player_area.centerx, self.player_area.y + 30)
        enemies = self._enemies()
        for i, e in enumerate(enemies):
            if e is target:
                area = self._side_area(self.enemy_area, i, max(1, len(enemies)))
                return (area.centerx, area.y + 30)
        return (self.enemy_area.centerx, self.enemy_area.y + 30)

    def _spawn_damage_floats(self) -> None:
        """消费引擎记录的本帧伤害事件，转成飘字。"""
        if self.engine is None:
            return
        for target, amount in self.engine.damage_floats:
            x, y = self._float_pos(target)
            self.float_texts.append(
                {"x": x, "y": y, "text": str(amount), "timer": self._FLOAT_LIFETIME}
            )
        self.engine.damage_floats.clear()

    def _update_float_texts(self) -> None:
        """飘字每帧上移并递减计时。"""
        for ft in self.float_texts:
            ft["timer"] -= 1
            ft["y"] -= 1.5
        self.float_texts = [ft for ft in self.float_texts if ft["timer"] > 0]

    def _draw_float_texts(self) -> None:
        """渲染飘字（红色，随计时淡出）。"""
        for ft in self.float_texts:
            alpha = max(0, int(255 * ft["timer"] / self._FLOAT_LIFETIME))
            surf = self.font_big.render(ft["text"], True, (255, 80, 80))
            surf.set_alpha(alpha)
            self.screen.blit(surf, surf.get_rect(center=(int(ft["x"]), int(ft["y"]))))


def main() -> None:
    smoke = "--smoke" in sys.argv
    app = GameApp()
    # PVP 访客模式：--pvp-guest <port>
    if "--pvp-guest" in sys.argv:
        idx = sys.argv.index("--pvp-guest")
        port = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 0
        app._pvp_guest_join(port)
    app.run(smoke=smoke)


if __name__ == "__main__":
    main()
