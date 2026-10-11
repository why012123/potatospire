"""战斗奖励系统的单元测试。"""

from __future__ import annotations

import random

from game.card import Rarity
from game.cards import get_card_def
from game.reward import (
    GOLD_MAX,
    GOLD_MIN,
    RELIC_CHANCE,
    reward_card_pool,
    roll_reward_cards,
    roll_reward_gold,
    roll_reward_relic,
    roll_rarity,
)


def test_reward_gold_range():
    rng = random.Random(0)
    for _ in range(500):
        g = roll_reward_gold(rng)
        assert GOLD_MIN <= g <= GOLD_MAX


def test_reward_card_pool_excludes_other_hero():
    # 蒸蛋的奖励卡池不应包含邦尼/鼠鼠特有牌
    pool = reward_card_pool("蒸蛋")
    all_keys = {k for keys in pool.values() for k in keys}
    assert "poison_enchant" not in all_keys  # 邦尼
    assert "body_slam" not in all_keys       # 鼠鼠
    assert "guilt" not in all_keys           # 诅咒牌
    # 包含公共牌和蒸蛋特有牌
    assert "strike" in all_keys
    assert "weakness_survey" in all_keys


def test_roll_reward_cards_are_legal():
    rng = random.Random(1)
    for _ in range(100):
        cards = roll_reward_cards("蒸蛋", count=3, rng=rng)
        assert len(cards) == 3
        for key in cards:
            d = get_card_def(key)
            assert d.rarity is not Rarity.CURSE
            # 不能是别的角色特有牌
            assert d.hero in (None, "蒸蛋")


def test_roll_rarity_distribution():
    rng = random.Random(0)
    n = 30000
    counts = {Rarity.RARE: 0, Rarity.UNCOMMON: 0, Rarity.COMMON: 0}
    for _ in range(n):
        counts[roll_rarity(rng)] += 1
    assert abs(counts[Rarity.RARE] / n - 0.10) < 0.02
    assert abs(counts[Rarity.UNCOMMON] / n - 0.25) < 0.03
    assert abs(counts[Rarity.COMMON] / n - 0.65) < 0.03


def test_roll_reward_relic_chance():
    rng = random.Random(0)
    hits = sum(1 for _ in range(20000) if roll_reward_relic(rng) is not None)
    ratio = hits / 20000
    assert abs(ratio - RELIC_CHANCE) < 0.03
