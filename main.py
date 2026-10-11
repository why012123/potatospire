from __future__ import annotations

import random

from game.card import Card
from game.cards import make_card
from game.engine import Engine
from game.player import Player
from game.state import GameState


def build_demo_game(seed: int | None = None) -> Engine:
    rng = random.Random(seed)
    # 用卡牌库构建卡组：打击/防御/爆发各若干张
    keys = ["strike", "strike", "strike", "defend", "defend", "burst", "burst"]
    cards = [make_card(k) for k in keys]
    rng.shuffle(cards)
    player = Player(draw_pile=cards)
    state = GameState(player=player)
    return Engine(state, rng=rng)


def render(engine: Engine) -> None:
    state = engine.state
    player = state.player
    print()
    print(
        f"回合 {state.turn} | 活跃牌堆 {state.active_slots}/{player.max_slots} "
        f"| 抽牌堆 {len(player.draw_pile)} | 弃牌堆 {len(player.discard_pile)} "
        f"| 阶段 {state.phase.name}"
    )

    print("手牌:")
    if not player.hand:
        print("  (无)")
    for i, card in enumerate(player.hand):
        print(f"  [{i}] {card}")

    print("牌堆:")
    for i, pile in enumerate(player.pile_slots):
        locked = " [锁定]" if i >= state.active_slots else ""
        content = " <- ".join(str(c) for c in pile.cards) if pile.cards else "(空)"
        print(f"  槽位{i + 1}{locked}: {content}")


def print_log(engine: Engine, since: int) -> int:
    log = engine.state.log
    for line in log[since:]:
        print(f"  > {line}")
    return len(log)


def cli() -> None:
    engine = build_demo_game(seed=42)
    engine.start_turn()
    log_index = 0

    while True:
        log_index = print_log(engine, log_index)
        render(engine)
        cmd = input("命令 [a 手牌索引 槽位 / skip / q]: ").strip().lower()

        if cmd in {"q", "quit", "exit"}:
            print("退出。")
            return

        if cmd in {"skip", "s"}:
            engine.skip()
            engine.start_turn()
            continue

        if cmd.startswith("a "):
            parts = cmd.split()
            if len(parts) != 3:
                print("用法: a <手牌索引> <槽位>（槽位从 1 开始）")
                continue
            try:
                hand_index = int(parts[1])
                slot_index = int(parts[2]) - 1
            except ValueError:
                print("索引必须是整数")
                continue
            engine.add_card_to_pile(hand_index, slot_index)
            continue

        print("未知命令。")


def main() -> None:
    import sys

    if "--cli" in sys.argv:
        cli()
        return
    from gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
