"""事件系统：定义事件结构、选项文案与事件库。

事件是肉鸽模式「事件房间」的内容。本模块只负责：
  1. 事件定义（软编码）：标题、描述、图片、选项；
  2. 事件选项的文案（标签 + 结果说明）。

选项的实际效果（改牌组 / 加遗物 / 改生命）由「运行层」（gui）根据选项 key 应用，
这样数据（文案）与逻辑（效果）分离。

新增事件只需在下方 `EVENTS` 追加一项。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventOption:
    """事件中的一个选项。"""

    key: str          # 唯一标识（gui 据此分发效果）
    label: str        # 选项按钮文字
    result_text: str  # 选中后展示的结果说明


@dataclass(frozen=True)
class GameEvent:
    """事件定义（软编码）。"""

    key: str
    title: str
    description: str
    image: str            # 图片路径（相对 sources/images）
    options: tuple[EventOption, ...]
    floor: int = 1        # 事件所属层数（1/2/3，只在该层出现）


# ---- 事件库：新增事件在此登记 ----
EVENTS: dict[str, GameEvent] = {
    "poison_takeout": GameEvent(
        key="poison_takeout",
        title="芬尼的毒外卖",
        description="芬尼（蒸蛋的外号）热情地端出一份冒着可疑绿烟的外卖，非让你尝尝。",
        image="events/芬尼的毒外卖.png",
        options=(
            EventOption(
                key="decline",
                label="好言拒绝",
                result_text="你婉拒了芬尼的好意，但心里过意不去。删除牌组里的一张牌，获得一张「愧疚」。",
            ),
            EventOption(
                key="devour",
                label="大吃特吃！",
                result_text="你硬着头皮吃光了外卖。恢复 15 点生命，获得遗物「吃剩的毒外卖」。",
            ),
        ),
    ),
    "boss_sale": GameEvent(
        key="boss_sale",
        title="老板娘大甩卖",
        description="老板娘扯着嗓子吆喝，摊子上堆满了各种好货，价格好商量。",
        image="",
        options=(
            EventOption(
                key="advertise",
                label="帮忙宣传",
                result_text="你帮忙吆喝了一下午。获得遗物「老板娘的怀表」。",
            ),
            EventOption(
                key="shop",
                label="趁机购物！",
                result_text="你掏钱买买买。失去 50 金币，从三张随机蓝色以上品质卡中任选一张。",
            ),
        ),
    ),
    "thirteenth_child": GameEvent(
        key="thirteenth_child",
        title="十三号孩子",
        description="一个瘦小的身影蹲在阴影里，浑身缠着绷带，向你咧开嘴。它看起来……不该活着。",
        image="",
        floor=2,
        options=(
            EventOption(
                key="fight",
                label="打！",
                result_text="你决定动手。",
            ),
            EventOption(
                key="run",
                label="跑！",
                result_text="你头也不回地逃走了，什么都没发生。",
            ),
        ),
    ),
}


def get_event(key: str) -> GameEvent | None:
    """按 key 查找事件定义。"""
    return EVENTS.get(key)


def random_event_key(floor: int = 1, rng=None) -> str:
    """随机返回指定层数的一个事件 key。

    分层规则：事件只出现在其所属层；若该层无事件则回退到第一层。
    """
    if rng is None:
        import random
        rng = random
    pool = [k for k, e in EVENTS.items() if e.floor == floor]
    if not pool:
        pool = [k for k, e in EVENTS.items() if e.floor == 1]
    if not pool:
        return next(iter(EVENTS))
    return rng.choice(pool)
