#!/usr/bin/env python3
"""从 MediaWiki 游戏 wiki 爬取素材图片。

支持两个 wiki：
  - 吉星派对  (starengine)  https://wiki.biligame.com/starengine
  - 杀戮尖塔2 (sts2)        https://sts2.huijiwiki.com

用法示例：
  # 吉星派对：下载前 50 张图片
  python fetch_wiki_images.py --wiki starengine --limit 50

  # 只下载文件名以「角色卡」开头的图片
  python fetch_wiki_images.py --wiki starengine --prefix 角色卡 --limit 100

  # 杀戮尖塔2（Cloudflare 防护，需要 playwright 后端）
  python fetch_wiki_images.py --wiki sts2 --backend playwright --limit 50

  # 只列出不下载
  python fetch_wiki_images.py --wiki starengine --limit 20 --dry-run

依赖：
  pip install requests            # 必需
  pip install playwright          # 仅 huijiwiki(Cloudflare) 需要
  playwright install chromium     # 首次使用 playwright 需要

版权与合规提示：
  - wiki 上的素材图片版权归游戏厂商所有，本脚本仅供个人学习、研究参考使用，
    请勿将下载的素材用于分发或商业用途。
  - 请遵守目标站点的 robots.txt 与使用条款，并控制请求频率（--delay）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

WIKIS = {
    "starengine": {
        "name": "吉星派对",
        "api": "https://wiki.biligame.com/starengine/api.php",
    },
    "sts2": {
        "name": "杀戮尖塔2",
        "api": "https://sts2.huijiwiki.com/api.php",
    },
}

# Cloudflare 挑战页的典型特征
CLOUDFLARE_MARKERS = ("challenges.cloudflare", "请稍候", "cf-challenge")

SCRIPT_DIR = Path(__file__).resolve().parent


class WikiError(RuntimeError):
    pass


def safe_filename(name: str) -> str:
    """把文件名清理成可安全落盘的名称（保留中文）。"""
    name = name.replace("\\", "_").replace("/", "_")
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "_", name)
    name = name.strip().strip(".")
    return name or "unnamed"


def _is_cloudflare(text: str) -> bool:
    return any(m in text for m in CLOUDFLARE_MARKERS)


# ---------------- 请求后端 ----------------
class RequestsBackend:
    """标准 requests 后端，适合没有 Cloudflare 防护的站点。"""

    def __init__(self, delay: float) -> None:
        import requests

        self.requests = requests
        self.session = requests.Session()
        self.session.headers["User-Agent"] = DEFAULT_UA
        self.delay = delay

    def get_json(self, api_url: str, params: dict) -> dict:
        resp = self.session.get(api_url, params=params, timeout=30)
        resp.raise_for_status()
        if _is_cloudflare(resp.text):
            raise WikiError(
                "目标站点启用了 Cloudflare 防护，请改用 --backend playwright"
            )
        return resp.json()

    def get_bytes(self, url: str) -> bytes:
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "text/html" in ctype and _is_cloudflare(resp.text):
            raise WikiError("图片被 Cloudflare 拦截")
        return resp.content


class PlaywrightBackend:
    """playwright 后端，用真实浏览器通过 Cloudflare 挑战（用于 huijiwiki）。"""

    def __init__(self, delay: float) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise WikiError(
                "未安装 playwright，请先执行: pip install playwright && playwright install chromium"
            ) from exc
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        self.context = self.browser.new_context(user_agent=DEFAULT_UA, locale="zh-CN")
        self.page = self.context.new_page()
        self.delay = delay

    def _wait_challenge(self) -> None:
        for _ in range(60):
            body = self.page.inner_text("body")
            if not _is_cloudflare(body):
                return
            self.page.wait_for_timeout(1000)
        raise WikiError("Cloudflare 挑战未通过，请稍后重试或改用有头模式")

    def get_json(self, api_url: str, params: dict) -> dict:
        from urllib.parse import urlencode

        url = api_url + "?" + urlencode(params)
        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self._wait_challenge()
        body = self.page.inner_text("body")
        if _is_cloudflare(body):
            raise WikiError("Cloudflare 挑战未通过")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise WikiError(f"响应不是合法 JSON：{body[:200]}") from exc

    def get_bytes(self, url: str) -> bytes:
        resp = self.context.request.get(url, timeout=60_000)
        if resp.status != 200:
            raise WikiError(f"HTTP {resp.status}")
        return resp.body()

    def close(self) -> None:
        self.browser.close()
        self._pw.stop()


# ---------------- 图片枚举 ----------------
def iter_all_images(backend, api_url: str, prefix: str | None):
    """遍历 wiki 所有图片（allimages API，自动分页）。"""
    params = {
        "action": "query",
        "list": "allimages",
        "ailimit": "500",
        "aiprop": "url|size",
        "format": "json",
    }
    if prefix:
        params["aiprefix"] = prefix
    while True:
        data = backend.get_json(api_url, params)
        for img in data.get("query", {}).get("allimages", []):
            yield img
        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
        time.sleep(backend.delay)


def iter_category_files(backend, api_url: str, category: str):
    """遍历某个分类下的所有文件（categorymembers API，自动分页）。

    返回每个文件的标题（形如「文件:xxx.png」），随后用 imageinfo 解析 URL。
    """
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"分类:{category}",
        "cmtype": "file",
        "cmlimit": "500",
        "format": "json",
    }
    while True:
        data = backend.get_json(api_url, params)
        for member in data.get("query", {}).get("categorymembers", []):
            yield member.get("title", "")
        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
        time.sleep(backend.delay)


def resolve_image_url(backend, api_url: str, title: str) -> tuple[str, str]:
    """根据文件标题获取直链 URL 与文件名（imageinfo API）。

    返回 (url, name)。name 为去掉「文件:」前缀后的文件名。
    """
    params = {
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }
    data = backend.get_json(api_url, params)
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        infos = page.get("imageinfo", [])
        if infos:
            url = infos[0].get("url", "")
            name = title
            if name.startswith("文件:"):
                name = name[len("文件:"):]
            elif name.startswith("File:"):
                name = name[len("File:"):]
            return url, name
    return "", title


def main() -> int:
    parser = argparse.ArgumentParser(description="从 MediaWiki 游戏 wiki 爬取素材图片")
    parser.add_argument("--wiki", choices=sorted(WIKIS), required=True, help="目标 wiki")
    parser.add_argument("--prefix", default=None, help="只下载文件名以此为前缀的图片")
    parser.add_argument("--category", default=None, help="按分类下载该分类下所有文件（如 文件/怪物/立绘）")
    parser.add_argument("--limit", type=int, default=0, help="最多下载数量，0 表示不限制（默认 0）")
    parser.add_argument("--out", default=None, help="输出目录（默认 sourcecache/<wiki>）")
    parser.add_argument("--backend", choices=["auto", "requests", "playwright"],
                        default="auto", help="请求后端，默认 auto")
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔秒数（默认 0.3）")
    parser.add_argument("--dry-run", action="store_true", help="只列出不下载")
    args = parser.parse_args()

    info = WIKIS[args.wiki]
    api_url = info["api"]
    out_dir = Path(args.out) if args.out else SCRIPT_DIR / args.wiki

    backend = None
    try:
        if args.backend == "playwright":
            backend = PlaywrightBackend(args.delay)
        else:
            backend = RequestsBackend(args.delay)
    except WikiError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"目标 wiki：{info['name']} ({args.wiki})")
        print(f"API：{api_url}")
        print(f"输出目录：{out_dir}")
        if args.prefix:
            print(f"前缀过滤：{args.prefix}")
        if args.category:
            print(f"分类：{args.category}")
        print("-" * 60)

        # 根据参数构造图片枚举源：分类模式走 categorymembers+imageinfo，
        # 否则走 allimages（可加前缀过滤）。
        if args.category:
            def _iter():
                for title in iter_category_files(backend, api_url, args.category):
                    if not title:
                        continue
                    url, name = resolve_image_url(backend, api_url, title)
                    if url:
                        yield name, url
        else:
            def _iter():
                for img in iter_all_images(backend, api_url, args.prefix):
                    yield img.get("name", ""), img.get("url", "")

        count = 0
        for name, url in _iter():
            if not name or not url:
                continue
            dest = out_dir / safe_filename(name)
            count += 1

            if args.dry_run:
                print(f"[{count:4d}] {name}")
            else:
                if dest.exists():
                    print(f"[{count:4d}] 已存在，跳过: {name}")
                else:
                    print(f"[{count:4d}] 下载: {name}")
                    data = backend.get_bytes(url)
                    dest.write_bytes(data)

            if args.limit and count >= args.limit:
                break

        print("-" * 60)
        print(f"完成，共处理 {count} 张图片。")
        return 0
    except WikiError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1
    finally:
        if isinstance(backend, PlaywrightBackend):
            backend.close()


if __name__ == "__main__":
    sys.exit(main())
