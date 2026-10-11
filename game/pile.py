from __future__ import annotations

from dataclasses import dataclass, field

from .card import Card


class WeightRuleError(ValueError):
    """违反重量堆叠规则。"""


@dataclass
class Pile:
    # index 0 是顶部，index -1 是底部
    cards: list[Card] = field(default_factory=list)

    @property
    def top(self) -> Card | None:
        return self.cards[0] if self.cards else None

    def is_empty(self) -> bool:
        return not self.cards

    def can_add(self, card: Card) -> bool:
        if not self.cards:
            return True
        # 只有严格更轻的牌才能叠到顶部；重量相同也不能叠放。
        return card.weight < self.cards[0].weight

    def add_to_top(self, card: Card) -> None:
        if not self.can_add(card):
            top = self.cards[0]
            raise WeightRuleError(
                f"不能把 {card} 放到 {top} 上面：新卡更重或重量相同"
            )
        self.cards.insert(0, card)

    def snapshot_top_to_bottom(self) -> list[Card]:
        return list(self.cards)
