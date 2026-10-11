# 土豆尖塔（Potatospire）

**当前版本：`R1.01`**（主界面底部显示）

一款以**「卡牌堆叠 / 重量」**为核心玩法的 Roguelike 卡牌游戏，Python + pygame-ce。
像《杀戮尖塔》那样爬三层地图打 Boss，但出牌方式不是「选一张打出去」——而是把手牌**叠成牌堆**，
回合结束时从最前面的牌堆自上而下依次结算。

## 玩法要点

- **重量堆叠**：手牌拖到 4 个牌堆槽位之一，新放的牌必须**严格轻于**当前顶牌（重量数值更小）。
  所以每个牌堆自上而下重量递减，怎么排布就是这套玩法的策略核心。
- **每回合放牌上限**：槽位 1 最多 4 张、槽位 2 最多 3 张、槽位 3 最多 2 张、槽位 4 最多 1 张；
  第 1 回合只有 3 个槽位可用。
- **结算顺序**：弃置手牌 → 状态判定 → 结算最前牌堆（从顶到底依次打出）→ 该牌堆移除、
  后续牌堆前移、末尾补空 → 怪物回合 → 抽 5 张开新回合。
- **逻辑牌**：描述以「逻辑牌；」开头的牌拖上去**立即生效**，不进牌堆、不占容量、不参与堆叠。
- **两种模式**：主菜单的「战斗模拟」（自由选角色 / 敌人 / 牌组，单局对战）与
  「肉鸽模式」（三层蜂巢地图：战斗 / 事件 / 商店 / 火堆 / 宝箱，最后打每层 Boss）。
- 完整规则见 [`玩法与卡牌.txt`](玩法与卡牌.txt)。

## 内容规模

| 内容 | 数量 |
|---|---|
| 卡牌 | 37（`game/cards.py` 的 `CARD_DEFS`） |
| 角色 | 4：蒸蛋 / 邦尼 / 鼠鼠 / 阿兰娜（各有被动与专属卡） |
| 敌人 | 20（`game/enemy.py` 的 `_ENEMY_TEMPLATES`，带两回合**意图**显示） |
| 状态 | 27（中毒 / 灼烧 / 流血 / 调查 / 隐匿 / 韧性…） |
| 附魔 | 7（临时 + 永久两类，`game/enchants.py`） |
| 遗物 / 药水 / 事件 | 6 / 4 / 3 |
| 测试 | 189 个（`pytest`） |

其他系统：牌组编辑页、怪物意图与攻击动画、格挡 / 扣血平滑动画、奖励界面（战利品弹窗）、
商店与删牌、遗物与药水、附魔（冒泡 / 黏糊 / 粘底 / 重放…）、局域网 **PVE / PVP 联机**、
调试控制台（按 `` ` `` 呼出，指令见 [`指令格式.txt`](指令格式.txt)）。

## 环境要求

- **Python 3.10+**（开发环境 3.13）
- **pygame-ce 2.5.8**（运行只依赖这一个；`pip install -r requirements.txt`）

开发 / 打包额外需要 pillow、requests、playwright、pytest，见 `requirements-dev.txt`。

## 快速开始

```bash
git clone git@github.com:why012123/potatospire.git
cd potatospire

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py                     # 启动游戏
```

命令行参数：

| 参数 | 作用 |
|---|---|
| `python main.py` | 正常启动图形界面 |
| `python main.py --cli` | 命令行原型（不依赖图形界面，用来验证战斗逻辑） |
| `python main.py --smoke` | 无头冒烟：建窗口、画几帧就退出（CI / 免打扰自检用） |
| `python main.py --pvp-guest <port>` | 作为访客连主机的 PVP 对局（主程序自己会调） |

无显示环境（服务器 / CI）可以加 `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`。

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q          # 189 passed
```

## 打包 Windows 版（发给同学）

macOS 上**无法**直接生成 Windows 的 `.exe`（PyInstaller 不支持交叉编译），三条路：

1. **GitHub Actions 自动打包（推荐）**：推 `v*` tag 或手动 Run workflow，
   等 3~5 分钟，到 **Actions / Releases** 下载 `potatospire-win.zip`。
   配置见 [`.github/workflows/build-windows.yml`](.github/workflows/build-windows.yml)。
2. **在 Windows 本机打包**：把项目拷过去，装好 Python 3.10+ 后跑
   [`build_windows.bat`](build_windows.bat)（产物在 `dist\Potatospire\`）。
3. **让同学装 Python 直接跑**：`pip install pygame-ce` + `python main.py`。

> 注：本仓库是**私有仓库**，Actions 会消耗私有仓库的免费额度（每月 2000 分钟）。

细节见 [`打包说明.md`](打包说明.md)。

## 目录结构

```
potatospire/
├── main.py                 # 入口（--cli / --smoke / --pvp-guest）
├── gui.py                  # pygame 图形界面（主菜单 / 战斗 / 地图 / 奖励 / 商店…）
├── fightui.py              # 战斗界面绘制与动画
├── ui_common.py            # 两个 UI 模块共用的常量与工具（含 VERSION）
├── game/                   # 与界面解耦的游戏逻辑
│   ├── card.py  cards.py   # 卡牌与卡牌库（37 张）
│   ├── pile.py  player.py  # 重量堆叠规则 / 手牌与牌堆
│   ├── engine.py  state.py # 回合流程与状态
│   ├── character.py  heroes.py  enemy.py   # 角色 / 敌人（含意图）
│   ├── status.py  enchants.py  relics.py  potions.py
│   ├── map.py  events.py  shop.py  reward.py  pve.py  pvp.py
│   └── net.py  pve_net.py  pvp_net.py      # 局域网联机
├── tools/                  # 开发工具（卡面生成、地图可视化）
├── sourcecache/            # 素材爬取脚本（抓来的原图缓存不进仓库）
├── sources/                # 游戏素材目录：**仓库里只有一份 README**，图片要自己准备（见下）
├── tests/                  # 189 个 pytest 用例
└── 玩法与卡牌.txt  指令格式.txt  开发历程.md  打包说明.md
```

## 素材与版权（重要）

**本仓库不包含游戏素材图片** —— `sources/` 里只有一份 [`sources/README.md`](sources/README.md) 说明。

- 素材来源是游戏 wiki，爬取脚本是 [`sourcecache/fetch_wiki_images.py`](sourcecache/fetch_wiki_images.py)：
  - 吉星派对（`starengine`）：<https://wiki.biligame.com/starengine>
  - 杀戮尖塔 2（`sts2`）：<https://sts2.huijiwiki.com>
- **这些素材的版权归各自游戏厂商所有**，所以公开仓库里不放（`.gitignore` 排除了 `sources/*`），
  只在个人学习、研究的范围内自己抓来用 —— 这也和 `sourcecache/README.md` 里的合规说明一致。
- **没有素材照样能跑**：图片加载失败时界面会退回**程序化绘制的占位**卡面 / 头像 / 图标，
  `--cli`、`--smoke` 和全部逻辑测试都不受影响（只有 3 个「图片文件存在性」测试会跳过）。
- 想要带图版本：照 [`sources/README.md`](sources/README.md) 把素材抓回来放进 `sources/` 即可。

## 许可

未声明开源许可证，保留所有权利。代码可以拿来读、拿来学，但不要当成自己的作品发布。
素材不在本仓库内；如果你自行获取素材，请自行遵守其版权方的要求。
