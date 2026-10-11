from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .enemy import Enemy
from .player import Player


class Phase(Enum):
    TURN_START = auto()
    PLAYER_ACTION = auto()
    CLEAR_HAND = auto()
    STATUS = auto()
    RESOLVE_PILE = auto()
    MONSTER = auto()
    TURN_END = auto()


@dataclass
class GameState:
    player: Player
    turn: int = 0
    active_slots: int = 3
    phase: Phase = Phase.TURN_START
    log: list[str] = field(default_factory=list)
    enemy: Enemy | None = None   # 兼容旧单怪引用（第一个敌人）
    enemies: list[Enemy] = field(default_factory=list)  # 多怪：本场所有敌人

    def __post_init__(self) -> None:
        if self.enemies and self.enemy is None:
            self.enemy = self.enemies[0]
        elif self.enemy is not None and not self.enemies:
            self.enemies = [self.enemy]

    @property
    def alive_enemies(self) -> list[Enemy]:
        """当前还活着的敌人列表。"""
        return [e for e in self.enemies if e.is_alive]
