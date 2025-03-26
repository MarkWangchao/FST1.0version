#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强型缓存管理器

提供多级缓存管理功能：
- 多级缓存架构(L1/L2/L3)
- 自适应内存分配
- 数据压缩
- 故障转移
- 连接池优化
"""

import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict
from prometheus_client import Counter, Gauge, Histogram
import json
import zlib
import pickle
import psutil
import aioredis
from diskcache import Cache

# 缓存指标
CACHE_OPS = Counter('cache_operations_total', '缓存操作数', 
                    ['operation', 'cache_type', 'level'])
CACHE_SIZE = Gauge('cache_size_bytes', '缓存大小', ['cache_type', 'level'])
CACHE_ITEMS = Gauge('cache_items', '缓存项数', ['cache_type', 'level'])
CACHE_HIT_RATIO = Gauge('cache_hit_ratio', '缓存命中率', ['cache_type', 'level'])
CACHE_LATENCY = Histogram('cache_operation_latency_seconds', '操作延迟',
                         ['operation', 'level'],
                         buckets=[0.001, 0.005, 0.01, 0.05, 0.1])

class CircuitBreaker:
    """断路器"""
    
    def __init__(self, error_threshold: float, reset_timeout: int):
        self.error_threshold = error_threshold
        self.reset_timeout = reset_timeout
        self.errors = 0
        self.total_requests = 0
        self.last_error_time = None
        self.is_open = False
        
    def record_success(self):
        self.total_requests += 1
        if self.total_requests > 100:
            self.errors = int(self.errors * 0.9)
            self.total_requests = int(self.total_requests * 0.9)
            
    def record_error(self):
        self.errors += 1
        self.total_requests += 1
        self.last_error_time = datetime.now()
        
        if self.error_rate > self.error_threshold:
            self.is_open = True
            
    @property
    def error_rate(self) -> float:
        return self.errors / max(1, self.total_requests)
        
    def can_execute(self) -> bool:
        if not self.is_open:
            return True
            
        if (datetime.now() - self.last_error_time).total_seconds() > self.reset_timeout:
            self.is_open = False
            self.errors = 0
            self.total_requests = 0
            return True
            
        return False

class CacheLevel:
    """缓存层基类"""
    
    def __init__(self, name: str, config: Dict):
        self.name = name
        self.config = config
        self.logger = logging.getLogger(f"cache.{name}")
        self.circuit_breaker = CircuitBreaker(
            error_threshold=config.get('error_threshold', 0.5),
            reset_timeout=config.get('reset_timeout', 30)
        )
        
    async def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError
        
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        raise NotImplementedError
        
    async def delete(self, key: str) -> bool:
        raise NotImplementedError
        
    async def clear(self) -> bool:
        raise NotImplementedError

class MemoryCache(CacheLevel):
    """L1内存缓存"""
    
    def __init__(self, config: Dict):
        super().__init__('L1', config)
        self.cache = OrderedDict()
        self.max_size = config.get('max_size', 1000)
        
    async def get(self, key: str) -> Optional[Any]:
        try:
            if key in self.cache:
                value = self.cache.pop(key)
                self.cache[key] = value
                return value
            return None
        except Exception as e:
            self.logger.error(f"内存缓存获取失败: {str(e)}")
            return None
            
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        try:
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
            self.cache[key] = value
            return True
        except Exception as e:
            self.logger.error(f"内存缓存设置失败: {str(e)}")
            return False

class RedisCache(CacheLevel):
    """L2 Redis缓存"""
    
    def __init__(self, config: Dict):
        super().__init__('L2', config)
        self.pool = aioredis.ConnectionPool.from_url(
            config['redis_url'],
            max_connections=config.get('max_connections', 50)
        )
        self.redis = aioredis.Redis(connection_pool=self.pool)
        
    async def get(self, key: str) -> Optional[Any]:
        if not self.circuit_breaker.can_execute():
            return None
            
        try:
            value = await self.redis.get(key)
            if value:
                self.circuit_breaker.record_success()
                return pickle.loads(zlib.decompress(value))
            return None
        except Exception as e:
            self.logger.error(f"Redis缓存获取失败: {str(e)}")
            self.circuit_breaker.record_error()
            return None

class DiskCache(CacheLevel):
    """L3磁盘缓存"""
    
    def __init__(self, config: Dict):
        super().__init__('L3', config)
        self.cache = Cache(config.get('cache_dir', 'data/cache'))
        
    async def get(self, key: str) -> Optional[Any]:
        try:
            return self.cache.get(key)
        except Exception as e:
            self.logger.error(f"磁盘缓存获取失败: {str(e)}")
            return None

class AdaptiveCache:
    """自适应缓存管理"""
    
    def __init__(self, config: Dict):
        self.total_memory = psutil.virtual_memory().total
        self.min_allocation = config.get('min_allocation', {
            'market_data': 0.3,
            'trading_data': 0.2
        })
        self.current_allocation = self.min_allocation.copy()
        
    async def rebalance(self):
        """重新平衡缓存分配"""
        try:
            current_load = psutil.cpu_percent() / 100
            memory_usage = psutil.virtual_memory().percent / 100
            
            new_allocation = {}
            for cache_type, min_alloc in self.min_allocation.items():
                if current_load < 0.5 and memory_usage < 0.7:
                    new_allocation[cache_type] = min(min_alloc * 2, 0.4)
                else:
                    new_allocation[cache_type] = min_alloc
                    
            self.current_allocation = new_allocation
            
        except Exception as e:
            logging.error(f"缓存重平衡失败: {str(e)}")

class EnhancedCacheManager:
    """增强型缓存管理器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化多级缓存
        self.cache_levels = {
            'L1': MemoryCache(config.get('L1', {})),
            'L2': RedisCache(config.get('L2', {})),
            'L3': DiskCache(config.get('L3', {}))
        }
        
        # 初始化自适应管理
        self.adaptive_cache = AdaptiveCache(config.get('adaptive', {}))
        
        # 故障转移配置
        self.failover_order = config.get('failover', {}).get('order', ['L1', 'L2', 'L3'])
        
    async def start(self):
        """启动缓存管理器"""
        self.logger.info("增强型缓存管理器已启动")
        asyncio.create_task(self._run_maintenance())
        
    async def _run_maintenance(self):
        """运行维护任务"""
        while True:
            try:
                # 重平衡缓存分配
                await self.adaptive_cache.rebalance()
                
                # 更新指标
                await self._update_metrics()
                
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"维护任务失败: {str(e)}")
                await asyncio.sleep(5)
                
    async def get(self, cache_type: str, key: str) -> Optional[Any]:
        """获取缓存项"""
        start_time = datetime.now()
        
        for level in self.failover_order:
            try:
                with CACHE_LATENCY.labels(operation='get', level=level).time():
                    value = await self.cache_levels[level].get(key)
                    if value is not None:
                        CACHE_OPS.labels(operation='hit', 
                                       cache_type=cache_type,
                                       level=level).inc()
                        return value
                    CACHE_OPS.labels(operation='miss',
                                   cache_type=cache_type,
                                   level=level).inc()
            except Exception as e:
                self.logger.error(f"{level}缓存获取失败: {str(e)}")
                
        return None
        
    async def set(self, cache_type: str, key: str, value: Any,
                  ttl: Optional[int] = None) -> bool:
        """设置缓存项"""
        success = False
        compressed_value = zlib.compress(pickle.dumps(value))
        
        for level in reversed(self.failover_order):
            try:
                with CACHE_LATENCY.labels(operation='set', level=level).time():
                    if await self.cache_levels[level].set(key, compressed_value, ttl):
                        CACHE_OPS.labels(operation='set',
                                       cache_type=cache_type,
                                       level=level).inc()
                        success = True
            except Exception as e:
                self.logger.error(f"{level}缓存设置失败: {str(e)}")
                
        return success
        
    async def _update_metrics(self):
        """更新缓存指标"""
        try:
            for level_name, level in self.cache_levels.items():
                # 更新大小指标
                size = sum(len(pickle.dumps(v)) for v in level.cache.values())
                CACHE_SIZE.labels(cache_type='total', level=level_name).set(size)
                
                # 更新项数指标
                items = len(level.cache)
                CACHE_ITEMS.labels(cache_type='total', level=level_name).set(items)
                
                # 更新命中率
                hits = CACHE_OPS.labels(operation='hit',
                                      cache_type='total',
                                      level=level_name)._value.get()
                total = hits + CACHE_OPS.labels(operation='miss',
                                              cache_type='total',
                                              level=level_name)._value.get()
                hit_ratio = hits / max(1, total)
                CACHE_HIT_RATIO.labels(cache_type='total',
                                     level=level_name).set(hit_ratio)
                
        except Exception as e:
            self.logger.error(f"更新缓存指标失败: {str(e)}")