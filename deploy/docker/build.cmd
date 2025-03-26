@echo off
REM FST Docker构建脚本 - 用于灵活切换不同网络环境的构建配置 (Windows版)
setlocal enabledelayedexpansion

REM 默认参数
set "USE_CN_MIRROR=true"
set "TAG=latest"
set "DOCKERFILE=deploy\docker\Dockerfile.flexible"
set "SHOW_HELP=false"

REM 简化的参数解析
if "%1"=="-h" goto :show_help
if "%1"=="--help" goto :show_help
if "%1"=="-c" set "USE_CN_MIRROR=true" & shift
if "%1"=="--use-cn" set "USE_CN_MIRROR=true" & shift
if "%1"=="-g" set "USE_CN_MIRROR=false" & shift
if "%1"=="--use-global" set "USE_CN_MIRROR=false" & shift
if "%1"=="-l" set "DOCKERFILE=deploy\docker\Dockerfile.light" & shift
if "%1"=="--light" set "DOCKERFILE=deploy\docker\Dockerfile.light" & shift

if "%1"=="-t" set "TAG=%2" & shift & shift
if "%1"=="--tag" set "TAG=%2" & shift & shift

REM 显示帮助
:show_help
if "%1"=="-h" goto :help_message
if "%1"=="--help" goto :help_message
goto :continue

:help_message
echo FST Docker构建脚本 (Windows版)
echo 此脚本用于构建FST Docker镜像，可根据网络环境灵活选择配置。
echo.
echo 用法: %0 [选项]
echo.
echo 选项:
echo   -h, --help            显示此帮助信息
echo   -c, --use-cn          使用国内镜像源 (默认)
echo   -g, --use-global      使用官方镜像源 (使用VPN时选择)
echo   -t, --tag TAG         指定镜像标签 (默认: latest)
echo   -f, --file FILE       指定Dockerfile (默认: Dockerfile.flexible)
echo   -l, --light           构建轻量级版本 (使用Dockerfile.light)
echo.
echo 示例:
echo   %0 --use-cn           # 在国内网络环境下构建
echo   %0 --use-global       # 在使用VPN的情况下构建
echo   %0 --tag dev          # 构建标签为dev的镜像
echo   %0 --light            # 构建轻量级版本
exit /b 0

:continue
REM 切换到项目根目录
cd %~dp0\..\..

REM 显示当前配置
echo 当前构建配置:
echo   使用国内镜像: %USE_CN_MIRROR%
echo   镜像标签: %TAG%
echo   Dockerfile: %DOCKERFILE%
echo.

REM 确认构建
set /p "CONFIRM=是否继续构建? [Y/n] "
if /i not "%CONFIRM%"=="Y" if not "%CONFIRM%"=="" (
    echo 已取消构建
    exit /b 0
)

REM 开始构建
echo 开始构建Docker镜像...

REM 提取Dockerfile名称用于显示
for %%F in ("%DOCKERFILE%") do set "DOCKERFILE_NAME=%%~nxF"

REM 构建命令
if "%DOCKERFILE_NAME%"=="Dockerfile.flexible" (
    if "%USE_CN_MIRROR%"=="true" (
        set "PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/"
        set "PIP_TRUSTED_HOST=mirrors.aliyun.com"
    ) else (
        set "PIP_INDEX_URL=https://pypi.org/simple/"
        set "PIP_TRUSTED_HOST=pypi.org"
    )
    
    docker build ^
        --build-arg USE_CN_MIRROR=%USE_CN_MIRROR% ^
        --build-arg PIP_INDEX_URL=%PIP_INDEX_URL% ^
        --build-arg PIP_TRUSTED_HOST=%PIP_TRUSTED_HOST% ^
        -t fst:%TAG% ^
        -f %DOCKERFILE% .
) else (
    docker build -t fst:%TAG% -f %DOCKERFILE% .
)

REM 检查构建结果
if %ERRORLEVEL% EQU 0 (
    echo 构建成功!
    echo 镜像信息:
    docker images fst:%TAG%
) else (
    echo 构建失败!
    exit /b 1
)

REM 提示下一步操作
echo.
echo 下一步操作:
echo 1. 运行容器: docker run -p 8000:8000 fst:%TAG%
echo 2. 使用Docker Compose: cd deploy\docker ^& docker-compose up -d
echo.