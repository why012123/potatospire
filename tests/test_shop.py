"""商店定价与老板娘大甩卖事件的单元测试。"""

from __future__ import annotations

import random

from game.card import Rarity
from game.cards import get_card_def
from game.events import EVENTS, get_event
from game.relics import get_relic_def, make_relic
from game.shop import (
    generate_offers,
    price_range,
    remove_service_price,
    roll_price,
    shop_card_keys,
)


# ---------- 定价 ----------
def test_price_ranges():
    assert price_range(Rarity.COMMON) == (60, 80)
    assert price_range(Rarity.UNCOMMON) == (90, 150)
    assert price_range(Rarity.RARE) == (160, 240)


def test_roll_price_within_range():
    rng = random.Random(0)
    for _ in range(500):
        price, _ = roll_price(Rarity.UNCOMMON, rng)
        # 特价可能低于区间下限，但不会低于 1
        assert price >= 1


def test_roll_price_common_full_range_no_discount():
    rng = random.Random(0)
    # 抽样确保普通卡存在非特价且落在 60~80 区间的样本
    saw_normal = False
    for _ in range(200):
        price, discounted = roll_price(Rarity.COMMON, rng)
        if not discounted:
            assert 60 <= price <= 80
            saw_normal = True
    assert saw_normal


def test_remove_service_price():
    assert remove_service_price(0) == 75
    assert remove_service_price(1) == 125
    assert remove_service_price(3) == 225


# ---------- 商品生成 ----------
def test_shop_card_keys_exclude_curse():
    keys = shop_card_keys("蒸蛋")
    assert "guilt" not in keys
    for k in keys:
        assert get_card_def(k).rarity is not Rarity.CURSE


def test_shop_card_keys_no_pool_leak():
    # 商店卡池不能串池：蒸蛋商店不应出现邦尼/鼠鼠特有牌
    keys = shop_card_keys("蒸蛋")
    for k in keys:
        d = get_card_def(k)
        assert d.hero in (None, "蒸蛋"), f"串池: {k} -> {d.hero}"
    # 邦尼商店不含蒸蛋特有牌
    bunny = shop_card_keys("邦尼")
    for k in bunny:
        d = get_card_def(k)
        assert d.hero in (None, "邦尼"), f"串池: {k} -> {d.hero}"


def test_generate_offers():
    rng = random.Random(42)
    offers = generate_offers("蒸蛋", count=3, rng=rng)
    assert len(offers) == 3
    for key, price, discounted in offers:
        assert get_card_def(key) is not None
        assert price >= 1
        assert isinstance(discounted, bool)


# ---------- 事件：老板娘大甩卖 ----------
def test_boss_sale_event():
    ev = get_event("boss_sale")
    assert ev is not None
    assert ev.title == "老板娘大甩卖"
    keys = [o.key for o in ev.options]
    assert keys == ["advertise", "shop"]


def test_boss_watch_relic():
    d = get_relic_def("boss_watch")
    assert d is not None
    assert d.name == "老板娘的怀表"
    assert d.default_battles is None  # 永久遗物
    relic = make_relic("boss_watch")
    assert relic.is_expiring() is False


def test_all_events_have_options():
    for key, ev in EVENTS.items():
        assert len(ev.options) >= 2, key
