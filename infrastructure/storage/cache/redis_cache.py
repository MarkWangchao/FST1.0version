#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - Redis缓存实现

提供基于Redis的高性能缓存实现:
- 智能连接池管理
- 自适应压缩
- 动态TTL管理
- 高可用支持
- 增强监控
"""

import logging
import asyncio
from typing import Dict, Optional, Any, List, Union
from datetime import datetime, timedelta
import aioredis
import json
import zlib
import lz4.frame
import snappy
import msgpack
import pickle
from collections import defaultdict
from prometheus_client import Counter, Gauge, Histogram
from ..base import CacheStorage

# 监控指标
CACHE_OPS = Counter('redis_operations_total', '缓存操作数', ['operation'])
CACHE_SIZE = Gauge('redis_memory_usage_bytes', '缓存内存使用')
CACHE_HITS = Counter('redis_cache_hits_total', '缓存命中数')
CACHE_MISSES = Counter('redis_cache_misses_total', '缓存未命中数')
OP_LATENCY = Histogram('redis_operation_latency_seconds', '操作延迟')
CONN_GAUGE = Gauge('redis_connections', '连接数', ['state'])

# 压缩算法配置
COMPRESSION_ALGORITHMS = {
    'zlib': (zlib.compress, zlib.decompress),
    'lz4': (lz4.frame.compress, lz4.frame.decompress),
    'snappy': (snappy.compress, snappy.decompress)
}

# 内存优化配置
MEMORY_OPTIMIZATION = {
    'hash-max-ziplist-entries': 512,
    'hash-max-ziplist-value': 64,
    'list-max-ziplist-size': -2,
    'set-max-intset-entries': 512,
    'zset-max-ziplist-entries': 128,
    'zset-max-ziplist-value': 64
}

class SmartConnectionPool:
    """智能连接池管理"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.pool = None
        self.health_checker = HealthChecker()
        
    async def create_pool(self):
        """创建连接池"""
        self.pool = await aioredis.create_redis_pool(
            self.config['url'],
            minsize=self.config.get('minsize', 5),
            maxsize=self.config.get('maxsize', 50),
            timeout=self.config.get('timeout', 10),
            encoding='utf-8'
        )
        
    async def adjust_pool_size(self):
        """动态调整连接池大小"""
        try:
            current_usage = await self._get_connection_usage()
            if current_usage > 0.8:  # 连接池使用率超过80%
                new_size = min(self.pool.maxsize * 1.2, 1000)
                await self.pool.resize(new_size)
                self.logger.info(f"连接池扩容至: {new_size}")
            elif current_usage < 0.3:  # 使用率低于30%
                new_size = max(self.pool.minsize, int(self.pool.maxsize * 0.8))
                await self.pool.resize(new_size)
                self.logger.info(f"连接池缩容至: {new_size}")
                
            # 更新指标
            CONN_GAUGE.labels(state='in_use').set(self.pool.size)
            CONN_GAUGE.labels(state='available').set(self.pool.maxsize - self.pool.size)
            
        except Exception as e:
            self.logger.error(f"调整连接池大小失败: {str(e)}")
            
    async def _get_connection_usage(self) -> float:
        """获取连接池使用率"""
        return self.pool.size / self.pool.maxsize

class HealthChecker:
    """连接健康检查"""
    
    async def check_connections(self, pool):
        """检查连接健康状态"""
        try:
            invalid_conns = []
            for conn in pool._connections:
                try:
                    if not await conn.ping():
                        invalid_conns.append(conn)
                except Exception:
                    invalid_conns.append(conn)
                    
            # 关闭无效连接
            for conn in invalid_conns:
                pool._connections.remove(conn)
                conn.close()
                
            return len(invalid_conns)
            
        except Exception as e:
            self.logger.error(f"健康检查失败: {str(e)}")
            return 0

class AdaptiveCompressor:
    """自适应压缩器"""
    
    def __init__(self):
        self.compression_stats = defaultdict(lambda: {'size': 0, 'time': 0})
        
    def select_algorithm(self, data: Any) -> str:
        """选择最优压缩算法"""
        if isinstance(data, (bytes, bytearray)):
            return 'lz4' if len(data) > 4096 else 'snappy'
        elif isinstance(data, str):
            return 'zlib' if len(data) > 1024 else 'snappy'
        return 'zlib'
        
    def compress(self, data: Any, algorithm: str) -> bytes:
        """压缩数据"""
        compress_func = COMPRESSION_ALGORITHMS[algorithm][0]
        return compress_func(data)
        
    def decompress(self, data: bytes, algorithm: str) -> Any:
        """解压数据"""
        decompress_func = COMPRESSION_ALGORITHMS[algorithm][1]
        return decompress_func(data)

