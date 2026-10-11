from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from itertools import count

from .enchants import get_enchant_def

_id_counter = count(1)


class CardType(Enum):
    """卡牌类型。"""

    ATTACK = auto()   # 攻击牌
    SKILL = auto()    # 技能牌
    POWER = auto()    # 能力牌
    STATUS = auto()   # 状态牌（负面）
    CURSE = auto()    # 诅咒牌（负面）


class Rarity(Enum):
    """稀有度。"""

    STARTER = auto()
    COMMON = auto()
    UNCOMMON = auto()
    RARE = auto()
    SPECIAL = auto()
    CURSE = auto()  # 诅咒牌（紫色，负面）


@dataclass
class Card:
    name: str
    weight: int
    cost: int = 0
    card_type: CardType = CardType.SKILL
    rarity: Rarity = Rarity.COMMON
    description: str = ""
    tags: tuple[str, ...] = ()
    # 是否可自定义重量（蒸蛋被动：多抽的那张牌）
    customizable_weight: bool = False
    # 效果数值：造成伤害 / 获得格挡 / 之后攻击值加成
    damage: int = 0
    block: int = 0
    attack_bonus: int = 0
    # 是否需要选择目标（如「打击」可选敌方/友方/自己）
    needs_target: bool = False
    # 标记：选定一名敌方施加一层「标记」
    apply_mark: bool = False
    # 韧性：同牌堆所有防御牌整局 weight+1、block+1
    toughness: bool = False
    # 爆发：之后攻击牌整局 weight+1
    attack_weight_up: bool = False
    # 加护：获得「牌堆内卡牌数」的格挡
    block_from_pile: bool = False
    # 喝水：回复生命
    heal: int = 0
    # 减肥：同牌组所有牌重量永久 -N（最低 1）
    weight_reduce_all: int = 0
    # 抽牌：直接触发，抽取 N 张
    draw_cards: int = 0
    # 数值打击：同牌组所有牌数值（伤害/格挡/攻击加成）+1
    buff_numbers: bool = False
    # 淬毒：同牌组所有攻击牌获得附魔
    enchant_poison: bool = False
    # 毒发：对目标造成中毒层数*N 伤害并清除中毒
    poison_detonate: bool = False
    # 隐匿：获得 hide 层数
    gain_hide: int = 0
    # 弱点调查：给全体敌方施加 N 层标记
    mark_all: int = 0
    # 毒外卖：给自己 N 层中毒
    self_poison: int = 0
    # 诅咒你：对目标施加诅咒（stacks 层 damage 伤害）
    apply_curse: bool = False
    curse_stacks: int = 0
    curse_damage: int = 0
    # 附骨诅咒：使自己获得附骨层数
    gain_attached_curse: int = 0
    # 咒仪之礼：使自己获得咒仪层数
    gain_ritual: int = 0
    # 大限已至：使目标身上所有诅咒立即爆发
    detonate_curses: bool = False
    # 全身撞击：对目标造成当前格挡值伤害
    block_damage: bool = False
    # 岿然不动：丢弃所有手牌，每张 2 格挡（恒定）+ 1 韧性
    discard_hand_block: bool = False
    # 附魔类型（攻击牌生效时附加，如 "poison"）
    enchant: str = ""
    # 数值打击附魔层数：这张牌所有可变数字 +n
    num_enchant: int = 0
    # 永久附魔 key（整局肉鸽生效，最多一种；空串=无）
    perm_enchant: str = ""
    # 临时附魔实例列表（本场战斗生效，可多个，部分可叠层）
    temp_enchants: list = field(default_factory=list)
    # 粘底：首次生效后固定于 1 号牌堆底（引擎内部状态）
    stuck_bottom: bool = False
    # 重放镜像：重放展开出的非末次生效副本，不重复进弃牌堆
    replay_mirror: bool = False
    # 逻辑牌：拖到任意牌堆立即生效，不进牌堆、不占牌堆容量
    logic: bool = False
    # 消耗牌：生效后进消耗牌堆（本场战斗后续无法使用）
    exhaust: bool = False
    # 蓄势：选一张手牌，其重量 +N（本回合，封顶 10）
    boost_hand_weight: int = 0
    # 轻重缓急：交换两张手牌重量
    swap_hand_weights: bool = False
    # 盘古开天：调整同重量手牌（2 张→a-1/a+1，3 张→a-2/a/a+2）
    pangu: bool = False
    # 铁壁：吸收后面牌堆防御卡数值，生效时消耗
    iron_wall: bool = False
    # 倒金字塔：倒置一个牌堆
    invert_pile: bool = False
    # 纠正错误：删除一个牌堆的顶牌
    remove_pile_top: bool = False
    # 科学勘误：删除下一牌堆第 X 张（X=当前重量）
    science_correction: bool = False
    # 汉堡：场上所有牌（手牌+牌堆）重量 +1
    buff_all_weight: bool = False
    # 重击：回合结束处于牌堆顶则伤害永久 +5
    heavy_strike: bool = False
    # 潜伏：获得格挡+隐匿，未打攻击牌则抽 1
    lurk: bool = False
    # 标记打击：对所有有标记敌人造成 3×层数伤害
    mark_strike: bool = False
    # 熊孩子的报复：获得反击 buff
    counterattack: bool = False
    # 获得力量（永久）
    gain_strength: int = 0
    # 奇巧 X：打出时重量恰好为 X 时触发额外效果
    quirk: int = 0
    # 奇巧触发：额外护甲 / 额外力量
    quirk_bonus_block: int = 0
    quirk_bonus_strength: int = 0
    # 选择模式：""（无）/ "hand_1" / "hand_2" / "hand_same" / "pile" / "deck_3"
    select_mode: str = ""
    # 固有：每场战斗首回合固定加入手牌
    innate: bool = False
    # 精准计数：本场战斗第几次以「恰如其分」相同费用打出
    precision_count: int = 0
    # 整局一次性强化是否已应用（保证 weight/block 加成只生效一次）
    buffed: bool = False
    instance_id: int = field(default_factory=lambda: next(_id_counter))

    @property
    def display(self) -> str:
        """用于界面的简要显示文本。"""
        return f"{self.name}（重量 {self.weight}，费用 {self.cost}）"

    @property
    def effect_text(self) -> str:
        """根据当前数值动态生成效果描述（数值被整局强化后自动更新）。"""
        n = self.num_enchant
        parts: list[str] = []
        if self.damage > 0:
            parts.append(f"伤害 {self.damage + n}")
        if self.block > 0:
            parts.append(f"格挡 {self.block + n}")
        if self.attack_bonus > 0:
            parts.append(f"攻击 +{self.attack_bonus + n}")
        if self.apply_mark:
            parts.append("施加标记")
        if self.toughness:
            parts.append("强化防御牌")
        return " ".join(parts) if parts else ""

    @property
    def enchant_text(self) -> str:
        """临时附魔描述（显示在卡面底部文本框）。

        包含旧字段（淬毒/数值打击）与新的临时附魔列表。
        """
        parts: list[str] = []
        if self.enchant == "poison":
            parts.append("淬毒")
        if self.num_enchant > 0:
            parts.append(f"数值打击+{self.num_enchant}")
        for e in self.temp_enchants:
            parts.append(e.display)
        return "，".join(parts)

    @property
    def perm_enchant_text(self) -> str:
        """永久附魔描述（金色，整局生效）。"""
        if not self.perm_enchant:
            return ""
        d = get_enchant_def(self.perm_enchant)
        return d.name if d else self.perm_enchant

    @property
    def temp_enchant_text(self) -> str:
        """临时附魔描述（紫色，本场生效）。"""
        return self.enchant_text

    @property
    def rendered_description(self) -> str:
        """用实时数值填充描述中的占位符。

        数值被整局强化后自动更新，供卡面文字渲染使用。
        """
        n = self.num_enchant
        try:
            return self.description.format(
                damage=self.damage + n,
                block=self.block + n,
                attack_bonus=self.attack_bonus + n,
                heal=self.heal + n,
                draw=self.draw_cards + n,
            )
        except (KeyError, IndexError, ValueError):
            return self.description

    def __str__(self) -> str:
        return f"{self.name}(w={self.weight})"

    def __repr__(self) -> str:
        return (
            f"Card(name={self.name!r}, weight={self.weight}, cost={self.cost}, "
            f"type={self.card_type.name}, rarity={self.rarity.name})"
        )
