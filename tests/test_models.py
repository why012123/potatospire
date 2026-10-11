from __future__ import annotations

import random

from game.card import Card, CardType, Rarity
from game.cards import make_card
from game.character import Character
from game.engine import Engine
from game.enemy import BOSS_PLACEHOLDER_NAME, enemy_names, make_enemy
from game.heroes import get_hero
from game.player import Player
from game.state import GameState
from game.status import get_status_def, make_status


def test_card_structured_fields():
    c = Card(
        "重击",
        weight=5,
        cost=2,
        card_type=CardType.ATTACK,
        rarity=Rarity.UNCOMMON,
        description="造成伤害",
        tags=("攻击",),
    )
    assert c.weight == 5
    assert c.cost == 2
    assert c.card_type is CardType.ATTACK
    assert c.rarity is Rarity.UNCOMMON
    assert c.description == "造成伤害"
    assert c.tags == ("攻击",)


def test_card_positional_backward_compat():
    c = Card("重卡", 100)
    assert c.name == "重卡"
    assert c.weight == 100
    assert c.cost == 0
    assert c.card_type is CardType.SKILL
    assert c.rarity is Rarity.COMMON


def test_character_damage_and_heal():
    ch = Character(name="测试", max_hp=10, attack=2)
    assert ch.hp == 10
    assert ch.take_damage(4) == 4
    assert ch.hp == 6
    assert ch.heal(2) == 2
    assert ch.hp == 8
    assert ch.heal(99) == 2  # 只补到满血
    assert ch.hp == 10


def test_character_death_and_ratio():
    ch = Character(name="测试", max_hp=10)
    assert ch.hp_ratio == 1.0
    ch.take_damage(10)
    assert ch.is_dead and not ch.is_alive
    assert ch.hp == 0
    ch.take_damage(5)  # 不会扣成负数
    assert ch.hp == 0
    assert ch.hp_ratio == 0.0


def test_player_is_character():
    p = Player()
    assert isinstance(p, Character)
    assert p.hp == p.max_hp == 20
    assert p.is_alive


def test_enemy_is_character():
    e = make_enemy("芬尼")
    assert isinstance(e, Character)
    assert e.max_hp == 30
    assert e.attack == 3
    assert e.take_damage(7) == 7
    assert e.hp == 23


def test_enemy_names_excludes_boss_placeholder():
    names = enemy_names()
    assert BOSS_PLACEHOLDER_NAME not in names
    assert "劣人杀手" in names
    assert "拳击构造体" in names


def test_boss_placeholder_one_hp():
    boss = make_enemy(BOSS_PLACEHOLDER_NAME)
    assert boss.max_hp == 1


def test_hero_library():
    hero = get_hero("蒸蛋")
    assert hero is not None
    assert hero.max_hp == 55
    assert hero.extra_draw == 1
    assert hero.customizable_extra is True


def test_steamed_egg_extra_draw():
    hero = get_hero("蒸蛋")
    p = Player(
        name=hero.name,
        max_hp=hero.max_hp,
        extra_draw=hero.extra_draw,
        draw_pile=[Card(f"c{i}", 5) for i in range(10)],
    )
    state = GameState(player=p, enemy=make_enemy("芬尼"))
    e = Engine(state, rng=random.Random(0))
    e.start_turn()
    # 正常 5 张 + 被动多抽 1 张 = 6 张
    assert len(p.hand) == 6
    # 多抽的那一张可自定义重量，其余 5 张不可
    assert p.hand[-1].customizable_weight is True
    assert all(not c.customizable_weight for c in p.hand[:-1])


def test_extra_draw_card_resets_after_play():
    hero = get_hero("蒸蛋")
    p = Player(
        name=hero.name,
        max_hp=hero.max_hp,
        extra_draw=hero.extra_draw,
        draw_pile=[Card(f"c{i}", 10 - i) for i in range(10)],
    )
    state = GameState(player=p, enemy=make_enemy("芬尼"))
    e = Engine(state, rng=random.Random(0))
    e.start_turn()
    extra = p.hand[-1]
    assert extra.customizable_weight is True
    # 放入牌堆（生效）后标记清除
    e.add_card_to_pile(len(p.hand) - 1, 0)
    assert extra.customizable_weight is False