class DynamicTTLManager:
    """动态TTL管理器"""
    
    def __init__(self):
        self.access_stats = defaultdict(int)
        self.ttl_adjustments = {
            'hot': lambda x: x * 2,    # 热门数据TTL翻倍
            'warm': lambda x: x * 1.5,  # 温数据TTL增加50%
            'cold': lambda x: x // 2    # 冷数据TTL减半
        }
        
    async def adjust_ttl(self, redis, key: str):
        """调整键的TTL"""
        try:
            access_count = self.access_stats[key]
            current_ttl = await redis.ttl(key)
            
            if current_ttl < 0:  # 键不存在或没有TTL
                return
                
            if access_count > 1000:
                new_ttl = self.ttl_adjustments['hot'](current_ttl)
            elif access_count > 100:
                new_ttl = self.ttl_adjustments['warm'](current_ttl)
            else:
                new_ttl = self.ttl_adjustments['cold'](current_ttl)
                
            await redis.expire(key, new_ttl)
            
        except Exception as e:
            self.logger.error(f"调整TTL失败: {str(e)}")

class CircuitBreaker:
    """断路器"""
    
    def __init__(self):
        self.failure_count = 0
        self.state = 'closed'
        self.reset_timeout = 30  # 重置超时时间(秒)
        
    async def execute(self, command):
        """执行命令"""
        if self.state == 'open':
            raise Exception("断路器开启")
            
        try:
            result = await command()
            self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count > 5:
                self.state = 'open'
                asyncio.create_task(self._reset_after(self.reset_timeout))
            raise e
            
    async def _reset_after(self, timeout: int):
        """延时重置断路器"""
        await asyncio.sleep(timeout)
        self.state = 'closed'
        self.failure_count = 0

class EnhancedMonitor:
    """增强监控"""
    
    async def collect_metrics(self, redis) -> Dict:
        """收集监控指标"""
        try:
            metrics = {}
            info_sections = [
                'keyspace', 'commandstats', 'memory', 'clients',
                'persistence', 'stats', 'replication', 'cpu', 'cluster'
            ]
            
            for section in info_sections:
                metrics[section] = await redis.info(section)
                
            # 获取延迟直方图
            metrics['latency'] = await redis.execute_command('LATENCY', 'HISTOGRAM')
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"收集监控指标失败: {str(e)}")
            return {}

class Serializer:
    """序列化器"""
    
    def serialize(self, data: Any) -> bytes:
        """序列化数据"""
        if isinstance(data, (dict, list)):
            return msgpack.packb(data)
        elif isinstance(data, str):
            return data.encode('utf-8')
        return pickle.dumps(data)
        
    def deserialize(self, data: bytes) -> Any:
        """反序列化数据"""
        try:
            return msgpack.unpackb(data)
        except:
            try:
                return data.decode('utf-8')
            except:
                return pickle.loads(data)

