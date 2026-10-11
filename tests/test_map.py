"""蜂巢探索地图：结构、占比、邻接、侦查与移动的单元测试。"""

from __future__ import annotations

import math
import random
from collections import Counter

from game.map import (
    BOSS_KEYS,
    GameMap,
    Room,
    RoomType,
    _hex_coords,
    _random_room_type,
    generate_map,
    hex_centers,
    hex_vertices,
)


def test_hex_coords_count():
    # 半径 radius 的大六边形共有 3*radius*(radius+1)+1 格
    for radius in (1, 2, 3, 5):
        assert len(_hex_coords(radius)) == 3 * radius * (radius + 1) + 1


def test_generate_map_structure():
    gmap = generate_map(radius=5, seed=42)
    assert gmap.radius == 5
    assert gmap.room_count == 3 * 5 * 6 + 1  # 91
    # 中心起点
    assert gmap.rooms[gmap.start_id].room_type is RoomType.START
    assert gmap.rooms[gmap.start_id].q == 0 and gmap.rooms[gmap.start_id].r == 0
    # 六个角都是 Boss
    assert len(gmap.boss_ids) == 6
    for bid in gmap.boss_ids:
        assert gmap.rooms[bid].room_type is RoomType.BOSS


def test_six_corners_three_distinct_bosses():
    gmap = generate_map(radius=5, seed=1)
    keys = [gmap.rooms[bid].boss_key for bid in gmap.boss_ids]
    # 对角（索引相差 3）是同一个 Boss
    for i in range(3):
        assert keys[i] == keys[i + 3]
    # 恰好 3 个不同 Boss
    assert set(keys) == set(BOSS_KEYS)


def test_middle_room_types_are_legal():
    gmap = generate_map(radius=5, seed=7)
    corner_ids = set(gmap.boss_ids) | {gmap.start_id}
    for rid, room in gmap.rooms.items():
        if rid in corner_ids:
            continue
        assert room.room_type in (
            RoomType.EVENT, RoomType.BATTLE, RoomType.REST, RoomType.ELITE, RoomType.SHOP, RoomType.CHEST,
        )


def test_room_type_distribution():
    # 大量采样验证普通房间占比 ≈ 战斗30% / 事件20% / 火堆15% / 精英15% / 商店15% / 宝箱5%
    rng = random.Random(0)
    n = 20000
    counter = Counter(_random_room_type(rng) for _ in range(n))
    total = sum(counter.values())
    assert abs(counter[RoomType.BATTLE] / total - 0.30) < 0.02
    assert abs(counter[RoomType.EVENT] / total - 0.20) < 0.02
    assert abs(counter[RoomType.REST] / total - 0.15) < 0.02
    assert abs(counter[RoomType.ELITE] / total - 0.15) < 0.02
    assert abs(counter[RoomType.SHOP] / total - 0.15) < 0.02
    assert abs(counter[RoomType.CHEST] / total - 0.05) < 0.02


def test_neighbors_are_bidirectional_and_bounded():
    gmap = generate_map(radius=5, seed=5)
    for room in gmap.rooms.values():
        # 内部房间 6 个邻居，边界房间 2~5 个
        assert 2 <= len(room.neighbors) <= 6
        for nid in room.neighbors:
            assert room.id in gmap.rooms[nid].neighbors


def test_center_has_six_neighbors():
    gmap = generate_map(radius=5, seed=2)
    assert len(gmap.neighbors(gmap.start_id)) == 6


def test_danger_counts_battle_and_elite():
    # 手工构造：中心起点，周围放 战斗/精英/事件/火堆 各若干
    gmap = GameMap(radius=1)
    center = Room(id=0, q=0, r=0, room_type=RoomType.START)
    battle = Room(id=1, q=1, r=0, room_type=RoomType.BATTLE)
    elite = Room(id=2, q=0, r=1, room_type=RoomType.ELITE)
    event = Room(id=3, q=-1, r=1, room_type=RoomType.EVENT)
    rest = Room(id=4, q=-1, r=0, room_type=RoomType.REST)
    for r in (center, battle, elite, event, rest):
        gmap.rooms[r.id] = r
    center.neighbors = [battle.id, elite.id, event.id, rest.id]
    assert gmap.danger(center.id) == 2  # 战斗 + 精英


