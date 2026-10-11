"""战斗奖励系统：普通战斗结束后的金币 / 遗物 / 卡牌奖励（纯逻辑，与 UI 解耦）。

普通战斗结束后：
  - 一定获得 35~50 金币；
  - 10% 概率获得一个随机遗物；
  - 100% 获得一次卡牌奖励：3 张随机牌选一张（不能是别的角色特有牌），
    单张稀有度：金卡 10% / 蓝卡 25% / 普卡 65%。
"""

from __future__ import annotations

import random

from .card import Rarity
from .cards import CARD_DEFS, get_card_def, hero_card_keys, public_card_keys
from .relics import RELIC_DEFS, make_relic

GOLD_MIN = 35
GOLD_MAX = 50
RELIC_CHANCE = 0.10

# 精英战斗奖励
ELITE_GOLD_MIN = 70
ELITE_GOLD_MAX = 90
ELITE_RELIC_CHANCE = 0.35

# 单张卡牌稀有度权重：金 / 蓝 / 普
_RARITY_WEIGHTS: tuple[tuple[float, Rarity], ...] = (
    (0.10, Rarity.RARE),
    (0.35, Rarity.UNCOMMON),
    (1.00, Rarity.COMMON),
)

# 稀有度归组：SPECIAL 归入金，STARTER 归入普
def _rarity_bucket(rarity: Rarity) -> Rarity:
    if rarity in (Rarity.RARE, Rarity.SPECIAL):
        return Rarity.RARE
    if rarity is Rarity.UNCOMMON:
        return Rarity.UNCOMMON
    return Rarity.COMMON


def reward_card_pool(hero_key: str) -> dict[Rarity, list[str]]:
    """返回当前角色可获得的卡池，按稀有度分组（排除诅咒牌与别的角色特有牌）。"""
    keys = public_card_keys() + hero_card_keys(hero_key)
    pool: dict[Rarity, list[str]] = {Rarity.COMMON: [], Rarity.UNCOMMON: [], Rarity.RARE: []}
    for key in keys:
        d = get_card_def(key)
        if d.rarity is Rarity.CURSE:
            continue
        pool[_rarity_bucket(d.rarity)].append(key)
    return pool


def roll_rarity(rng: random.Random) -> Rarity:
    """按 金 10% / 蓝 25% / 普 65% 掷一个稀有度档次。"""
    roll = rng.random()
    for threshold, rarity in _RARITY_WEIGHTS:
        if roll < threshold:
            return rarity
    return Rarity.COMMON


def roll_reward_cards(hero_key: str, count: int = 3, rng: random.Random | None = None) -> list[str]:
    """生成战斗奖励的 count 张随机卡（不能是别的角色特有牌）。

    每张卡先按稀有度权重决定档次，再从该档可用池里抽；若该档无牌则向下一档回退。
    """
    rng = rng or random.Random()
    pool = reward_card_pool(hero_key)
    picked: list[str] = []
    for _ in range(count):
        rarity = roll_rarity(rng)
        candidates = pool.get(rarity, [])
        # 回退：金 → 蓝 → 普
        if not candidates and rarity is Rarity.RARE:
            candidates = pool.get(Rarity.UNCOMMON, [])
            rarity = Rarity.UNCOMMON
        if not candidates and rarity is Rarity.UNCOMMON:
            candidates = pool.get(Rarity.COMMON, [])
            rarity = Rarity.COMMON
        if not candidates:
            continue
        picked.append(rng.choice(candidates))
    return picked


def roll_reward_gold(rng: random.Random | None = None) -> int:
    """掷普通战斗金币奖励（35~50）。"""
    rng = rng or random.Random()
    return rng.randint(GOLD_MIN, GOLD_MAX)


def roll_reward_relic(rng: random.Random | None = None) -> str | None:
    """20% 概率掷一个随机遗物 key；未触发返回 None。"""
    rng = rng or random.Random()
    if rng.random() >= RELIC_CHANCE:
        return None
    keys = list(RELIC_DEFS.keys())
    return rng.choice(keys) if keys else None


def roll_elite_gold(rng: random.Random | None = None) -> int:
    """掷精英战斗金币奖励（70~90）。"""
    rng = rng or random.Random()
    return rng.randint(ELITE_GOLD_MIN, ELITE_GOLD_MAX)


def roll_elite_relic(rng: random.Random | None = None) -> str | None:
    """50% 概率掷一个随机遗物 key；未触发返回 None。"""
    rng = rng or random.Random()
    if rng.random() >= ELITE_RELIC_CHANCE:
        return None
    keys = list(RELIC_DEFS.keys())
    return rng.choice(keys) if keys else None