def test_status_library():
    d = get_status_def("mark")
    assert d is not None
    assert d.name == "标记"
    assert get_status_def("不存在的状态") is None


def test_character_status_stack():
    ch = Character(name="测试", max_hp=10)
    assert ch.get_stacks("mark") == 0
    ch.add_status("mark", 1)
    ch.add_status("mark", 2)
    assert ch.get_stacks("mark") == 3
    assert ch.get_status("mark").stacks == 3
    assert len(ch.active_statuses()) == 1
    ch.remove_status("mark")
    assert ch.get_stacks("mark") == 0


def test_bunny_mark_on_attack():
    hero = get_hero("邦尼")
    assert hero is not None
    assert hero.mark_on_attack is True
    p = Player(
        name=hero.name,
        max_hp=hero.max_hp,
        mark_on_attack=hero.mark_on_attack,
    )
    state = GameState(player=p, enemy=make_enemy("芬尼"))
    e = Engine(state, rng=random.Random(0))
    attack = Card("重击", weight=5, card_type=CardType.ATTACK)
    skill = Card("防御", weight=5, card_type=CardType.SKILL)

    e.play_card(attack)
    assert state.enemy.get_stacks("mark") == 1
    e.play_card(attack)
    assert state.enemy.get_stacks("mark") == 2
    # 非攻击牌不施加标记
    e.play_card(skill)
    assert state.enemy.get_stacks("mark") == 2


def test_card_library():
    strike = make_card("strike")
    assert strike.name == "打击"
    assert strike.weight == 5
    assert strike.damage == 6
    assert strike.needs_target is True
    assert strike.card_type is CardType.ATTACK
    defend = make_card("defend")
    assert defend.block == 5
    burst = make_card("burst")
    assert burst.attack_bonus == 2
    assert burst.card_type is CardType.POWER


def test_new_cards_toughness_and_mark():
    toughness = make_card("toughness")
    assert toughness.toughness is True
    mark = make_card("mark_card")
    assert mark.apply_mark is True
    assert mark.needs_target is True


def test_new_public_cards():
    drink = make_card("drink")
    assert drink.heal == 2
    slim = make_card("slim")
    assert slim.weight_reduce_all == 2
    draw = make_card("draw")
    assert draw.draw_cards == 2
    num = make_card("num_strike")
    assert num.buff_numbers is True
    assert num.rarity is Rarity.RARE


def test_hero_unique_cards():
    from game.cards import hero_card_keys, public_card_keys, cards_for_hero
    bunny = hero_card_keys("邦尼")
    assert set(bunny) == {"poison_enchant", "poison_burst", "hide_card", "lurk", "mark_strike"}
    egg = hero_card_keys("蒸蛋")
    assert set(egg) == {"weakness_survey", "poison_takeout", "just_right", "iron_cleave", "enter_state"}
    mouse = hero_card_keys("鼠鼠")
    assert set(mouse) == {"body_slam", "unshakable", "bear_revenge"}
    # 公共卡不含特有卡
    public = public_card_keys()
    assert "poison_burst" not in public
    assert "strike" in public
    # 鼠鼠可选卡 = 公共 + 特有
    mouse_cards = cards_for_hero("鼠鼠")
    assert "body_slam" in mouse_cards
    assert "drink" in mouse_cards


def test_hero_decks():
    from game.heroes import get_hero
    steamed = get_hero("蒸蛋")
    assert steamed.deck == {"strike": 5, "defend": 5, "burst": 2, "toughness": 2, "just_right": 1}
    bunny = get_hero("邦尼")
    assert bunny.deck["strike"] == 5
    assert bunny.deck["defend"] == 5
    assert bunny.deck["mark_card"] == 2


def test_build_deck():
    from game.cards import build_deck
    cards = build_deck({"strike": 2, "defend": 1})
    assert len(cards) == 3
    assert [c.name for c in cards] == ["打击", "打击", "防御"]


def test_block_absorbs_damage():
    ch = Character(name="测试", max_hp=10)
    ch.gain_block(5)
    dealt = ch.take_damage(8)  # 5 格挡吸收，3 扣生命
    assert dealt == 3
    assert ch.hp == 7
    assert ch.block == 0
