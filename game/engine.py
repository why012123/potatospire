from __future__ import annotations

import copy
import random

from .card import Card, CardType
from .enchants import add_temp_enchant, has_enchant, temp_enchant_value
from .enemy import make_enemy
from .pile import Pile, WeightRuleError
from .state import GameState, Phase


class Engine:
    def __init__(self, state: GameState, rng: random.Random | None = None) -> None:
        self.state = state
        self.rng = rng or random.Random()
        # 结算队列：供 GUI 动画逐步推进（从顶到底的快照）
        self.resolution_queue: list[Card] = []
        # 完整牌堆快照（韧性遍历用）
        self.resolution_snapshot: list[Card] = []
        # 本牌堆结算中的攻击值加成（爆发累积）
        self.attack_bonus: int = 0
        # 蓄势等「本回合」重量临时加成，回合结束回退
        self._turn_weight_buffs: list[Card] = []
        # 粘底卡：首次生效后暂存于此，回合开始时插入 1 号牌堆底
        self._stuck_cards: list[Card] = []
        # 伤害飘字事件队列：(目标角色, 未被格挡的伤害值)，GUI 每帧消费
        self.damage_floats: list[tuple[object, int]] = []
        # 待召唤的典狱长（看守死后延迟一回合再召唤）
        self._pending_summon: set[int] = set()

    # ---------- 日志 ----------
    def log(self, message: str) -> None:
        self.state.log.append(message)

    # ---------- 抽牌 ----------
    def draw_cards(self, n: int = 5) -> list[Card]:
        player = self.state.player
        drawn: list[Card] = []

        for _ in range(n):
            if not player.draw_pile:
                if player.discard_pile:
                    self.log("抽牌堆为空，洗弃牌堆成为新抽牌堆")
                    player.draw_pile = player.discard_pile[:]
                    player.discard_pile.clear()
                    self.rng.shuffle(player.draw_pile)
                else:
                    self.log("抽牌堆和弃牌堆都为空，停止抽牌")
                    break
            drawn.append(player.draw_pile.pop())

        player.hand.extend(drawn)
        return drawn

    # ---------- 回合 ----------
    def start_turn(self) -> None:
        self.state.turn += 1
        player = self.state.player
        player.pile_turn_counts = [0] * player.max_slots
        player.attacks_played_this_turn = 0
        # 粘底卡：回合开始时插入 1 号牌堆底
        for c in self._stuck_cards:
            player.pile_slots[0].cards.append(c)
        self._stuck_cards = []
        # 回退「本回合」重量临时加成（蓄势）
        for c in self._turn_weight_buffs:
            c.weight = max(1, c.weight - 3)
        self._turn_weight_buffs = []
        self.state.active_slots = 3 if self.state.turn == 1 else player.max_slots
        # 恰如其分「目标」层数：每回合 +1，到 10 回 1
        if getattr(player, "has_target", False):
            player.target_level = player.target_level % 10 + 1
            self.log(f"目标层数：{player.target_level}")
        self.log(
            f"===== 回合 {self.state.turn} 开始，活跃牌堆 {self.state.active_slots}/{player.max_slots} ====="
        )
        # 震撼性激励：大嗓门在场时，回合开始给练家子 +3 临时力量，所有玩家 -3（无视护盾）
        self._apply_encouraging_shout()
        # 召唤：带「召唤」的敌人若场上没有看守，则召唤一个看守
        self._process_summons()
        # 怪加防御：回合开始时执行怪物意图的防御（格挡）部分
        self._enemy_defend_at_turn_start()
        # 固有卡：首回合固定加入手牌
        self._draw_innate_cards()
        drawn = self.draw_cards(5 + player.extra_draw)
        if drawn:
            # 蒸蛋被动：多抽的最后 extra_draw 张牌重量可自定义
            if player.extra_draw > 0:
                for c in drawn[-player.extra_draw:]:
                    c.customizable_weight = True
            self.log("抽到: " + ", ".join(str(c) for c in drawn))
        self.state.phase = Phase.PLAYER_ACTION

    def _draw_innate_cards(self) -> None:
        """固有卡：首回合从抽牌堆固定加入手牌（不影响正常抽牌）。"""
        if self.state.turn != 1:
            return
        player = self.state.player
        for card in list(player.draw_pile):
            if getattr(card, "innate", False):
                player.draw_pile.remove(card)
                player.hand.append(card)
                self.log(f"固有：{card.name} 固定加入手牌")

    def apply_curse_passive(self, enemy) -> None:
        """阿兰娜被动：给指定敌人施加 5 层 5 伤害诅咒。

        红色数字（伤害）存基础值 5，×1.5 倍率在诅咒爆发时最后乘上（见 _process_curse），
        这样随回合 +1 的红字才是正常基础伤害。
        """
        player = self.state.player
        base = 5
        self._apply_curse_with_bone(enemy, 5, base, source=player.name, mult=player.curse_mult)
        self.log(f"{player.name}：对 {enemy.name} 施加 5 层 {base} 伤害诅咒")

    def _apply_curse_with_bone(self, enemy, stacks: int, value: int, source: str = "", mult: float = 1.0) -> None:
        """施加诅咒；若玩家带「附骨」，额外施加 2 个一半层数/伤害的诅咒。"""
        enemy.add_curse(stacks, value, source=source, mult=mult)
        player = self.state.player
        if player.get_stacks("attached_curse") > 0:
            half_s = max(1, stacks // 2)
            half_v = max(1, value // 2)
            for _ in range(2):
                enemy.add_curse(half_s, half_v, source=source, mult=mult)
            self.log(f"附骨：额外施加 2 个 {half_s} 层 {half_v} 伤害诅咒")

    # ---------- 玩家加牌 ----------
    def add_card_to_pile(self, hand_index: int, slot_index: int) -> bool:
        player = self.state.player

        if self.state.phase != Phase.PLAYER_ACTION:
            self.log("当前不是玩家行动阶段，不能加牌")
            return False

        if not (0 <= slot_index < self.state.active_slots):
            self.log(f"槽位 {slot_index + 1} 本回合不可用")
            return False

        if not (0 <= hand_index < len(player.hand)):
            self.log("无效手牌索引")
            return False

        card = player.hand[hand_index]
        pile = player.pile_slots[slot_index]

        # 诅咒牌无法打出（仅占用牌位）
        if card.card_type is CardType.CURSE:
            self.log(f"诅咒牌「{card.name}」无法打出")
            return False

        # 逻辑牌：拖到任意牌堆立即生效，不进牌堆、不占容量
        if card.logic:
            player.hand.pop(hand_index)
            card.customizable_weight = False
            self._play_logic_card(card, slot_index)
            return True

        # 单回合加牌上限：1 号牌堆上限 = 牌堆数量，之后每个槽位依次递减 1
        capacity = player.max_slots - slot_index
        if player.pile_turn_counts[slot_index] >= capacity:
            self.log(f"牌堆 {slot_index + 1} 本回合已放满（上限 {capacity} 张）")
            return False

        try:
            pile.add_to_top(card)
        except WeightRuleError as exc:
            self.log(str(exc))
            return False

        player.hand.pop(hand_index)
        player.pile_turn_counts[slot_index] += 1
        card.customizable_weight = False  # 生效后重置
        self.log(f"把 {card} 放到牌堆 {slot_index + 1} 顶部")
        return True

    def _all_player_cards(self) -> list[Card]:
        """玩家当前持有的所有牌（手牌 + 抽牌堆 + 弃牌堆 + 所有牌堆）。"""
        player = self.state.player
        cards = list(player.hand) + list(player.draw_pile) + list(player.discard_pile)
        for pile in player.pile_slots:
            cards.extend(pile.cards)
        return cards

    def _play_logic_card(self, card: Card, slot_index: int) -> None:
        """逻辑牌立即生效：设置作用域后执行效果，进弃牌堆。"""
        pile = self.state.player.pile_slots[slot_index]
        # 作用域快照：
        #   resolution_snapshot = 整个牌组（减肥 / 淬毒等「同牌组」效果）
        #   resolution_queue   = 拖到的牌堆所有牌（数值打击等「同牌堆」效果）
        self.resolution_snapshot = self._all_player_cards()
        self.resolution_queue = list(pile.cards)
        self.attack_bonus = 0
        self.log(f"逻辑牌 {card} 立即生效")
        self.play_card(card, target=None)
        self.resolution_snapshot = []
        self.resolution_queue = []

    def play_select_card(
        self, card: Card, hand_indices: list[int], pile_indices: list[int]
    ) -> None:
        """应用需要选择目标的逻辑牌效果，然后进弃牌堆。

        支持：
          - 蓄势（hand_1）：手牌重量 +N（本回合）
          - 轻重缓急（hand_2）：交换两张手牌重量
          - 盘古开天（hand_same）：调整同重量手牌
          - 倒金字塔 / 纠正错误（pile）：倒置牌堆 / 删除顶牌
        """
        player = self.state.player

        if card.boost_hand_weight and hand_indices:
            idx = hand_indices[0]
            if 0 <= idx < len(player.hand):
                c = player.hand[idx]
                c.weight = min(10, c.weight + card.boost_hand_weight)
                self._turn_weight_buffs.append(c)
                self.log(f"{card.name}：{c.name} 重量 +{card.boost_hand_weight}（现 {c.weight}）")

        elif card.swap_hand_weights and len(hand_indices) >= 2:
            i, j = hand_indices[0], hand_indices[1]
            if 0 <= i < len(player.hand) and 0 <= j < len(player.hand):
                a, b = player.hand[i], player.hand[j]
                a.weight, b.weight = b.weight, a.weight
                self.log(f"{card.name}：交换 {a.name} 与 {b.name} 的重量")

        elif card.pangu and hand_indices:
            # 取同重量的手牌，按数量设为 a-2/a/a+2 或 a-1/a+1
            cards = [player.hand[i] for i in hand_indices if 0 <= i < len(player.hand)]
            if len(cards) >= 2:
                a = cards[0].weight
                if len(cards) >= 3:
                    offsets = (-2, 0, 2)
                else:
                    offsets = (-1, 1)
                for c, off in zip(cards, offsets):
                    c.weight = max(1, min(10, a + off))
                self.log(f"{card.name}：调整 {len(cards)} 张手牌重量")

        elif card.invert_pile and pile_indices:
            idx = pile_indices[0]
            if 0 <= idx < len(player.pile_slots):
                pile = player.pile_slots[idx]
                pile.cards.reverse()
                self.log(f"{card.name}：倒置牌堆 {idx + 1}")

        elif card.remove_pile_top and pile_indices:
            idx = pile_indices[0]
            if 0 <= idx < len(player.pile_slots):
                pile = player.pile_slots[idx]
                if pile.cards:
                    removed = pile.cards.pop(0)
                    self.log(f"{card.name}：删除牌堆 {idx + 1} 顶牌 {removed}")

        elif card.select_mode == "deck_3" and hand_indices:
            # 恰如其分：从牌组指定三张卡附魔「精准」；本场获得「目标」效果（已有则不再重复）
            deck = self._deck_cards()
            for i in hand_indices:
                if 0 <= i < len(deck):
                    add_temp_enchant(deck[i], "precision")
                    self.log(f"{card.name}：{deck[i].name} 获得「精准」")
            if not self.state.player.has_target:
                self.state.player.has_target = True
                self.state.player.target_level = 1
                self.log(f"{card.name}：本场获得「目标」效果（目标层数 1）")

        player.discard_pile.append(card)

    def _deck_cards(self) -> list[Card]:
        """玩家自己的当前牌组（手牌 + 抽牌堆 + 弃牌堆），恰如其分选牌用。"""
        player = self.state.player
        return list(player.hand) + list(player.draw_pile) + list(player.discard_pile)

    # ---------- Skip ----------
    def skip(self) -> None:
        if self.state.phase != Phase.PLAYER_ACTION:
            self.log("当前阶段不能 Skip")
            return

        self.clear_hand_to_discard()
        self.status_phase()
        # 冰冻：玩家本回合牌堆不向前推进
        frozen = self.state.player.get_stacks("frozen")
        if frozen > 0:
            self.state.player.set_stacks("frozen", frozen - 1)
            self.log(f"玩家被冰冻，牌堆不向前推进（冰冻 {frozen} -> {frozen - 1}）")
        else:
            self.resolve_front_pile()
        self.monster_phase()
        self.state.phase = Phase.TURN_END

    def _grow_heavy_strikes(self) -> None:
        """重击：回合结束时处于牌堆顶，伤害永久 +5。"""
        for pile in self.state.player.pile_slots:
            top = pile.top
            if top is not None and top.heavy_strike:
                top.damage += 5
                self.log(f"{top.name} 处于牌堆顶，伤害 +5（现 {top.damage}）")

    def clear_hand_to_discard(self) -> None:
        self.state.phase = Phase.CLEAR_HAND
        player = self.state.player
        for c in player.hand:
            c.customizable_weight = False  # 丢弃后重置
        count = len(player.hand)
        player.discard_pile.extend(player.hand)
        player.hand.clear()
        self.log(f"Skip：{count} 张手牌进入弃牌堆")

    def status_phase(self) -> None:
        self.state.phase = Phase.STATUS
        self.log("状态判定：")
        self._process_statuses(self.state.player)
        for enemy in self.state.alive_enemies:
            self._process_statuses(enemy)

    # ---------- 状态结算 ----------
    def _process_statuses(self, char) -> None:
        """按顺序结算一个角色的负面状态：中毒 > 灼烧 > 流血 > 诅咒，最后调查减层。"""
        self._process_poison(char)
        self._process_burn(char)
        self._process_bleed(char)
        self._process_curse(char)
        self._process_investigate(char)

    def _is_protected_warden(self, enemy) -> bool:
        """典狱长是否受到看守保护（看守在场时典狱长不受任何伤害）。"""
        if enemy is None or enemy.name != "典狱长":
            return False
        return any(e.is_alive and e.name == "看守" for e in self.state.enemies)

    def _process_poison(self, char) -> None:
        stacks = char.get_stacks("poison")
        if stacks <= 0:
            return
        if self._is_protected_warden(char):
            return
        if stacks <= 5:
            dmg = max(1, int(char.hp * stacks * 0.02))
            dmg = min(dmg, max(0, char.hp - 1))  # 不会扣为 0，最低扣到 1
            dealt = char.take_raw_damage(dmg)
            char.set_stacks("poison", stacks - 1)
            self._apply_surveillance(char, dealt)
            self.log(f"{char.name} 中毒：受到 {dmg} 点伤害（层数 {stacks} -> {stacks - 1}）")
        else:
            dmg = max(1, int(char.hp * stacks * 0.04))
            dmg = min(dmg, max(0, char.hp - 1))
            dealt = char.take_raw_damage(dmg)
            char.set_stacks("poison", stacks // 2)
            self._apply_surveillance(char, dealt)
            self.log(f"{char.name} 中毒：受到 {dmg} 点伤害（层数 {stacks} -> {stacks // 2}）")

    def _process_burn(self, char) -> None:
        stacks = char.get_stacks("burn")
        if stacks <= 0:
            return
        if self._is_protected_warden(char):
            return
        dmg = max(1, int(char.max_hp * stacks * 0.01))
        dealt = char.take_raw_damage(dmg)
        char.set_stacks("burn", stacks // 2)
        self._apply_surveillance(char, dealt)
        self.log(f"{char.name} 灼烧：受到 {dmg} 点伤害（层数 {stacks} -> {stacks // 2}）")

    def _process_bleed(self, char) -> None:
        stacks = char.get_stacks("bleed")
        if stacks <= 0:
            return
        if self._is_protected_warden(char):
            return
        dealt = char.take_raw_damage(stacks)
        char.set_stacks("bleed", stacks - 1)
        self._apply_surveillance(char, dealt)
        self.log(f"{char.name} 流血：受到 {stacks} 点伤害（层数 {stacks} -> {stacks - 1}）")

    def _process_investigate(self, char) -> None:
        stacks = char.get_stacks("investigate")
        if stacks <= 0:
            return
        char.set_stacks("investigate", stacks - 1)
        self.log(f"{char.name} 调查层数减少：{stacks} -> {stacks - 1}")

    def _process_curse(self, char) -> None:
        """诅咒：每个诅咒实例独立结算（层数不同分开处理）。

        蓝色数字（层数）每回合 -1，红色数字（伤害）每回合 +1；
        层数归零时受到等同于红色数字的伤害（可被格挡），随后移除该诅咒。
        阿兰娜的 ×1.5 倍率在爆发时最后乘上，红字显示的是基础伤害。
        """
        for status in list(char.curses):
            status.stacks -= 1
            status.value += 1
            if status.stacks <= 0:
                dmg = status.value
                mult = getattr(status, "mult", 1.0) or 1.0
                dmg = int(dmg * mult)
                char.curses.remove(status)
                if self._is_protected_warden(char):
                    self.log(f"{char.name} 受到看守保护，诅咒爆发被免疫")
                    continue
                dealt = char.take_damage(dmg)  # 可被格挡
                self._apply_surveillance(char, dealt)
                self.log(f"{char.name} 诅咒爆发：受到 {dmg} 点伤害")
            else:
                self.log(f"{char.name} 诅咒层数 -1（{status.stacks}），伤害 +1（{status.value}）")

    def check_game_over(self) -> str | None:
        """返回 "victory" / "defeat"，未结束返回 None。"""
        enemies = self.state.enemies
        # 典狱长死亡即胜利（无论看守是否存活）
        if any(e.name == "典狱长" and not e.is_alive for e in enemies):
            return "victory"
        if enemies and not self.state.alive_enemies:
            return "victory"
        # 血清：任意敌人生命上限被削到 1 时，该敌人立即被击败
        for enemy in enemies:
            if enemy.get_stacks("serum") > 0 and enemy.max_hp <= 1:
                enemy.hp = 0
        if any(e.name == "典狱长" and not e.is_alive for e in enemies):
            return "victory"
        if enemies and not self.state.alive_enemies:
            return "victory"
        if not self.state.player.is_alive:
            return "defeat"
        return None

    def resolve_front_pile(self) -> None:
        """同步结算最前牌堆（兼容旧调用，一次性打完）。"""
        self.begin_resolution()
        while self.resolution_pending():
            self.step_resolution()
        self.end_resolution()

    # ---------- 逐步结算（供动画推进） ----------
    def begin_resolution(self) -> None:
        """快照最前牌堆，进入结算阶段，重置本牌堆攻击加成。"""
        self.state.phase = Phase.RESOLVE_PILE
        front = self.state.player.pile_slots[0]
        raw = front.snapshot_top_to_bottom()
        # 完整快照：韧性需要遍历「同牌堆所有牌」（含已打出的）
        self.resolution_snapshot = list(raw)
        # 冒泡：带「冒泡」的牌提到最前（多张顺序随机）
        raw = self._order_bubbles(raw)
        # 重放：带「重放 X」的牌展开为 X+1 个节点（前 X 个为镜像，不重复进弃牌堆）
        raw = self._expand_replays(raw)
        self.resolution_queue = raw
        self.attack_bonus = 0
        if not self.resolution_queue:
            self.log("最前牌堆为空，无牌打出")
        else:
            self.log(
                "结算最前牌堆，从顶到底打出: "
                + ", ".join(str(c) for c in self.resolution_queue)
            )

    def _order_bubbles(self, cards: list[Card]) -> list[Card]:
        """冒泡：带「冒泡」的牌提到最前；多张冒泡顺序随机。"""
        bubbled = [c for c in cards if has_enchant(c, "bubble")]
        rest = [c for c in cards if not has_enchant(c, "bubble")]
        if bubbled:
            self.rng.shuffle(bubbled)
        return bubbled + rest

    def _expand_replays(self, cards: list[Card]) -> list[Card]:
        """重放：带「重放 X」的牌展开为 X+1 次生效（前 X 次为镜像）。"""
        out: list[Card] = []
        for c in cards:
            if has_enchant(c, "replay"):
                x = temp_enchant_value(c, "replay")
                for i in range(x + 1):
                    if i < x:
                        mirror = copy.copy(c)
                        mirror.replay_mirror = True
                        out.append(mirror)
                    else:
                        out.append(c)
            else:
                out.append(c)
        return out

    def resolution_pending(self) -> bool:
        return bool(self.resolution_queue)

    def next_resolution_card(self) -> Card | None:
        """查看下一张要打出的牌（不打出），供动画判断目标选择。"""
        return self.resolution_queue[0] if self.resolution_queue else None

    def step_resolution(self, target: str | None = None) -> Card | None:
        """打出队列头部的一张牌，执行效果，返回该牌（队列空则 None）。"""
        if not self.resolution_queue:
            return None
        card = self.resolution_queue.pop(0)
        self.play_card(card, target)
        return card

    def end_resolution(self) -> None:
        """结算结束：移除最前牌堆，后续前移，末尾补空。"""
        player = self.state.player
        player.pile_slots.pop(0)
        player.pile_slots.append(Pile())
        self.resolution_queue = []
        self.attack_bonus = 0
        self.log("最前牌堆移除，后续牌堆前移，末尾补空牌堆")
        # 重击：回合结束处于牌堆顶则伤害 +5
        self._grow_heavy_strikes()

    def _resolve_target(self, target: str | None):
        """把目标标识解析为具体角色对象。

        支持 "self"、"enemy"（首个敌人，兼容）、"enemyN"（第 N 个敌人）。
        """
        if target == "self":
            return self.state.player
        enemies = self.state.enemies
        # 嘲讽：存活敌人中有嘲讽时，无显式目标时优先选它
        if target is None:
            for e in enemies:
                if e.is_alive and e.get_stacks("taunt") > 0:
                    return e
        if target and target.startswith("enemy"):
            idx = target[5:]
            if idx.isdigit() and 0 <= int(idx) < len(enemies):
                return enemies[int(idx)]
        for e in enemies:
            if e.is_alive:
                return e
        return enemies[0] if enemies else None

    def _precision_mult(self, card: Card) -> int:
        """精准：本场已开启「目标」效果时，若打出时卡牌重量等于目标层数，效果 ×2。

        返回本次效果倍率（未触发精准为 1）。
        """
        if not has_enchant(card, "precision"):
            return 1
        player = self.state.player
        if not getattr(player, "has_target", False):
            return 1
        if card.weight != player.target_level:
            return 1
        self.log(f"精准：{card.name} 重量 {card.weight} 等于目标层数 {player.target_level}，效果×2")
        return 2

    def _quirk_triggered(self, card: Card) -> bool:
        """奇巧 X：打出时重量恰好为 X 时触发。"""
        return card.quirk > 0 and card.weight == card.quirk

    def play_card(self, card: Card, target: str | None = None) -> None:
        """执行一张牌的效果，然后进弃牌堆。"""
        target_char = self._resolve_target(target)
        player = self.state.player
        nb = card.num_enchant  # 数值打击附魔层数
        mult = self._precision_mult(card)  # 精准倍率（1=无）
        quirk = self._quirk_triggered(card)  # 奇巧是否触发

        # 统一出牌日志：便于追踪每张牌打出时的状态
        tname = target_char.name if target_char is not None else "无目标"
        self.log(
            f">> 打出「{card.name}」重量 {card.weight} 费用 {card.cost}"
            f"（目标 {tname}，精准×{mult}）"
        )

        # 缓慢：怪物身上有缓慢时，玩家每打出一张牌，计数 +1（本回合怪物受到的攻击伤害 +10%）
        for enemy in self.state.enemies:
            if enemy.is_alive and enemy.get_stacks("slow") > 0:
                enemy.slow_counter += 1

        # 标记牌：对选定敌方施加一层「标记」
        if card.apply_mark:
            if target_char is not None:
                stacks = target_char.add_status("mark", 1)
                self.log(f"{card.name}：{target_char.name} 获得 1 层「标记」（当前 {stacks} 层）")

        # 弱点调查：给全体敌方施加标记
        if card.mark_all > 0:
            n = (card.mark_all + nb) * mult
            for enemy in self.state.alive_enemies:
                stacks = enemy.add_status("mark", n)
                self.log(f"{card.name}：{enemy.name} 获得 {n} 层「标记」（当前 {stacks} 层）")

        # 毒外卖：给自己施加中毒
        if card.self_poison > 0:
            n = (card.self_poison + nb) * mult
            stacks = player.add_status("poison", n)
            self.log(f"{card.name}：{player.name} 获得 {n} 层「中毒」（当前 {stacks} 层）")

        # 诅咒你：对目标施加诅咒（含附骨）
        if card.apply_curse:
            if target_char is not None:
                self._apply_curse_with_bone(
                    target_char, card.curse_stacks, card.curse_damage,
                    source=player.name, mult=player.curse_mult,
                )
                self.log(f"{card.name}：对 {target_char.name} 施加 {card.curse_stacks} 层 {card.curse_damage} 伤害诅咒")

        # 附骨诅咒：使自己获得附骨
        if card.gain_attached_curse > 0:
            player.add_status("attached_curse", card.gain_attached_curse)
            self.log(f"{card.name}：{player.name} 获得 {card.gain_attached_curse} 层「附骨」")

        # 咒仪之礼：使自己获得咒仪
        if card.gain_ritual > 0:
            player.add_status("ritual", card.gain_ritual)
            self.log(f"{card.name}：{player.name} 获得 {card.gain_ritual} 层「咒仪」")

        # 大限已至：目标身上所有诅咒立即爆发
        if card.detonate_curses:
            if target_char is not None:
                total = 0
                for curse in list(target_char.curses):
                    dmg = int(curse.value * (getattr(curse, "mult", 1.0) or 1.0))
                    total += dmg
                    target_char.curses.remove(curse)
                self._deal_damage(target_char, total)
                self.log(f"{card.name}：{target_char.name} 所有诅咒爆发，共造成 {total} 点伤害")

        # 隐匿：获得 hide
        if card.gain_hide > 0:
            n = (card.gain_hide + nb) * mult
            player.add_status("hide", n)
            self.log(f"{card.name}：{player.name} 获得 {n} 层「隐匿」")

        # 喝水：回复生命
        if card.heal > 0:
            healed = player.heal((card.heal + nb) * mult)
            self.log(f"{card.name}：{player.name} 回复 {healed} 点生命")

        # 抽牌：逻辑牌，直接抽牌
        if card.draw_cards > 0:
            drawn = self.draw_cards((card.draw_cards + nb) * mult)
            self.log(f"{card.name}：抽取 {len(drawn)} 张牌")

        # 岿然不动：丢弃所有手牌，每张 2 格挡（恒定）+ 1 韧性（恒定，不受数值打击）
        if card.discard_hand_block:
            n = len(player.hand)
            player.gain_block(n * 2)
            player.add_status("resilience", n)
            player.discard_pile.extend(player.hand)
            player.hand.clear()
            self.log(f"{card.name}：丢弃 {n} 张手牌，获得 {n * 2} 点格挡与 {n} 层韧性")

        # 韧性牌：同牌堆所有防御牌整局 weight+1（封顶10）、block+1
        if card.toughness:
            self._apply_toughness()

        # 减肥：同牌组所有牌重量永久 -N（最低 1）
        if card.weight_reduce_all > 0:
            self._apply_weight_reduce(card.weight_reduce_all + nb)

        # 数值打击：给同牌堆剩余牌附魔 数值打击+1
        if card.buff_numbers:
            self._apply_buff_numbers()

        # 淬毒：同牌组所有攻击牌获得附魔
        if card.enchant_poison:
            self._apply_poison_enchant()

        # 爆发牌：本牌堆之后攻击值临时加成 + 之后攻击牌整局 weight+1
        if card.attack_bonus > 0:
            self.attack_bonus += (card.attack_bonus + nb) * mult
            self.log(f"{card.name}：本牌堆之后所有攻击值 +{(card.attack_bonus + nb) * mult}")
        if card.attack_weight_up:
            self._apply_attack_weight_up()

        # 毒发：对目标造成中毒层数*4 伤害，并清除中毒
        if card.poison_detonate:
            stacks = target_char.get_stacks("poison") if target_char else 0
            dmg = stacks * (4 + nb) * mult
            self._deal_damage(target_char, dmg, raw=True)
            target_char.remove_status("poison")
            self.log(f"{card.name}：对 {target_char.name} 造成 {dmg} 点中毒爆发伤害，并清除中毒")

        # 全身撞击：对目标造成当前格挡值伤害
        if card.block_damage:
            dmg = player.block * mult
            self._deal_damage(target_char, dmg)
            self.log(f"{card.name}：对 {target_char.name} 造成 {dmg} 点伤害（当前格挡值）")

        # 攻击牌：造成伤害（受本牌堆攻击加成影响）
        if card.card_type is CardType.ATTACK and card.damage > 0:
            dmg = (card.damage + nb) * mult + self.attack_bonus
            # 缩小：造成的攻击伤害减少 30%
            if player.get_stacks("shrink") > 0:
                dmg = int(dmg * 0.7)
            # 缓慢：每打出的一张牌使怪物受到的攻击伤害 +10%
            if target_char is not None and target_char.get_stacks("slow") > 0:
                dmg = int(dmg * (1.0 + 0.1 * target_char.slow_counter))
            before_block = target_char.block
            hp_loss = self._deal_damage(target_char, dmg)
            absorbed = before_block - target_char.block
            # 附魔：淬毒（未格挡伤害给目标 2 层中毒）
            if card.enchant == "poison" and hp_loss > 0:
                target_char.add_status("poison", 2)
                self.log(f"淬毒：{target_char.name} 获得 2 层「中毒」")
            self.log(
                f"{card.name} 对 {target_char.name} 造成 {dmg} 点伤害"
                f"（格挡吸收 {absorbed}，生命 -{hp_loss}）"
            )

        # 防御牌：自己获得格挡（韧性状态每层 +1）
        if card.block > 0:
            bonus = player.get_stacks("resilience")
            amount = (card.block + nb) * mult + bonus
            player.gain_block(amount)
            self.log(f"{card.name}：{player.name} 获得 {amount} 点格挡" + (f"（含韧性 +{bonus}）" if bonus else ""))

        # 加护牌：获得「牌堆内卡牌数」的格挡（韧性状态每层 +1）
        if card.block_from_pile:
            n = len(self.resolution_snapshot)
            bonus = player.get_stacks("resilience")
            amount = n + bonus
            player.gain_block(amount)
            self.log(f"{card.name}：{player.name} 获得 {amount} 点格挡" + (f"（牌堆 {n} 张 + 韧性 {bonus}）" if bonus else f"（牌堆 {n} 张）"))

        # 潜伏：获得 4 点格挡 + 1 层隐匿；若本回合未打攻击牌则抽 1 张
        if card.lurk:
            player.gain_block(4)
            player.add_status("hide", 1)
            if player.attacks_played_this_turn == 0:
                drawn = self.draw_cards(1)
                self.log(f"{card.name}：获得 4 点格挡与 1 层「隐匿」，并抽取 {len(drawn)} 张牌")
            else:
                self.log(f"{card.name}：获得 4 点格挡与 1 层「隐匿」")

        # 铁壁：获得 3 点格挡，吸收后面至多三个牌堆防御牌数值，消耗
        if card.iron_wall:
            total = 3
            for pile in player.pile_slots[1:4]:
                for c in pile.cards:
                    if c.block > 0:
                        total += c.block
                        c.block += 1
            player.gain_block(total)
            self.log(f"{card.name}：获得 {total} 点格挡，并强化后方牌堆防御牌")

        # 科学勘误：删除下一个牌堆的第 X 张牌（X = 当前重量）
        if card.science_correction:
            x = card.weight
            if len(player.pile_slots) > 1 and x <= len(player.pile_slots[1].cards):
                removed = player.pile_slots[1].cards.pop(x - 1)
                self.log(f"{card.name}：删除下一个牌堆第 {x} 张牌 {removed}")
            else:
                self.log(f"{card.name}：下一个牌堆不足 {x} 张，未删除")

        # 汉堡：场上所有牌（手牌 + 牌堆）重量 +1
        if card.buff_all_weight:
            for c in player.hand:
                c.weight = min(10, c.weight + 1)
            for pile in player.pile_slots:
                for c in pile.cards:
                    c.weight = min(10, c.weight + 1)
            self.log(f"{card.name}：场上所有牌重量 +1")

        # 标记打击：对所有有标记的敌人造成 3×标记层数伤害
        if card.mark_strike:
            for enemy in self.state.alive_enemies:
                stacks = enemy.get_stacks("mark")
                if stacks <= 0:
                    continue
                dmg = stacks * 3
                self._deal_damage(enemy, dmg)
                self.log(f"{card.name}：对 {enemy.name} 造成 {dmg} 点伤害（标记 {stacks} 层）")

        # 熊孩子的报复：获得等同于当前韧性的反击层数
        if card.counterattack:
            res = player.get_stacks("resilience")
            player.add_status("counterattack", res)
            self.log(f"{card.name}：获得 {res} 层反击（等同于当前韧性）")

        # 获得力量（进入状态等）
        if card.gain_strength > 0:
            gain = (card.gain_strength + nb) * mult
            if quirk:
                gain += card.quirk_bonus_strength
            player.strength += gain
            self.log(f"{card.name}：获得 {gain} 点力量（当前 {player.strength}）")

        # 奇巧额外护甲（铁斩波等）
        if quirk and card.quirk_bonus_block > 0:
            player.gain_block(card.quirk_bonus_block)
            self.log(f"{card.name}：奇巧{card.quirk}触发，额外获得 {card.quirk_bonus_block} 点护甲")

        # 进弃牌堆（消耗牌进消耗牌堆）
        if card.exhaust:
            player.exhaust_pile.append(card)
            self.log(f"{card.name} 被消耗")
        elif card.replay_mirror:
            # 重放镜像：效果已生效，但不重复进弃牌堆
            pass
        elif has_enchant(card, "stick_bottom") and not card.stuck_bottom:
            # 粘底：首次生效后固定于 1 号牌堆底，重量 11，不进弃牌堆
            card.weight = 11
            card.stuck_bottom = True
            self._stuck_cards.append(card)
            self.log(f"{card.name} 粘底：重量设为 11，回合开始将回到 1 号牌堆底")
        else:
            player.discard_pile.append(card)
            # 黏糊：每次生效后重量 +1（封顶 10）
            if has_enchant(card, "sticky") and card.weight < 10:
                card.weight += 1
                self.log(f"{card.name} 黏糊：重量 +1（现 {card.weight}）")

        # 攻击牌计数（潜伏判断用）
        if card.card_type is CardType.ATTACK:
            player.attacks_played_this_turn += 1

        # 邦尼被动：攻击牌起效时对目标施加一层标记
        if card.card_type is CardType.ATTACK and player.mark_on_attack:
            if target_char is not None:
                stacks = target_char.add_status("mark", 1)
                self.log(f"{target_char.name} 获得 1 层「标记」（当前 {stacks} 层）")

    def _apply_weight_reduce(self, n: int) -> None:
        """减肥：同牌组所有牌重量永久 -N（最低 1）。"""
        for c in self.resolution_snapshot:
            c.weight = max(1, c.weight - n)
        self.log(f"减肥：同牌组所有牌重量 -{n}（最低 1）")

    def _apply_buff_numbers(self) -> None:
        """数值打击：给同牌堆剩余牌附魔 数值打击+1（所有可变数字 +1，重量字段也 +1）。"""
        for c in self.resolution_queue:
            c.num_enchant += 1
            if c.weight < 10:
                c.weight += 1
        n = len(self.resolution_queue)
        self.log(f"数值打击：同牌堆剩余 {n} 张牌获得「数值打击+1」附魔（数值与重量 +1）")

    def _apply_poison_enchant(self) -> None:
        """淬毒：同牌组所有攻击牌获得附魔：淬毒。"""
        for c in self.resolution_snapshot:
            if c.card_type is CardType.ATTACK:
                c.enchant = "poison"
        self.log("淬毒：同牌组所有攻击牌获得「淬毒」附魔")

    def _apply_toughness(self) -> None:
        """韧性：同牌堆所有防御牌 weight+1（封顶10）、block+1（整局，只一次）。"""
        for c in self.resolution_snapshot:
            if c.block > 0 and not c.buffed:
                c.weight = min(10, c.weight + 1)
                c.block += 1
                c.buffed = True
                self.log(f"韧性：{c.name} 重量 +1、格挡 +1（现重量 {c.weight}，格挡 {c.block}）")

    def _apply_attack_weight_up(self) -> None:
        """爆发：之后（剩余队列中）攻击牌 weight+1（封顶10，整局，只一次）。"""
        for c in self.resolution_queue:
            if c.card_type is CardType.ATTACK and not c.buffed:
                c.weight = min(10, c.weight + 1)
                c.buffed = True
                self.log(f"爆发：{c.name} 重量 +1（现重量 {c.weight}）")

    def monster_phase(self) -> None:
        self.state.phase = Phase.MONSTER
        enemies = self.state.alive_enemies
        if not enemies:
            self.log("怪物回合：跳过")
            return
        for enemy in enemies:
            self._enemy_act(enemy)
        # 回合结束：怪物格挡清零
        for enemy in enemies:
            self._end_enemy_turn(enemy)
        # 回合结束：玩家护甲清零 / 回合类效果减少
        self._end_player_turn()

    def _end_player_turn(self) -> None:
        """回合结束：玩家护甲清零、隐匿清除、临时重量回退。"""
        player = self.state.player
        if not player.keep_block:
            player.block = 0
        player.remove_status("hide")
        # 蓄势等本回合临时重量加成回退
        for c in self._turn_weight_buffs:
            c.weight = max(1, c.weight - 3)
        self._turn_weight_buffs = []

    def _enemy_act(self, enemy) -> None:
        """单个敌人的行动：清零缓慢计数 → 冰冻判定 → 执行意图 → 领地意识。"""
        # 缓慢：怪物回合开始清零本回合计数
        enemy.slow_counter = 0
        # 冰冻：怪物跳过本回合行动（输出伤害阶段）
        frozen = enemy.get_stacks("frozen")
        if frozen > 0:
            enemy.set_stacks("frozen", frozen - 1)
            self.log(f"{enemy.name} 被冰冻，跳过本回合行动（冰冻 {frozen} -> {frozen - 1}）")
            self._apply_territorial(enemy)
            return
        # 前导意图优先于循环 pattern
        intent, kind = self._peek_enemy_intent(enemy)
        if intent is not None:
            self._execute_intent(enemy, intent)
            self._advance_enemy_intent(enemy, kind)
        else:
            # 回退：无模式时用基础攻击
            self._player_take_attack_damage(self.state.player, enemy, enemy.attack)
            self.log(f"怪物回合：{enemy.name} 攻击，造成 {enemy.attack} 点伤害")
        # 领地意识：回合结束获得等同于层数的力量
        self._apply_territorial(enemy)

    def _peek_enemy_intent(self, enemy):
        """查看怪物本回合要执行的意图（不推进索引），返回 (intent, kind)。"""
        if enemy.lead and enemy.lead_index < len(enemy.lead):
            return enemy.lead[enemy.lead_index], "lead"
        if enemy.pattern:
            return enemy.pattern[enemy.pattern_index % len(enemy.pattern)], "pattern"
        return None, None

    def _advance_enemy_intent(self, enemy, kind: str) -> None:
        """推进怪物意图索引。"""
        if kind == "lead":
            enemy.lead_index += 1
        elif kind == "pattern":
            enemy.pattern_index += 1

    def _has_alive_enemy_with_status(self, status_id: str) -> bool:
        """场上是否有存活敌人带某状态。"""
        return any(
            e.get_stacks(status_id) > 0 for e in self.state.alive_enemies
        )

    def _apply_encouraging_shout(self) -> None:
        """震撼性激励：大嗓门在场时，每回合开始给练家子 +3 临时力量，所有玩家 -3（无视护盾）。

        第一回合（战斗刚开始）不触发，从第二回合开始。
        """
        if self.state.turn < 2:
            return
        if not self._has_alive_enemy_with_status("encouraging_shout"):
            return
        for enemy in self.state.alive_enemies:
            if enemy.get_stacks("synergy_defense") > 0:
                enemy.temp_strength += 3
                self.log(f"{enemy.name} 获得 3 点临时力量（震撼性激励，当前 {enemy.temp_strength}）")
        # 所有玩家 -3 无视护盾（隐匿免疫）
        for player in self._all_players():
            if player.get_stacks("hide") > 0:
                self.log(f"{player.name} 被「隐匿」免疫（震撼性激励）")
                continue
            player.take_raw_damage(3)
            self.log(f"{player.name} 受到 3 点无视护盾伤害（震撼性激励）")

    def _process_summons(self) -> None:
        """召唤：看守死亡后，典狱长等一回合再召唤一个看守。

        - 先清理已死亡的看守（避免屏幕外堆积）；
        - 看守在场时取消待召唤标记；
        - 看守不在且已等待过一回合，则召唤（生命上限 = 25 + 10 × 召唤次数）。
        """
        # 及时清理已死亡的看守
        self.state.enemies = [
            e for e in self.state.enemies
            if not (e.name == "看守" and not e.is_alive)
        ]
        for enemy in self.state.alive_enemies:
            if enemy.get_stacks("summon") <= 0:
                continue
            has_guard = any(
                e.is_alive and e.name == "看守" for e in self.state.enemies
            )
            eid = id(enemy)
            if has_guard:
                self._pending_summon.discard(eid)
                continue
            if eid not in self._pending_summon:
                # 本回合标记，等下一回合再召唤
                self._pending_summon.add(eid)
                self.log(f"{enemy.name} 准备召唤看守（下一回合）")
                continue
            # 已等待一回合，真正召唤
            self._pending_summon.discard(eid)
            status = enemy.get_status("summon")
            count = (status.value if status else 0) + 1
            if status is not None:
                status.value = count
            guard = make_enemy("看守")
            guard.max_hp = 25 + 10 * count
            guard.hp = guard.max_hp
            self.state.enemies.append(guard)
            self.log(f"{enemy.name} 召唤了一个「看守」（生命上限 {guard.max_hp}）")

    def _all_players(self) -> list:
        """返回本场所有玩家（单机时只有 state.player）。"""
        st = self.state
        if getattr(st, "players", None):
            return list(st.players)
        return [st.player]

    def _enemy_defend_at_turn_start(self) -> None:
        """怪加防御：回合开始时执行怪物意图的防御（格挡）部分 + 覆甲。"""
        for enemy in self.state.alive_enemies:
            # 覆甲：回合开始时获得等同于层数的格挡
            coating = enemy.get_stacks("coating")
            if coating > 0:
                enemy.gain_block(coating)
                self.log(f"{enemy.name} 覆甲：获得 {coating} 点格挡")
            intent, _ = self._peek_enemy_intent(enemy)
            if intent is None or intent.block <= 0:
                continue
            block = intent.block + enemy.get_stacks("resilience")
            enemy.gain_block(block)
            self.log(f"{enemy.name} 回合开始：获得 {block} 点格挡")
            # 协同性防御：练家子获得防御时，大嗓门获得等量防御
            if enemy.get_stacks("synergy_defense") > 0:
                for ally in self.state.alive_enemies:
                    if ally is not enemy and ally.get_stacks("encouraging_shout") > 0:
                        ally.gain_block(block)
                        self.log(f"{ally.name} 获得 {block} 点格挡（协同性防御）")

    def _end_enemy_turn(self, enemy) -> None:
        """回合结束：怪物格挡清零（协同性防御的练家子保留，即壁垒）；覆甲减一层。"""
        enemy.temp_strength = 0
        # 覆甲：行动结束时减少一层
        coating = enemy.get_stacks("coating")
        if coating > 0:
            enemy.set_stacks("coating", coating - 1)
        if enemy.get_stacks("synergy_defense") > 0:
            return  # 壁垒：格挡跨回合保留
        enemy.block = 0

    def _apply_territorial(self, enemy) -> None:
        """领地意识：怪物回合结束时获得等同于层数的力量。"""
        stacks = enemy.get_stacks("territorial")
        if stacks > 0:
            enemy.strength += stacks
            self.log(f"{enemy.name} 领地意识：获得 {stacks} 点力量（当前力量 {enemy.strength}）")

    def _execute_intent(self, enemy, intent, target_player=None) -> None:
        """执行怪物的单个意图。多人 PVE 可传入 target_player 指定受害玩家。"""
        player = target_player if target_player is not None else self.state.player
        # 隐匿：免疫敌方攻击伤害
        hide = player.get_stacks("hide") > 0
        atk = enemy.strength + enemy.temp_strength
        if intent.kind == "attack":
            dmg = intent.value + atk
            if hide:
                self.log(f"{enemy.name} 攻击被「隐匿」免疫")
                return
            self._player_take_attack_damage(player, enemy, dmg)
            self.log(f"{enemy.name} 攻击，造成 {dmg} 点伤害")
            self._counterattack(enemy, player)
        elif intent.kind == "multi":
            per = intent.value + atk
            total = per * intent.times
            if hide:
                self.log(f"{enemy.name} 攻击被「隐匿」免疫")
                return
            for _ in range(intent.times):
                self._player_take_attack_damage(player, enemy, per)
            self.log(f"{enemy.name} 攻击 {intent.times} 次，共造成 {total} 点伤害")
            self._counterattack(enemy, player)
        elif intent.kind == "strength":
            enemy.strength += intent.value
            self.log(f"{enemy.name} 获得 {intent.value} 点力量（当前力量 {enemy.strength}）")
        elif intent.kind == "buff":
            # 格挡部分已在回合开始执行，此处只处理力量
            if intent.strength:
                enemy.strength += intent.strength
                self.log(f"{enemy.name} 获得 {intent.strength} 点力量（当前力量 {enemy.strength}）")
            elif not intent.block:
                self.log(f"{enemy.name} 待机")
        elif intent.kind == "attack_block":
            # 格挡部分已在回合开始执行，此处只处理攻击
            dmg = intent.value + atk
            times = 1
            # 协同性防御（练家子）在场且大嗓门在场时，攻击次数 +1
            if enemy.get_stacks("synergy_defense") > 0 and self._has_alive_enemy_with_status("encouraging_shout"):
                times = 2
            if hide:
                self.log(f"{enemy.name} 攻击被「隐匿」免疫")
                return
            for _ in range(times):
                self._player_take_attack_damage(player, enemy, dmg)
            self.log(f"{enemy.name} 攻击 {times} 次，每次 {dmg} 点伤害")
            self._counterattack(enemy, player)
        elif intent.kind == "attack_strength":
            dmg = intent.value + atk
            if not hide:
                self._player_take_attack_damage(player, enemy, dmg)
                self.log(f"{enemy.name} 攻击，造成 {dmg} 点伤害")
                self._counterattack(enemy, player)
            else:
                self.log(f"{enemy.name} 攻击被「隐匿」免疫")
            enemy.strength += intent.strength
            self.log(f"{enemy.name} 获得 {intent.strength} 点力量（当前力量 {enemy.strength}）")
        elif intent.kind == "shrink":
            n = max(1, intent.value)
            player.add_status("shrink", n)
            self.log(f"{enemy.name} 使玩家获得 {n} 层「缩小」")
        elif intent.kind == "sleep":
            self.log(f"{enemy.name} 正在沉睡")
        elif intent.kind == "gain_counterattack":
            enemy.add_status("counterattack", intent.value)
            self.log(f"{enemy.name} 获得 {intent.value} 层「反击」（当前 {enemy.get_stacks('counterattack')}）")
        elif intent.kind == "gain_resilience":
            enemy.add_status("resilience", intent.value)
            self.log(f"{enemy.name} 获得 {intent.value} 层「韧性」（当前 {enemy.get_stacks('resilience')}）")
        elif intent.kind == "heal_block":
            # 格挡部分已在回合开始通过 _enemy_defend_at_turn_start 添加，此处只处理恢复
            if intent.heal:
                healed = enemy.heal(intent.heal)
                self.log(f"{enemy.name} 回复 {healed} 点生命")
        elif intent.kind == "summon_minion":
            self._summon_minion(enemy, intent)
        elif intent.kind == "buff_minions_strength":
            self._buff_minions_strength(intent)

    def _summon_minion(self, owner, intent) -> None:
        """召唤 minion；若场上已有 2 个则恢复其中一只（血量最低的）heal 点生命。"""
        minions = [e for e in self.state.enemies if e.name == intent.minion and e.is_alive]
        if len(minions) >= 2:
            target = min(minions, key=lambda e: e.hp)
            healed = target.heal(intent.heal)
            self.log(f"{owner.name} 恢复 {target.name} {healed} 点生命")
            return
        m = make_enemy(intent.minion)
        self.state.enemies.append(m)
        self.log(f"{owner.name} 召唤了一个「{intent.minion}」")

    def _buff_minions_strength(self, intent) -> None:
        """给场上所有指定 minion 增加 value 点力量。"""
        for e in self.state.alive_enemies:
            if e.name == intent.minion:
                e.strength += intent.value
                self.log(f"{e.name} 力量 +{intent.value}（当前 {e.strength}）")

    def _counterattack(self, enemy, target_player=None) -> None:
        """反击：对攻击者造成等同于「反击」层数的伤害。"""
        player = target_player if target_player is not None else self.state.player
        retal = player.get_stacks("counterattack")
        if retal > 0 and enemy.is_alive:
            self._deal_damage(enemy, retal)
            self.log(f"反击：造成 {retal} 点伤害")

    def _deal_damage(self, enemy, amount: int, raw: bool = False) -> int:
        """对敌人造成伤害；大嗓门（震撼性激励）在练家子（协同性防御）在场时受到伤害减半。

        看守在场时典狱长不受任何伤害；未被格挡的实际伤害记录进 damage_floats 供 GUI 飘字。
        """
        if self._is_protected_warden(enemy):
            self.log("典狱长受到看守保护，不受伤害")
            return 0
        if enemy.get_stacks("encouraging_shout") > 0 and self._has_alive_enemy_with_status("synergy_defense"):
            amount = max(0, amount // 2)
        if raw:
            dealt = enemy.take_raw_damage(amount)
        else:
            dealt = enemy.take_damage(amount)
        if dealt > 0:
            self.damage_floats.append((enemy, dealt))
            self._apply_surveillance(enemy, dealt)
            # 敌人的反击：对玩家造成等同于「反击」层数的伤害
            retal = enemy.get_stacks("counterattack")
            if retal > 0 and enemy.is_alive:
                hp_loss = self.state.player.take_damage(retal)
                self.log(f"{enemy.name} 反击：对玩家造成 {retal} 点伤害")
                if hp_loss > 0:
                    self.damage_floats.append((self.state.player, hp_loss))
        return dealt

    def _apply_surveillance(self, target, dealt: int) -> None:
        """监管：看守每受到一次伤害，给玩家（伤害来源）施加 1 层「罪证」。"""
        if dealt > 0 and target is not None and target.get_stacks("surveillance") > 0:
            self.state.player.add_status("evidence", 1)
            self.log(f"监管：{self.state.player.name} 获得 1 层「罪证」")

    def _player_take_attack_damage(self, player, attacker, dmg: int) -> int:
        """玩家受到攻击伤害：咒仪减伤（按攻击者诅咒总层数）+ 飘字记录。"""
        if player.get_stacks("ritual") > 0:
            total_curse = sum(c.stacks for c in attacker.curses if c.stacks > 0)
            reduce_by = min(5, total_curse // 5)
            if reduce_by > 0:
                dmg = max(0, dmg - reduce_by)
                self.log(f"咒仪：{player.name} 减伤 {reduce_by}（对方诅咒 {total_curse} 层）")
        # 罪证：每层使受到来自典狱长的攻击 +2
        if attacker is not None and attacker.name == "典狱长":
            evidence = player.get_stacks("evidence")
            if evidence > 0:
                dmg += 2 * evidence
                self.log(f"罪证：{player.name} 受到典狱长攻击 +{2 * evidence}")
        dealt = player.take_damage(dmg)
        if dealt > 0:
            self.damage_floats.append((player, dealt))
        return dealt
