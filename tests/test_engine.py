from __future__ import annotations

import random

from game.card import Card
from game.cards import make_card
from game.engine import Engine
from game.enemy import make_enemy
from game.player import Player
from game.state import GameState, Phase


def make_engine() -> Engine:
    player = Player()
    state = GameState(player=player)
    return Engine(state, rng=random.Random(0))


def make_engine_with_enemy() -> Engine:
    player = Player()
    state = GameState(player=player, enemy=make_enemy("芬尼"))
    return Engine(state, rng=random.Random(0))


def test_empty_pile_accepts_any_card():
    e = make_engine()
    e.start_turn()
    heavy = Card("重卡", 100)
    e.state.player.hand = [heavy]
    assert e.add_card_to_pile(0, 0) is True
    assert e.state.player.pile_slots[0].top is heavy


def test_lighter_card_can_stack_on_heavier():
    e = make_engine()
    e.start_turn()
    heavy = Card("重卡", 10)
    light = Card("轻卡", 3)
    e.state.player.hand = [heavy, light]
    assert e.add_card_to_pile(0, 0) is True
    assert e.add_card_to_pile(0, 0) is True
    top_to_bottom = e.state.player.pile_slots[0].cards
    assert [c.name for c in top_to_bottom] == ["轻卡", "重卡"]


def test_equal_weight_card_cannot_stack():
    e = make_engine()
    e.start_turn()
    a = Card("卡A", 5)
    b = Card("卡B", 5)
    e.state.player.hand = [a, b]
    assert e.add_card_to_pile(0, 0) is True
    assert e.add_card_to_pile(0, 0) is False
    assert e.state.player.pile_slots[0].top is a
    assert b in e.state.player.hand


def test_heavier_card_cannot_stack_on_lighter():
    e = make_engine()
    e.start_turn()
    light = Card("轻卡", 3)
    heavy = Card("重卡", 10)
    e.state.player.hand = [light, heavy]
    assert e.add_card_to_pile(0, 0) is True
    assert e.add_card_to_pile(0, 0) is False
    assert e.state.player.pile_slots[0].top is light
    assert heavy in e.state.player.hand


def test_first_turn_only_three_slots():
    e = make_engine()
    e.start_turn()
    assert e.state.active_slots == 3
    card = Card("卡", 1)
    e.state.player.hand = [card]
    assert e.add_card_to_pile(0, 3) is False
    assert e.state.player.pile_slots[3].is_empty()


def test_second_turn_uses_four_slots():
    e = make_engine()
    e.start_turn()
    e.skip()
    e.start_turn()
    assert e.state.active_slots == 4


def test_skip_moves_hand_to_discard():
    e = make_engine()
    e.start_turn()
    hand_size = len(e.state.player.hand)
    discard_before = len(e.state.player.discard_pile)
    e.skip()
    assert len(e.state.player.hand) == 0
    assert len(e.state.player.discard_pile) == discard_before + hand_size


def test_front_pile_resolves_top_to_bottom():
    e = make_engine()
    e.start_turn()
    heavy = Card("重卡", 10)
    light = Card("轻卡", 3)
    e.state.player.hand = [heavy, light]
    e.add_card_to_pile(0, 0)
    e.add_card_to_pile(0, 0)
    e.state.player.hand = []
    e.skip()
    played = [c.name for c in e.state.player.discard_pile[-2:]]
    assert played == ["轻卡", "重卡"]


def test_pile_slots_shift_after_resolve():
    e = make_engine()
    e.start_turn()
    marker = Card("标记", 5)
    e.state.player.hand = [marker]
    e.add_card_to_pile(0, 1)
    e.state.player.hand = []
    e.skip()
    # 原来的槽位2（索引1）现在变成槽位1（索引0）
    assert e.state.player.pile_slots[0].top is marker
    assert len(e.state.player.pile_slots) == 4


def test_draw_reshuffles_discard_when_draw_empty():
    e = make_engine()
    e.state.player.draw_pile = []
    e.state.player.discard_pile = [Card("弃卡", 1) for _ in range(3)]
    drawn = e.draw_cards(5)
    assert len(drawn) == 3
    assert len(e.state.player.draw_pile) == 0
    assert len(e.state.player.discard_pile) == 0


def test_draw_both_empty_does_not_crash():
    e = make_engine()
    e.state.player.draw_pile = []
    e.state.player.discard_pile = []
    drawn = e.draw_cards(5)
    assert drawn == []


