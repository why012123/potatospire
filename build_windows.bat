@echo off
REM ============================================
REM  土豆尖塔 Windows 打包脚本
REM  在 Windows 上运行，自动安装依赖并打包成 exe
REM ============================================
chcp 65001 >nul

echo [1/4] 检查 Python...
where python >nul 2>nul
if errorlevel 1 (
    echo 错误：未找到 Python，请先到 https://www.python.org/downloads/ 安装 Python 3.10+ 并勾选 "Add to PATH"
    pause
    exit /b 1
)

echo [2/4] 安装打包依赖...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo 错误：依赖安装失败
    pause
    exit /b 1
)

echo [3/4] 开始打包...
pyinstaller --noconfirm potatospire.spec
if errorlevel 1 (
    echo 错误：打包失败
    pause
    exit /b 1
)

echo [4/4] 完成！
echo 生成的 exe 在 dist\Potatospire\ 文件夹中
echo 可以把整个 dist\Potatospire\ 文件夹压缩成 zip 发给同学
pause
