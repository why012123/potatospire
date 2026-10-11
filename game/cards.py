from __future__ import annotations

from dataclasses import dataclass

from .card import Card, CardType, Rarity
from .enchants import add_temp_enchant


@dataclass(frozen=True)
class CardDef:
    """卡牌定义（软编码）：数值与效果都集中在此登记。

    新增卡牌只需在下方 `CARD_DEFS` 字典追加一项，然后用 `make_card(key)` 创建实例。
    """

    key: str
    name: str
    weight: int
    card_type: CardType
    cost: int = 0
    description: str = ""
    damage: int = 0          # 造成伤害
    block: int = 0           # 获得格挡
    attack_bonus: int = 0    # 该牌堆之后所有攻击值加成
    needs_target: bool = False  # 是否需要选择目标（敌方/友方/自己）
    apply_mark: bool = False    # 标记：选定敌方施加一层标记
    toughness: bool = False     # 韧性：同牌堆防御牌整局 weight+1/block+1
    attack_weight_up: bool = False  # 爆发：之后攻击牌整局 weight+1
    block_from_pile: bool = False  # 加护：获得牌堆内卡牌数量的格挡
    heal: int = 0               # 喝水：回复生命
    weight_reduce_all: int = 0  # 减肥：同牌组所有牌重量 -N
    draw_cards: int = 0         # 抽牌：抽 N 张
    buff_numbers: bool = False  # 数值打击：同牌组所有数值 +1
    enchant_poison: bool = False  # 淬毒：攻击牌附魔
    poison_detonate: bool = False  # 毒发
    gain_hide: int = 0          # 隐匿：获得 hide
    mark_all: int = 0           # 弱点调查：全体敌方标记
    self_poison: int = 0        # 毒外卖：自身中毒
    apply_curse: bool = False   # 诅咒你：施加诅咒
    curse_stacks: int = 0       # 诅咒层数
    curse_damage: int = 0       # 诅咒伤害
    gain_attached_curse: int = 0  # 附骨诅咒：获得附骨层数
    gain_ritual: int = 0        # 咒仪之礼：获得咒仪层数
    detonate_curses: bool = False  # 大限已至：引爆目标所有诅咒
    block_damage: bool = False  # 全身撞击：格挡值伤害
    discard_hand_block: bool = False  # 岿然不动
    logic: bool = False         # 逻辑牌：拖到任意牌堆立即生效
    exhaust: bool = False       # 消耗牌：生效后进消耗牌堆
    boost_hand_weight: int = 0  # 蓄势：选一张手牌重量 +N
    swap_hand_weights: bool = False  # 轻重缓急：交换两张手牌重量
    pangu: bool = False         # 盘古开天
    iron_wall: bool = False     # 铁壁
    invert_pile: bool = False   # 倒金字塔
    remove_pile_top: bool = False  # 纠正错误
    science_correction: bool = False  # 科学勘误
    buff_all_weight: bool = False  # 汉堡
    heavy_strike: bool = False  # 重击
    lurk: bool = False          # 潜伏
    mark_strike: bool = False   # 标记打击
    counterattack: bool = False  # 熊孩子的报复
    gain_strength: int = 0       # 获得力量
    quirk: int = 0               # 奇巧 X：重量恰为 X 时触发
    quirk_bonus_block: int = 0   # 奇巧额外护甲
    quirk_bonus_strength: int = 0  # 奇巧额外力量
    start_enchants: tuple = ()   # 出场自带临时附魔 key
    select_mode: str = ""       # 选择模式
    innate: bool = False        # 固有：首回合固定加入手牌
    hero: str | None = None     # 归属角色（None=公共）
    rarity: Rarity = Rarity.COMMON