def test_pile_turn_capacity_decreases_per_slot():
    e = make_engine()
    e.start_turn()
    p = e.state.player
    p.hand = [Card(f"c{i}", 10 - i) for i in range(4)]
    # 槽位0（上限4）：可放4张
    for _ in range(4):
        assert e.add_card_to_pile(0, 0) is True
    assert e.add_card_to_pile(0, 0) is False  # 第5张被拒
    # 槽位2（上限2）：只能放2张
    p.hand = [Card("a", 9), Card("b", 5), Card("c", 2)]
    assert e.add_card_to_pile(0, 2) is True
    assert e.add_card_to_pile(0, 2) is True
    assert e.add_card_to_pile(0, 2) is False  # 第3张被容量拒绝


def test_enemy_library_stats():
    finny = make_enemy("芬尼")
    assert finny.max_hp == 30
    assert finny.attack == 3
    assert finny.hp == 30
    dealt = finny.take_damage(7)
    assert dealt == 7
    assert finny.hp == 23
    assert finny.is_alive
    assert 0.0 < finny.hp_ratio < 1.0


def test_strike_deals_damage_to_enemy():
    e = make_engine_with_enemy()
    strike = make_card("strike")
    e.play_card(strike, "enemy")
    assert e.state.enemy.hp == 24


def test_strike_can_target_self():
    e = make_engine_with_enemy()
    e.state.player.max_hp = 50
    e.state.player.hp = 50
    strike = make_card("strike")
    e.play_card(strike, "self")
    assert e.state.player.hp == 44


def test_defend_gains_block():
    e = make_engine_with_enemy()
    defend = make_card("defend")
    e.play_card(defend)
    assert e.state.player.block == 5


def test_burst_bonus_applies_to_later_attacks():
    e = make_engine_with_enemy()
    burst = make_card("burst")
    strike = make_card("strike")
    e.play_card(burst)
    e.play_card(strike, "enemy")
    assert e.state.enemy.hp == 22  # 30 - (6 + 2)


def test_block_absorbs_enemy_hit():
    e = make_engine_with_enemy()
    e.state.player.gain_block(5)
    e.state.player.keep_block = True  # 保留护甲，验证吸收
    e.monster_phase()  # 芬尼攻击 3，被格挡吸收，生命不变
    assert e.state.player.hp == 20
    assert e.state.player.block == 2


def test_toughness_buffs_defend_cards():
    e = make_engine_with_enemy()
    e.start_turn()
    # 牌堆：[韧性, 防御]（韧性叠在防御上）
    e.state.player.hand = [make_card("defend"), make_card("toughness")]
    e.add_card_to_pile(0, 0)  # 防御(4)
    e.add_card_to_pile(0, 0)  # 韧性(3) 叠到顶部
    e.state.player.hand = []
    defend = e.state.player.pile_slots[0].cards[1]  # 底部的防御
    e.skip()
    assert defend.weight == 5  # 4 + 1
    assert defend.block == 6   # 5 + 1
    assert defend.buffed is True


def test_toughness_caps_weight_at_10():
    e = make_engine_with_enemy()
    e.start_turn()
    defend = make_card("defend")
    defend.weight = 10
    toughness = make_card("toughness")
    e.state.player.hand = [defend, toughness]
    e.add_card_to_pile(0, 0)
    e.add_card_to_pile(0, 0)
    e.state.player.hand = []
    e.skip()
    assert defend.weight == 10  # 封顶
    assert defend.block == 6


def test_burst_buffs_later_attack_weight():
    e = make_engine_with_enemy()
    e.start_turn()
    # 牌堆：[爆发, 打击]（爆发叠在打击上）
    e.state.player.hand = [make_card("strike"), make_card("burst")]
    e.add_card_to_pile(0, 0)  # 打击(5)
    e.add_card_to_pile(0, 0)  # 爆发(2)
    e.state.player.hand = []
    strike = e.state.player.pile_slots[0].cards[1]
    e.skip()
    assert strike.weight == 6  # 5 + 1
    assert strike.buffed is True


def test_mark_card_applies_mark_to_enemy():
    e = make_engine_with_enemy()
    mark = make_card("mark_card")
    e.play_card(mark, "enemy")
    assert e.state.enemy.get_stacks("mark") == 1


