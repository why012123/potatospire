from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatusDef:
    """状态定义（软编码）：每种状态的元数据在此登记。

    新增状态只需在下方 `STATUS_DEFS` 字典追加一项。
    """

    key: str          # 唯一标识
    name: str         # 显示名
    description: str = ""  # 效果描述


# ---- 状态库：新增状态在此登记 ----
STATUS_DEFS: dict[str, StatusDef] = {
    "mark": StatusDef("mark", "标记", "每层使受到的伤害 +1（永久，不衰减）"),
    "investigate": StatusDef("investigate", "调查", "拥有时受到伤害 +层数，每回合减少一层"),
    "bleed": StatusDef("bleed", "流血", "回合结束受到等同于层数的伤害，每回合触发后层数 -1"),
    "burn": StatusDef("burn", "灼烧", "回合结束受到层数*1%最大生命值伤害，触发后减半层数"),
    "poison": StatusDef("poison", "中毒", "回合结束受到当前生命百分比伤害，层数衰减"),
    "resilience": StatusDef("resilience", "韧性", "每一层使从卡牌获得的格挡 +1"),
    "counterattack": StatusDef("counterattack", "反击", "受到敌方攻击后，对攻击者造成等同于层数的反击伤害"),
    "hide": StatusDef("hide", "隐匿", "本回合免疫所有来自敌方的攻击伤害"),
    "vulnerable": StatusDef("vulnerable", "易伤", "受到伤害 +50%，生效后 -1 层"),
    "frozen": StatusDef("frozen", "冰冻", "玩家：本回合牌堆不向前推进；怪物：跳过本回合行动"),
    "territorial": StatusDef("territorial", "领地意识", "回合结束时获得等同于层数的力量"),
    "shrink": StatusDef("shrink", "缩小", "造成的攻击伤害减少 30%"),
    "artifact": StatusDef("artifact", "人工制品", "每层可以和一次负面效果立刻抵消"),
    "slow": StatusDef("slow", "缓慢", "本回合玩家每打出一张牌，该怪物受到的攻击伤害增加 10%"),
    "slippery": StatusDef("slippery", "滑溜", "生命值即将减少时减少一层，此次生命值不再减少"),
    "serum": StatusDef("serum", "血清", "恰好受到当前生命值的伤害才会死亡，否则生命归零时生命上限 -1、力量 +1、韧性 +1"),
    "encouraging_shout": StatusDef("encouraging_shout", "震撼性激励", "每回合开始为练家子 +3 临时力量，并使所有玩家受到 3 点无视护盾伤害；在场时练家子攻击次数 +1"),
    "synergy_defense": StatusDef("synergy_defense", "协同性防御", "获得防御时使大嗓门获得等量防御；在场时大嗓门受到伤害减半，且格挡跨回合保留（壁垒）"),
    "curse": StatusDef("curse", "诅咒", "蓝色数字（层数）每回合 -1，红色数字（伤害）每回合 +1；层数归零时受到等同于红色数字的伤害（可被格挡）"),
    "attached_curse": StatusDef("attached_curse", "附骨", "施加诅咒时，额外施加 2 个诅咒，层数与伤害是原诅咒的一半（向下取整，至少 1）"),
    "ritual": StatusDef("ritual", "咒仪", "受到伤害时，攻击者每有 5 层诅咒层数，受到伤害 -1（最多 -5）"),
    "incorporeal": StatusDef("incorporeal", "无实体", "每次损失血量只会损失 1 点（格挡耗尽后的剩余扣血封顶 1）"),
    "summon": StatusDef("summon", "召唤", "每回合开始时，若场上没有看守，则召唤一个看守并使其生命上限 +10"),
    "surveillance": StatusDef("surveillance", "监管", "每受到一次伤害，给伤害来源施加 1 层「罪证」"),
    "taunt": StatusDef("taunt", "嘲讽", "在场时，玩家所有需要选择敌人的牌只能选择它"),
    "evidence": StatusDef("evidence", "罪证", "每层使受到来自典狱长的攻击伤害 +2"),
    "coating": StatusDef("coating", "覆甲", "回合开始时获得等同于层数的格挡，随后在行动结束时减少一层"),
}


def get_status_def(key: str) -> StatusDef | None:
    """按 key 查找状态定义。"""
    return STATUS_DEFS.get(key)


@dataclass
class Status:
    """角色身上实际挂着的状态实例，带层数。

    诅咒等复合状态：value 存红色数字（伤害，基础值），source 存来源，
    mult 存爆发时最后乘上的伤害倍率（阿兰娜 = 1.5）。
    """

    status_id: str
    stacks: int = 1
    value: int = 0     # 附加数值（诅咒的红色伤害数字等）
    source: str = ""   # 来源标记（如阿兰娜的诅咒）
    mult: float = 1.0  # 诅咒爆发时结算的伤害倍率

    @property
    def name(self) -> str:
        d = get_status_def(self.status_id)
        return d.name if d else self.status_id

    @property
    def description(self) -> str:
        d = get_status_def(self.status_id)
        return d.description if d else ""

    def __str__(self) -> str:
        return f"{self.name}×{self.stacks}"


def make_status(status_id: str, stacks: int = 1, value: int = 0, source: str = "") -> Status:
    """按状态库创建状态实例（层数不会为负）。"""
    return Status(status_id=status_id, stacks=max(0, stacks), value=value, source=source)