CARD_DEFS: dict[str, CardDef] = {
    "strike": CardDef(
        key="strike",
        name="打击",
        weight=5,
        card_type=CardType.ATTACK,
        cost=1,
        description="对目标造成 {damage} 点伤害",
        damage=6,
        needs_target=True,
    ),
    "defend": CardDef(
        key="defend",
        name="防御",
        weight=4,
        card_type=CardType.SKILL,
        cost=1,
        description="使自己获得 {block} 点格挡",
        block=5,
    ),
    "burst": CardDef(
        key="burst",
        name="爆发",
        weight=2,
        card_type=CardType.POWER,
        cost=1,
        description="使该牌堆之后所有攻击值 +{attack_bonus}，并让之后攻击牌重量 +1",
        attack_bonus=2,
        attack_weight_up=True,
    ),
    "toughness": CardDef(
        key="toughness",
        name="韧性",
        weight=3,
        card_type=CardType.POWER,
        cost=1,
        description="同牌堆所有防御牌，重量 +1（封顶 10），防御值 +1",
        toughness=True,
    ),
    "mark_card": CardDef(
        key="mark_card",
        name="标记",
        weight=4,
        card_type=CardType.SKILL,
        cost=1,
        description="选定一名敌方，施加一层「标记」",
        needs_target=True,
        apply_mark=True,
    ),
    "guard": CardDef(
        key="guard",
        name="加护",
        weight=1,
        card_type=CardType.SKILL,
        cost=1,
        description="获得牌堆内卡牌数量的格挡",
        block_from_pile=True,
    ),
    # ---------- 公共牌 ----------
    "drink": CardDef(
        key="drink",
        name="喝水",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="回复 {heal} 点生命",
        heal=2,
        logic=True,
    ),
    "slim": CardDef(
        key="slim",
        name="减肥",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="同牌组下所有牌重量永久 -2（最低 1）",
        weight_reduce_all=2,
        logic=True,
    ),
    "draw": CardDef(
        key="draw",
        name="抽牌",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="抽取 {draw} 张牌",
        draw_cards=2,
        logic=True,
    ),
    "num_strike": CardDef(
        key="num_strike",
        name="数值打击",
        weight=0,
        card_type=CardType.POWER,
        cost=0,
        description="给同牌堆剩余牌附魔：数值打击+1（该牌所有可变数字 +1）",
        buff_numbers=True,
        rarity=Rarity.RARE,
    ),
    # ---------- 新增公共牌 ----------
    "store_power": CardDef(
        key="store_power",
        name="蓄势",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="选择一张手牌，其重量本回合 +3（最高为 10）",
        boost_hand_weight=3,
        logic=True,
        select_mode="hand_1",
    ),
    "priority": CardDef(
        key="priority",
        name="轻重缓急",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="选择两张手牌，交换它们的重量",
        swap_hand_weights=True,
        logic=True,
        rarity=Rarity.UNCOMMON,
        select_mode="hand_2",
    ),
    "pangu": CardDef(
        key="pangu",
        name="盘古开天",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="选择至多三张重量相同的手牌，分别设为 a-2、a、a+2（两张则 a-1、a+1）",
        pangu=True,
        logic=True,
        rarity=Rarity.UNCOMMON,
        select_mode="hand_same",
    ),
    "iron_wall": CardDef(
        key="iron_wall",
        name="铁壁",
        weight=10,
        card_type=CardType.SKILL,
        cost=1,
        description="获得 3 点格挡，吸收后面至多三个牌堆所有防御牌的格挡值，并使它们格挡 +1。生效时消耗",
        iron_wall=True,
        exhaust=True,
        rarity=Rarity.UNCOMMON,
    ),
    "inverted_pyramid": CardDef(
        key="inverted_pyramid",
        name="倒金字塔",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="倒置一个牌堆（倒置后仍可向上放牌）",
        invert_pile=True,
        logic=True,
        rarity=Rarity.RARE,
        select_mode="pile",
    ),
    "correct_mistake": CardDef(
        key="correct_mistake",
        name="纠正错误",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="选择任意一个牌堆，删除其顶牌",
        remove_pile_top=True,
        logic=True,
        select_mode="pile",
    ),
    "science_correction": CardDef(
        key="science_correction",
        name="科学勘误",
        weight=2,
        card_type=CardType.SKILL,
        cost=1,
        description="生效时删除下一个牌堆里的第 X 张牌（X 为这张卡当前的重量）",
        science_correction=True,
        rarity=Rarity.UNCOMMON,
    ),
    "hamburger": CardDef(
        key="hamburger",
        name="汉堡",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="使场上所有牌（手牌与四个牌堆）重量 +1",
        buff_all_weight=True,
        logic=True,
    ),
    "heavy_strike": CardDef(
        key="heavy_strike",
        name="重击",
        weight=7,
        card_type=CardType.ATTACK,
        cost=1,
        description="造成 2 点伤害。若回合结束时处于牌堆顶，则伤害永久 +5",
        damage=2,
        heavy_strike=True,
        needs_target=True,
        rarity=Rarity.UNCOMMON,
    ),
    # ---------- 诅咒牌（仅事件获得，不出现在选牌列表） ----------
    "guilt": CardDef(
        key="guilt",
        name="愧疚",
        weight=10,
        card_type=CardType.CURSE,
        cost=0,
        description="无法被打出，仅占用牌位。三场战斗后移出牌组。",
        rarity=Rarity.CURSE,
        hero="_curse",
    ),
    # ---------- 邦尼特有 ----------
    "poison_enchant": CardDef(
        key="poison_enchant",
        name="淬毒",
        weight=0,
        card_type=CardType.POWER,
        cost=1,
        description="同牌组所有攻击获得附魔：淬毒（未格挡伤害给目标 2 层中毒）。生效时消耗",
        enchant_poison=True,
        hero="邦尼",
        rarity=Rarity.RARE,
        logic=True,
        exhaust=True,
    ),
    "poison_burst": CardDef(
        key="poison_burst",
        name="毒发",
        weight=8,
        card_type=CardType.ATTACK,
        cost=1,
        description="对目标造成中毒层数 ×4 的伤害，并清除其所有中毒",
        needs_target=True,
        poison_detonate=True,
        hero="邦尼",
    ),
    "hide_card": CardDef(
        key="hide_card",
        name="隐匿",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="获得 1 层「隐匿」（本回合免疫敌方攻击伤害）",
        gain_hide=1,
        hero="邦尼",
        logic=True,
    ),
    "lurk": CardDef(
        key="lurk",
        name="潜伏",
        weight=10,
        card_type=CardType.SKILL,
        cost=1,
        description="获得 4 点格挡与 1 层「隐匿」。若本回合尚未打出攻击牌，抽 1 张牌",
        lurk=True,
        hero="邦尼",
        rarity=Rarity.UNCOMMON,
    ),
    "mark_strike": CardDef(
        key="mark_strike",
        name="标记打击",
        weight=5,
        card_type=CardType.ATTACK,
        cost=1,
        description="对所有有标记的敌人造成三倍于标记层数的伤害",
        mark_strike=True,
        hero="邦尼",
        rarity=Rarity.UNCOMMON,
    ),
    # ---------- 蒸蛋特有 ----------
    "weakness_survey": CardDef(
        key="weakness_survey",
        name="弱点调查",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="给全体敌方施加 2 层「标记」",
        mark_all=2,
        hero="蒸蛋",
        logic=True,
    ),
    "poison_takeout": CardDef(
        key="poison_takeout",
        name="毒外卖",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="给自己施加 2 层「中毒」",
        self_poison=2,
        hero="蒸蛋",
        logic=True,
    ),
    # ---------- 鼠鼠特有 ----------
    "body_slam": CardDef(
        key="body_slam",
        name="全身撞击",
        weight=6,
        card_type=CardType.ATTACK,
        cost=1,
        description="对目标造成当前自身格挡值的伤害",
        needs_target=True,
        block_damage=True,
        hero="鼠鼠",
        rarity=Rarity.UNCOMMON,
    ),
    "unshakable": CardDef(
        key="unshakable",
        name="岿然不动",
        weight=0,
        card_type=CardType.SKILL,
        cost=1,
        description="丢弃所有手牌，每张使自身获得两点格挡与一层韧性",
        discard_hand_block=True,
        hero="鼠鼠",
        rarity=Rarity.RARE,
        logic=True,
    ),
    "bear_revenge": CardDef(
        key="bear_revenge",
        name="熊孩子的报复",
        weight=4,
        card_type=CardType.POWER,
        cost=1,
        description="打出时获得等同于当前韧性值的反击层数。生效后消耗",
        counterattack=True,
        hero="鼠鼠",
        rarity=Rarity.RARE,
        exhaust=True,
    ),
    "just_right": CardDef(
        key="just_right",
        name="恰如其分",
        weight=1,
        card_type=CardType.SKILL,
        cost=1,
        description="指定三张牌附魔「精准」，本场获得「目标」效果",
        hero="蒸蛋",
        rarity=Rarity.RARE,
        logic=True,
        select_mode="deck_3",
        innate=True,
    ),
    "iron_cleave": CardDef(
        key="iron_cleave",
        name="铁斩波",
        weight=1,
        card_type=CardType.ATTACK,
        cost=1,
        description="造成 {damage} 点伤害。奇巧5：额外获得 10 点护甲",
        damage=7,
        needs_target=True,
        quirk=5,
        quirk_bonus_block=10,
        start_enchants=("sticky",),
        hero="蒸蛋",
        rarity=Rarity.UNCOMMON,
    ),
    "enter_state": CardDef(
        key="enter_state",
        name="进入状态",
        weight=2,
        card_type=CardType.SKILL,
        cost=1,
        description="获得 1 点力量。奇巧1：额外获得 2 点力量",
        gain_strength=1,
        quirk=1,
        quirk_bonus_strength=2,
        hero="蒸蛋",
        rarity=Rarity.UNCOMMON,
    ),
    # ---------- 阿兰娜特有 ----------
    "attached_curse": CardDef(
        key="attached_curse",
        name="附骨诅咒",
        weight=3,
        card_type=CardType.POWER,
        cost=1,
        description="使自己获得一层「附骨」：施加诅咒时，额外施加 2 个诅咒，层数与伤害是原诅咒的一半。生效时消耗",
        gain_attached_curse=1,
        hero="阿兰娜",
        rarity=Rarity.RARE,
        exhaust=True,
    ),
    "curse_ritual": CardDef(
        key="curse_ritual",
        name="咒仪之礼",
        weight=10,
        card_type=CardType.POWER,
        cost=1,
        description="使自己获得一层「咒仪」：受到伤害时，攻击者每有 5 层诅咒层数，受到伤害 -1（最多 -5）。生效时消耗",
        gain_ritual=1,
        hero="阿兰娜",
        rarity=Rarity.UNCOMMON,
        exhaust=True,
    ),
    "curse_you": CardDef(
        key="curse_you",
        name="诅咒你",
        weight=1,
        card_type=CardType.SKILL,
        cost=1,
        description="对目标施加 2 层 2 伤害诅咒",
        needs_target=True,
        apply_curse=True,
        curse_stacks=2,
        curse_damage=2,
        hero="阿兰娜",
        rarity=Rarity.COMMON,
    ),
    "doomsday": CardDef(
        key="doomsday",
        name="大限已至",
        weight=10,
        card_type=CardType.ATTACK,
        cost=1,
        description="使目标身上所有诅咒立即爆发伤害（并移除）",
        needs_target=True,
        detonate_curses=True,
        hero="阿兰娜",
        rarity=Rarity.RARE,
    ),
}


