"""PVP 会话层：封装房主（服务端）/ 访客（客户端）的完整同步流程。

房主权威模型：
  - 房主持有权威 PvpMatch，访客只上报操作、接收状态；
  - 每回合双方本地放牌后点「结束回合」，上报自己的牌堆布局；
  - 房主集齐双方后结算整回合，把完整状态广播给访客。

消息（换行分隔 JSON）：
  config     房主→访客：{type, multiplier, deck_min, deck_max}
  deck_ready 任一方→房主：{type, hero_key, deck}
  match_start 房主→访客：{type, your_index, state}
  action     访客→房主：{type, piles}
  state      房主→访客：{type, state}
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .card import Card
from .heroes import get_hero
from .net import (
    NetClient,
    NetServer,
    apply_player_state,
    card_from_dict,
    card_to_dict,
    cards_from_list,
    cards_to_list,
    player_to_dict,
)
from .player import Player
from .pvp import PvpMatch, build_pvp_player

# 轮询超时（秒）
POLL_TIMEOUT = 0.05


def _match_state_dict(match: PvpMatch) -> dict:
    """序列化整个对局状态（含结算动画序列）。"""
    return {
        "p1": player_to_dict(match.p1),
        "p2": player_to_dict(match.p2),
        "turn": match.turn,
        "order": match.order,
        "winner": match.winner,
        "anims": [
            {
                "source": a["source"],
                "card": card_to_dict(a["card"]),
                "text": a["text"],
            }
            for a in match.last_animations
        ],
    }


@dataclass
class PvpSession:
    """一个 PVP 会话（房主或访客一侧）。"""

    role: str  # "host" / "client"
    hp_multiplier: float = 1.0
    deck_min: int = 8
    deck_max: int = 20
    my_index: int = 1
    match: PvpMatch | None = None
    net_server: NetServer | None = None
    net_client: NetClient | None = None
    # 已收到的对端牌组信息
    peer_hero_key: str | None = None
    peer_deck: dict | None = None
    # 房主自己的牌组（本地暂存，等双方都就绪后开赛）
    _host_hero_key: str | None = None
    _host_deck: dict | None = None
    # 状态标记
    config_received: bool = False
    match_started: bool = False
    my_ready: bool = False
    peer_ready: bool = False
    last_state: dict | None = None
    pending_anims: list[dict] = field(default_factory=list)
    pending_messages: list[dict] = field(default_factory=list)
    rng: random.Random = field(default_factory=lambda: random.Random())

    # ---------- 房主 ----------
    def host_listen(self, port: int = 0, host: str = "0.0.0.0") -> int:
        self.net_server = NetServer(host=host)
        return self.net_server.listen(port)

    def host_accept(self, timeout: float = 30.0) -> bool:
        return self.net_server.accept(timeout=timeout)

    def host_send_config(self) -> None:
        self.net_server.send({
            "type": "config",
            "multiplier": self.hp_multiplier,
            "deck_min": self.deck_min,
            "deck_max": self.deck_max,
        })

    def host_start_match(self, my_hero_key: str, my_deck: dict) -> PvpMatch:
        """房主：拿到双方牌组后构建权威对局。"""
        hero1 = get_hero(my_hero_key)
        hero2 = get_hero(self.peer_hero_key)
        p1 = build_pvp_player(hero1, my_deck, self.hp_multiplier, random.Random(1))
        p2 = build_pvp_player(hero2, self.peer_deck, self.hp_multiplier, random.Random(2))
        match = PvpMatch(p1, p2, hero_name_1=hero1.name, hero_name_2=hero2.name)
        match.start()
        self.match = match
        self.match_started = True
        self.net_server.send({"type": "match_start", "your_index": 2, "state": _match_state_dict(match)})
        return match

    # ---------- 访客 ----------
    def client_connect(self, host: str, port: int) -> bool:
        self.net_client = NetClient()
        return self.net_client.connect(host, port)

    def client_send_deck(self, hero_key: str, deck: dict) -> None:
        self.net_client.send({"type": "deck_ready", "hero_key": hero_key, "deck": deck})

    # ---------- 通用轮询 ----------
    def poll(self) -> list[dict]:
        """非阻塞轮询网络，返回新消息列表。"""
        messages: list[dict] = []
        while True:
            if self.role == "host":
                msg = self.net_server.recv(timeout=0) if self.net_server and self.net_server.framing else None
            else:
                msg = self.net_client.recv(timeout=0) if self.net_client and self.net_client.framing else None
            if msg is None:
                break
            messages.append(msg)
        return messages

    def handle_messages(self) -> list[dict]:
        """处理收到的消息，更新会话状态，返回需要 UI 关注的提示。"""
        events = []
        for msg in self.poll():
            t = msg.get("type")
            if t == "config":
                self.hp_multiplier = msg.get("multiplier", 1.0)
                self.deck_min = msg.get("deck_min", 8)
                self.deck_max = msg.get("deck_max", 20)
                self.config_received = True
                events.append(msg)
            elif t == "deck_ready":
                self.peer_hero_key = msg.get("hero_key")
                self.peer_deck = msg.get("deck", {})
                # 注意：不设置 peer_ready（那是「回合就绪」标志，配牌阶段不可复用）
                events.append(msg)
            elif t == "match_start":
                self.my_index = msg.get("your_index", 2)
                self._apply_state(msg["state"])
                self.match_started = True
                events.append(msg)
            elif t == "action":
                # 收到对方牌堆布局：写回「对方」玩家
                if self.match is not None:
                    piles = msg.get("piles", [])
                    other = 1 if self.my_index == 2 else 2
                    self._apply_piles(self.match.player(other), piles)
                    self.peer_ready = True
                events.append(msg)
            elif t == "state":
                # 兼容旧协议（新流程不再广播 state，仅 match_start 时携带初始 state）
                self._apply_state(msg["state"])
                events.append(msg)
        return events

    def _apply_state(self, state: dict) -> None:
        """用房主下发的状态重建本地 match（或就地更新）。"""
        from .state import Phase
        if self.match is None:
            # 访客首次：构建空 match
            p1 = Player()
            p2 = Player()
            self.match = PvpMatch(p1, p2)
        apply_player_state(self.match.p1, state["p1"])
        apply_player_state(self.match.p2, state["p2"])
        self.match.turn = state.get("turn", 0)
        self.match.order = state.get("order", [])
        self.match.winner = state.get("winner")
        # 结算动画序列（牌反序列化）
        self.pending_anims = [
            {
                "source": a["source"],
                "card": card_from_dict(a["card"]),
                "text": a["text"],
            }
            for a in state.get("anims", [])
        ]
        # 关键：重建后进入玩家行动阶段，否则 add_card_to_pile 会被 phase 检查拒绝
        for idx in (1, 2):
            e = self.match.engine(idx)
            e.state.phase = Phase.PLAYER_ACTION
            e.state.active_slots = self.match.player(idx).max_slots
        self.last_state = state

    def _apply_piles(self, player: Player, piles: list[list[dict]]) -> None:
        """把序列化的牌堆布局写回玩家。"""
        from .pile import Pile
        player.pile_slots = [Pile(cards_from_list(l)) for l in piles]

    # ---------- 回合动作 ----------
    def submit_piles(self, piles: list[list[Card]]) -> None:
        """上报自己的牌堆布局并标记就绪（双方都发送给对方）。"""
        payload = {"type": "action", "piles": [cards_to_list(l) for l in piles]}
        if self.role == "client":
            self.net_client.send(payload)
        else:
            self.net_server.send(payload)
        self.my_ready = True

    def my_player(self) -> Player | None:
        """返回自己一侧的玩家对象（房主=p1，访客=p2）。"""
        if self.match is None:
            return None
        return self.match.p1 if self.my_index == 1 else self.match.p2

    def both_ready(self) -> bool:
        return self.my_ready and self.peer_ready

    def resolve_local(self) -> None:
        """双方各自在本地结算整回合（确定性，结果一致，无需广播）。"""
        if self.match is None:
            return
        self.match.resolve_round()
        self.my_ready = False
        self.peer_ready = False

    def close(self) -> None:
        if self.net_server:
            self.net_server.close()
        if self.net_client:
            self.net_client.close()