class RedisCache(CacheStorage):
    """Redis缓存实现"""
    
    def __init__(self, config: Dict):
        """初始化Redis缓存"""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 组件初始化
        self.pool_manager = SmartConnectionPool(config)
        self.compressor = AdaptiveCompressor()
        self.ttl_manager = DynamicTTLManager()
        self.circuit_breaker = CircuitBreaker()
        self.monitor = EnhancedMonitor()
        self.serializer = Serializer()
        
        # 缓存配置
        self.default_ttl = config.get('default_ttl', 300)
        self.compression_threshold = config.get('compression_threshold', 1024)
        
    async def start(self):
        """启动缓存服务"""
        self.logger.info("Redis缓存服务启动中...")
        
        try:
            # 创建连接池
            await self.pool_manager.create_pool()
            
            # 应用内存优化配置
            await self._optimize_memory()
            
            # 启动维护任务
            asyncio.create_task(self._maintenance_task())
            
            self.logger.info("Redis缓存服务已启动")
            
        except Exception as e:
            self.logger.error(f"启动缓存服务失败: {str(e)}")
            raise
            
    async def _maintenance_task(self):
        """维护任务"""
        while True:
            try:
                # 调整连接池大小
                await self.pool_manager.adjust_pool_size()
                
                # 健康检查
                invalid_count = await self.pool_manager.health_checker.check_connections(
                    self.pool_manager.pool
                )
                if invalid_count > 0:
                    self.logger.warning(f"发现 {invalid_count} 个无效连接")
                    
                # 收集监控指标
                metrics = await self.monitor.collect_metrics(self.pool_manager.pool)
                
                # 更新监控指标
                CACHE_SIZE.set(metrics['memory'].get('used_memory', 0))
                
                await asyncio.sleep(60)  # 每分钟执行一次
                
            except Exception as e:
                self.logger.error(f"维护任务失败: {str(e)}")
                await asyncio.sleep(5)
                
    async def _optimize_memory(self):
        """应用内存优化配置"""
        try:
            for param, value in MEMORY_OPTIMIZATION.items():
                await self.pool_manager.pool.config_set(param, value)
            await self.pool_manager.pool.config_rewrite()
            self.logger.info("内存优化配置已应用")
        except Exception as e:
            self.logger.error(f"应用内存优化配置失败: {str(e)}")
            
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        try:
            async def _get():
                data = await self.pool_manager.pool.get(key)
                if data is None:
                    CACHE_MISSES.inc()
                    return None
                    
                CACHE_HITS.inc()
                
                # 更新访问统计
                self.ttl_manager.access_stats[key] += 1
                await self.ttl_manager.adjust_ttl(self.pool_manager.pool, key)
                
                # 解压缩和反序列化
                if isinstance(data, bytes):
                    algorithm = data[:5].decode().strip()
                    if algorithm in COMPRESSION_ALGORITHMS:
                        data = self.compressor.decompress(data[5:], algorithm)
                        
                return self.serializer.deserialize(data)
                
            return await self.circuit_breaker.execute(_get)
            
        except Exception as e:
            self.logger.error(f"获取缓存失败: {str(e)}")
            return None
            
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            async def _set():
                # 序列化
                data = self.serializer.serialize(value)
                
                # 压缩
                if len(data) > self.compression_threshold:
                    algorithm = self.compressor.select_algorithm(data)
                    compressed = self.compressor.compress(data, algorithm)
                    data = f"{algorithm:<5}".encode() + compressed
                    
                # 设置值
                return await self.pool_manager.pool.set(
                    key,
                    data,
                    expire=ttl or self.default_ttl
                )
                
            success = await self.circuit_breaker.execute(_set)
            if success:
                CACHE_OPS.labels(operation='set').inc()
                
            return bool(success)
            
        except Exception as e:
            self.logger.error(f"设置缓存失败: {str(e)}")
            return False
            
    async def delete(self, key: str) -> bool:
        """删除缓存值"""
        try:
            async def _delete():
                return await self.pool_manager.pool.delete(key)
                
            success = await self.circuit_breaker.execute(_delete)
            if success:
                CACHE_OPS.labels(operation='delete').inc()
                
            return bool(success)
            
        except Exception as e:
            self.logger.error(f"删除缓存失败: {str(e)}")
            return False
            
    async def clear(self) -> bool:
        """清空缓存"""
        try:
            async def _clear():
                return await self.pool_manager.pool.flushdb()
                
            success = await self.circuit_breaker.execute(_clear)
            if success:
                CACHE_OPS.labels(operation='clear').inc()
                
            return bool(success)
            
        except Exception as e:
            self.logger.error(f"清空缓存失败: {str(e)}")
            return False
            
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        try:
            return {
                'operations': {
                    'get': CACHE_OPS.labels(operation='get')._value.get(),
                    'set': CACHE_OPS.labels(operation='set')._value.get(),
                    'delete': CACHE_OPS.labels(operation='delete')._value.get(),
                    'clear': CACHE_OPS.labels(operation='clear')._value.get()
                },
                'hits': CACHE_HITS._value.get(),
                'misses': CACHE_MISSES._value.get(),
                'memory_usage': CACHE_SIZE._value.get(),
                'connections': {
                    'in_use': CONN_GAUGE.labels(state='in_use')._value.get(),
                    'available': CONN_GAUGE.labels(state='available')._value.get()
                }
            }
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {str(e)}")
            return {}