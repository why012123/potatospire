from __future__ import annotations

from dataclasses import dataclass, field

from .character import Character


@dataclass
class Intent:
    """怪物单回合意图。

    kind 可选：
      - "attack"          单次攻击（伤害 = value + 力量）
      - "multi"           多次攻击（times 次，每次 = value + 力量）
      - "strength"        获得 value 点力量
      - "buff"            获得 block 点格挡 + strength 点力量
      - "attack_block"    攻击（value + 力量）并获得 block 点格挡
      - "attack_strength" 攻击（value + 力量）并获得 strength 点力量
      - "shrink"          给玩家施加缩小（层数 value）
      - "sleep"           沉睡（待机，不行动）
    """

    kind: str
    value: int = 0
    times: int = 1
    block: int = 0
    strength: int = 0
    heal: int = 0          # 恢复生命（heal_block / summon_minion 恢复用）
    minion: str = ""       # 召唤 / 强化的 minion 名称

    def describe(self, current_strength: int = 0) -> str:
        """生成意图描述文本（含力量加成）。"""
        if self.kind == "attack":
            return f"攻击 {self.value + current_strength}"
        if self.kind == "multi":
            return f"攻击 {self.value + current_strength}×{self.times}"
        if self.kind == "strength":
            return f"力量 +{self.value}"
        if self.kind == "buff":
            parts = []
            if self.block:
                parts.append(f"格挡 +{self.block}")
            if self.strength:
                parts.append(f"力量 +{self.strength}")
            return "，".join(parts) if parts else "待机"
        if self.kind == "attack_block":
            return f"攻击 {self.value + current_strength} 并获得 {self.block} 格挡"
        if self.kind == "attack_strength":
            return f"攻击 {self.value + current_strength} 并获得 {self.strength} 力量"
        if self.kind == "shrink":
            return "缩小"
        if self.kind == "sleep":
            return "沉睡"
        if self.kind == "gain_counterattack":
            return f"反击 +{self.value}"
        if self.kind == "gain_resilience":
            return f"韧性 +{self.value}"
        if self.kind == "heal_block":
            parts = []
            if self.heal:
                parts.append(f"回复 {self.heal}")
            if self.block:
                parts.append(f"格挡 +{self.block}")
            return "，".join(parts) if parts else "待机"
        if self.kind == "summon_minion":
            return f"召唤 {self.minion}"
        if self.kind == "buff_minions_strength":
            return f"{self.minion} 力量 +{self.value}"
        return "待机"


@dataclass
class Enemy(Character):
    """敌方单位：数值与行为统一由 `Character` 基类提供。

    通过 `make_enemy(name)` 从敌方库创建，行动模式由 `pattern` 定义。
    """

    # 前导意图（只在开局执行一次，之后循环 pattern）
    lead: list[Intent] = field(default_factory=list)
    # 当前 lead 索引
    lead_index: int = 0
    # 行动循环：每回合按顺序执行一项意图，循环往复
    pattern: list[Intent] = field(default_factory=list)
    # 当前行动索引
    pattern_index: int = 0

    def take_damage(self, amount: int) -> int:
        """受到伤害；带「血清」状态时走特殊结算。"""
        if self.get_stacks("serum") > 0:
            return self._take_serum_damage(amount)
        return super().take_damage(amount)

    def _take_serum_damage(self, amount: int) -> int:
        """血清：恰好扣到当前生命值才死亡；否则生命归零时上限 -1、力量 +1、韧性 +1。

        返回实际减少的生命值（未死亡时回满新上限，故返回 0）。
        """
        amount = max(0, amount)
        absorbed = min(self.block, amount)
        self.block -= absorbed
        remaining = amount - absorbed
        if remaining == self.hp:
            # 恰好等于当前生命：真正死亡
            self.hp = 0
            return remaining
        if remaining > self.hp:
            # 超过当前生命：不死亡，上限 -1、力量 +1、韧性 +1，生命回满新上限
            self.max_hp = max(1, self.max_hp - 1)
            self.strength += 1
            self.add_status("resilience", 1)
            self.hp = self.max_hp
            return 0
        # 少于当前生命：正常掉血
        self.hp -= remaining
        return remaining


