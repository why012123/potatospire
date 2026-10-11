from __future__ import annotations

import os
from dataclasses import dataclass, field


def char_image_path(name: str, kind: str) -> str:
    """角色图片相对路径（相对 sources/images）。

    kind 可选：
      - "小人"   战斗立绘
      - "大头像" 选人页展示
      - "小头像" 顶部栏头像
    """
    return os.path.join("char", name, f"{kind}.png")


@dataclass(frozen=True)
class HeroDef:
    """角色定义（软编码）：数值、被动都集中在此登记。

    立绘等图片按约定放在 sources/images/char/<角色名>/ 下，
    通过 char_image_path(name, kind) 解析，无需在此写死路径。

    新增角色只需在下方 `HEROES` 列表追加一项。
    """

    key: str          # 唯一标识
    name: str         # 显示名（同时用作图片目录名）
    max_hp: int       # 血量上限
    passive_name: str  # 被动名称
    passive_desc: str  # 被动描述
    extra_draw: int = 0            # 被动参数：每回合额外抽牌数
    customizable_extra: bool = False  # 额外抽的牌是否可自定义重量
    mark_on_attack: bool = False   # 被动参数：攻击牌起效时对目标施加一层标记
    keep_block: bool = False       # 被动参数：回合结束格挡不重置
    gain_resilience_on_hit: bool = False  # 被动参数：失去血量韧性+1
    curse_on_turn: bool = False    # 被动参数：每回合施诅咒（阿兰娜）
    curse_mult: float = 1.0        # 诅咒伤害倍率（阿兰娜 = 1.5）
    start_statuses: dict = field(default_factory=dict)  # 出场自带状态
    deck: dict = field(default_factory=dict)  # 初始抽牌堆：{卡牌 key: 数量}


HEROES: list[HeroDef] = [
    HeroDef(
        key="蒸蛋",
        name="蒸蛋",
        max_hp=55,
        passive_name="额外抽卡",
        passive_desc="每回合多抽一张牌，且该牌重量可自定义（生效或丢弃后重置）",
        extra_draw=1,
        customizable_extra=True,
        deck={"strike": 5, "defend": 5, "burst": 2, "toughness": 2, "just_right": 1},
    ),
    HeroDef(
        key="邦尼",
        name="邦尼",
        max_hp=60,
        passive_name="标记",
        passive_desc="攻击牌起效时，对目标施加一层「标记」",
        mark_on_attack=True,
        deck={"strike": 5, "defend": 5, "burst": 1, "toughness": 2, "mark_card": 2},
    ),
    HeroDef(
        key="鼠鼠",
        name="鼠鼠",
        max_hp=45,
        passive_name="坚韧不拔",
        passive_desc="回合结束时格挡不重置；出场自带 1 层韧性，每失去一次血量韧性 +1",
        keep_block=True,
        gain_resilience_on_hit=True,
        start_statuses={"resilience": 1},
        deck={"strike": 4, "defend": 5, "toughness": 3, "guard": 2, "burst": 1},
    ),
    HeroDef(
        key="阿兰娜",
        name="阿兰娜",
        max_hp=52,
        passive_name="咒术",
        passive_desc="每回合指定一个敌人施加 5 层 5 伤害诅咒；自己施加的诅咒伤害 ×1.5",
        curse_on_turn=True,
        curse_mult=1.5,
        deck={"strike": 5, "defend": 6, "burst": 2, "toughness": 2},
    ),
]


def get_hero(key: str) -> HeroDef | None:
    """按 key 查找角色定义。"""
    for hero in HEROES:
        if hero.key == key:
            return hero
    return None
