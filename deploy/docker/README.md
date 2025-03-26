# Docker构建指南

本文档提供FST交易平台Docker镜像构建的详细指南，特别针对在不同网络环境下的构建需求。

## 问题背景

在构建Docker镜像时，我们经常会遇到以下网络相关的问题：

1. **开启VPN时**: 
   - 可以访问官方Docker服务和PyPI源
   - 但国内镜像源可能访问不稳定

2. **关闭VPN时**:
   - 可以快速访问国内镜像源
   - 但可能无法访问某些国外服务

为了解决这个问题，我们提供了灵活配置的Docker构建工具。

## 文件说明

- `Dockerfile.flexible`: 灵活配置的Dockerfile，可在构建时通过参数选择使用国内或官方镜像源
- `Dockerfile.light`: 轻量级Dockerfile，仅包含核心依赖，适合快速测试
- `build.sh`: Linux/Mac环境下的构建脚本
- `build.cmd`: Windows环境下的构建脚本

## 使用方法

### Windows环境

```cmd
# 显示帮助信息
deploy\docker\build.cmd --help

# 默认使用国内镜像源构建
deploy\docker\build.cmd

# 使用官方镜像源构建（开启VPN时使用）
deploy\docker\build.cmd --use-global

# 构建轻量级版本
deploy\docker\build.cmd --light

# 自定义镜像标签
deploy\docker\build.cmd --tag dev
```

### Linux/Mac环境

```bash
# 显示帮助信息
bash deploy/docker/build.sh --help

# 默认使用国内镜像源构建
bash deploy/docker/build.sh

# 使用官方镜像源构建（开启VPN时使用）
bash deploy/docker/build.sh --use-global

# 构建轻量级版本
bash deploy/docker/build.sh --light

# 自定义镜像标签
bash deploy/docker/build.sh --tag dev
```

## 网络环境与构建选项对照表

| 网络环境 | VPN状态 | 推荐构建选项 |
|---------|---------|------------|
| 国内网络 | 关闭 | `--use-cn`（默认） |
| 国内网络 | 开启 | `--use-global` |
| 海外网络 | - | `--use-global` |

## 构建失败的解决方案

如果在构建过程中遇到网络相关的问题：

1. **依赖下载失败**:
   - 确认网络环境与构建选项是否匹配
   - 尝试使用`--light`选项构建轻量级版本

2. **构建过程中断**:
   - 如果在使用VPN时构建中断，可能是VPN连接不稳定
   - 尝试重新运行构建脚本或更换VPN服务器

3. **Docker服务无法连接**:
   - 确认Docker Desktop已正常运行
   - 在Windows环境中，检查WSL状态

## 高级配置

### 自定义PyPI镜像源

如果需要使用其他PyPI镜像源，可以直接编辑`Dockerfile.flexible`文件：

```dockerfile
# 修改默认的国内PyPI镜像源
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
```

### Docker Compose

构建完成后，可以使用Docker Compose启动完整的开发环境：

```bash
cd deploy/docker
docker-compose up -d
```

## 附录：常用命令

```bash
# 查看构建的镜像
docker images fst

# 删除镜像
docker rmi fst:latest

# 运行容器
docker run -p 8000:8000 fst:latest

# 查看运行中的容器
docker ps

# 停止容器
docker stop <container_id>
```