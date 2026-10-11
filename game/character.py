from __future__ import annotations

from dataclasses import dataclass, field

from .status import Status, make_status

# 负面状态集合：拥有「人工制品」时可被抵消
NEGATIVE_STATUSES = {
    "poison", "burn", "bleed", "investigate", "vulnerable",
    "mark", "frozen", "slow", "shrink",
}


@dataclass
class Character:
    """角色的公共数值模型：血量、攻击、受伤、治疗与状态。

    `Player` 与 `Enemy` 都继承它，保证数值访问和操作方式统一。
    """

    name: str = "角色"
    max_hp: int = 20
    attack: int = 0
    hp: int | None = None
    # 力量：永久攻击力加成（每点使攻击 +1）
    strength: int = 0
    # 临时力量：仅本回合生效的攻击力加成，回合结束清零
    temp_strength: int = 0
    # 格挡值：受伤时优先消耗格挡，格挡耗尽后才扣生命
    block: int = 0
    # 立绘/头像图片文件名（相对 sources/images，软编码）
    image: str = ""
    # 小头像（顶部栏等小尺寸展示用）
    icon: str = ""
    # 身上挂着的状态：状态 id -> 状态实例
    statuses: dict[str, Status] = field(default_factory=dict)
    # 独立的诅咒实例列表（每个诅咒层数/伤害独立推进）
    curses: list[Status] = field(default_factory=list)
    # 缓慢：本回合玩家已打出的牌数（旧日雕像专属，结算时清零）
    slow_counter: int = 0

    def __post_init__(self) -> None:
        if self.hp is None:
            self.hp = self.max_hp
        # 血量夹紧到 [0, max_hp]
        self.hp = max(0, min(self.hp, self.max_hp))

    # ---------- 状态 ----------
    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def is_dead(self) -> bool:
        return not self.is_alive

    @property
    def hp_ratio(self) -> float:
        """血量百分比，范围 0.0 ~ 1.0。"""
        if self.max_hp <= 0:
            return 0.0
        return max(0.0, min(1.0, self.hp / self.max_hp))

    # ---------- 数值变化 ----------
    def take_damage(self, amount: int) -> int:
        """受到伤害，返回实际扣除的血量（不会扣成负数）。

        默认先消耗格挡，格挡耗尽后才扣生命。
        若拥有「调查」状态，受到的伤害额外 +层数。
        若拥有「标记」状态，受到的伤害额外 +层数（永久，不衰减）。
        若拥有「易伤」状态，受到的伤害 +50%，生效后 -1 层。
        若拥有「滑溜」状态，生命即将减少时消耗一层，本次生命不再减少。
        """
        amount = max(0, amount)
        investigate = self.get_stacks("investigate")
        if investigate > 0:
            amount += investigate
        mark = self.get_stacks("mark")
        if mark > 0:
            amount += mark
        vulnerable = self.get_stacks("vulnerable")
        if vulnerable > 0:
            amount = int(amount * 1.5)
            self.set_stacks("vulnerable", vulnerable - 1)
        absorbed = min(self.block, amount)
        self.block -= absorbed
        remaining = amount - absorbed
        if remaining > 0:
            slippery = self.get_stacks("slippery")
            if slippery > 0:
                self.set_stacks("slippery", slippery - 1)
                return 0  # 滑溜抵消本次生命损失
        dealt = min(self.hp, remaining)
        # 无实体：每次损失血量封顶 1（格挡照常吸收）
        if self.get_stacks("incorporeal") > 0:
            dealt = min(dealt, 1)
        self.hp -= dealt
        return dealt

    def take_raw_damage(self, amount: int) -> int:
        """直接伤害：无视格挡与调查增伤，直接扣除生命。"""
        amount = max(0, amount)
        dealt = min(self.hp, amount)
        # 无实体：每次损失血量封顶 1
        if self.get_stacks("incorporeal") > 0:
            dealt = min(dealt, 1)
        self.hp -= dealt
        return dealt

    def heal(self, amount: int) -> int:
        """治疗，返回实际恢复的血量（不会超过上限）。"""
        amount = max(0, amount)
        healed = min(self.max_hp - self.hp, amount)
        self.hp += healed
        return healed

    def gain_block(self, amount: int) -> int:
        """获得格挡，返回实际获得的格挡值。"""
        amount = max(0, amount)
        self.block += amount
        return amount

    # ---------- 状态 ----------
    def set_stacks(self, status_id: str, stacks: int) -> int:
        """直接设置状态层数（<=0 时移除），返回最终层数。"""
        stacks = max(0, stacks)
        if stacks == 0:
            self.statuses.pop(status_id, None)
            return 0
        status = self.statuses.get(status_id)
        if status is None:
            status = make_status(status_id, 0)
            self.statuses[status_id] = status
        status.stacks = stacks
        return stacks

    def add_status(self, status_id: str, stacks: int = 1) -> int:
        """施加（或累加）状态，返回施加后的总层数。

        若拥有「人工制品」且施加的是负面状态，则消耗一层人工制品抵消该次负面效果。
        """
        stacks = max(0, stacks)
        if status_id in NEGATIVE_STATUSES and stacks > 0:
            artifact = self.get_stacks("artifact")
            if artifact > 0:
                self.set_stacks("artifact", artifact - 1)
                return 0  # 被人工制品抵消
        status = self.statuses.get(status_id)
        if status is None:
            status = make_status(status_id, 0)
            self.statuses[status_id] = status
        status.stacks += stacks
        return status.stacks

    def add_curse(self, stacks: int, value: int, source: str = "", mult: float = 1.0) -> int:
        """施加一个独立的诅咒实例（不与其他诅咒合并）。

        stacks = 蓝色数字（层数），value = 红色数字（伤害，基础值），
        source = 来源，mult = 爆发时最后乘上的伤害倍率（阿兰娜 = 1.5）。
        层数不同的诅咒分开结算与显示。
        """
        status = make_status("curse", stacks, value=value, source=source)
        status.mult = mult
        self.curses.append(status)
        return status.stacks

    def get_status(self, status_id: str) -> Status | None:
        """获取某个状态实例（没有则返回 None）。"""
        return self.statuses.get(status_id)

    def get_stacks(self, status_id: str) -> int:
        """获取某个状态的当前层数（没有则返回 0）。"""
        status = self.statuses.get(status_id)
        return status.stacks if status else 0

    def remove_status(self, status_id: str) -> Status | None:
        """移除某个状态，返回被移除的状态（没有则返回 None）。"""
        return self.statuses.pop(status_id, None)

    def clear_statuses(self) -> None:
        """清空所有状态（含诅咒）。"""
        self.statuses.clear()
        self.curses.clear()

    def active_statuses(self) -> list[Status]:
        """当前身上层数大于 0 的所有状态（含各个独立的诅咒实例）。"""
        base = [s for s in self.statuses.values() if s.stacks > 0]
        return base + [c for c in self.curses if c.stacks > 0]

    def __str__(self) -> str:
        return f"{self.name}(hp={self.hp}/{self.max_hp}, atk={self.attack})"
