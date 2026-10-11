# sources —— 游戏素材（不在仓库里，需要自己准备）

这个目录放游戏用到的图片：卡面、角色立绘 / 头像、敌人图、事件图、状态图标。

**公开仓库不包含这些图片**：它们是从游戏 wiki 爬下来的，
版权归各自游戏厂商所有（见 [`../sourcecache/README.md`](../sourcecache/README.md)），
不能公开分发，所以 `.gitignore` 里把 `sources/*` 排除了（只留这份说明）。

## 没有素材会怎样

不影响运行：图片加载失败时界面会退回**程序化绘制的占位**（卡面、头像、状态图标都会用色块+文字画出来），
`python main.py`、`python main.py --cli`、`python main.py --smoke` 都照常。

只有 3 个「图片文件真的存在」的测试会跳过（`tests/test_new_enemies.py` 里带 `@requires_art` 的那三个）。

## 怎么把素材弄回来

### 方式 1：用仓库里的爬虫脚本抓（个人学习用）

```bash
pip install requests playwright    # playwright 只有爬杀戮尖塔2 才需要
playwright install chromium

cd sourcecache
python fetch_wiki_images.py --wiki starengine --limit 0     # 吉星派对
python fetch_wiki_images.py --wiki sts2 --backend playwright --limit 0   # 杀戮尖塔2
```

抓下来的是原图缓存，按游戏读取的约定整理进本目录（下面的目录结构）。

### 方式 2：自己放图

按代码里的约定（`game/heroes.py`、`game/enemy.py`、`game/events.py` 里的 `image` 字段）
把对应的图片放进来即可，文件名要和字段一致。

## 目录约定

```
sources/
├── images/            # ui_common.IMAGES_DIR 指向这里
│   ├── card/<卡名>/<卡名>.png     # 卡面（也支持 templates：普卡/蓝卡/金卡模板.png）
│   ├── char/<角色名>/             # 小人 / 大头像 / 小头像
│   ├── enemy/<敌人名>.png|webp    # 敌人图（支持镜像）
│   ├── events/<事件名>.png        # 事件插图
│   └── ...                        # 其它按代码里的相对路径
└── icon/
    ├── general/                   # 意图图标、盾牌等
    └── buff/                      # 状态图标（sources/icon/buff/<状态名>.png|webp）
```

> 路径都是「相对 `sources/images`」的软编码：代码里找不到图不会崩，
> 所以你可以只放一部分图片，剩下的用占位图。
