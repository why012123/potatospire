"""遗物系统：定义遗物元数据、实例与倒计时推进。

遗物是肉鸽模式下跨战斗的被动道具，效果由「运行层」（gui）在对应时机应用，
本模块只负责：
  1. 遗物定义（软编码）：名称、描述、图片；
  2. 遗物实例：携带剩余生效战斗数（remaining_battles，None 表示永久）；
  3. 每场战斗结束后的倒计时推进（tick_relics）。

新增遗物只需在下方 `RELIC_DEFS` 追加一项，然后用 `make_relic(key, n)` 创建实例。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RelicDef:
    """遗物定义（软编码）。"""

    key: str          # 唯一标识
    name: str         # 显示名
    description: str = ""  # 效果描述
    image: str = ""        # 图片路径（相对 sources/images），可为空
    default_battles: int | None = None  # 默认剩余生效战斗数（None=永久）


@dataclass
class Relic:
    """玩家实际持有的遗物实例。"""

    relic_id: str
    # 剩余生效战斗数；None 表示永久生效
    remaining_battles: int | None = None

    @property
    def name(self) -> str:
        d = get_relic_def(self.relic_id)
        return d.name if d else self.relic_id

    @property
    def description(self) -> str:
        d = get_relic_def(self.relic_id)
        return d.description if d else ""

    def is_expiring(self) -> bool:
        """是否为有时限遗物（remaining_battles 非 None）。"""
        return self.remaining_battles is not None

    def __str__(self) -> str:  # pragma: no cover - 调试用
        if self.remaining_battles is None:
            return self.name
        return f"{self.name}（剩余 {self.remaining_battles} 场）"


# ---- 遗物库：新增遗物在此登记 ----
RELIC_DEFS: dict[str, RelicDef] = {
    "leftover_poison_takeout": RelicDef(
        key="leftover_poison_takeout",
        name="吃剩的毒外卖",
        description="之后三场战斗开始时，自身自带 5 层中毒（三场后失效）",
        image="treasures/吃剩的毒外卖.png",
        default_battles=3,
    ),
    "boss_watch": RelicDef(
        key="boss_watch",
        name="老板娘的怀表",
        description="到每个商店可以免费获得两样东西或服务",
        image="",
        default_battles=None,
    ),
    "mystery_relic": RelicDef(
        key="mystery_relic",
        name="神秘遗物",
        description="（占位）宝箱开出的遗物，效果待定",
        image="",
        default_battles=None,
    ),
    "bubble_machine": RelicDef(
        key="bubble_machine",
        name="泡泡机",
        description="获得时从牌组指定两张牌，为它们附加永久「冒泡」",
        image="",
        default_battles=None,
    ),
    "bad_glue": RelicDef(
        key="bad_glue",
        name="劣质胶水",
        description="获得时从牌组指定两张牌，为它们附加永久「黏糊」",
        image="",
        default_battles=None,
    ),
    "dilute_serum": RelicDef(
        key="dilute_serum",
        name="稀释血清",
        description="仅一次：受到致命伤害时，恢复 100% 生命值，但生命上限 -20",
        image="",
        default_battles=None,
    ),
}


def get_relic_def(key: str) -> RelicDef | None:
    """按 key 查找遗物定义。"""
    return RELIC_DEFS.get(key)


def make_relic(key: str, remaining_battles: int | None = None) -> Relic:
    """按遗物库创建实例；未显式给剩余场数时用定义默认值。"""
    d = RELIC_DEFS.get(key)
    if d is None:
        raise KeyError(f"未知遗物 key: {key}")
    if remaining_battles is None:
        remaining_battles = d.default_battles
    return Relic(relic_id=key, remaining_battles=remaining_battles)


def tick_relics(relics: list[Relic]) -> list[Relic]:
    """每场战斗结束后推进遗物倒计时，返回剩余生效的遗物列表。

    有时限遗物 remaining_battles 每次 -1，减到 0 即失效移除；永久遗物保留。
    """
    survivors: list[Relic] = []
    for relic in relics:
        if relic.remaining_battles is not None:
            relic.remaining_battles -= 1
            if relic.remaining_battles <= 0:
                continue  # 失效移除
        survivors.append(relic)
    return survivors
