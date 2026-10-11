"""新增卡牌的单元测试。"""

from __future__ import annotations

import random

from game.cards import make_card
from game.engine import Engine
from game.enemy import make_enemy
from game.player import Player
from game.state import GameState


def make_engine() -> Engine:
    player = Player()
    state = GameState(player=player, enemy=make_enemy("芬尼"))
    return Engine(state, rng=random.Random(0))


# ---------- 逻辑牌（选择目标） ----------
def test_store_power_boosts_hand_weight():
    e = make_engine()
    e.start_turn()
    strike = make_card("strike")
    strike.weight = 5
    e.state.player.hand = [strike]
    card = make_card("store_power")
    assert card.select_mode == "hand_1" and card.logic
    e.play_select_card(card, [0], [])
    assert strike.weight == 8  # 5 + 3
    assert card in e.state.player.discard_pile


def test_priority_swaps_weights():
    e = make_engine()
    e.start_turn()
    a = make_card("strike")  # 5
    b = make_card("defend")  # 4
    e.state.player.hand = [a, b]
    e.play_select_card(make_card("priority"), [0, 1], [])
    assert a.weight == 4 and b.weight == 5


def test_pangu_three_cards():
    e = make_engine()
    e.start_turn()
    cards = [make_card("strike") for _ in range(3)]
    for c in cards:
        c.weight = 5
    e.state.player.hand = cards
    e.play_select_card(make_card("pangu"), [0, 1, 2], [])
    assert [c.weight for c in cards] == [3, 5, 7]  # a-2, a, a+2


def test_pangu_two_cards():
    e = make_engine()
    e.start_turn()
    cards = [make_card("strike") for _ in range(2)]
    for c in cards:
        c.weight = 5
    e.state.player.hand = cards
    e.play_select_card(make_card("pangu"), [0, 1], [])
    assert [c.weight for c in cards] == [4, 6]  # a-1, a+1


def test_inverted_pyramid():
    e = make_engine()
    e.start_turn()
    c1, c2, c3 = make_card("strike"), make_card("defend"), make_card("strike")
    e.state.player.pile_slots[0].cards = [c1, c2, c3]
    e.play_select_card(make_card("inverted_pyramid"), [], [0])
    assert e.state.player.pile_slots[0].cards == [c3, c2, c1]


def test_correct_mistake_removes_top():
    e = make_engine()
    e.start_turn()
    c1, c2 = make_card("strike"), make_card("defend")
    e.state.player.pile_slots[2].cards = [c1, c2]
    e.play_select_card(make_card("correct_mistake"), [], [2])
    assert e.state.player.pile_slots[2].cards == [c2]


# ---------- 牌堆牌（结算时生效） ----------
def test_iron_wall_absorbs_defense_and_exhausts():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    d1, d2 = make_card("defend"), make_card("defend")  # 各 5 格挡
    player.pile_slots[1].cards = [d1]
    player.pile_slots[2].cards = [d2]
    iron = make_card("iron_wall")
    assert iron.exhaust and iron.weight == 10
    e.play_card(iron)
    assert player.block == 13  # 3 + 5 + 5
    assert d1.block == 6 and d2.block == 6  # 防御牌 +1
    assert iron in player.exhaust_pile  # 消耗


def test_science_correction_deletes_nth_next_pile():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    c1, c2, c3 = make_card("strike"), make_card("defend"), make_card("strike")
    player.pile_slots[1].cards = [c1, c2, c3]
    sc = make_card("science_correction")
    assert sc.weight == 2
    e.play_card(sc)
    assert player.pile_slots[1].cards == [c1, c3]  # 删除第 2 张


def test_hamburger_buffs_field_weight():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    hand_card = make_card("strike")  # 5
    pile_card = make_card("defend")  # 4
    player.hand = [hand_card]
    player.pile_slots[0].cards = [pile_card]
    e.play_card(make_card("hamburger"))
    assert hand_card.weight == 6
    assert pile_card.weight == 5


