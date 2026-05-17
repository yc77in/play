@echo off
chcp 936 >nul 2>&1

:: ================= 【可替换】核心配置区 =================
:: 你的Anaconda安装根目录(如D:\program\anaconda）
set CONDA_ROOT=YOUR_ANACONDA_INSTALL_PATH
:: 你的conda虚拟环境名称（如oc_pet）
set ENV_NAME=YOUR_CONDA_ENV_NAME
:: 主程序文件名（默认oc.py，如果你改了名字就对应修改）
set MAIN_FILE=oc.py
:: 窗口标题
set WINDOW_TITLE=AI Desktop Pet
:: ======================================================

title %WINDOW_TITLE%

echo 正在启动 AI 桌宠...
echo.

:: 自动切换到脚本所在目录（切换不到就填绝对路径，例如cd /d D:\AI\oc）
cd /d "%~dp0"

:: 激活conda环境（%ENV_NAME%你的环境名如oc_pet）
call "%CONDA_ROOT%\Scripts\activate.bat" %ENV_NAME%

:: 运行主程序("%MAIN_FILE%"你的主程序名如oc.py）
python "%MAIN_FILE%"

:: 错误处理
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo [错误] 启动失败！
    echo 可能的原因：
    echo 1. Anaconda路径配置错误
    echo 2. 虚拟环境不存在
    echo 3. 缺少依赖包
    echo 4. 主程序文件名错误
    echo ========================================
    echo.
    pause
)