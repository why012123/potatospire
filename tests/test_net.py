"""网络层序列化与本地回环测试。"""

from __future__ import annotations

import random
import threading
import time

from game.cards import make_card
from game.heroes import get_hero
from game.net import (
    NetClient,
    NetServer,
    apply_player_state,
    card_from_dict,
    card_to_dict,
    player_to_dict,
)
from game.pvp import build_pvp_player


def test_card_roundtrip():
    card = make_card("strike")
    card.weight = 9
    card.damage = 12
    card.num_enchant = 2
    card.enchant = "poison"
    card.buffed = True
    d = card_to_dict(card)
    c2 = card_from_dict(d)
    assert c2.name == card.name
    assert c2.weight == 9
    assert c2.damage == 12
    assert c2.num_enchant == 2
    assert c2.enchant == "poison"
    assert c2.buffed is True


def test_player_roundtrip():
    h = get_hero("蒸蛋")
    p = build_pvp_player(h, h.deck, 2.0, random.Random(1))
    p.hp = 30
    p.block = 5
    p.add_status("poison", 2)
    p.pile_slots[0].cards = [make_card("strike")]
    d = player_to_dict(p)
    p2 = build_pvp_player(h, h.deck, 2.0, random.Random(1))
    apply_player_state(p2, d)
    assert p2.hp == 30
    assert p2.block == 5
    assert p2.get_stacks("poison") == 2
    assert p2.pile_slots[0].cards[0].name == "打击"
    assert p2.max_hp == 110


def test_server_client_echo():
    server = NetServer()
    port = server.listen(0)
    client = NetClient()

    results = {}

    def server_thread():
        if server.accept(timeout=5):
            msg = server.recv(timeout=5)
            results["received"] = msg
            server.send({"type": "reply", "ok": True})

    t = threading.Thread(target=server_thread)
    t.start()
    time.sleep(0.2)

    assert client.connect("127.0.0.1", port) is True
    client.send({"type": "hello", "value": 42})
    reply = client.recv(timeout=5)
    assert reply == {"type": "reply", "ok": True}
    assert results["received"] == {"type": "hello", "value": 42}

    t.join()
    client.close()
    server.close()