# ---- 敌方库：预置模板，新增敌人只需在此登记 ----
# image 为相对 sources/images 的路径
_ENEMY_TEMPLATES: dict[str, dict] = {
    "劣人杀手": {
        "max_hp": 70,
        "attack": 0,
        "image": "enemy/劣人杀手.webp",
        "pattern": [
            Intent("attack", value=7),
            Intent("multi", value=7, times=2),
            Intent("strength", value=3),
        ],
    },
    "拳击构造体": {
        "max_hp": 40,
        "attack": 0,
        "image": "enemy/拳击构造体.webp",
        "pattern": [
            Intent("buff", block=7, strength=1),
            Intent("attack", value=14),
            Intent("multi", value=5, times=2),
        ],
    },
    "芬尼": {
        "max_hp": 30,
        "attack": 3,
        "image": "",
        "pattern": [Intent("attack", value=3)],
    },
    # 肉鸽模式 Boss 占位符（1 滴血，便于测试推进到下一层）
    "Boss 占位符": {
        "max_hp": 1,
        "attack": 0,
        "image": "",
        "pattern": [Intent("attack", value=1)],
    },
    # ---------- 新增怪物 ----------
    "多伦斯异鸟": {
        "max_hp": 70,
        "attack": 0,
        "image": "enemy/多伦斯异鸟.webp",
        "start_statuses": {"territorial": 1},
        "pattern": [
            Intent("attack", value=17),
            Intent("multi", value=3, times=3),
        ],
    },
    "小啃兽": {
        "max_hp": 39,
        "hp_range": (37, 41),
        "attack": 0,
        "image": "enemy/小啃兽.webp",
        "pattern": [
            Intent("attack", value=12),
            Intent("attack_block", value=6, block=5),
            Intent("strength", value=3),
        ],
    },
    "缩小甲虫": {
        "max_hp": 30,
        "attack": 0,
        "image": "enemy/缩小甲虫.webp",
        "pattern": [
            Intent("shrink"),
            Intent("attack", value=7),
            Intent("attack", value=13),
        ],
    },
    "立柱构造体": {
        "max_hp": 60,
        "attack": 0,
        "image": "enemy/立柱构造体.webp",
        "start_statuses": {"artifact": 1},
        "start_block": 14,
        "lead": [Intent("strength", value=2)],
        "pattern": [
            Intent("attack_strength", value=7, strength=2),
            Intent("attack_strength", value=7, strength=2),
            Intent("multi", value=5, times=2),
        ],
    },
    "旧日雕像": {
        "max_hp": 120,
        "attack": 0,
        "image": "enemy/旧日雕像.webp",
        "start_statuses": {"slow": 1},
        "lead": [
            Intent("sleep"),
            Intent("strength", value=10),
        ],
        "pattern": [Intent("attack", value=13)],
    },
    "墨影幻灵": {
        "max_hp": 173,
        "attack": 0,
        "image": "enemy/墨影幻灵.webp",
        "start_statuses": {"slippery": 9},
        "pattern": [
            Intent("attack", value=7),
            Intent("multi", value=6, times=2),
            Intent("attack", value=26),
            Intent("strength", value=2),
        ],
    },
    "十三号孩子": {
        "max_hp": 14,
        "attack": 0,
        "image": "",
        "start_statuses": {"serum": 1},
        "pattern": [
            Intent("attack_block", value=1, block=2),
        ],
    },
    "大嗓门": {
        "max_hp": 30,
        "attack": 0,
        "image": "enemy/大嗓门.png",
        "start_statuses": {"encouraging_shout": 1},
        "pattern": [
            Intent("attack_block", value=5, block=5),
        ],
    },
    "练家子": {
        "max_hp": 60,
        "attack": 0,
        "image": "enemy/练家子.png",
        "start_statuses": {"synergy_defense": 1},
        "pattern": [
            Intent("attack_block", value=2, block=5),
        ],
    },
    # 二层 Boss：典狱长 + 看守
    "典狱长": {
        "max_hp": 5,
        "attack": 0,
        "image": "enemy/典狱长.png",
        "start_statuses": {"incorporeal": 1, "summon": 1},
        "pattern": [
            Intent("attack", value=1),
        ],
    },
    "看守": {
        "max_hp": 25,
        "attack": 0,
        "image": "enemy/看守.png",
        "start_statuses": {"surveillance": 1, "taunt": 1},
        "pattern": [
            Intent("attack_block", value=7, block=5),
            Intent("strength", value=3),
        ],
    },
    # 二层精英：迎宾雁
    "迎宾雁": {
        "max_hp": 108,
        "attack": 0,
        "image": "enemy/迎宾雁.png",
        "lead": [Intent("strength", value=1)],
        "pattern": [
            Intent("strength", value=2),
            Intent("attack", value=3),
            Intent("buff", block=15),
        ],
    },
    # 二层小怪：罪恶茶壶
    "罪恶茶壶": {
        "max_hp": 26,
        "attack": 0,
        "image": "enemy/罪恶茶壶.png",
        "start_strength": 3,
        "start_statuses": {"coating": 10, "counterattack": 5},
        "pattern": [
            Intent("attack", value=15),
            Intent("strength", value=3),
        ],
    },
    # 一层 Boss：海盗王噶呜
    "海盗王噶呜": {
        "max_hp": 170,
        "attack": 0,
        "image": "enemy/海盗王噶呜.png",
        "start_statuses": {"counterattack": 10},
        "pattern": [
            Intent("gain_counterattack", value=1),
            Intent("buff", block=5),
            Intent("gain_resilience", value=1),
        ],
    },
    # 一层 Boss：科学怪呜 + 科学怪猿
    "科学怪呜": {
        "max_hp": 100,
        "attack": 0,
        "image": "enemy/科学怪呜.png",
        "pattern": [
            Intent("summon_minion", minion="科学怪猿", heal=20),
            Intent("heal_block", heal=10, block=20),
            Intent("buff_minions_strength", value=5, minion="科学怪猿"),
        ],
    },
    "科学怪猿": {
        "max_hp": 40,
        "attack": 0,
        "image": "enemy/科学怪猿.png",
        "pattern": [
            Intent("attack", value=10),
        ],
    },
}

