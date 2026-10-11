"""六边形密铺探索地图：中心起点 + 六角 Boss。

地图结构：
  - 由小六边形密铺成一个大六边形（半径 radius）；
  - 中心格子是起点，大六边形的六个顶点（角）是 Boss 房；
  - 对角两个 Boss 是同一个，因此实际只有 3 个不同 Boss；
  - 玩家每一步可以进入当前房间相邻的 6 个房间之一；
  - 流程：侦查（揭示相邻 6 格类型）→ 移动（6 选 1）。

房间类型与占比（起点 / Boss 除外）：
  - 普通战斗 30%、事件 20%、精英怪 15%、商店 15%、火堆 15%、宝箱 5%。

坐标：pointy-top 轴向坐标 (q, r)，像素换算：
  x = size * sqrt(3) * (q + r / 2)
  y = size * 3/2 * r
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto

SQRT3 = math.sqrt(3)

# 轴向坐标的 6 个邻居方向
NEIGHBOR_DIRS: tuple[tuple[int, int], ...] = (
    (1, 0),    # 东
    (1, -1),   # 东北
    (0, -1),   # 西北
    (-1, 0),   # 西
    (-1, 1),   # 西南
    (0, 1),    # 东南
)


class RoomType(Enum):
    """房间类型。"""

    START = auto()   # 起点（中心）
    EVENT = auto()   # 事件
    BATTLE = auto()  # 普通战斗
    REST = auto()    # 火堆（休息）
    ELITE = auto()   # 精英怪
    SHOP = auto()    # 商店
    CHEST = auto()   # 宝箱
    BOSS = auto()    # Boss（六角）


# 颜色约定：白事件 / 黄战斗 / 粉火堆 / 紫精英 / 绿商店 / 金宝箱 / 红 Boss / 蓝起点
ROOM_COLORS: dict[RoomType, tuple[int, int, int]] = {
    RoomType.START: (120, 180, 235),
    RoomType.EVENT: (245, 245, 245),
    RoomType.BATTLE: (240, 200, 80),
    RoomType.REST: (238, 148, 180),
    RoomType.ELITE: (168, 118, 218),
    RoomType.SHOP: (110, 210, 130),
    RoomType.CHEST: (232, 176, 60),
    RoomType.BOSS: (222, 90, 90),
}

ROOM_LABELS: dict[RoomType, str] = {
    RoomType.START: "起",
    RoomType.EVENT: "事",
    RoomType.BATTLE: "战",
    RoomType.REST: "火",
    RoomType.ELITE: "精",
    RoomType.SHOP: "店",
    RoomType.CHEST: "箱",
    RoomType.BOSS: "Boss",
}

# 3 个不同 Boss：对角相同
BOSS_KEYS: tuple[str, str, str] = ("boss_a", "boss_b", "boss_c")
BOSS_LABELS: dict[str, str] = {
    "boss_a": "Boss Ⅰ",
    "boss_b": "Boss Ⅱ",
    "boss_c": "Boss Ⅲ",
}
BOSS_COLORS: dict[str, tuple[int, int, int]] = {
    "boss_a": (222, 90, 90),
    "boss_b": (196, 56, 56),
    "boss_c": (238, 128, 70),
}

# 普通房间类型权重：普通战斗 30% / 事件 20% / 火堆 15% / 精英 15% / 商店 15% / 宝箱 5%
_TYPE_WEIGHTS: tuple[tuple[float, RoomType], ...] = (
    (0.30, RoomType.BATTLE),
    (0.50, RoomType.EVENT),
    (0.65, RoomType.REST),
    (0.80, RoomType.ELITE),
    (0.95, RoomType.SHOP),
    (1.00, RoomType.CHEST),
)

# 每回合可侦查的相邻格数上限
MAX_SCOUTS_PER_TURN = 2


@dataclass
class Room:
    """地图上的一个六边形房间。"""

    id: int
    q: int             # 轴向坐标 q
    r: int             # 轴向坐标 r
    room_type: RoomType = RoomType.EVENT
    # 相邻房间 id（有效范围内，双向登记）
    neighbors: list[int] = field(default_factory=list)
    # 是否已被揭示类型（未揭示的房间类型对玩家隐藏）
    revealed: bool = False
    # 是否已被走过（走过的房间不能再进入）
    visited: bool = False
    # 仅 Boss 房有：对角相同（boss_a/boss_b/boss_c）
    boss_key: str | None = None

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"Room({self.id}, ({self.q},{self.r}), {self.room_type.name})"


@dataclass
class GameMap:
    """一次随机生成的蜂巢探索地图。"""

    radius: int
    rooms: dict[int, Room] = field(default_factory=dict)
    start_id: int = -1
    boss_ids: list[int] = field(default_factory=list)  # 六个角（按生成顺序）
    player_pos: int = -1
    scouts_this_turn: int = 0  # 本回合已侦查的格数（每回合上限 MAX_SCOUTS_PER_TURN）

    # ---------- 坐标 / 邻接 ----------
    def room_at(self, q: int, r: int) -> Room | None:
        for room in self.rooms.values():
            if room.q == q and room.r == r:
                return room
        return None

    def neighbors(self, room_id: int) -> list[Room]:
        """返回某房间的相邻房间对象列表（最多 6 个）。"""
        room = self.rooms[room_id]
        return [self.rooms[n] for n in room.neighbors]

    def danger(self, room_id: int) -> int:
        """某房间的「危险度」：相邻房间中 战斗 + 精英 的数量。"""
        return sum(
            1
            for n in self.neighbors(room_id)
            if n.room_type in (RoomType.BATTLE, RoomType.ELITE)
        )

    # ---------- 探索：侦查 / 移动 ----------
    def available_moves(self) -> list[Room]:
        """当前房间可移动进入的相邻房间（排除已走过的房间）。"""
        return [n for n in self.neighbors(self.player_pos) if not n.visited]

    def scout(self, room_id: int) -> Room | None:
        """侦查指定相邻房间（每回合最多 MAX_SCOUTS_PER_TURN 格），返回被揭示的房间。

        返回 None 表示失败：次数用尽、非相邻、该格已揭示或已走过。
        """
        if self.scouts_this_turn >= MAX_SCOUTS_PER_TURN:
            return None
        if room_id not in self.rooms:
            return None
        if room_id not in self.rooms[self.player_pos].neighbors:
            return None
        room = self.rooms[room_id]
        if room.revealed or room.visited:
            return None
        room.revealed = True
        self.scouts_this_turn += 1
        return room

    def move_to(self, room_id: int) -> bool:
        """移动到相邻房间；成功返回 True。

        走过的房间不能再进入：把旧位置标记为已走过，移动到目标并揭示、重置侦查。
        """
        if room_id not in self.rooms:
            return False
        if room_id not in self.rooms[self.player_pos].neighbors:
            return False
        target = self.rooms[room_id]
        if target.visited:
            return False
        # 旧位置标记为已走过
        self.rooms[self.player_pos].visited = True
        self.player_pos = room_id
        target.revealed = True
        self.scouts_this_turn = 0
        return True

    @property
    def current_room(self) -> Room:
        return self.rooms[self.player_pos]

    @property
    def room_count(self) -> int:
        return len(self.rooms)


def _in_hex(q: int, r: int, radius: int) -> bool:
    """判断 (q, r) 是否在大六边形范围内。"""
    return abs(q) <= radius and abs(r) <= radius and abs(q + r) <= radius


def _hex_coords(radius: int) -> list[tuple[int, int]]:
    """枚举大六边形内所有格子的 (q, r)。"""
    return [
        (q, r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if _in_hex(q, r, radius)
    ]


def _corner_coords(radius: int) -> list[tuple[int, int]]:
    """六个顶点（角）的 (q, r)，按逆时针顺序。"""
    return [
        (radius, 0),
        (0, radius),
        (-radius, radius),
        (-radius, 0),
        (0, -radius),
        (radius, -radius),
    ]


def _boss_key_for(corner_index: int) -> str:
    """六个角 → 3 个 Boss：对角相同（角 i 与角 i+3 相对）。"""
    return BOSS_KEYS[corner_index % 3]


def _random_room_type(rng: random.Random) -> RoomType:
    """按权重随机一个普通房间类型（不含 START / BOSS）。"""
    roll = rng.random()
    for threshold, rtype in _TYPE_WEIGHTS:
        if roll < threshold:
            return rtype
    return RoomType.ELITE


def generate_map(
    radius: int = 5,
    seed: int | None = None,
    rng: random.Random | None = None,
) -> GameMap:
    """随机生成一张蜂巢探索地图。

    参数：
      - radius: 大六边形半径（每条边含顶点共 radius + 1 格），默认 5。
      - seed:   随机种子；同时传 rng 时忽略 seed。
    """
    if rng is None:
        rng = random.Random(seed)

    gmap = GameMap(radius=radius)
    coords = _hex_coords(radius)
    corners = _corner_coords(radius)
    corner_set = set(corners)

    coord_to_id: dict[tuple[int, int], int] = {}
    next_id = 0

    def make_room(q: int, r: int, rtype: RoomType, boss_key: str | None = None) -> Room:
        nonlocal next_id
        room = Room(id=next_id, q=q, r=r, room_type=rtype, boss_key=boss_key)
        gmap.rooms[next_id] = room
        coord_to_id[(q, r)] = next_id
        next_id += 1
        return room

    # 中心起点
    start = make_room(0, 0, RoomType.START, None)
    gmap.start_id = start.id

    # 六个角：Boss（对角相同）
    gmap.boss_ids = []
    for i, (q, r) in enumerate(corners):
        boss = make_room(q, r, RoomType.BOSS, _boss_key_for(i))
        gmap.boss_ids.append(boss.id)

    # 其余普通房间
    for q, r in coords:
        if (q, r) == (0, 0) or (q, r) in corner_set:
            continue
        make_room(q, r, _random_room_type(rng), None)

    # 建立邻接（有效范围内的双向边）
    for room in gmap.rooms.values():
        for dq, dr in NEIGHBOR_DIRS:
            nq, nr = room.q + dq, room.r + dr
            if _in_hex(nq, nr, radius):
                nid = coord_to_id[(nq, nr)]
                room.neighbors.append(nid)

    # 初始状态：仅起点可见，玩家在起点
    gmap.rooms[gmap.start_id].revealed = True
    gmap.player_pos = gmap.start_id

    return gmap


# ---------- 六边形像素坐标 ----------
def hex_centers(gmap: GameMap, size: float) -> dict[int, tuple[float, float]]:
    """每个房间六边形中心的像素坐标（轴向坐标直接换算，原点为地图中心）。"""
    centers: dict[int, tuple[float, float]] = {}
    for room in gmap.rooms.values():
        x = size * SQRT3 * (room.q + room.r / 2)
        y = size * 1.5 * room.r
        centers[room.id] = (x, y)
    return centers


def hex_vertices(cx: float, cy: float, size: float) -> list[tuple[float, float]]:
    """尖顶朝上六边形的 6 个顶点（从正上方开始顺时针）。"""
    return [
        (cx + size * math.cos(math.radians(60 * i + 30)),
         cy + size * math.sin(math.radians(60 * i + 30)))
        for i in range(6)
    ]