def test_scout_reveals_two_specified():
    gmap = generate_map(radius=5, seed=3)
    assert gmap.current_room.id == gmap.start_id
    # 初始只有起点可见
    assert sum(1 for r in gmap.rooms.values() if r.revealed) == 1
    neighbors = [n.id for n in gmap.neighbors(gmap.start_id)]
    # 侦查指定两格成功
    r1 = gmap.scout(neighbors[0])
    r2 = gmap.scout(neighbors[1])
    assert r1 is not None and r1.id == neighbors[0]
    assert r2 is not None and r2.id == neighbors[1]
    assert gmap.rooms[neighbors[0]].revealed is True
    assert gmap.rooms[neighbors[1]].revealed is True
    # 第三格：次数用尽
    assert gmap.scout(neighbors[2]) is None
    # 已揭示的不重复计数，仍返回 None
    assert gmap.scout(neighbors[0]) is None


def test_scout_requires_adjacent():
    gmap = generate_map(radius=5, seed=3)
    # 不相邻房间无法侦查（取一个非相邻的 Boss 角）
    far = next(bid for bid in gmap.boss_ids if bid not in gmap.rooms[gmap.start_id].neighbors)
    assert gmap.scout(far) is None


def test_scout_resets_after_move():
    gmap = generate_map(radius=5, seed=4)
    neighbors = [n.id for n in gmap.neighbors(gmap.start_id)]
    assert gmap.scout(neighbors[0]) is not None
    assert gmap.scout(neighbors[1]) is not None
    assert gmap.scouts_this_turn == 2
    # 移动到已侦查的房间，重置侦查次数
    assert gmap.move_to(neighbors[0]) is True
    assert gmap.scouts_this_turn == 0
    # 新位置可继续侦查
    unrevealed = [n.id for n in gmap.neighbors(gmap.player_pos) if not gmap.rooms[n.id].revealed]
    if unrevealed:
        assert gmap.scout(unrevealed[0]) is not None


def test_move_to_adjacent_and_non_adjacent():
    gmap = generate_map(radius=5, seed=4)
    start = gmap.start_id
    neighbors = [n.id for n in gmap.neighbors(start)]
    target = neighbors[0]
    assert gmap.move_to(target) is True
    assert gmap.player_pos == target
    assert gmap.rooms[target].revealed is True
    # 跳到不相邻房间失败
    far = max(gmap.rooms)  # 编号最大（Boss 角之一，通常不相邻于起点）
    if far not in gmap.rooms[start].neighbors:
        assert gmap.move_to(far) is False


def test_cannot_backtrack_to_visited_room():
    gmap = generate_map(radius=5, seed=4)
    start = gmap.start_id
    target = gmap.neighbors(start)[0].id
    assert gmap.move_to(target) is True
    # 旧位置（起点）被标记为已走过
    assert gmap.rooms[start].visited is True
    # 不能回头移动到起点
    assert gmap.move_to(start) is False
    # 可移动列表里不再包含起点
    assert start not in {r.id for r in gmap.available_moves()}


def test_seed_reproducible():
    def sig(m):
        return [(r.q, r.r, r.room_type) for r in m.rooms.values()]
    a = generate_map(radius=5, seed=999)
    b = generate_map(radius=5, seed=999)
    assert sig(a) == sig(b)


def test_different_seed_differs():
    a = generate_map(radius=6, seed=1)
    b = generate_map(radius=6, seed=2)
    sig = lambda m: [(r.q, r.r, r.room_type) for r in m.rooms.values()]
    assert sig(a) != sig(b)


def test_rng_injected():
    rng = random.Random(42)
    a = generate_map(radius=5, rng=rng)
    b = generate_map(radius=5, seed=42)
    sa = [(r.q, r.r, r.room_type) for r in a.rooms.values()]
    sb = [(r.q, r.r, r.room_type) for r in b.rooms.values()]
    assert sa == sb


def test_hex_centers_and_vertices():
    gmap = generate_map(radius=5, seed=3)
    centers = hex_centers(gmap, size=40)
    assert set(centers) == set(gmap.rooms)
    # 中心在原点
    cx, cy = centers[gmap.start_id]
    assert abs(cx) < 1e-6 and abs(cy) < 1e-6
    # 顶点六边形，6 个顶点到中心距离 = 外接圆半径
    for x, y in hex_vertices(0.0, 0.0, 10.0):
        assert abs(math.hypot(x, y) - 10.0) < 1e-6