def test_guard_card_blocks_by_pile_size():
    e = make_engine_with_enemy()
    e.state.enemy.attack = 0  # 怪物不攻击，避免消耗格挡
    e.state.enemy.pattern = []
    e.start_turn()
    e.state.player.keep_block = True  # 保留护甲，验证格挡值
    # 牌堆 2 张：[加护(顶), 防御(底)]
    e.state.player.hand = [make_card("defend"), make_card("guard")]
    e.add_card_to_pile(0, 0)  # 防御(4)
    e.add_card_to_pile(0, 0)  # 加护(1) 叠到顶部
    e.state.player.hand = []
    e.skip()
    # 加护(牌堆2张→2) + 防御(5) = 7 格挡
    assert e.state.player.block == 7


def test_resilience_status_boosts_card_block():
    e = make_engine_with_enemy()
    e.state.player.add_status("resilience", 2)
    defend = make_card("defend")
    e.play_card(defend)
    assert e.state.player.block == 7  # 5 + 2


def test_resilience_status_boosts_guard():
    e = make_engine_with_enemy()
    e.state.enemy.attack = 0
    e.state.enemy.pattern = []
    e.start_turn()
    e.state.player.keep_block = True  # 保留护甲，验证格挡值
    e.state.player.add_status("resilience", 1)
    e.state.player.hand = [make_card("guard")]
    e.add_card_to_pile(0, 0)
    e.state.player.hand = []
    e.skip()
    # 牌堆 1 张 + 韧性 1 = 2 点格挡
    assert e.state.player.block == 2


def test_mouse_keep_block():
    from game.heroes import get_hero
    hero = get_hero("鼠鼠")
    assert hero.keep_block is True
    assert hero.gain_resilience_on_hit is True
    assert hero.start_statuses == {"resilience": 1}
    assert hero.deck == {"strike": 4, "defend": 5, "toughness": 3, "guard": 2, "burst": 1}


def test_mouse_gains_resilience_on_hit():
    p = Player(gain_resilience_on_hit=True, max_hp=30)
    p.hp = 30
    p.take_damage(5)
    assert p.get_stacks("resilience") == 1
    p.take_damage(3)
    assert p.get_stacks("resilience") == 2


def test_enemy_hp_updated():
    killer = make_enemy("劣人杀手")
    assert killer.max_hp == 70
    boxer = make_enemy("拳击构造体")
    assert boxer.max_hp == 40


def test_killer_pattern_loop():
    from game.enemy import get_upcoming_intents
    killer = make_enemy("劣人杀手")
    # 三回合循环：攻击7 -> 攻击2×7 -> 力量+3
    intents = get_upcoming_intents(killer, 3)
    kinds = [i.kind for i, _ in intents]
    assert kinds == ["attack", "multi", "strength"]
    assert intents[0][0].value == 7
    assert intents[1][0].times == 2
    assert intents[2][0].value == 3


def test_killer_executes_pattern():
    e = Engine(GameState(player=Player(), enemy=make_enemy("劣人杀手")), rng=random.Random(0))
    e.state.player.hp = 100
    e.state.player.max_hp = 100
    # 回合1：攻击7
    e.monster_phase()
    assert e.state.player.hp == 93
    # 回合2：攻击2×7=14
    e.monster_phase()
    assert e.state.player.hp == 79
    # 回合3：力量+3
    e.monster_phase()
    assert e.state.enemy.strength == 3
    # 回合4：攻击7+3力量=10
    e.monster_phase()
    assert e.state.player.hp == 69


def test_boxer_pattern_loop():
    from game.enemy import get_upcoming_intents
    boxer = make_enemy("拳击构造体")
    intents = get_upcoming_intents(boxer, 3)
    kinds = [i.kind for i, _ in intents]
    assert kinds == ["buff", "attack", "multi"]
    assert intents[0][0].block == 7
    assert intents[0][0].strength == 1
    assert intents[1][0].value == 14


def test_boxer_executes_pattern():
    e = Engine(GameState(player=Player(), enemy=make_enemy("拳击构造体")), rng=random.Random(0))
    e.state.player.hp = 100
    e.state.player.max_hp = 100
    # 回合1：回合开始加7格挡，怪物输出阶段获得1力量，回合结束格挡清零
    e.start_turn()
    assert e.state.enemy.block == 7
    e.monster_phase()
    assert e.state.enemy.block == 0
    assert e.state.enemy.strength == 1
    # 回合2：攻击14+力量1=15
    e.start_turn()
    e.monster_phase()
    assert e.state.player.hp == 85  # 100 - 15
    # 回合3：攻击5×2，每次5+1力量=6，共12
    e.start_turn()
    e.monster_phase()
    assert e.state.player.hp == 73  # 85 - 12


