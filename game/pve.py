"""多人合作 PVE 对战模型（纯逻辑，与 UI / 网络解耦）。

N 名玩家（最多 4 人）合作对抗一组敌人。每回合流程：
  1. 每名玩家独立放牌到自己的 4 个牌堆；
  2. 每人点「结束回合」后，全员就绪，房主统一结算：
     - 每名玩家最前牌堆从顶到底打出，效果作用于敌人；
     - 怪物回合：每个存活敌人对每个存活玩家各执行一次意图；
     - 状态判定、胜负判定；
  3. 下一回合：格挡清零、抽牌、怪加防御、重置就绪标记。

房主权威：结算由房主完成，访客只上报牌堆布局、接收完整状态。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .card import Card
from .enemy import Enemy
from .engine import Engine
from .pile import Pile
from .player import Player
from .state import GameState, Phase


def build_pve_player(hero, deck: dict[str, int], rng: random.Random | None = None) -> Player:
    """按角色定义 + 牌组构建一个 PVE 玩家（血量 = max_hp，不乘乘数）。"""
    from .cards import build_deck
    from .heroes import char_image_path

    rng = rng or random.Random()
    cards = build_deck(deck)
    rng.shuffle(cards)
    return Player(
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


@dataclass
class PveMatch:
    """一场多人合作 PVE 对局。"""

    players: list[Player]
    enemies: list[Enemy]
    hero_names: list[str] = field(default_factory=list)
    turn: int = 0
    # 每名玩家是否已「结束回合」
    ready_flags: list[bool] = field(default_factory=list)
    # 胜负：None 未结束 / True 玩家胜 / False 玩家败
    winner: bool | None = None
    # 本轮结算动画序列：[{source, card, text}]
    last_animations: list[dict] = field(default_factory=list)
    # 待播放的动画序列（访客从 state 接收）
    pending_anims: list[dict] = field(default_factory=list)
    rng: random.Random = field(default_factory=lambda: random.Random(0))

    def __post_init__(self) -> None:
        n = len(self.players)
        if not self.ready_flags:
            self.ready_flags = [False] * n
        if not self.hero_names:
            self.hero_names = [p.name for p in self.players]
        # 每个玩家各持一个 Engine：player=自己，enemies=共享敌人列表
        shared_log: list[str] = []
        self.engines: list[Engine] = []
        for p in self.players:
            st = GameState(player=p, enemies=self.enemies)
            st.log = shared_log  # 共享日志，避免结算日志分散
            e = Engine(st, rng=self.rng)
            e.state.enemies = self.enemies
            e.state.players = self.players  # 供 UI 多玩家显示
            self.engines.append(e)

    # ---------- 查询 ----------
    def player(self, idx: int) -> Player:
        return self.players[idx]

    def engine(self, idx: int) -> Engine:
        return self.engines[idx]

    def alive_players(self) -> list[Player]:
        return [p for p in self.players if p.is_alive]

    def alive_enemies(self) -> list[Enemy]:
        return [e for e in self.enemies if e.is_alive]

    def all_ready(self) -> bool:
        return all(self.ready_flags)

    def start(self) -> None:
        """开始对局：怪加防御，每人抽初始手牌。"""
        authoritative = self.engines[0]
        for idx in range(len(self.players)):
            p = self.player(idx)
            e = self.engine(idx)
            p.pile_turn_counts = [0] * p.max_slots
            e.state.active_slots = p.max_slots
            e.state.phase = Phase.PLAYER_ACTION
            e.draw_cards(5 + p.extra_draw)
        # 回合开始：怪加防御
        authoritative._enemy_defend_at_turn_start()

    # ---------- 回合推进 ----------
    def set_ready(self, idx: int) -> None:
        """某玩家点「结束回合」：弃掉剩余手牌并标记就绪。"""
        p = self.player(idx)
        p.discard_pile.extend(p.hand)
        p.hand.clear()
        self.ready_flags[idx] = True
        if self.all_ready():
            self.resolve_round()

    def resolve_round(self) -> None:
        """全员就绪后结算一整回合。"""
        authoritative = self.engines[0]
        self.turn += 1
        # 弃掉所有玩家剩余手牌（网络路径绕过 set_ready，需在此统一处理）
        for p in self.players:
            p.discard_pile.extend(p.hand)
            p.hand.clear()
        self.last_animations = []

        # 1. 每名玩家结算最前牌堆（打怪）
        for idx in range(len(self.players)):
            if self.winner is not None:
                break
            if self.player(idx).is_alive:
                self._resolve_front_pile(idx)

        # 2. 怪物回合：每个存活敌人对每个存活玩家执行意图
        self._enemy_phase()

        # 3. 状态判定
        for p in self.alive_players():
            authoritative._process_statuses(p)
        for e in self.alive_enemies():
            authoritative._process_statuses(e)

        # 4. 胜负判定
        self._check_winner()

        # 5. 下一回合（除非已结束）
        if self.winner is None:
            self._start_next_round()

    def _resolve_front_pile(self, idx: int) -> None:
        """结算某玩家最前牌堆：从顶到底打出，效果作用于敌人。"""
        e = self.engine(idx)
        player = self.player(idx)
        frozen = player.get_stacks("frozen")
        if frozen > 0:
            player.set_stacks("frozen", frozen - 1)
            e.log(f"{player.name} 被冰冻，牌堆不向前推进")
            return

        front = player.pile_slots[0]
        cards = front.snapshot_top_to_bottom()
        e.resolution_queue = list(cards)
        e.resolution_snapshot = list(cards)
        e.attack_bonus = 0
        for card in cards:
            e.resolution_queue.pop(0)
            # 自动选择第一个存活的敌人作为目标
            e.play_card(card, target=None)
            text = e.state.log[-1] if e.state.log else card.name
            self.last_animations.append({"source": idx, "card": card, "text": text})
        player.pile_slots.pop(0)
        player.pile_slots.append(Pile())
        e.log(f"{player.name} 结算完成")

    def _enemy_phase(self) -> None:
        """怪物回合：攻击类意图对每个存活玩家各执行一次，自身增益只执行一次。"""
        authoritative = self.engines[0]
        players = self.alive_players()
        # 对目标玩家生效（每个玩家独立结算）的意图
        per_player_kinds = {"attack", "multi", "attack_block", "attack_strength", "shrink"}
        for enemy in self.alive_enemies():
            enemy.slow_counter = 0
            frozen = enemy.get_stacks("frozen")
            if frozen > 0:
                enemy.set_stacks("frozen", frozen - 1)
                authoritative.log(f"{enemy.name} 被冰冻，跳过本回合行动")
                authoritative._apply_territorial(enemy)
                continue
            intent, kind = authoritative._peek_enemy_intent(enemy)
            if intent is not None:
                if intent.kind in per_player_kinds:
                    for p in players:
                        authoritative._execute_intent(enemy, intent, target_player=p)
                else:
                    # 自身增益（力量/格挡/沉睡）只执行一次
                    authoritative._execute_intent(enemy, intent)
                authoritative._advance_enemy_intent(enemy, kind)
            else:
                for p in players:
                    p.take_damage(enemy.attack)
                authoritative.log(f"{enemy.name} 攻击，造成 {enemy.attack} 点伤害")
            authoritative._apply_territorial(enemy)

    def _check_winner(self) -> None:
        """胜负判定：所有敌人死亡=玩家胜；所有玩家死亡=玩家败。"""
        # 血清：敌人生命上限被削到 1 时直接击败
        for e in self.alive_enemies():
            if e.get_stacks("serum") > 0 and e.max_hp <= 1:
                e.hp = 0
        if not self.alive_enemies():
            self.winner = True
            return
        if not self.alive_players():
            self.winner = False

    def _start_next_round(self) -> None:
        """回合收尾：格挡清零、怪加防御、抽牌、重置就绪标记。"""
        authoritative = self.engines[0]
        for idx in range(len(self.players)):
            p = self.player(idx)
            e = self.engine(idx)
            if not p.keep_block:
                p.block = 0
            p.remove_status("hide")
            p.attacks_played_this_turn = 0
            p.pile_turn_counts = [0] * p.max_slots
            e.state.active_slots = p.max_slots
            e.state.phase = Phase.PLAYER_ACTION
            e.draw_cards(5 + p.extra_draw)
        # 怪物格挡清零 + 怪加防御（下回合的防御在回合开始生效）
        for enemy in self.enemies:
            if enemy.get_stacks("synergy_defense") <= 0:
                enemy.block = 0
            enemy.temp_strength = 0
        authoritative._enemy_defend_at_turn_start()
        self.ready_flags = [False] * len(self.players)
