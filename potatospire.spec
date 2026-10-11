# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

用法（在目标平台 Windows 上执行）：
    pip install pyinstaller
    pyinstaller potatospire.spec

产物在 dist/ 下，可打包成单文件 exe + 资源文件夹，或纯单文件。
"""

import os

block_cipher = None

# 项目根目录（spec 文件所在目录；PyInstaller 会提供 SPECPATH 全局变量）
BASE = globals().get("SPECPATH") or os.path.dirname(os.path.abspath(globals().get("__file__", ".")))

# 资源目录（相对项目根）。
# 注意：sources/ 里的素材**不在公开仓库里**（卡面/立绘是 wiki 爬的，版权原因不能公开分发），
# 要打带图的包就先照 sources/README.md 把素材放好；没有素材时这里自动跳过，
# 游戏会用程序化绘制的占位卡面 / 头像照常跑起来。
datas = []
if os.path.isdir(os.path.join(BASE, "sources")):
    datas.append((os.path.join(BASE, "sources"), "sources"))  # 角色 / 卡牌 / 敌人图片
else:
    print("[potatospire.spec] 没找到 sources/，打成「无素材版」（游戏里用程序化占位图）")

# 仅打包游戏运行依赖，排除开发依赖
hiddenimports = []

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "playwright",
        "requests",
        "urllib3",
        "PIL",
        "numpy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Potatospire",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台窗口（游戏）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
