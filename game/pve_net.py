"""多人合作 PVE 会话层：封装房主（服务端）/ 访客（客户端）的同步流程。

房主权威模型（最多 4 人）：
  - 房主持有权威 PveMatch，访客只上报操作、接收状态；
  - 每名玩家本地放牌后点「结束回合」，上报自己的牌堆布局；
  - 房主集齐所有人后结算整回合，把完整状态广播给所有访客。

消息（换行分隔 JSON）：
  config  房主→访客：{type, enemy_names}
  join    访客→房主：{type, hero_key, deck}
  start   房主→访客：{type, your_index, state}
  action  访客→房主：{type, piles}
  state   房主→访客：{type, state}
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field

from .enemy import Enemy, make_enemy
from .heroes import get_hero
from .net import (
    _Framing,
    NetClient,
    apply_player_state,
    card_from_dict,
    card_to_dict,
    cards_from_list,
    cards_to_list,
    player_to_dict,
)
from .player import Player
from .pve import PveMatch, build_pve_player

POLL_TIMEOUT = 0.05


# ---------- 敌人序列化 ----------
def enemy_to_dict(e: Enemy) -> dict:
    return {
        "name": e.name,
        "max_hp": e.max_hp,
        "hp": e.hp,
        "attack": e.attack,
        "strength": e.strength,
        "temp_strength": getattr(e, "temp_strength", 0),
        "block": e.block,
        "image": e.image,
        "statuses": {k: {"stacks": v.stacks, "value": v.value, "source": v.source} for k, v in e.statuses.items()},
        "curses": [{"stacks": v.stacks, "value": v.value, "source": v.source, "mult": v.mult} for v in e.curses],
        "slow_counter": e.slow_counter,
        "lead_index": e.lead_index,
        "pattern_index": e.pattern_index,
    }


def apply_enemy_state(e: Enemy, d: dict) -> None:
    e.max_hp = d.get("max_hp", e.max_hp)
    e.hp = d.get("hp", e.hp)
    e.attack = d.get("attack", e.attack)
    e.strength = d.get("strength", e.strength)
    e.temp_strength = d.get("temp_strength", 0)
    e.block = d.get("block", e.block)
    e.statuses.clear()
    for k, sd in d.get("statuses", {}).items():
        if isinstance(sd, dict):
            e.set_stacks(k, sd.get("stacks", 0))
            s = e.get_status(k)
            if s is not None:
                s.value = sd.get("value", 0)
                s.source = sd.get("source", "")
        else:
            e.set_stacks(k, sd)
    e.curses.clear()
    for sd in d.get("curses", []):
        e.add_curse(
            sd.get("stacks", 0),
            sd.get("value", 0),
            source=sd.get("source", ""),
            mult=sd.get("mult", 1.0),
        )
    e.slow_counter = d.get("slow_counter", 0)
    e.lead_index = d.get("lead_index", 0)
    e.pattern_index = d.get("pattern_index", 0)


def _pve_state_dict(match: PveMatch) -> dict:
    """序列化整个 PVE 对局状态（含结算动画序列）。"""
    return {
        "players": [player_to_dict(p) for p in match.players],
        "enemies": [enemy_to_dict(e) for e in match.enemies],
        "turn": match.turn,
        "winner": match.winner,
        "anims": [
            {"source": a["source"], "card": card_to_dict(a["card"]), "text": a["text"]}
            for a in match.last_animations
        ],
    }


def _apply_pve_state(match: PveMatch, state: dict) -> None:
    """用房主下发的状态重建本地 match。"""
    for p, pd in zip(match.players, state["players"]):
        apply_player_state(p, pd)
    for e, ed in zip(match.enemies, state["enemies"]):
        apply_enemy_state(e, ed)
    match.turn = state.get("turn", 0)
    match.winner = state.get("winner")
    match.pending_anims = [
        {"source": a["source"], "card": card_from_dict(a["card"]), "text": a["text"]}
        for a in state.get("anims", [])
    ]
    # 重建后进入玩家行动阶段
    from .state import Phase
    for idx, e in enumerate(match.engines):
        e.state.phase = Phase.PLAYER_ACTION
        e.state.active_slots = match.player(idx).max_slots


# ---------- 多连接服务端 ----------
@dataclass
class PveServer:
    """房主：监听本地端口，接受多个客户端连接（最多 3 个访客）。"""

    host: str = "0.0.0.0"
    port: int = 0
    sock: socket.socket | None = None
    framings: list[_Framing] = field(default_factory=list)

    def listen(self, port: int = 0) -> int:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, port))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        return self.port

    def accept_pending(self) -> int:
        """接受所有待连接，返回新增连接数。"""
        self.sock.setblocking(False)
        accepted = 0
        while True:
            try:
                conn, _ = self.sock.accept()
                conn.setblocking(False)
                self.framings.append(_Framing(conn))
                accepted += 1
            except BlockingIOError:
                break
            except OSError:
                break
        return accepted

    def send_all(self, obj: dict) -> None:
        for f in self.framings:
            f.send(obj)

    def recv_all(self) -> list[tuple[int, dict]]:
        """非阻塞读取所有客户端的消息，返回 (framing索引, 消息)。"""
        messages: list[tuple[int, dict]] = []
        for i, f in enumerate(self.framings):
            while True:
                msg = f.recv(timeout=0)
                if msg is None:
                    break
                messages.append((i, msg))
        return messages

    def close(self) -> None:
        for f in self.framings:
            try:
                f.sock.close()
            except OSError:
                pass
        if self.sock:
            self.sock.close()


@dataclass
class PveSession:
    """一个多人 PVE 会话（房主或访客一侧）。"""

    role: str  # "host" / "client"
    enemy_names: list[str] = field(default_factory=list)
    my_index: int = 0
    match: PveMatch | None = None
    server: PveServer | None = None
    client: NetClient | None = None
    # 房主收集的访客信息：slot(1..n-1) -> {hero_key, deck}
    peers_by_slot: dict[int, dict] = field(default_factory=dict)
    _host_hero_key: str | None = None
    _host_deck: dict | None = None
    # 状态标记
    config_received: bool = False
    match_started: bool = False
    my_ready: bool = False
    pending_anims: list[dict] = field(default_factory=list)

    # ---------- 房主 ----------
    def host_listen(self, port: int = 0) -> int:
        self.server = PveServer()
        return self.server.listen(port)

    def host_poll(self) -> list[tuple[int, dict]]:
        """房主：接受新连接 + 收集访客消息（带 slot）。"""
        self.server.accept_pending()
        return self.server.recv_all()

    def host_start_match(self, my_hero_key: str, my_deck: dict) -> PveMatch:
        """房主：集齐所有玩家后构建权威对局并广播开赛。"""
        from .enemy import make_enemy

        # 按 slot 顺序组装玩家（slot 0 = 房主）
        n = len(self.server.framings) + 1
        heroes = [get_hero(my_hero_key)]
        decks = [my_deck]
        for s in range(1, n):
            info = self.peers_by_slot.get(s)
            if info:
                heroes.append(get_hero(info["hero_key"]))
                decks.append(info.get("deck", {}))
            else:
                # 防御：未 join 的 slot 用房主英雄兜底
                heroes.append(get_hero(my_hero_key))
                decks.append(my_deck)
        enemies = [make_enemy(nm) for nm in self.enemy_names]
        players = [
            build_pve_player(h, d, __import__("random").Random(i))
            for i, (h, d) in enumerate(zip(heroes, decks))
        ]
        match = PveMatch(
            players=players,
            enemies=enemies,
            hero_names=[h.name for h in heroes],
        )
        match.start()
        self.match = match
        self.match_started = True
        # 广播开赛：给每个访客一个 index（framing 顺序 = slot）
        for i, f in enumerate(self.server.framings):
            f.send({"type": "start", "your_index": i + 1, "state": _pve_state_dict(match)})
        return match

    def host_broadcast_state(self) -> None:
        """房主结算后广播完整状态。"""
        if self.match is not None:
            self.server.send_all({"type": "state", "state": _pve_state_dict(self.match)})

    # ---------- 访客 ----------
    def client_connect(self, host: str, port: int) -> bool:
        self.client = NetClient()
        return self.client.connect(host, port)

    def client_send_join(self, hero_key: str, deck: dict) -> None:
        self.client.send({"type": "join", "hero_key": hero_key, "deck": deck})

    def client_send_action(self, piles: list) -> None:
        self.client.send({"type": "action", "piles": piles})
        self.my_ready = True

    def poll(self) -> list[dict]:
        """访客：非阻塞轮询。"""
        messages: list[dict] = []
        while True:
            msg = self.client.recv(timeout=0) if self.client and self.client.framing else None
            if msg is None:
                break
            messages.append(msg)
        return messages

    def handle_messages(self) -> list[dict]:
        """处理收到的消息，返回需要 UI 关注的事件。"""
        events = []
        if self.role == "host":
            for slot, msg in self.host_poll():
                t = msg.get("type")
                if t == "join":
                    self.peers_by_slot[slot + 1] = {
                        "hero_key": msg.get("hero_key"),
                        "deck": msg.get("deck", {}),
                    }
                    events.append(msg)
                elif t == "action":
                    self._apply_peer_action(slot + 1, msg.get("piles", []))
                    events.append(msg)
        else:
            for msg in self.poll():
                t = msg.get("type")
                if t == "config":
                    self.enemy_names = msg.get("enemy_names", [])
                    self.config_received = True
                    events.append(msg)
                elif t == "start":
                    self.my_index = msg.get("your_index", 1)
                    self._build_from_state(msg["state"])
                    self.match_started = True
                    events.append(msg)
                elif t == "state":
                    if self.match is not None:
                        _apply_pve_state(self.match, msg["state"])
                    events.append(msg)
        return events

    def _apply_peer_action(self, player_index: int, piles: list) -> None:
        """房主：把访客牌堆写回对应玩家。"""
        if self.match is None:
            return
        from .pile import Pile

        player = self.match.players[player_index]
        player.pile_slots = [Pile(cards_from_list(l)) for l in piles]
        self.match.ready_flags[player_index] = True

    def _build_from_state(self, state: dict) -> None:
        """访客：根据 start 消息构建本地 match。"""
        from .enemy import make_enemy

        players = [Player() for _ in state["players"]]
        enemies = [make_enemy(d["name"]) for d in state["enemies"]]
        self.match = PveMatch(players=players, enemies=enemies)
        _apply_pve_state(self.match, state)

    # ---------- 查询 ----------
    def my_player(self) -> Player | None:
        if self.match is None:
            return None
        return self.match.players[self.my_index]

    def close(self) -> None:
        if self.server:
            self.server.close()
        if self.client:
            self.client.close()
