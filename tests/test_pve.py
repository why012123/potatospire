"""多人 PVE 数据层与网络层测试。"""

import random
import time

from game.cards import make_card
from game.enemy import make_enemy
from game.heroes import get_hero
from game.net import cards_to_list
from game.pve import PveMatch, build_pve_player
from game.pve_net import PveSession


def _two_players():
    heroes = [get_hero("蒸蛋"), get_hero("邦尼")]
    players = [build_pve_player(h, h.deck, random.Random(i)) for i, h in enumerate(heroes)]
    return players


def test_pve_match_setup_and_resolve():
    players = _two_players()
    enemies = [make_enemy("拳击构造体")]
    m = PveMatch(players=players, enemies=enemies)
    m.start()
    assert len(m.players) == 2
    assert m.enemies[0].block == 7  # 回合开始怪加防御
    # 双方各放一张打击
    for i in (0, 1):
        m.player(i).hand = [make_card("strike")]
        assert m.engine(i).add_card_to_pile(0, 0)
    m.set_ready(0)
    m.set_ready(1)
    # 7 格挡吸收 12 伤害 → 穿透 5
    assert m.enemies[0].hp == 35
    assert m.turn == 1


def test_pve_multi_enemy_attack_hits_all_players():
    players = _two_players()
    enemies = [make_enemy("芬尼")]  # 攻击 3
    m = PveMatch(players=players, enemies=enemies)
    m.start()
    hp0 = m.player(0).hp
    hp1 = m.player(1).hp
    m.set_ready(0)
    m.set_ready(1)
    # 芬尼攻击 3 打两个玩家
    assert m.player(0).hp == hp0 - 3
    assert m.player(1).hp == hp1 - 3


def test_pve_net_full_round():
    host = PveSession(role="host", enemy_names=["拳击构造体"])
    port = host.host_listen(0)
    guest = PveSession(role="client")
    assert guest.client_connect("127.0.0.1", port)
    guest.client_send_join("邦尼", {"strike": 5, "defend": 5, "burst": 1, "toughness": 2, "mark_card": 2})

    for _ in range(50):
        host.handle_messages()
        time.sleep(0.02)
        if host.peers_by_slot:
            break
    assert host.peers_by_slot

    match = host.host_start_match("蒸蛋", {"strike": 5, "defend": 6, "burst": 2, "toughness": 2})
    assert len(match.players) == 2

    for _ in range(50):
        guest.handle_messages()
        time.sleep(0.02)
        if guest.match_started:
            break
    assert guest.match_started
    assert guest.my_index == 1

    # 双方各放一张打击，结束回合
    match.player(0).hand = [make_card("strike")]
    match.engine(0).add_card_to_pile(0, 0)
    guest.match.player(1).hand = [make_card("strike")]
    guest.match.engine(1).add_card_to_pile(0, 0)
    match.set_ready(0)
    guest.client_send_action([cards_to_list(p.cards) for p in guest.match.player(1).pile_slots])
    for _ in range(50):
        host.handle_messages()
        time.sleep(0.02)
        if match.all_ready():
            break
    assert match.all_ready()
    match.resolve_round()
    host.host_broadcast_state()
    for _ in range(50):
        guest.handle_messages()
        time.sleep(0.02)
    assert match.enemies[0].hp == guest.match.enemies[0].hp
