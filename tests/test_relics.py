"""遗物系统与事件系统的单元测试。"""

from __future__ import annotations

from game.card import CardType, Rarity
from game.cards import CARD_DEFS, get_card_def, make_card, public_card_keys, hero_card_keys
from game.engine import Engine
from game.enemy import make_enemy
from game.events import EVENTS, GameEvent, get_event, random_event_key
from game.player import Player
from game.relics import Relic, get_relic_def, make_relic, tick_relics
from game.state import GameState


# ---------- 遗物 ----------
def test_relic_def_and_make():
    d = get_relic_def("leftover_poison_takeout")
    assert d is not None
    assert d.name == "吃剩的毒外卖"
    assert d.default_battles == 3
    relic = make_relic("leftover_poison_takeout")
    assert relic.relic_id == "leftover_poison_takeout"
    assert relic.remaining_battles == 3
    assert relic.is_expiring() is True


def test_relic_permanent():
    relic = Relic(relic_id="some_permanent")
    assert relic.is_expiring() is False


def test_tick_relics_expires_after_countdown():
    relics = [
        make_relic("leftover_poison_takeout", 3),
        make_relic("leftover_poison_takeout", 3),
    ]
    # 3 场战斗后全部失效
    relics = tick_relics(relics)  # 2
    assert len(relics) == 2 and relics[0].remaining_battles == 2
    relics = tick_relics(relics)  # 1
    assert relics[0].remaining_battles == 1
    relics = tick_relics(relics)  # 0 -> 移除
    assert relics == []


def test_tick_relics_keeps_permanent():
    relics = [make_relic("leftover_poison_takeout", 2), Relic(relic_id="permanent")]
    relics = tick_relics(relics)
    assert len(relics) == 2
    relics = tick_relics(relics)  # 有时限的到期移除，永久的保留
    assert [r.relic_id for r in relics] == ["permanent"]


# ---------- 事件 ----------
def test_event_library():
    ev = get_event("poison_takeout")
    assert ev is not None
    assert ev.title == "芬尼的毒外卖"
    assert ev.image == "events/芬尼的毒外卖.png"
    assert len(ev.options) == 2
    keys = [o.key for o in ev.options]
    assert keys == ["decline", "devour"]


def test_random_event_key():
    for _ in range(5):
        assert random_event_key() in EVENTS


# ---------- 愧疚（诅咒卡） ----------
def test_guilt_is_curse_card():
    d = get_card_def("guilt")
    assert d is not None
    assert d.card_type is CardType.CURSE
    assert d.rarity is Rarity.CURSE
    card = make_card("guilt")
    assert card.card_type is CardType.CURSE
    assert card.name == "愧疚"


def test_guilt_not_obtainable_in_lists():
    # 诅咒牌不出现在公共牌 / 任何角色特有牌里
    assert "guilt" not in public_card_keys()
    assert "guilt" not in hero_card_keys("蒸蛋")
    assert "guilt" not in hero_card_keys("邦尼")
    assert "guilt" not in hero_card_keys("鼠鼠")


def test_guilt_cannot_be_played():
    from game.cards import build_deck
    player = Player(draw_pile=[])
    player.hand = build_deck({"guilt": 1})
    state = GameState(player=player, enemy=make_enemy("芬尼"))
    engine = Engine(state)
    engine.start_turn()
    guilt_idx = next(
        i for i, c in enumerate(player.hand) if c.card_type is CardType.CURSE
    )
    # 尝试放入牌堆：应被拒绝，手牌不变
    assert engine.add_card_to_pile(guilt_idx, 0) is False
    assert len(player.hand) == 1  # 诅咒牌仍在手牌
