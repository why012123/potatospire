# sourcecache

从游戏 wiki 爬取素材图片的脚本与缓存目录。

## 文件

- `fetch_wiki_images.py` — 爬虫脚本（MediaWiki allimages API）
- `starengine/` — 吉星派对素材缓存
- `sts2/` — 杀戮尖塔2素材缓存

## 快速开始

```bash
# 安装依赖
pip install requests            # 必需
pip install playwright          # 仅爬取杀戮尖塔2(Cloudflare) 需要
playwright install chromium     # 首次使用 playwright 需要

# 吉星派对：下载前 50 张
python fetch_wiki_images.py --wiki starengine --limit 50

# 按文件名前缀过滤
python fetch_wiki_images.py --wiki starengine --prefix 角色卡 --limit 100

# 杀戮尖塔2（Cloudflare，需要 playwright 后端）
python fetch_wiki_images.py --wiki sts2 --backend playwright --limit 50

# 只列出不下载
python fetch_wiki_images.py --wiki starengine --limit 20 --dry-run
```

## 参数

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--wiki` | 目标 wiki：`starengine` / `sts2` | 必填 |
| `--prefix` | 只下载文件名以此为前缀的图片 | 无 |
| `--limit` | 最多下载数量，0 表示不限制 | 50 |
| `--out` | 输出目录 | `sourcecache/<wiki>` |
| `--backend` | `auto` / `requests` / `playwright` | `auto` |
| `--delay` | 请求间隔秒数 | 0.3 |
| `--dry-run` | 只列出不下载 | 关闭 |

## 站点说明

- **吉星派对**（`starengine`）：MediaWiki 1.37，API 公开可用，`requests` 后端即可。
- **杀戮尖塔2**（`sts2`）：huijiwiki 有 Cloudflare 挑战防护，`requests`/`curl`
  会被拦截，需用 `--backend playwright`（真实浏览器）通过挑战。

## 版权与合规

- wiki 上的素材图片版权归游戏厂商所有，本脚本**仅供个人学习、研究参考**，
  请勿将下载素材用于分发或商业用途。
- 请遵守目标站点的 robots.txt 与使用条款，控制请求频率（`--delay`）。
