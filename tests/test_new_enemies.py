"""新怪物与新状态机制的单元测试。"""

from __future__ import annotations

import os
import random

import pytest

from game.cards import make_card
from game.engine import Engine
from game.enemy import make_enemy
from game.player import Player
from game.state import GameState


def _has_art() -> bool:
    """`sources/images` 里有没有素材图片。

    公开仓库不包含素材（卡面 / 立绘是 wiki 爬的，不能公开分发），
    所以「图片文件真的存在」这类断言在没有素材时跳过；
    游戏本身缺图也能跑（加载失败会退回程序化绘制的占位）。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    images = os.path.join(root, "sources", "images")
    if not os.path.isdir(images):
        return False
    return any(
        name.lower().endswith((".png", ".webp", ".jpg", ".jpeg"))
        for _, _, files in os.walk(images)
        for name in files
    )


requires_art = pytest.mark.skipif(
    not _has_art(), reason="sources/images 里没有素材（公开仓库不含素材），跳过图片存在性断言"
)


def make_engine(enemy_name: str) -> Engine:
    player = Player()
    state = GameState(player=player, enemy=make_enemy(enemy_name))
    return Engine(state, rng=random.Random(0))


# ---------- 新怪物库 ----------
def test_new_enemies_exist():
    for name in ("多伦斯异鸟", "小啃兽", "缩小甲虫", "立柱构造体", "旧日雕像", "墨影幻灵"):
        e = make_enemy(name)
        assert e.name == name


def test_territorial_wyvern_stats():
    e = make_enemy("多伦斯异鸟")
    assert e.max_hp == 70
    assert e.get_stacks("territorial") == 1
    assert [i.kind for i in e.pattern] == ["attack", "multi"]


def test_gnawer_random_hp():
    for _ in range(50):
        e = make_enemy("小啃兽")
        assert 37 <= e.max_hp <= 41


def test_pillar_construct_start():
    e = make_enemy("立柱构造体")
    assert e.max_hp == 60
    assert e.get_stacks("artifact") == 1
    assert e.block == 14
    assert [i.kind for i in e.lead] == ["strength"]


def test_ancient_statue_start():
    e = make_enemy("旧日雕像")
    assert e.max_hp == 120
    assert e.get_stacks("slow") == 1
    assert [i.kind for i in e.lead] == ["sleep", "strength"]


def test_ink_phantom_start():
    e = make_enemy("墨影幻灵")
    assert e.max_hp == 173
    assert e.get_stacks("slippery") == 9


# ---------- 滑溜 ----------
def test_slippery_negates_hp_loss():
    e = make_engine("墨影幻灵")
    enemy = e.state.enemy
    enemy.block = 0
    hp_before = enemy.hp
    dealt = enemy.take_damage(10)
    # 滑溜抵消：hp 不变，层数 -1
    assert dealt == 0
    assert enemy.hp == hp_before
    assert enemy.get_stacks("slippery") == 8


def test_slippery_after_block():
    e = make_engine("墨影幻灵")
    enemy = e.state.enemy
    enemy.block = 5
    enemy.set_stacks("slippery", 1)
    hp_before = enemy.hp
    enemy.take_damage(20)
    # 5 格挡吸收，剩余 15 被 1 层滑溜抵消，hp 不变
    assert enemy.hp == hp_before
    assert enemy.get_stacks("slippery") == 0


# ---------- 人工制品 ----------
def test_artifact_cancels_negative():
    e = make_engine("立柱构造体")
    enemy = e.state.enemy
    assert enemy.get_stacks("artifact") == 1
    # 施加负面状态：被人工制品抵消
    enemy.add_status("poison", 2)
    assert enemy.get_stacks("poison") == 0
    assert enemy.get_stacks("artifact") == 0
    # 再次施加：正常生效
    enemy.add_status("poison", 2)
    assert enemy.get_stacks("poison") == 2


# ---------- 缩小 ----------
def test_shrink_reduces_attack():
    e = make_engine("缩小甲虫")
    # 玩家被缩小后攻击伤害减少 30%
    player = e.state.player
    player.add_status("shrink", 1)
    strike = make_card("strike")  # 6 伤害
    enemy = e.state.enemy
    enemy.block = 0
    hp_before = enemy.hp
    e.play_card(strike, "enemy")
    assert enemy.hp == hp_before - 4  # int(6*0.7) = 4


def test_shrink_beetle_pattern():
    e = make_engine("缩小甲虫")
    enemy = e.state.enemy
    e.monster_phase()  # 第一回合：shrink
    assert e.state.player.get_stacks("shrink") >= 1


# ---------- 领地意识 ----------
def test_territorial_gains_strength():
    e = make_engine("多伦斯异鸟")
    enemy = e.state.enemy
    player = e.state.player
    player.block = 0
    player.hp = 100
    player.max_hp = 100
    e.monster_phase()  # 攻击 17 + 回合结束领地意识 +1 力量
    assert enemy.strength == 1
    e.monster_phase()  # multi 3x3（力量1 => 每次4），回合结束再+1
    assert enemy.strength == 2


# ---------- 缓慢 ----------
def test_slow_increases_damage_per_card():
    e = make_engine("旧日雕像")
    enemy = e.state.enemy
    enemy.block = 0
    # 打出第一张攻击牌：缓慢计数 1 => 伤害 +10%
    strike = make_card("strike")  # 6 伤害
    hp_before = enemy.hp
    e.play_card(strike, "enemy")
    assert enemy.slow_counter == 1
    # int(6 * 1.1) = 6
    assert enemy.hp == hp_before - 6
    # 再打一张：计数 2 => 伤害 +20%
    strike2 = make_card("strike")
    hp2 = enemy.hp
    e.play_card(strike2, "enemy")
    assert enemy.slow_counter == 2
    # int(6 * 1.2) = 7
    assert enemy.hp == hp2 - 7


def test_slow_counter_resets_each_monster_turn():
    e = make_engine("旧日雕像")
    enemy = e.state.enemy
    enemy.block = 0
    strike = make_card("strike")
    e.play_card(strike, "enemy")
    assert enemy.slow_counter == 1
    # 怪物回合：slow_counter 清零
    e.monster_phase()
    assert enemy.slow_counter == 0


# ---------- 前导意图（lead） ----------
def test_ancient_statue_lead_then_loop():
    e = make_engine("旧日雕像")
    enemy = e.state.enemy
    e.state.player.block = 0
    e.state.player.hp = 100
    e.state.player.max_hp = 100
    # 第一回合：沉睡（lead[0]）
    e.monster_phase()
    assert enemy.lead_index == 1
    assert enemy.strength == 0
    # 第二回合：唤醒 +10 力量（lead[1]）
    e.monster_phase()
    assert enemy.lead_index == 2
    assert enemy.strength == 10
    # 第三回合：循环 pattern 攻击 13 + 力量 10 = 23
    hp_before = e.state.player.hp
    e.monster_phase()
    assert e.state.player.hp == hp_before - 23


def test_pillar_construct_loop():
    e = make_engine("立柱构造体")
    enemy = e.state.enemy
    e.state.player.block = 0
    e.state.player.hp = 100
    e.state.player.max_hp = 100
    # 第一回合：lead strength +2
    e.monster_phase()
    assert enemy.strength == 2
    # 第二回合：attack_strength 打7+2力 => 7+2=9 伤害，力量 2+2=4
    hp_before = e.state.player.hp
    e.monster_phase()
    assert e.state.player.hp == hp_before - 9
    assert enemy.strength == 4


# ---------- 敌人图片 ----------
@requires_art
def test_new_enemies_have_images():
    import os
    from gui import IMAGES_DIR
    for name in ("多伦斯异鸟", "小啃兽", "缩小甲虫", "立柱构造体", "旧日雕像", "墨影幻灵"):
        e = make_enemy(name)
        assert e.image, name
        assert os.path.exists(os.path.join(IMAGES_DIR, e.image)), e.image


# ---------- 二层 Boss：典狱长 + 看守 ----------
def make_warden_engine() -> Engine:
    player = Player(name="测试", max_hp=100)
    state = GameState(player=player, enemies=[make_enemy("典狱长"), make_enemy("看守")])
    return Engine(state, rng=random.Random(0))


def test_warden_guard_templates():
    w = make_enemy("典狱长")
    assert w.max_hp == 5
    assert w.get_stacks("incorporeal") == 1
    assert w.get_stacks("summon") == 1
    assert [i.kind for i in w.pattern] == ["attack"]
    g = make_enemy("看守")
    assert g.max_hp == 25
    assert g.get_stacks("surveillance") == 1
    assert g.get_stacks("taunt") == 1
    assert [i.kind for i in g.pattern] == ["attack_block", "strength"]


def test_incorporeal_caps_hp_loss():
    e = make_warden_engine()
    warden = e.state.enemies[0]
    # 移除看守：典狱长不再受保护，暴露无实体机制
    guard = e.state.enemies[1]
    e.state.enemies.remove(guard)
    warden.block = 0
    hp_before = warden.hp
    strike = make_card("strike")  # 6 伤害
    e.play_card(strike, "enemy0")
    assert warden.hp == hp_before - 1  # 无实体：只掉 1


def test_taunt_forces_target():
    e = make_warden_engine()
    target = e._resolve_target(None)
    assert target.name == "看守"


def test_surveillance_applies_evidence():
    e = make_warden_engine()
    guard = e.state.enemies[1]
    guard.block = 0
    e.play_card(make_card("strike"), "enemy1")
    assert e.state.player.get_stacks("evidence") == 1


def test_warden_protected_while_guard_alive():
    e = make_warden_engine()
    warden = e.state.enemies[0]
    warden.block = 0
    hp_before = warden.hp
    e.play_card(make_card("strike"), "enemy0")
    assert warden.hp == hp_before  # 看守在场：典狱长不受伤害


def test_warden_death_ends_battle():
    e = make_warden_engine()
    warden, guard = e.state.enemies
    e.state.enemies.remove(guard)  # 看守死亡
    warden.hp = 0
    assert e.check_game_over() == "victory"


def test_summon_when_guard_dead():
    e = make_warden_engine()
    warden, guard = e.state.enemies
    e.state.enemies.remove(guard)  # 看守死亡
    e.start_turn()  # 第一回合：标记待召唤，不召唤
    guards = [en for en in e.state.enemies if en.name == "看守"]
    assert len(guards) == 0
    e.start_turn()  # 第二回合：真正召唤
    guards = [en for en in e.state.enemies if en.name == "看守"]
    assert len(guards) == 1
    assert guards[0].max_hp == 35  # 25 + 10
    assert guards[0].hp == 35


def test_evidence_amplifies_warden_attack():
    e = make_warden_engine()
    player = e.state.player
    player.block = 0
    player.hp = 100
    player.add_status("evidence", 2)
    dealt = e._player_take_attack_damage(player, e.state.enemies[0], 1)
    assert dealt == 1 + 2 * 2  # 典狱长打 1 + 罪证 2 层 ×2 = 5


@requires_art
def test_warden_guard_images():
    import os
    from gui import IMAGES_DIR
    for name in ("典狱长", "看守", "迎宾雁", "罪恶茶壶"):
        e = make_enemy(name)
        assert e.image, name
        assert os.path.exists(os.path.join(IMAGES_DIR, e.image)), e.image


# ---------- 二层新怪物 ----------
def test_greeting_goose_template():
    e = make_enemy("迎宾雁")
    assert e.max_hp == 108
    assert [i.kind for i in e.lead] == ["strength"]
    assert [i.kind for i in e.pattern] == ["strength", "attack", "buff"]


def test_sin_teapot_template():
    e = make_enemy("罪恶茶壶")
    assert e.max_hp == 26
    assert e.strength == 3
    assert e.get_stacks("coating") == 10
    assert e.get_stacks("counterattack") == 5
    assert [i.kind for i in e.pattern] == ["attack", "strength"]


def test_coating_gains_block_then_decays():
    from game.player import Player
    from game.state import GameState
    player = Player(name="测试", max_hp=100)
    teapot = make_enemy("罪恶茶壶")
    state = GameState(player=player, enemies=[teapot])
    e = Engine(state, rng=random.Random(0))
    teapot.block = 0
    e._enemy_defend_at_turn_start()
    assert teapot.block == 10  # 覆甲 10 层 → 10 格挡
    e._end_enemy_turn(teapot)
    assert teapot.get_stacks("coating") == 9  # 行动结束减一层


def test_enemy_counterattack():
    from game.player import Player
    from game.state import GameState
    player = Player(name="测试", max_hp=100)
    teapot = make_enemy("罪恶茶壶")
    state = GameState(player=player, enemies=[teapot])
    e = Engine(state, rng=random.Random(0))
    teapot.block = 0
    player.hp = 100
    player.block = 0
    e.play_card(make_card("strike"), "enemy0")
    assert player.hp == 95  # 茶壶反击 5 点伤害


# ---------- 一层 Boss：海盗王噶呜 / 科学怪呜 ----------
def test_pirate_king_template():
    e = make_enemy("海盗王噶呜")
    assert e.max_hp == 170
    assert e.get_stacks("counterattack") == 10
    assert [i.kind for i in e.pattern] == ["gain_counterattack", "buff", "gain_resilience"]


def test_pirate_king_intents():
    from game.player import Player
    from game.state import GameState
    player = Player(name="测试", max_hp=100)
    king = make_enemy("海盗王噶呜")
    state = GameState(player=player, enemies=[king])
    e = Engine(state, rng=random.Random(0))
    e._execute_intent(king, king.pattern[0])  # 获得 1 层反击
    assert king.get_stacks("counterattack") == 11
    e._execute_intent(king, king.pattern[2])  # 获得 1 层韧性
    assert king.get_stacks("resilience") == 1


def test_mad_scientist_template():
    e = make_enemy("科学怪呜")
    assert e.max_hp == 100
    assert [i.kind for i in e.pattern] == ["summon_minion", "heal_block", "buff_minions_strength"]
    ape = make_enemy("科学怪猿")
    assert ape.max_hp == 40
    assert [i.kind for i in ape.pattern] == ["attack"]


def test_mad_scientist_summon_and_cap():
    from game.player import Player
    from game.state import GameState
    player = Player(name="测试", max_hp=100)
    sci = make_enemy("科学怪呜")
    state = GameState(player=player, enemies=[sci])
    e = Engine(state, rng=random.Random(0))
    e._execute_intent(sci, sci.pattern[0])  # 召唤第一个猿
    e._execute_intent(sci, sci.pattern[0])  # 召唤第二个猿
    apes = [x for x in state.enemies if x.name == "科学怪猿"]
    assert len(apes) == 2
    for a in apes:
        a.hp = 10
    e._execute_intent(sci, sci.pattern[0])  # 已有 2 个，恢复血量最低的
    assert len([x for x in state.enemies if x.name == "科学怪猿"]) == 2
    assert max(a.hp for a in apes) == 30  # 10 + 20 恢复


def test_mad_scientist_buff_apes():
    from game.player import Player
    from game.state import GameState
    player = Player(name="测试", max_hp=100)
    sci = make_enemy("科学怪呜")
    state = GameState(player=player, enemies=[sci])
    e = Engine(state, rng=random.Random(0))
    e._execute_intent(sci, sci.pattern[0])  # 召唤一个猿
    e._execute_intent(sci, sci.pattern[2])  # 所有猿 +5 力量
    apes = [x for x in state.enemies if x.name == "科学怪猿"]
    assert all(a.strength == 5 for a in apes)


@requires_art
def test_floor1_boss_images():
    import os
    from gui import IMAGES_DIR
    for name in ("海盗王噶呜", "科学怪呜", "科学怪猿"):
        e = make_enemy(name)
        assert e.image, name
        assert os.path.exists(os.path.join(IMAGES_DIR, e.image)), e.image
