from __future__ import annotations

from dataclasses import dataclass, field

from .card import Card
from .character import Character
from .pile import Pile
from .potions import Potion


@dataclass
class Player(Character):
    max_slots: int = 4
    # 被动：每回合额外多抽的牌数（蒸蛋 = 1）
    extra_draw: int = 0
    # 被动：攻击牌起效时对目标施加一层标记（邦尼 = True）
    mark_on_attack: bool = False
    # 被动：回合结束时格挡不重置（鼠鼠 = True）
    keep_block: bool = False
    # 被动：每受到一次伤害，自身「韧性」状态 +1（鼠鼠 = True）
    gain_resilience_on_hit: bool = False
    # 被动：每回合指定一个敌人施诅咒（阿兰娜 = True）
    curse_on_turn: bool = False
    # 诅咒伤害倍率（阿兰娜 = 1.5）
    curse_mult: float = 1.0
    # 恰如其分「目标」效果：本场是否已开启，当前目标层数（初始 1，每回合 +1，到 10 回 1）
    has_target: bool = False
    target_level: int = 1
    hand: list[Card] = field(default_factory=list)
    draw_pile: list[Card] = field(default_factory=list)
    discard_pile: list[Card] = field(default_factory=list)
    pile_slots: list[Pile] = field(default_factory=list)
    # 本回合每个槽位已放牌数量（索引对应槽位）
    pile_turn_counts: list[int] = field(default_factory=list)
    # 消耗牌堆：本场战斗已消耗、无法再使用的牌
    exhaust_pile: list[Card] = field(default_factory=list)
    # 药水槽：持有的药水（战斗中使用）
    potions: list[Potion] = field(default_factory=list)
    # 本回合已打出的攻击牌数量（潜伏判断用）
    attacks_played_this_turn: int = 0
    # 稀释血清：可用时受致命伤害触发（仅一次）
    dilute_serum: bool = False
    # 本次战斗是否已触发过稀释血清
    dilute_serum_used: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.pile_slots:
            self.pile_slots = [Pile() for _ in range(self.max_slots)]
        if len(self.pile_slots) != self.max_slots:
            raise ValueError("pile_slots 数量必须等于 max_slots")
        if len(self.pile_turn_counts) != self.max_slots:
            self.pile_turn_counts = [0] * self.max_slots

    def take_damage(self, amount: int) -> int:
        """受到伤害，额外触发「每失去一次血量韧性 +1」被动与「稀释血清」保护。"""
        dealt = super().take_damage(amount)
        # 稀释血清：受致命伤害时恢复 100% 生命，但生命上限 -20（仅一次）
        if self.dilute_serum and self.hp <= 0:
            self.dilute_serum = False
            self.dilute_serum_used = True
            self.max_hp = max(1, self.max_hp - 20)
            self.hp = self.max_hp
            return 0
        if self.gain_resilience_on_hit and dealt > 0:
            self.add_status("resilience", 1)
        return dealt