def get_card_def(key: str) -> CardDef | None:
    """按 key 查找卡牌定义。"""
    return CARD_DEFS.get(key)


def make_card(key: str) -> Card:
    """按卡牌库定义创建卡牌实例；未知 key 抛异常。"""
    d = CARD_DEFS.get(key)
    if d is None:
        raise KeyError(f"未知卡牌 key: {key}")
    description = d.description
    if d.logic:
        description = f"逻辑牌；{description}"
    if d.innate:
        description = f"固有；{description}"
    card = Card(
        name=d.name,
        weight=d.weight,
        cost=d.cost,
        card_type=d.card_type,
        block_from_pile=d.block_from_pile,
        rarity=d.rarity,
        description=description,
        damage=d.damage,
        block=d.block,
        attack_bonus=d.attack_bonus,
        needs_target=d.needs_target,
        apply_mark=d.apply_mark,
        toughness=d.toughness,
        attack_weight_up=d.attack_weight_up,
        heal=d.heal,
        weight_reduce_all=d.weight_reduce_all,
        draw_cards=d.draw_cards,
        buff_numbers=d.buff_numbers,
        enchant_poison=d.enchant_poison,
        poison_detonate=d.poison_detonate,
        gain_hide=d.gain_hide,
        mark_all=d.mark_all,
        self_poison=d.self_poison,
        apply_curse=d.apply_curse,
        curse_stacks=d.curse_stacks,
        curse_damage=d.curse_damage,
        gain_attached_curse=d.gain_attached_curse,
        gain_ritual=d.gain_ritual,
        detonate_curses=d.detonate_curses,
        block_damage=d.block_damage,
        discard_hand_block=d.discard_hand_block,
        logic=d.logic,
        exhaust=d.exhaust,
        boost_hand_weight=d.boost_hand_weight,
        swap_hand_weights=d.swap_hand_weights,
        pangu=d.pangu,
        iron_wall=d.iron_wall,
        invert_pile=d.invert_pile,
        remove_pile_top=d.remove_pile_top,
        science_correction=d.science_correction,
        buff_all_weight=d.buff_all_weight,
        heavy_strike=d.heavy_strike,
        lurk=d.lurk,
        mark_strike=d.mark_strike,
        counterattack=d.counterattack,
        gain_strength=d.gain_strength,
        quirk=d.quirk,
        quirk_bonus_block=d.quirk_bonus_block,
        quirk_bonus_strength=d.quirk_bonus_strength,
        select_mode=d.select_mode,
        innate=d.innate,
    )
    # 出场自带临时附魔
    for ek in d.start_enchants:
        add_temp_enchant(card, ek)
    return card


def public_card_keys() -> list[str]:
    """返回公共牌 key 列表（所有角色都能带）。"""
    return [k for k, d in CARD_DEFS.items() if d.hero is None]


def hero_card_keys(hero_key: str) -> list[str]:
    """返回某角色特有牌 key 列表。"""
    return [k for k, d in CARD_DEFS.items() if d.hero == hero_key]


def cards_for_hero(hero_key: str) -> list[str]:
    """返回某角色可选牌（公共 + 特有）。"""
    return public_card_keys() + hero_card_keys(hero_key)


def build_deck(counts: dict[str, int]) -> list[Card]:
    """按 {卡牌 key: 数量} 构建抽牌堆。"""
    cards: list[Card] = []
    for key, n in counts.items():
        cards.extend(make_card(key) for _ in range(n))
    return cards
