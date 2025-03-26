#!/bin/bash
set -e

# 检查环境变量
echo "Starting FST Trading Platform..."
echo "Environment: ${ENVIRONMENT:-development}"

# 等待依赖服务就绪
wait_for_service() {
    local host="$1"
    local port="$2"
    local service="$3"
    local timeout=30
    local count=0
    
    echo "Waiting for $service to be ready..."
    until nc -z -w 1 "$host" "$port" > /dev/null 2>&1; do
        count=$((count + 1))
        if [ $count -ge $timeout ]; then
            echo "Timeout reached waiting for $service to be ready"
            return 1
        fi
        echo "Waiting for $service to be ready... ($count/$timeout)"
        sleep 1
    done
    echo "$service is ready!"
    return 0
}

# 等待MongoDB (如果配置了)
if [ ! -z "$MONGODB_HOST" ]; then
    wait_for_service "$MONGODB_HOST" "${MONGODB_PORT:-27017}" "MongoDB"
fi

# 等待Redis (如果配置了)
if [ ! -z "$REDIS_HOST" ]; then
    wait_for_service "$REDIS_HOST" "${REDIS_PORT:-6379}" "Redis"
fi

# 初始化数据库(如果需要)
if [ "$INITIALIZE_DB" = "true" ]; then
    echo "Initializing database..."
    python scripts/init_db.py
    echo "Database initialized!"
fi

# 启动应用
echo "Starting application with command: $@"
exec "$@"