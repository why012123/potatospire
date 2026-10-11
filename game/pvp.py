"""PVP 对战模型（纯逻辑，与 UI / 网络解耦）。

两名玩家各自拥有 4 个牌堆与手牌，共用一套卡牌效果结算逻辑（复用 Engine.play_card）。
每回合流程：
  1. 双方各自往牌堆放牌（本地操作，互不干扰）；
  2. 双方都「结束回合」后，比较「待生效派对总负重」（所有牌堆卡牌重量之和），
     总负重更小的一方先结算；
  3. 依次结算双方的最前牌堆（从顶到底打出，效果作用于对手）；
  4. 双方状态判定、格挡/隐匿重置、抽牌，进入下一回合；
  5. 一方生命归零则分出胜负。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .card import Card
from .engine import Engine
from .player import Player
from .state import GameState, Phase


def pending_weight(player: Player) -> int:
    """待生效派对总负重：所有牌堆卡牌重量之和。"""
    return sum(card.weight for pile in player.pile_slots for card in pile.cards)


@dataclass
class PvpMatch:
    """一场本地双人对战。"""

    p1: Player
    p2: Player
    hero_name_1: str = "玩家一"
    hero_name_2: str = "玩家二"
    turn: int = 0
    # 本回合双方是否已「结束回合」
    p1_ready: bool = False
    p2_ready: bool = False
    # 结算顺序：本回合先手方（1 或 2）
    order: list[int] = field(default_factory=list)
    # 胜利者：None / 1 / 2
    winner: int | None = None
    # 本轮结算动画序列：[{source, card, text}]
    last_animations: list[dict] = field(default_factory=list)
    # 固定种子 rng：保证房主与访客各自独立结算时结果完全一致
    rng: random.Random = field(default_factory=lambda: random.Random(0))

    def __post_init__(self) -> None:
        # 双方各持一个 Engine：player=自己，enemy=对手，复用卡牌效果结算
        self._e1 = Engine(GameState(player=self.p1, enemy=self.p2), rng=self.rng)
        self._e2 = Engine(GameState(player=self.p2, enemy=self.p1), rng=self.rng)

    def start(self) -> None:
        """开始对局：双方抽初始手牌，重置放牌计数与活跃槽位。"""
        for idx in (1, 2):
            p = self.player(idx)
            e = self.engine(idx)
            p.pile_turn_counts = [0] * p.max_slots
            e.state.active_slots = p.max_slots
            e.state.phase = Phase.PLAYER_ACTION
            e.draw_cards(5 + p.extra_draw)

    # ---------- 查询 ----------
    def player(self, idx: int) -> Player:
        return self.p1 if idx == 1 else self.p2

    def engine(self, idx: int) -> Engine:
        return self._e1 if idx == 1 else self._e2

    def _ready_count(self) -> int:
        return int(self.p1_ready) + int(self.p2_ready)

    # ---------- 回合推进 ----------
    def set_ready(self, idx: int) -> None:
        """某方点击「结束回合」：弃掉剩余手牌并标记就绪。"""
        p = self.player(idx)
        # 弃掉剩余手牌
        p.discard_pile.extend(p.hand)
        p.hand.clear()
        if idx == 1:
            self.p1_ready = True
        else:
            self.p2_ready = True
        if self._ready_count() == 2:
            self.resolve_round()

    def resolve_round(self) -> None:
        """双方都结束回合后，结算一整回合。"""
        self.turn += 1
        # 弃掉双方剩余手牌（网络路径绕过 set_ready，需在此统一处理，避免手牌累积）
        for idx in (1, 2):
            p = self.player(idx)
            p.discard_pile.extend(p.hand)
            p.hand.clear()
        w1 = pending_weight(self.p1)
        w2 = pending_weight(self.p2)
        # 总负重小者先手；相同则玩家一先手
        self.order = [1, 2] if w1 <= w2 else [2, 1]
        self.last_animations = []

        for idx in self.order:
            if self.winner is not None:
                break
            self._resolve_front_pile(idx)

        # 状态判定（每个角色各处理一次，处理顺序：先手方先）
        for idx in self.order:
            e = self.engine(idx)
            e._process_statuses(self.player(idx))

        # 胜负判定
        if not self.p1.is_alive and not self.p2.is_alive:
            self.winner = 0  # 平局
        elif not self.p1.is_alive:
            self.winner = 2
        elif not self.p2.is_alive:
            self.winner = 1

        # 进入下一回合（除非已结束）
        if self.winner is None:
            self._start_next_round()

    def _resolve_front_pile(self, idx: int) -> None:
        """结算某方最前牌堆：从顶到底打出，效果作用于对手。"""
        e = self.engine(idx)
        player = self.player(idx)
        # 冰冻：本回合牌堆不向前推进
        frozen = player.get_stacks("frozen")
        if frozen > 0:
            player.set_stacks("frozen", frozen - 1)
            e.log(f"{player.name} 被冰冻，牌堆不向前推进")
            return

        from .pile import Pile

        front = player.pile_slots[0]
        cards = front.snapshot_top_to_bottom()
        e.resolution_queue = list(cards)
        e.resolution_snapshot = list(cards)
        e.attack_bonus = 0
        for card in cards:
            e.resolution_queue.pop(0)
            target = "enemy"  # 对手
            e.play_card(card, target=target)
            text = e.state.log[-1] if e.state.log else card.name
            self.last_animations.append({"source": idx, "card": card, "text": text})
        # 移除最前牌堆，后续前移，末尾补空
        player.pile_slots.pop(0)
        player.pile_slots.append(Pile())
        e.log(f"{player.name} 结算完成")

    def _start_next_round(self) -> None:
        """回合收尾：格挡/隐匿重置、抽牌、重置 ready 标记。"""
        for idx in (1, 2):
            p = self.player(idx)
            if not p.keep_block:
                p.block = 0
            p.remove_status("hide")
            p.attacks_played_this_turn = 0
            p.pile_turn_counts = [0] * p.max_slots
            e = self.engine(idx)
            e.state.active_slots = p.max_slots
            e.state.phase = Phase.PLAYER_ACTION
            e.draw_cards(5 + p.extra_draw)
        self.p1_ready = False
        self.p2_ready = False
        # 保留 self.order 供 UI 展示本回合先手顺序


def build_pvp_player(
    hero, deck: dict[str, int], hp_multiplier: float = 1.0, rng: random.Random | None = None
) -> Player:
    """按角色定义 + 牌组构建一个 PVP 玩家（血量 = max_hp × 乘数）。"""
    from .cards import build_deck
    from .heroes import char_image_path

    rng = rng or random.Random()
    cards = build_deck(deck)
    rng.shuffle(cards)
    max_hp = max(1, int(hero.max_hp * hp_multiplier))
    return Player(
        name=hero.name,
        max_hp=max_hp,
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