def test_heavy_strike_grows_at_top():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    hs = make_card("heavy_strike")
    assert hs.damage == 2
    player.pile_slots[1].cards = [hs]  # 非前牌堆顶部
    e.resolve_front_pile()  # 结算前牌堆（空），随后重击 +5
    assert hs.damage == 7


def test_lurk_blocks_and_draws_when_no_attack():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    player.draw_pile = [make_card("strike") for _ in range(3)]
    lurk = make_card("lurk")
    assert lurk.weight == 10
    e.play_card(lurk)
    assert player.block == 4
    assert player.get_stacks("hide") == 1
    assert len(player.hand) == 1  # 未打攻击，抽了 1 张


def test_lurk_no_draw_after_attack():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    player.attacks_played_this_turn = 1  # 本回合已打攻击
    e.play_card(make_card("lurk"))
    assert player.block == 4
    assert player.get_stacks("hide") == 1
    assert len(player.hand) == 0  # 不抽牌


def test_mark_strike_damages_by_mark():
    e = make_engine()
    e.start_turn()
    enemy = e.state.enemy
    enemy.add_status("mark", 3)
    enemy.hp = 40
    e.play_card(make_card("mark_strike"))
    # 3×层数(9) + 标记增伤(3) = 12
    assert enemy.hp == 28  # 40 - 12


def test_bear_revenge_counterattack():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    # 先获得 2 层韧性，打出熊孩子的报复应获得 2 层反击
    player.add_status("resilience", 2)
    e.play_card(make_card("bear_revenge"))
    assert player.get_stacks("counterattack") == 2
    enemy = e.state.enemy
    enemy.hp = 30
    e._counterattack(enemy)
    assert enemy.hp == 28  # 30 - 2


# ---------- 状态：易伤 / 冰冻 ----------
def test_num_strike_enchant():
    e = make_engine()
    e.start_turn()
    strike = make_card("strike")
    e.resolution_queue = [strike]
    e._apply_buff_numbers()
    assert strike.num_enchant == 1
    assert strike.enchant_text == "数值打击+1"
    assert strike.rendered_description == "对目标造成 7 点伤害"


def test_enchant_text_poison_and_num():
    e = make_engine()
    e.start_turn()
    strike = make_card("strike")
    strike.enchant = "poison"
    strike.num_enchant = 2
    assert strike.enchant_text == "淬毒，数值打击+2"
    assert strike.rendered_description == "对目标造成 8 点伤害"  # 6 + 2


def test_mark_increases_damage():
    e = make_engine()
    e.start_turn()
    enemy = e.state.enemy
    enemy.add_status("mark", 3)
    enemy.hp = 40
    enemy.take_damage(10)
    assert enemy.hp == 27  # 10 + 3 标记增伤
    assert enemy.get_stacks("mark") == 3  # 标记永久不衰减


def test_vulnerable_increases_damage():
    e = make_engine()
    e.start_turn()
    enemy = e.state.enemy
    enemy.add_status("vulnerable", 2)
    enemy.hp = 40
    enemy.take_damage(10)
    assert enemy.hp == 25  # 10 * 1.5 = 15 伤害
    assert enemy.get_stacks("vulnerable") == 1  # 生效后 -1 层


def test_frozen_player_skips_pile_resolution():
    e = make_engine()
    e.start_turn()
    player = e.state.player
    strike = make_card("strike")
    player.pile_slots[0].cards = [strike]
    player.add_status("frozen", 1)
    e.skip()
    # 前牌堆未被结算移除
    assert len(player.pile_slots) == 4
    assert strike in player.pile_slots[0].cards
    assert player.get_stacks("frozen") == 0


def test_frozen_monster_skips_action():
    e = make_engine()
    e.start_turn()
    enemy = e.state.enemy
    enemy.add_status("frozen", 1)
    player_hp = e.state.player.hp
    e.skip()
    assert e.state.player.hp == player_hp  # 怪物被冰冻，未攻击
    assert enemy.get_stacks("frozen") == 0
