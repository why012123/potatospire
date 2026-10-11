"""本地 TCP 联机层：房主（服务端）与访客（客户端）的同步。

消息协议：换行符分隔的 JSON 文本，每条一行。
本层只负责：
  1. 卡牌 / 玩家的序列化与反序列化（保证双方状态一致）；
  2. NetServer / NetClient 的建立、收发；
  3. 房主权威：客户端只上报操作，房主下发完整状态。

后续做局域网联机时只需把 host 从 127.0.0.1 换成目标 IP。
"""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass

from .card import Card, CardType, Rarity
from .cards import make_card
from .enchants import make_enchant
from .player import Player
from .pile import Pile

# 卡牌可变字段（影响结算、需跨端同步）
_CARD_MUTABLE = (
    "weight", "damage", "block", "attack_bonus", "heal", "draw_cards",
    "num_enchant", "enchant", "buffed", "customizable_weight", "perm_enchant",
    "precision_count",
)


def get_local_ip() -> str:
    """获取本机局域网 IP（无网卡时回退 127.0.0.1）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def card_to_dict(card: Card) -> dict:
    """把卡牌序列化为字典（含可变字段，key 用于重建类型与描述）。"""
    d = {"key": _card_key_of(card)}
    for f in _CARD_MUTABLE:
        d[f] = getattr(card, f)
    d["temp_enchants"] = [
        {"id": e.enchant_id, "value": e.value} for e in getattr(card, "temp_enchants", [])
    ]
    return d


def card_from_dict(d: dict) -> Card:
    """从字典重建卡牌。"""
    key = d.get("key", "strike")
    try:
        card = make_card(key)
    except KeyError:
        # 未知 key：构建一个占位卡，保留关键字段
        card = Card(name=d.get("name", key), weight=d.get("weight", 1))
        return card
    for f in _CARD_MUTABLE:
        if f in d:
            setattr(card, f, d[f])
    card.temp_enchants = [
        make_enchant(e["id"], e.get("value")) for e in d.get("temp_enchants", [])
    ]
    return card


def _card_key_of(card: Card) -> str:
    """反查卡牌的 key（用于重建）。"""
    from .cards import CARD_DEFS
    for key, cdef in CARD_DEFS.items():
        if cdef.name == card.name:
            return key
    return card.name


def cards_to_list(cards: list[Card]) -> list[dict]:
    return [card_to_dict(c) for c in cards]


def cards_from_list(lst: list[dict]) -> list[Card]:
    return [card_from_dict(d) for d in lst]


def player_to_dict(p: Player) -> dict:
    """序列化玩家完整状态（用于房主下发 / 双方重建）。"""
    return {
        "name": p.name,
        "image": p.image,
        "icon": p.icon,
        "max_hp": p.max_hp,
        "hp": p.hp,
        "strength": p.strength,
        "block": p.block,
        "statuses": {k: {"stacks": v.stacks, "value": v.value, "source": v.source} for k, v in p.statuses.items()},
        "curses": [{"stacks": v.stacks, "value": v.value, "source": v.source, "mult": v.mult} for v in p.curses],
        "hand": cards_to_list(p.hand),
        "draw_pile": cards_to_list(p.draw_pile),
        "discard_pile": cards_to_list(p.discard_pile),
        "pile_slots": [cards_to_list(pile.cards) for pile in p.pile_slots],
        "exhaust_pile": cards_to_list(p.exhaust_pile),
        "keep_block": p.keep_block,
        "extra_draw": p.extra_draw,
        "mark_on_attack": p.mark_on_attack,
        "gain_resilience_on_hit": p.gain_resilience_on_hit,
        "curse_on_turn": p.curse_on_turn,
        "curse_mult": p.curse_mult,
        "has_target": p.has_target,
        "target_level": p.target_level,
        "attacks_played_this_turn": p.attacks_played_this_turn,
        "slow_counter": p.slow_counter,
    }


def apply_player_state(p: Player, d: dict) -> None:
    """把序列化状态写回玩家对象（就地更新，避免重建身份）。"""
    p.name = d.get("name", p.name)
    p.image = d.get("image", "")
    p.icon = d.get("icon", "")
    p.max_hp = d["max_hp"]
    p.hp = d["hp"]
    p.strength = d.get("strength", 0)
    p.block = d.get("block", 0)
    p.statuses.clear()
    for k, sd in d.get("statuses", {}).items():
        if isinstance(sd, dict):
            p.set_stacks(k, sd.get("stacks", 0))
            s = p.get_status(k)
            if s is not None:
                s.value = sd.get("value", 0)
                s.source = sd.get("source", "")
        else:
            # 兼容旧格式：纯层数
            p.set_stacks(k, sd)
    p.curses.clear()
    for sd in d.get("curses", []):
        p.add_curse(
            sd.get("stacks", 0),
            sd.get("value", 0),
            source=sd.get("source", ""),
            mult=sd.get("mult", 1.0),
        )
    p.hand = cards_from_list(d.get("hand", []))
    p.draw_pile = cards_from_list(d.get("draw_pile", []))
    p.discard_pile = cards_from_list(d.get("discard_pile", []))
    p.pile_slots = [Pile(cards_from_list(l)) for l in d.get("pile_slots", [])]
    p.exhaust_pile = cards_from_list(d.get("exhaust_pile", []))
    # 每回合放牌计数在回合结束必重置为 0（不跨回合），恢复状态时直接归零
    p.pile_turn_counts = [0] * p.max_slots
    p.keep_block = d.get("keep_block", False)
    p.extra_draw = d.get("extra_draw", 0)
    p.mark_on_attack = d.get("mark_on_attack", False)
    p.gain_resilience_on_hit = d.get("gain_resilience_on_hit", False)
    p.curse_on_turn = d.get("curse_on_turn", False)
    p.curse_mult = d.get("curse_mult", 1.0)
    p.has_target = d.get("has_target", False)
    p.target_level = d.get("target_level", 1)
    p.attacks_played_this_turn = d.get("attacks_played_this_turn", 0)
    p.slow_counter = d.get("slow_counter", 0)


class _Framing:
    """换行分隔的 JSON 收发。"""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = b""

    def send(self, obj: dict) -> None:
        data = json.dumps(obj, ensure_ascii=False) + "\n"
        self.sock.sendall(data.encode("utf-8"))

    def recv(self, timeout: float | None = None) -> dict | None:
        """阻塞读取一条消息；超时/无数据/断连返回 None。"""
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            while b"\n" not in self._buf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None
                self._buf += chunk
            line, self._buf = self._buf.split(b"\n", 1)
            return json.loads(line.decode("utf-8"))
        except (socket.timeout, BlockingIOError, ConnectionResetError, ConnectionAbortedError):
            return None
        except UnicodeDecodeError:
            # 单个 recv 可能截断多字节 UTF-8 字符，继续读取直至完整
            return None
        finally:
            if timeout is not None:
                self.sock.settimeout(None)


@dataclass
class NetServer:
    """房主：监听本地端口，接受一个客户端连接。"""

    host: str = "127.0.0.1"
    port: int = 0
    sock: socket.socket | None = None
    conn: socket.socket | None = None
    framing: _Framing | None = None

    def listen(self, port: int = 0) -> int:
        """开始监听，返回实际端口（port=0 时由系统分配）。"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, port))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        return self.port

    def accept(self, timeout: float | None = None) -> bool:
        """等待客户端连接，成功返回 True。"""
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            self.conn, _ = self.sock.accept()
            self.framing = _Framing(self.conn)
            return True
        except (socket.timeout, BlockingIOError):
            return False
        finally:
            if timeout is not None:
                self.sock.settimeout(None)

    def send(self, obj: dict) -> None:
        self.framing.send(obj)

    def recv(self, timeout: float | None = None) -> dict | None:
        return self.framing.recv(timeout)

    def close(self) -> None:
        if self.conn:
            self.conn.close()
        if self.sock:
            self.sock.close()


@dataclass
class NetClient:
    """访客：连接房主。"""

    host: str = "127.0.0.1"
    port: int = 0
    sock: socket.socket | None = None
    framing: _Framing | None = None

    def connect(self, host: str, port: int, timeout: float = 5.0) -> bool:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        try:
            self.sock.connect((host, port))
            self.framing = _Framing(self.sock)
            return True
        except OSError:
            return False

    def send(self, obj: dict) -> None:
        self.framing.send(obj)

    def recv(self, timeout: float | None = None) -> dict | None:
        return self.framing.recv(timeout)

    def close(self) -> None:
        if self.sock:
            self.sock.close()