def test_enemy_block_does_not_carry_over():
    e = Engine(GameState(player=Player(), enemy=make_enemy("拳击构造体")), rng=random.Random(0))
    # 回合1开始：怪加防御7
    e.start_turn()
    assert e.state.enemy.block == 7
    # 回合1结束：格挡清零
    e.monster_phase()
    assert e.state.enemy.block == 0
    # 回合2开始：pattern[1]=attack 无格挡
    e.start_turn()
    assert e.state.enemy.block == 0


def test_intent_display_with_strength():
    from game.enemy import get_upcoming_intents
    boxer = make_enemy("拳击构造体")
    boxer.strength = 1
    intents = get_upcoming_intents(boxer, 3)
    # 第二回合 attack：起始力量1 + 第一回合buff力量1 = 2，伤害 14+2 = 16
    assert intents[1][0].describe(intents[1][1]) == "攻击 16"


def test_drink_heals():
    e = make_engine_with_enemy()
    e.state.player.hp = 10
    e.state.player.max_hp = 30
    drink = make_card("drink")
    e.play_card(drink)
    assert e.state.player.hp == 12


def test_slim_reduces_weight():
    e = make_engine_with_enemy()
    e.start_turn()
    strike = make_card("strike")
    slim = make_card("slim")
    e.state.player.hand = [strike, slim]
    # 逻辑牌：拖到牌堆立即生效，作用于整个牌组
    assert e.add_card_to_pile(1, 0) is True  # 拖「减肥」到牌堆 0
    assert strike.weight == 3  # 5 - 2
    # 减肥不进牌堆，进入弃牌堆
    assert e.state.player.pile_slots[0].is_empty()
    assert slim in e.state.player.discard_pile


def test_slim_min_weight_1():
    e = make_engine_with_enemy()
    e.start_turn()
    strike = make_card("strike")
    strike.weight = 2
    slim = make_card("slim")
    e.state.player.hand = [strike, slim]
    assert e.add_card_to_pile(1, 0) is True
    assert strike.weight == 1  # 最低 1


def test_logic_card_takes_effect_immediately():
    e = make_engine_with_enemy()
    e.start_turn()
    e.state.player.hp = 10
    drink = make_card("drink")
    assert drink.logic is True
    assert drink.description.startswith("逻辑牌；")
    e.state.player.hand = [drink]
    assert e.add_card_to_pile(0, 0) is True
    assert e.state.player.hp == 12  # 立即回血
    assert e.state.player.pile_slots[0].is_empty()  # 不进牌堆
    assert drink in e.state.player.discard_pile


def test_unshakable_discards_remaining_hand():
    e = make_engine_with_enemy()
    e.start_turn()
    unshakable = make_card("unshakable")
    assert unshakable.logic is True
    extra = make_card("strike")
    e.state.player.hand = [unshakable, extra]
    assert e.add_card_to_pile(0, 0) is True
    # 岿然不动立即丢弃剩余手牌（extra），获得 1*2 格挡 + 1 韧性
    assert e.state.player.hand == []
    assert e.state.player.block == 2
    assert e.state.player.get_stacks("resilience") == 1


def test_num_strike_buffs_numbers():
    e = make_engine_with_enemy()
    num = make_card("num_strike")
    assert num.logic is False  # 不是逻辑牌
    assert num.weight == 0     # 重量 0，可放任意牌堆顶部
    # 数值打击只作用于同牌堆剩余（还未打出）的牌，以附魔形式
    strike = make_card("strike")
    e.resolution_queue = [strike]  # 剩余要打出的牌
    e._apply_buff_numbers()
    assert strike.num_enchant == 1
    assert strike.rendered_description == "对目标造成 7 点伤害"  # 卡面即时显示 7
    # 打击打出时伤害 7
    e.state.enemy.hp = 30
    e.state.enemy.block = 0
    e.play_card(strike, "enemy")
    assert e.state.enemy.hp == 23  # 30 - 7


def test_num_strike_does_not_affect_already_played():
    e = make_engine_with_enemy()
    already = make_card("strike")
    remaining = make_card("strike")
    # 只剩 remaining 未打出，already 已经打过了
    e.resolution_queue = [remaining]
    e._apply_buff_numbers()
    assert remaining.num_enchant == 1
    assert already.num_enchant == 0


