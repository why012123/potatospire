"""PVP 对战模型单元测试。"""

from __future__ import annotations

import random

from game.cards import make_card
from game.heroes import get_hero
from game.pvp import PvpMatch, build_pvp_player, pending_weight


def build_match(hp_multiplier: float = 1.0):
    h1 = get_hero("蒸蛋")
    h2 = get_hero("邦尼")
    p1 = build_pvp_player(h1, h1.deck, hp_multiplier, random.Random(1))
    p2 = build_pvp_player(h2, h2.deck, hp_multiplier, random.Random(2))
    m = PvpMatch(p1, p2, hero_name_1="蒸蛋", hero_name_2="邦尼")
    m.start()
    return m


def test_pending_weight_sums_piles():
    p1 = get_hero("蒸蛋")
    p = build_pvp_player(p1, p1.deck, 1.0, random.Random(1))
    # 清空牌堆，手动放牌
    for pile in p.pile_slots:
        pile.cards.clear()
    p.pile_slots[0].cards = [make_card("strike")]  # 5
    p.pile_slots[1].cards = [make_card("defend")]  # 4
    assert pending_weight(p) == 9


def test_hp_multiplier():
    h = get_hero("蒸蛋")
    p = build_pvp_player(h, h.deck, 2.0, random.Random(1))
    assert p.max_hp == 110  # 55 * 2


def test_initial_hand_drawn():
    m = build_match()
    assert len(m.p1.hand) == 6  # 蒸蛋多抽 1
    assert len(m.p2.hand) == 5


def test_lighter_weight_acts_first():
    m = build_match()
    # 清空双方牌堆
    for p in (m.p1, m.p2):
        for pile in p.pile_slots:
            pile.cards.clear()
    # p1 总负重 5，p2 总负重 9 → p1 先手
    m.p1.pile_slots[0].cards = [make_card("strike")]  # 5
    m.p2.pile_slots[0].cards = [make_card("strike"), make_card("defend")]  # 9
    m.set_ready(1)
    m.set_ready(2)
    assert m.order == [1, 2]


def test_resolve_deals_damage_to_opponent():
    m = build_match()
    for p in (m.p1, m.p2):
        for pile in p.pile_slots:
            pile.cards.clear()
        p.block = 0
    m.p1.pile_slots[0].cards = [make_card("strike")]  # 6 伤害
    m.p2.pile_slots[0].cards = []  # 空牌堆
    hp2_before = m.p2.hp
    m.set_ready(1)
    m.set_ready(2)
    # p1 先手，打击 6 点打在 p2 身上
    assert m.p2.hp == hp2_before - 6
    assert m.winner is None


def test_winner_when_hp_zero():
    m = build_match()
    for p in (m.p1, m.p2):
        for pile in p.pile_slots:
            pile.cards.clear()
    m.p2.hp = 1
    m.p2.block = 0
    m.p1.pile_slots[0].cards = [make_card("strike")]  # 6 伤害
    m.p2.pile_slots[0].cards = []
    m.set_ready(1)
    m.set_ready(2)
    assert m.winner == 1


def test_round_advances_and_draws():
    m = build_match()
    for p in (m.p1, m.p2):
        for pile in p.pile_slots:
            pile.cards.clear()
    m.p1.pile_slots[0].cards = [make_card("strike")]
    m.p2.pile_slots[0].cards = []
    m.set_ready(1)
    m.set_ready(2)
    assert m.turn == 1
    assert m.p1_ready is False and m.p2_ready is False
    # 双方各抽 5 张（蒸蛋 6）
    assert len(m.p1.hand) == 6
    assert len(m.p2.hand) == 5


def test_frozen_player_skips_resolution():
    m = build_match()
    for p in (m.p1, m.p2):
        for pile in p.pile_slots:
            pile.cards.clear()
    m.p1.pile_slots[0].cards = [make_card("strike")]
    m.p1.add_status("frozen", 1)
    m.p2.pile_slots[0].cards = []
    hp2_before = m.p2.hp
    m.set_ready(1)
    m.set_ready(2)
    # p1 被冰冻，牌堆不推进，p2 不受伤害
    assert m.p2.hp == hp2_before
    assert m.p1.get_stacks("frozen") == 0


def test_resolve_records_animations():
    m = build_match()
    for p in (m.p1, m.p2):
        for pile in p.pile_slots:
            pile.cards.clear()
    m.p1.pile_slots[0].cards = [make_card("strike")]   # p1 一张攻击
    m.p2.pile_slots[0].cards = [make_card("defend")]   # p2 一张防御
    m.set_ready(1)
    m.set_ready(2)
    # 结算动画序列：双方各一张牌，按先手顺序
    assert len(m.last_animations) == 2
    sources = [a["source"] for a in m.last_animations]
    assert sources == m.order  # 先手方在前
    # 每张动画记录包含牌对象和效果文本
    for a in m.last_animations:
        assert a["card"].name in ("打击", "防御")
        assert isinstance(a["text"], str) and a["text"]

