"""药水系统：定义药水元数据、实例与效果。

药水是肉鸽模式下可携带、战斗中随时使用的消耗品。
本模块只负责：
  1. 药水定义（软编码）：名称、描述、效果类型与数值；
  2. 药水实例；
  3. 随机药水。

药水效果由运行层（gui）在对应时机应用：
  - heal     回复生命
  - strength 本场战斗力量 +N
  - block    获得格挡
  - draw     抽牌
  - energy   清除本回合已用放牌次数（重置 pile_turn_counts）
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class PotionDef:
    """药水定义（软编码）。"""

    key: str          # 唯一标识
    name: str         # 显示名
    description: str = ""  # 效果描述
    effect: str = ""       # 效果类型：heal/strength/block/draw/energy
    value: int = 0         # 效果数值


@dataclass
class Potion:
    """玩家持有的一瓶药水实例。"""

    potion_id: str

    @property
    def name(self) -> str:
        d = get_potion_def(self.potion_id)
        return d.name if d else self.potion_id

    @property
    def description(self) -> str:
        d = get_potion_def(self.potion_id)
        return d.description if d else ""

    def __str__(self) -> str:  # pragma: no cover - 调试用
        return self.name


# ---- 药水库：新增药水在此登记 ----
POTION_DEFS: dict[str, PotionDef] = {
    "health_potion": PotionDef(
        key="health_potion",
        name="治疗药水",
        description="回复 15 点生命",
        effect="heal",
        value=15,
    ),
    "strength_potion": PotionDef(
        key="strength_potion",
        name="力量药水",
        description="本场战斗力量 +2",
        effect="strength",
        value=2,
    ),
    "block_potion": PotionDef(
        key="block_potion",
        name="格挡药水",
        description="获得 12 点格挡",
        effect="block",
        value=12,
    ),
    "draw_potion": PotionDef(
        key="draw_potion",
        name="抽牌药水",
        description="抽取 3 张牌",
        effect="draw",
        value=3,
    ),
}


def get_potion_def(key: str) -> PotionDef | None:
    """按 key 查找药水定义。"""
    return POTION_DEFS.get(key)


def make_potion(key: str) -> Potion:
    """按药水库创建实例；未知 key 抛异常。"""
    if key not in POTION_DEFS:
        raise KeyError(f"未知药水 key: {key}")
    return Potion(potion_id=key)


def random_potion_key(rng: random.Random | None = None) -> str:
    """随机返回一个药水 key。"""
    rng = rng or random.Random()
    keys = list(POTION_DEFS.keys())
    return rng.choice(keys) if keys else "health_potion"
