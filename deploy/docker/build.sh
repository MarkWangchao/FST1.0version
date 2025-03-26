#!/bin/bash
# FST Docker构建脚本 - 用于灵活切换不同网络环境的构建配置

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 显示帮助
show_help() {
    echo -e "${BLUE}FST Docker构建脚本${NC}"
    echo "此脚本用于构建FST Docker镜像，可根据网络环境灵活选择配置。"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help            显示此帮助信息"
    echo "  -c, --use-cn          使用国内镜像源 (默认)"
    echo "  -g, --use-global      使用官方镜像源 (使用VPN时选择)"
    echo "  -t, --tag TAG         指定镜像标签 (默认: latest)"
    echo "  -f, --file FILE       指定Dockerfile (默认: Dockerfile.flexible)"
    echo "  -l, --light           构建轻量级版本 (使用Dockerfile.light)"
    echo ""
    echo "示例:"
    echo "  $0 --use-cn           # 在国内网络环境下构建"
    echo "  $0 --use-global       # 在使用VPN的情况下构建"
    echo "  $0 --tag dev          # 构建标签为dev的镜像"
    echo "  $0 --light            # 构建轻量级版本"
}

# 默认参数
USE_CN_MIRROR="true"
TAG="latest"
DOCKERFILE="deploy/docker/Dockerfile.flexible"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--use-cn)
            USE_CN_MIRROR="true"
            shift
            ;;
        -g|--use-global)
            USE_CN_MIRROR="false"
            shift
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -f|--file)
            DOCKERFILE="$2"
            shift 2
            ;;
        -l|--light)
            DOCKERFILE="deploy/docker/Dockerfile.light"
            shift
            ;;
        *)
            echo -e "${RED}错误: 未知选项 $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 切换到项目根目录
cd $(dirname "$0")/../..

# 显示当前配置
echo -e "${BLUE}当前构建配置:${NC}"
echo -e "  使用国内镜像: ${YELLOW}$USE_CN_MIRROR${NC}"
echo -e "  镜像标签: ${YELLOW}$TAG${NC}"
echo -e "  Dockerfile: ${YELLOW}$DOCKERFILE${NC}"
echo ""

# 确认构建
read -p "是否继续构建? [Y/n] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
    echo -e "${RED}已取消构建${NC}"
    exit 0
fi

# 开始构建
echo -e "${GREEN}开始构建Docker镜像...${NC}"

# 提取Dockerfile名称用于显示
DOCKERFILE_NAME=$(basename $DOCKERFILE)

# 构建命令
if [[ "$DOCKERFILE_NAME" == "Dockerfile.flexible" ]]; then
    docker build \
        --build-arg USE_CN_MIRROR=$USE_CN_MIRROR \
        --build-arg PIP_INDEX_URL=$([ "$USE_CN_MIRROR" = "true" ] && echo "https://mirrors.aliyun.com/pypi/simple/" || echo "https://pypi.org/simple/") \
        --build-arg PIP_TRUSTED_HOST=$([ "$USE_CN_MIRROR" = "true" ] && echo "mirrors.aliyun.com" || echo "pypi.org") \
        -t fst:$TAG \
        -f $DOCKERFILE .
else
    docker build -t fst:$TAG -f $DOCKERFILE .
fi

# 检查构建结果
if [ $? -eq 0 ]; then
    echo -e "${GREEN}构建成功!${NC}"
    echo -e "镜像信息:"
    docker images fst:$TAG
else
    echo -e "${RED}构建失败!${NC}"
    exit 1
fi

# 提示下一步操作
echo ""
echo -e "${BLUE}下一步操作:${NC}"
echo -e "1. 运行容器: ${YELLOW}docker run -p 8000:8000 fst:$TAG${NC}"
echo -e "2. 使用Docker Compose: ${YELLOW}cd deploy/docker && docker-compose up -d${NC}"
echo ""