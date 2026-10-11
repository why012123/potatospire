"""商店系统：定价与商品生成（纯逻辑，与 UI 解耦）。

商店出售：
  - 卡牌：按稀有度定价，偶尔有特价（低价，UI 用红色显示）；
  - 遗物 / 药水：占位，暂不生成实际商品；
  - 删牌服务：初始 75 金币，每删一张 +50。

新增卡牌稀有度定价只需在 `PRICE_RANGES` 补充即可。
"""

from __future__ import annotations

import random

from .card import Rarity
from .cards import get_card_def, hero_card_keys, public_card_keys

# 稀有度 → 价格区间（普通 60~80 / 蓝 90~150 / 金 160~240）
PRICE_RANGES: dict[Rarity, tuple[int, int]] = {
    Rarity.STARTER: (60, 80),
    Rarity.COMMON: (60, 80),
    Rarity.UNCOMMON: (90, 150),
    Rarity.RARE: (160, 240),
    Rarity.SPECIAL: (160, 240),
}

# 特价概率与折扣区间
DISCOUNT_CHANCE = 0.10
DISCOUNT_RATIO = (0.2, 0.6)

# 删牌服务：初始价 + 每次加价
REMOVE_BASE_PRICE = 75
REMOVE_STEP_PRICE = 50


def price_range(rarity: Rarity) -> tuple[int, int]:
    """返回某稀有度的价格区间（未知稀有度回退普通价）。"""
    return PRICE_RANGES.get(rarity, (60, 80))


def roll_price(rarity: Rarity, rng: random.Random) -> tuple[int, bool]:
    """按稀有度掷一个价格，返回 (价格, 是否特价)。"""
    lo, hi = price_range(rarity)
    price = rng.randint(lo, hi)
    discounted = rng.random() < DISCOUNT_CHANCE
    if discounted:
        price = max(1, int(price * rng.uniform(*DISCOUNT_RATIO)))
    return price, discounted


def shop_card_keys(hero_key: str) -> list[str]:
    """商店可售卖的卡牌 key（公共 + 角色特有，排除诅咒牌）。"""
    keys = public_card_keys() + hero_card_keys(hero_key)
    return [k for k in keys if get_card_def(k).rarity is not Rarity.CURSE]


def generate_offers(
    hero_key: str,
    count: int = 3,
    rng: random.Random | None = None,
) -> list[tuple[str, int, bool]]:
    """生成商店卡牌商品：[(key, 价格, 是否特价)]。"""
    rng = rng or random.Random()
    pool = shop_card_keys(hero_key)
    if not pool:
        return []
    picked = rng.sample(pool, min(count, len(pool)))
    offers: list[tuple[str, int, bool]] = []
    for key in picked:
        rarity = get_card_def(key).rarity
        price, discounted = roll_price(rarity, rng)
        offers.append((key, price, discounted))
    return offers


def remove_service_price(removed_count: int) -> int:
    """删牌服务当前价格：初始 75，每删一张 +50。"""
    return REMOVE_BASE_PRICE + REMOVE_STEP_PRICE * removed_count
