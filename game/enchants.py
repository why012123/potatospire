"""附魔系统：定义附魔元数据与实例，并提供创建/查询/挂载函数。

附魔分两种：
  - 临时（temp）：本场战斗生效，可叠加多个；部分可叠层（如数值打击）。
  - 永久（perm）：整局肉鸽生效，一张卡最多一种。

数据软编码在下方 `ENCHANT_DEFS`，命名风格参照 `status.py` 的 `STATUS_DEFS`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅类型标注
    from .card import Card


@dataclass(frozen=True)
class EnchantDef:
    """附魔定义（软编码）：每种附魔的元数据在此登记。"""

    key: str              # 唯一标识
    name: str             # 显示名
    description: str = "" # 效果描述
    trigger: str = ""     # 触发时机：before_resolve / on_resolve / on_attack / static
    default_value: int = 0   # 默认值（重放 X 的 X 等）
    stackable: bool = False  # 是否可叠层（显示为「名字+N」）


# ---- 附魔库：新增附魔在此登记 ----
ENCHANT_DEFS: dict[str, EnchantDef] = {
    "bubble": EnchantDef(
        key="bubble",
        name="冒泡",
        description="无论这张牌处于牌堆哪个位置，一定第一个打出；多张冒泡同牌堆时顺序随机",
        trigger="before_resolve",
    ),
    "sticky": EnchantDef(
        key="sticky",
        name="黏糊",
        description="每次生效后重量 +1（封顶 10）",
        trigger="on_resolve",
    ),
    "stick_bottom": EnchantDef(
        key="stick_bottom",
        name="粘底",
        description="第一次生效后永远处于 1 号牌堆底，重量设为 11，不因生效进入弃牌堆",
        trigger="on_resolve",
    ),
    "replay": EnchantDef(
        key="replay",
        name="重放",
        description="这张牌连续生效 X+1 次",
        trigger="on_resolve",
        default_value=1,
    ),
    "poison": EnchantDef(
        key="poison",
        name="淬毒",
        description="攻击未格挡的伤害给目标 2 层中毒",
        trigger="on_attack",
    ),
    "num_strike": EnchantDef(
        key="num_strike",
        name="数值打击",
        description="该牌所有可变数字 +N",
        trigger="static",
        default_value=1,
        stackable=True,
    ),
    "precision": EnchantDef(
        key="precision",
        name="精准",
        description="打出时重量等于「目标」层数，则本次效果 ×2",
        trigger="on_resolve",
    ),
}


def get_enchant_def(key: str) -> EnchantDef | None:
    """按 key 查找附魔定义。"""
    return ENCHANT_DEFS.get(key)


@dataclass
class Enchant:
    """卡牌上实际挂着的附魔实例。"""

    enchant_id: str
    value: int = 0  # 层数 / 重放 X 等数值

    @property
    def name(self) -> str:
        d = get_enchant_def(self.enchant_id)
        return d.name if d else self.enchant_id

    @property
    def description(self) -> str:
        d = get_enchant_def(self.enchant_id)
        return d.description if d else ""

    @property
    def display(self) -> str:
        """显示文本（叠层附魔带 +N，重放带 X，精准写死效果说明）。"""
        d = get_enchant_def(self.enchant_id)
        name = d.name if d else self.enchant_id
        if self.enchant_id == "replay":
            return f"{name} {self.value}"
        if self.enchant_id == "precision":
            return f"{name}：效果×2"
        if d and d.stackable and self.value:
            return f"{name}+{self.value}"
        return name

    def __str__(self) -> str:
        return self.display


def make_enchant(enchant_id: str, value: int | None = None) -> Enchant:
    """按附魔库创建附魔实例；未显式给值时用定义默认值。"""
    d = ENCHANT_DEFS.get(enchant_id)
    if d is None:
        raise KeyError(f"未知附魔 key: {enchant_id}")
    if value is None:
        value = d.default_value
    return Enchant(enchant_id=enchant_id, value=value)


# ---- 卡牌上的挂载 / 查询辅助（duck typing，避免循环导入） ----

def _temp_list(card: "Card") -> list[Enchant]:
    """取卡牌的临时附魔列表（兼容旧 Card 无此字段时返回空列表）。"""
    return getattr(card, "temp_enchants", [])


def has_temp_enchant(card: "Card", key: str) -> bool:
    """卡牌是否带某临时附魔。"""
    return any(e.enchant_id == key for e in _temp_list(card))


def has_perm_enchant(card: "Card", key: str) -> bool:
    """卡牌是否带某永久附魔。"""
    return getattr(card, "perm_enchant", "") == key


def has_enchant(card: "Card", key: str) -> bool:
    """卡牌是否带某附魔（临时或永久）。"""
    return has_perm_enchant(card, key) or has_temp_enchant(card, key)


def temp_enchant_value(card: "Card", key: str) -> int:
    """取某临时附魔的累计数值（叠层求和）；不存在返回 0。"""
    total = 0
    for e in _temp_list(card):
        if e.enchant_id == key:
            total += e.value
    return total


def add_temp_enchant(card: "Card", key: str, value: int | None = None) -> None:
    """给卡牌追加一个临时附魔；可叠层的附魔累加层数。"""
    d = ENCHANT_DEFS.get(key)
    if d is None:
        raise KeyError(f"未知附魔 key: {key}")
    if value is None:
        value = d.default_value
    lst = _temp_list(card)
    if d.stackable:
        for e in lst:
            if e.enchant_id == key:
                e.value += value
                return
    lst.append(Enchant(enchant_id=key, value=value))


def set_perm_enchant(card: "Card", key: str) -> None:
    """给卡牌设置唯一永久附魔（覆盖旧值）。"""
    if key and key not in ENCHANT_DEFS:
        raise KeyError(f"未知附魔 key: {key}")
    card.perm_enchant = key