def test_num_strike_buffs_block():
    e = make_engine_with_enemy()
    defend = make_card("defend")
    e.resolution_queue = [defend]
    e._apply_buff_numbers()
    assert defend.num_enchant == 1
    assert defend.rendered_description == "使自己获得 6 点格挡"  # 5 + 1


def test_poison_detonate():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("poison", 3)
    e.state.enemy.hp = 40
    detonate = make_card("poison_burst")
    e.play_card(detonate, "enemy")
    assert e.state.enemy.hp == 28  # 40 - 3*4
    assert e.state.enemy.get_stacks("poison") == 0


def test_hide_blocks_monster_attack():
    e = make_engine_with_enemy()
    e.state.player.hp = 50
    e.state.player.max_hp = 50
    e.state.player.add_status("hide", 1)
    e.monster_phase()
    assert e.state.player.hp == 50  # 被隐匿免疫


def test_weakness_survey_marks_enemy():
    e = make_engine_with_enemy()
    survey = make_card("weakness_survey")
    e.play_card(survey)
    assert e.state.enemy.get_stacks("mark") == 2


def test_poison_takeout_self_poison():
    e = make_engine_with_enemy()
    takeout = make_card("poison_takeout")
    e.play_card(takeout)
    assert e.state.player.get_stacks("poison") == 2


def test_body_slam_uses_block():
    e = make_engine_with_enemy()
    e.state.player.block = 10
    e.state.enemy.hp = 30
    slam = make_card("body_slam")
    e.play_card(slam, "enemy")
    assert e.state.enemy.hp == 20  # 30 - 10


def test_unshakable_discards_hand():
    e = make_engine_with_enemy()
    e.state.player.hand = [make_card("strike"), make_card("defend"), make_card("drink")]
    unshakable = make_card("unshakable")
    e.play_card(unshakable)
    assert len(e.state.player.hand) == 0
    assert e.state.player.block == 6  # 3 * 2
    assert e.state.player.get_stacks("resilience") == 3


def test_bleed_damage_and_decay():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("bleed", 3)
    e.state.enemy.hp = 30
    e.status_phase()
    assert e.state.enemy.hp == 27  # 30 - 3
    assert e.state.enemy.get_stacks("bleed") == 2


def test_burn_damage_and_halve():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("burn", 5)
    e.state.enemy.hp = 40
    e.state.enemy.max_hp = 40
    e.status_phase()
    # 5 * 1% * 40 = 2 点伤害
    assert e.state.enemy.hp == 38
    assert e.state.enemy.get_stacks("burn") == 2  # 5 // 2


def test_poison_damage_and_decay():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("poison", 3)
    e.state.enemy.hp = 100
    e.status_phase()
    # 3 * 2% * 100 = 6
    assert e.state.enemy.hp == 94
    assert e.state.enemy.get_stacks("poison") == 2


def test_poison_high_stacks_halve():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("poison", 8)
    e.state.enemy.hp = 100
    e.status_phase()
    # 8 * 4% * 100 = 32
    assert e.state.enemy.hp == 68
    assert e.state.enemy.get_stacks("poison") == 4  # 8 // 2


def test_poison_does_not_kill():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("poison", 3)
    e.state.enemy.hp = 2
    e.status_phase()
    assert e.state.enemy.hp == 1  # 最低扣到 1


def test_investigate_increases_damage():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("investigate", 3)
    e.state.enemy.hp = 30
    e.state.enemy.take_damage(5)  # 5 + 3 = 8
    assert e.state.enemy.hp == 22


def test_status_order_poison_burn_bleed():
    e = make_engine_with_enemy()
    e.state.enemy.add_status("poison", 1)
    e.state.enemy.add_status("burn", 1)
    e.state.enemy.add_status("bleed", 1)
    e.state.enemy.hp = 100
    e.state.enemy.max_hp = 100
    e.status_phase()
    # 中毒 1*2%*100=2，灼烧 1*1%*100=1，流血 1
    assert e.state.enemy.hp == 96


def test_check_game_over():
    e = make_engine_with_enemy()
    assert e.check_game_over() is None
    e.state.enemy.hp = 0
    assert e.check_game_over() == "victory"
    e.state.enemy.hp = 10
    e.state.player.hp = 0
    assert e.check_game_over() == "defeat"