# Boss 占位符名称（肉鸽模式每层 Boss 用）
BOSS_PLACEHOLDER_NAME = "Boss 占位符"


def enemy_names() -> list[str]:
    """返回战斗模拟可选敌人的名称列表（不含 Boss 占位符）。"""
    return [n for n in _ENEMY_TEMPLATES if n != BOSS_PLACEHOLDER_NAME]


def make_enemy(name: str) -> Enemy:
    """按名称从敌方库创建实例；未知名称回退到默认数值。"""
    import random

    template = _ENEMY_TEMPLATES.get(name)
    if template is None:
        return Enemy(name=name, max_hp=10, attack=1, pattern=[Intent("attack", value=1)])
    max_hp = template["max_hp"]
    if "hp_range" in template:
        lo, hi = template["hp_range"]
        max_hp = random.randint(lo, hi)
    enemy = Enemy(
        name=name,
        max_hp=max_hp,
        attack=template["attack"],
        image=template.get("image", ""),
        lead=list(template.get("lead", [])),
        pattern=list(template.get("pattern", [])),
    )
    # 初始力量
    enemy.strength = template.get("start_strength", 0)
    # 初始状态 / 初始格挡
    for sid, stacks in template.get("start_statuses", {}).items():
        enemy.add_status(sid, stacks)
    if template.get("start_block", 0) > 0:
        enemy.gain_block(template["start_block"])
    return enemy


def get_upcoming_intents(enemy: Enemy, n: int = 2) -> list[tuple[Intent, int]]:
    """返回敌人未来 n 回合的意图，及执行该意图时的力量值。

    力量值会随着前面的力量意图逐步累加，使意图显示更准确。
    前导意图（lead）优先于循环 pattern。
    """
    result: list[tuple[Intent, int]] = []
    if not enemy.pattern and not enemy.lead:
        return result
    strength = enemy.strength
    # 剩余前导意图
    lead_queue = list(enemy.lead[enemy.lead_index:])
    pat_idx = enemy.pattern_index

    while len(result) < n:
        if lead_queue:
            intent = lead_queue.pop(0)
        elif enemy.pattern:
            intent = enemy.pattern[pat_idx % len(enemy.pattern)]
            pat_idx += 1
        else:
            break
        result.append((intent, strength))
        strength = _predict_strength(intent, strength)
    return result


def _predict_strength(intent: Intent, strength: int) -> int:
    """预判意图执行后力量值的变化。"""
    if intent.kind == "strength":
        return strength + intent.value
    if intent.kind == "buff":
        return strength + intent.strength
    if intent.kind == "attack_strength":
        return strength + intent.strength
    return strength
