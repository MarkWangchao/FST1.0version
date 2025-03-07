#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强版市场数据提供者

此模块提供高性能的市场数据接口，处理实时行情、K线数据、价差计算等功能。
优化特性:
- 完全异步架构与生产者-消费者模式
- 多级缓存与智能内存管理
- 高效数据结构和增量K线合成
- 智能心跳检测与自动恢复机制
- 插件化架构支持与多市场适配
- 全面的性能监控和指标埋点
"""

import asyncio
import logging
import time
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Set, Tuple, Callable, Any
from collections import defaultdict, deque
import copy
import numpy as np
import pandas as pd
try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from infrastructure.api.broker_adapter import BrokerAdapter, ConnectionState

# 常量定义
MAX_CACHE_SIZE = 10000       # 最大缓存条目数
CACHE_TTL = 300              # 缓存过期时间(秒)
HEARTBEAT_INTERVAL = 15      # 心跳检测间隔(秒)
MAX_RETRY_COUNT = 3          # 最大重试次数
DATA_FRESHNESS_THRESHOLD = 5 # 数据新鲜度阈值(秒)

class DataPlugin:
    """数据处理插件基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"fst.core.market.plugin.{name}")

    async def pre_process(self, data_type: str, data: Dict) -> Dict:
        """
        数据预处理钩子
        
        Args:
            data_type: 数据类型 ('market_data', 'kline', 'spread')
            data: 原始数据
            
        Returns:
            Dict: 处理后的数据
        """
        return data
    
    async def post_process(self, data_type: str, data: Dict) -> Dict:
        """
        数据后处理钩子
        
        Args:
            data_type: 数据类型 ('market_data', 'kline', 'spread')
            data: 处理后的数据
            
        Returns:
            Dict: 最终数据
        """
        return data

class LRUCache:
    """LRU缓存实现"""
    
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size
        self.usage_queue = deque()
        self.lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存项"""
        async with self.lock:
            if key not in self.cache:
                return None
            
            # 更新使用时间
            self.usage_queue.remove(key)
            self.usage_queue.append(key)
            
            value, _ = self.cache[key]
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存项"""
        async with self.lock:
            # 如果已存在，先移除旧的使用记录
            if key in self.cache:
                self.usage_queue.remove(key)
            
            # 检查缓存大小
            if len(self.cache) >= self.max_size:
                # 移除最久未使用的项
                oldest_key = self.usage_queue.popleft()
                del self.cache[oldest_key]
            
            # 添加新项
            expiry = None
            if ttl is not None:
                expiry = time.time() + ttl
            
            self.cache[key] = (value, expiry)
            self.usage_queue.append(key)
    
    async def remove(self, key: str) -> None:
        """移除缓存项"""
        async with self.lock:
            if key in self.cache:
                self.usage_queue.remove(key)
                del self.cache[key]
    
    async def clear(self) -> None:
        """清空缓存"""
        async with self.lock:
            self.cache.clear()
            self.usage_queue.clear()
    
    async def clean_expired(self) -> int:
        """清理过期项"""
        async with self.lock:
            now = time.time()
            expired_keys = []
            
            for key, (_, expiry) in self.cache.items():
                if expiry is not None and now > expiry:
                    expired_keys.append(key)
            
            for key in expired_keys:
                self.usage_queue.remove(key)
                del self.cache[key]
            
            return len(expired_keys)

class LatencyMonitor:
    """延迟监控器"""
    
    def __init__(self, max_history: int = 1000):
        self.history = deque(maxlen=max_history)
        self.total_count = 0
        self.sum_latency = 0
        self._lock = asyncio.Lock()
    
    async def record(self, recv_time: float) -> None:
        """
        记录延迟
        
        Args:
            recv_time: 数据接收时间戳
        """
        latency = time.time() - recv_time
        
        async with self._lock:
            self.history.append(latency)
            self.total_count += 1
            self.sum_latency += latency
    
    async def get_statistics(self) -> Dict:
        """
        获取延迟统计信息
        
        Returns:
            Dict: 延迟统计数据
        """
        async with self._lock:
            if not self.history:
                return {
                    "count": 0,
                    "min": 0,
                    "max": 0,
                    "avg": 0,
                    "p50": 0,
                    "p90": 0,
                    "p99": 0
                }
            
            hist_array = np.array(self.history)
            
            return {
                "count": self.total_count,
                "min": float(np.min(hist_array)),
                "max": float(np.max(hist_array)),
                "avg": float(np.mean(hist_array)),
                "p50": float(np.percentile(hist_array, 50)),
                "p90": float(np.percentile(hist_array, 90)),
                "p99": float(np.percentile(hist_array, 99))
            }
    
    async def reset(self) -> None:
        """重置统计数据"""
        async with self._lock:
            self.history.clear()
            self.total_count = 0
            self.sum_latency = 0

class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.metrics = defaultdict(lambda: defaultdict(int))
        self._lock = asyncio.Lock()
    
    async def increment(self, category: str, name: str, value: int = 1) -> None:
        """增加计数器"""
        async with self._lock:
            self.metrics[category][name] += value
    
    async def set(self, category: str, name: str, value: Any) -> None:
        """设置值"""
        async with self._lock:
            self.metrics[category][name] = value
    
    async def get_all(self) -> Dict:
        """获取所有指标"""
        async with self._lock:
            return copy.deepcopy(dict(self.metrics))
    
    async def get(self, category: str, name: str) -> Any:
        """获取特定指标"""
        async with self._lock:
            return self.metrics[category][name]

class PlaybackEngine:
    """历史数据回放引擎"""
    
    def __init__(self, data_source: str, speed_multiplier: float = 1.0):
        """
        初始化回放引擎
        
        Args:
            data_source: 数据源路径
            speed_multiplier: 回放速度倍数
        """
        self.data_source = data_source
        self.speed_multiplier = speed_multiplier
        self.data = None
        self.is_running = False
        self.current_index = 0
        self.callbacks = []
        self.logger = logging.getLogger("fst.core.market.playback")
    
    async def load_data(self) -> bool:
        """加载历史数据"""
        try:
            self.logger.info(f"加载历史数据: {self.data_source}")
            
            if self.data_source.endswith('.csv'):
                if POLARS_AVAILABLE:
                    self.data = pl.read_csv(self.data_source)
                else:
                    self.data = pd.read_csv(self.data_source)
            elif self.data_source.endswith('.parquet'):
                if POLARS_AVAILABLE:
                    self.data = pl.read_parquet(self.data_source)
                else:
                    self.data = pd.read_parquet(self.data_source)
            else:
                self.logger.error(f"不支持的数据源格式: {self.data_source}")
                return False
            
            # 确保数据按时间排序
            if POLARS_AVAILABLE:
                self.data = self.data.sort("timestamp")
            else:
                self.data = self.data.sort_values("timestamp")
            
            self.logger.info(f"历史数据加载完成，共 {len(self.data)} 条记录")
            return True
            
        except Exception as e:
            self.logger.error(f"加载历史数据出错: {str(e)}")
            return False
    
    async def start(self) -> None:
        """启动回放"""
        if self.data is None:
            success = await self.load_data()
            if not success:
                return
        
        self.is_running = True
        self.logger.info("开始回放历史数据")
        
        await self._playback_loop()
    
    async def stop(self) -> None:
        """停止回放"""
        self.is_running = False
        self.logger.info("停止回放历史数据")
    
    async def add_callback(self, callback: Callable) -> None:
        """添加数据回调"""
        self.callbacks.append(callback)
    
    async def _playback_loop(self) -> None:
        """回放循环"""
        start_time = time.time()
        data_start_time = self.data["timestamp"][0] if POLARS_AVAILABLE else self.data["timestamp"].iloc[0]
        
        while self.is_running and self.current_index < len(self.data):
            # 获取当前记录
            if POLARS_AVAILABLE:
                record = self.data.row(self.current_index)
                timestamp = record["timestamp"]
            else:
                record = self.data.iloc[self.current_index]
                timestamp = record["timestamp"]
            
            # 计算应该等待的时间
            target_time = start_time + (timestamp - data_start_time) / self.speed_multiplier
            now = time.time()
            
            if now < target_time:
                # 等待直到应该播放的时间
                await asyncio.sleep(target_time - now)
            
            # 发送数据到所有回调
            for callback in self.callbacks:
                if POLARS_AVAILABLE:
                    data_dict = {col: record[col] for col in self.data.columns}
                else:
                    data_dict = record.to_dict()
                await callback(data_dict)
            
            self.current_index += 1
        
        self.is_running = False
        self.logger.info("历史数据回放完成")

class DataProvider:
    """增强版市场数据提供者，负责处理和管理所有市场数据"""
    
    def __init__(self, broker_adapter: BrokerAdapter, 
                 cache_size: int = MAX_CACHE_SIZE,
                 enable_redis: bool = False,
                 redis_url: Optional[str] = None):
        """
        初始化市场数据提供者
        
        Args:
            broker_adapter: 券商适配器
            cache_size: 缓存大小
            enable_redis: 是否启用Redis二级缓存
            redis_url: Redis连接URL (如 "redis://localhost:6379/0")
        """
        self.logger = logging.getLogger("fst.core.market.data_provider")
        self.broker_adapter = broker_adapter
        
        # 缓存初始化
        self._setup_cache(cache_size, enable_redis, redis_url)
        
        # 异步锁
        self._subscription_lock = asyncio.Lock()
        
        # 行情订阅管理
        self._subscribed_symbols = set()
        self._subscription_callbacks = defaultdict(list)
        
        # 数据处理队列
        self._market_data_queue = asyncio.Queue(maxsize=10000)
        self._kline_update_queue = asyncio.Queue(maxsize=5000)
        
        # K线合成器
        self._kline_generators = {}
        
        # 价差计算器
        self._spread_calculators = {}
        self._spread_configs = {}
        
        # 数据更新事件
        self._data_update_callbacks = defaultdict(list)
        
        # 性能监控
        self._latency_monitor = LatencyMonitor()
        self._metrics = MetricsCollector()
        
        # 插件系统
        self._plugins = []
        
        # 任务管理
        self._tasks = []
        self._shutdown_event = asyncio.Event()
        
        # 心跳状态
        self._last_heartbeat = time.time()
        self._data_freshness = {}
        
        # 添加连接状态监听
        self.broker_adapter.add_connection_listener(self._on_connection_state_change)
        
        self.logger.info("增强版市场数据提供者初始化完成")
    
    async def start(self) -> None:
        """启动数据提供者"""
        self.logger.info("启动市场数据提供者")
        
        # 启动处理任务
        processor_task = asyncio.create_task(self._market_data_processor())
        self._tasks.append(processor_task)
        
        kline_processor_task = asyncio.create_task(self._kline_update_processor())
        self._tasks.append(kline_processor_task)
        
        # 启动心跳检测
        heartbeat_task = asyncio.create_task(self._heartbeat_check())
        self._tasks.append(heartbeat_task)
        
        # 启动缓存清理任务
        cache_cleaner_task = asyncio.create_task(self._cache_cleaner())
        self._tasks.append(cache_cleaner_task)
        
        # 初始化指标
        await self._metrics.set("status", "startup_time", time.time())
        await self._metrics.set("status", "state", "running")
        
        self.logger.info("市场数据提供者启动完成")
    
    async def stop(self) -> None:
        """停止数据提供者"""
        self.logger.info("停止市场数据提供者")
        
        # 设置关闭事件
        self._shutdown_event.set()
        
        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # 等待任务取消
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        
        # 断开Redis连接
        if self._redis:
            await self._redis.close()
            self._redis = None
        
        await self._metrics.set("status", "state", "stopped")
        self.logger.info("市场数据提供者已停止")
    
    async def subscribe_symbol(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        """
        订阅合约行情
        
        Args:
            symbol: 合约代码
            callback: 行情更新回调函数，接收行情数据字典
            
        Returns:
            bool: 订阅是否成功
        """
        await self._metrics.increment("subscriptions", "total_requests")
        
        async with self._subscription_lock:
            # 检查是否已订阅
            if symbol in self._subscribed_symbols:
                # 如果已订阅且提供了回调函数，则添加到回调列表
                if callback is not None and callback not in self._subscription_callbacks[symbol]:
                    self._subscription_callbacks[symbol].append(callback)
                self.logger.debug(f"合约 {symbol} 已订阅")
                return True
            
            # 添加到订阅集合
            self._subscribed_symbols.add(symbol)
            
            # 添加回调函数
            if callback is not None:
                self._subscription_callbacks[symbol].append(callback)
        
        # 执行实际订阅
        self.logger.info(f"订阅合约行情: {symbol}")
        for retry in range(MAX_RETRY_COUNT):
            try:
                success = await self.broker_adapter.subscribe_market_data([symbol])
                
                if not success:
                    self.logger.warning(f"订阅合约 {symbol} 失败，尝试重试 ({retry+1}/{MAX_RETRY_COUNT})")
                    await asyncio.sleep(1 * (retry + 1))  # 指数退避
                    continue
                
                # 立即获取一次行情数据
                market_data = await self.get_market_data(symbol)
                
                # 更新缓存
                await self._update_market_data_cache(symbol, market_data)
                
                await self._metrics.increment("subscriptions", "success")
                return True
                
            except Exception as e:
                self.logger.error(f"订阅合约 {symbol} 出错 ({retry+1}/{MAX_RETRY_COUNT}): {str(e)}")
                await asyncio.sleep(1 * (retry + 1))
        
        # 所有重试失败
        async with self._subscription_lock:
            self._subscribed_symbols.discard(symbol)
            if symbol in self._subscription_callbacks:
                del self._subscription_callbacks[symbol]
        
        await self._metrics.increment("subscriptions", "failures")
        return False
    
    async def unsubscribe_symbol(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        """
        取消订阅合约行情
        
        Args:
            symbol: 合约代码
            callback: 要移除的回调函数，None表示移除所有回调
            
        Returns:
            bool: 是否成功
        """
        async with self._subscription_lock:
            # 检查是否已订阅
            if symbol not in self._subscribed_symbols:
                self.logger.debug(f"合约 {symbol} 未订阅，无需取消")
                return True
            
            # 处理回调函数
            if callback is not None:
                # 只移除特定回调
                if symbol in self._subscription_callbacks:
                    if callback in self._subscription_callbacks[symbol]:
                        self._subscription_callbacks[symbol].remove(callback)
                    
                    # 如果还有其他回调，则保持订阅状态
                    if self._subscription_callbacks[symbol]:
                        return True
            
            # 移除所有回调
            if symbol in self._subscription_callbacks:
                del self._subscription_callbacks[symbol]
            
            # 从订阅集合中移除
            self._subscribed_symbols.discard(symbol)
        
        self.logger.info(f"取消订阅合约行情: {symbol}")
        await self._metrics.increment("subscriptions", "unsubscribe")
        return True
    
    async def get_market_data(self, symbol: str, use_cache: bool = True) -> Dict:
        """
        获取市场数据
        
        Args:
            symbol: 合约代码
            use_cache: 是否使用缓存
            
        Returns:
            Dict: 市场数据字典
        """
        await self._metrics.increment("requests", "market_data")
        start_time = time.time()
        
        # 检查缓存
        if use_cache:
            # 先检查内存缓存
            cache_key = f"market_data:{symbol}"
            cached_data = await self._lru_cache.get(cache_key)
            
            if cached_data:
                await self._metrics.increment("cache", "hits")
                await self._metrics.set("latency", "market_data_cache", (time.time() - start_time) * 1000)
                return copy.deepcopy(cached_data)
            
            # 再检查Redis缓存
            if self._redis:
                try:
                    redis_data = await self._redis.get(cache_key)
                    if redis_data:
                        market_data = json.loads(redis_data)
                        # 更新内存缓存
                        await self._lru_cache.set(cache_key, market_data, CACHE_TTL)
                        await self._metrics.increment("cache", "redis_hits")
                        await self._metrics.set("latency", "market_data_redis", (time.time() - start_time) * 1000)
                        return market_data
                except Exception as e:
                    self.logger.warning(f"Redis缓存读取失败: {str(e)}")
        
        await self._metrics.increment("cache", "misses")
        
        # 获取实时数据
        for retry in range(MAX_RETRY_COUNT):
            try:
                market_data = await self.broker_adapter.get_market_data(symbol)
                
                # 更新缓存
                await self._update_market_data_cache(symbol, market_data)
                
                # 记录延迟
                latency = (time.time() - start_time) * 1000
                await self._metrics.set("latency", "market_data_api", latency)
                await self._latency_monitor.record(start_time)
                
                return market_data
            
            except Exception as e:
                self.logger.error(f"获取合约 {symbol} 行情数据出错 ({retry+1}/{MAX_RETRY_COUNT}): {str(e)}")
                if retry < MAX_RETRY_COUNT - 1:
                    await asyncio.sleep(0.5 * (retry + 1))
        
        # 所有重试都失败，抛出异常
        raise Exception(f"获取合约 {symbol} 行情数据失败，已重试 {MAX_RETRY_COUNT} 次")
    
    async def get_klines(self, symbol: str, interval: str, count: int = 200,
                         start_time: Optional[datetime] = None, 
                         end_time: Optional[datetime] = None,
                         use_cache: bool = True) -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            interval: K线周期 ('1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w', '1M')
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            use_cache: 是否使用缓存
            
        Returns:
            pd.DataFrame: K线数据DataFrame，包含列：
                datetime, open, high, low, close, volume, open_interest
        """
        await self._metrics.increment("requests", "klines")
        start_perf = time.time()
        
        cache_key = f"klines:{symbol}_{interval}"
        
        # 检查缓存
        if use_cache:
            # 检查内存缓存
            cached_klines = await self._lru_cache.get(cache_key)
            
            if cached_klines is not None:
                # 将极化数据框转换回pandas (如果需要)
                if POLARS_AVAILABLE and isinstance(cached_klines, pl.DataFrame):
                    klines_df = cached_klines.to_pandas()
                else:
                    klines_df = cached_klines
                
                # 过滤时间范围
                if start_time:
                    klines_df = klines_df[klines_df.index >= pd.Timestamp(start_time)]
                if end_time:
                    klines_df = klines_df[klines_df.index <= pd.Timestamp(end_time)]
                
                # 如果缓存中的数据足够，直接返回
                if len(klines_df) >= count:
                    await self._metrics.increment("cache", "hits")
                    await self._metrics.set("latency", "klines_cache", (time.time() - start_perf) * 1000)
                    return klines_df.tail(count).copy()
            
            # 检查Redis缓存
            if self._redis:
                try:
                    redis_data = await self._redis.get(cache_key)
                    if redis_data:
                        # 解析JSON数据
                        klines_list = json.loads(redis_data)
                        
                        # 创建DataFrame
                        if POLARS_AVAILABLE:
                            klines_df = pl.DataFrame(klines_list)
                            # 设置日期索引
                            klines_df = klines_df.sort("datetime")
                            pd_df = klines_df.to_pandas()
                            pd_df.set_index("datetime", inplace=True)
                            pd_df.index = pd.to_datetime(pd_df.index)
                        else:
                            klines_df = pd.DataFrame(klines_list)
                            klines_df.set_index("datetime", inplace=True)
                            klines_df.index = pd.to_datetime(klines_df.index)
                            klines_df.sort_index(inplace=True)
                        
                        # 更新内存缓存
                        if POLARS_AVAILABLE:
                            await self._lru_cache.set(cache_key, klines_df, CACHE_TTL)
                        else:
                            await self._lru_cache.set(cache_key, klines_df, CACHE_TTL)
                        
                        # 过滤时间范围
                        if start_time:
                            pd_df = pd_df[pd_df.index >= pd.Timestamp(start_time)]
                        if end_time:
                            pd_df = pd_df[pd_df.index <= pd.Timestamp(end_time)]
                        
                        # 如果数据足够，直接返回
                        if len(pd_df) >= count:
                            await self._metrics.increment("cache", "redis_hits")
                            await self._metrics.set("latency", "klines_redis", (time.time() - start_perf) * 1000)
                            return pd_df.tail(count).copy()
                
                except Exception as e:
                    self.logger.warning(f"Redis缓存读取K线失败: {str(e)}")
        
        await self._metrics.increment("cache", "misses")
        
        # 检查是否为合成K线周期
        if self._is_custom_interval(interval):
            # 使用K线合成器生成自定义周期K线
            klines_df = await self._generate_custom_klines(symbol, interval, count, start_time, end_time)
        else:
            # 获取标准周期K线数据
            for retry in range(MAX_RETRY_COUNT):
                try:
                    klines = await self.broker_adapter.get_klines(
                        symbol=symbol,
                        interval=interval,
                        count=count * 2,  # 多获取一些，以便过滤和满足计数需求
                        start_time=start_time,
                        end_time=end_time
                    )
                    
                    # 验证K线数据
                    if not self._validate_klines(klines):
                        if retry < MAX_RETRY_COUNT - 1:
                            self.logger.warning(f"K线数据验证失败，重试 ({retry+1}/{MAX_RETRY_COUNT})")
                            await asyncio.sleep(0.5 * (retry + 1))
                            continue
                        else:
                            raise ValueError("K线数据验证失败")
                    
                    # 转换为DataFrame
                    if POLARS_AVAILABLE:
                        klines_df = pl.DataFrame(klines)
                        klines_df = klines_df.sort("datetime")
                        pd_df = klines_df.to_pandas()
                        pd_df.set_index("datetime", inplace=True)
                        pd_df.index = pd.to_datetime(pd_df.index)
                        
                        # 缓存极化数据框
                        await self._lru_cache.set(cache_key, klines_df, CACHE_TTL)
                        
                        # 缓存到Redis
                        if self._redis:
                            try:
                                await self._redis.set(cache_key, json.dumps(klines), ex=CACHE_TTL)
                            except Exception as e:
                                self.logger.warning(f"Redis缓存K线失败: {str(e)}")
                        
                        # 返回pandas数据框
                        klines_df = pd_df
                    else:
                        klines_df = pd.DataFrame(klines)
                        klines_df.set_index("datetime", inplace=True)
                        klines_df.index = pd.to_datetime(klines_df.index)
                        klines_df.sort_index(inplace=True)
                        
                        # 缓存数据框
                        await self._lru_cache.set(cache_key, klines_df, CACHE_TTL)
                        
                        # 缓存到Redis
                        if self._redis:
                            try:
                                await self._redis.set(cache_key, json.dumps(klines), ex=CACHE_TTL)
                            except Exception as e:
                                self.logger.warning(f"Redis缓存K线失败: {str(e)}")
                    
                    break
                    
                except Exception as e:
                    self.logger.error(f"获取合约 {symbol} K线数据出错 ({retry+1}/{MAX_RETRY_COUNT}): {str(e)}")
                    if retry < MAX_RETRY_COUNT - 1:
                        await asyncio.sleep(1 * (retry + 1))
                    else:
                        raise
        
        # 记录延迟
        latency = (time.time() - start_perf) * 1000
        await self._metrics.set("latency", "klines_api", latency)
        
        # 过滤时间范围并返回指定数量
        if start_time:
            klines_df = klines_df[klines_df.index >= pd.Timestamp(start_time)]
        if end_time:
            klines_df = klines_df[klines_df.index <= pd.Timestamp(end_time)]
        
        return klines_df.tail(count).copy()
    
    async def create_spread(self, name: str, leg1: str, leg2: str, 
                            leg1_ratio: float = 1.0, leg2_ratio: float = 1.0,
                            auto_subscribe: bool = True) -> bool:
        """
        创建价差
        
        Args:
            name: 价差名称
            leg1: 第一腿合约代码
            leg2: 第二腿合约代码
            leg1_ratio: 第一腿比例
            leg2_ratio: 第二腿比例
            auto_subscribe: 是否自动订阅腿合约
            
        Returns:
            bool: 创建是否成功
        """
        self.logger.info(f"创建价差: {name} = {leg1_ratio}*{leg1} - {leg2_ratio}*{leg2}")
        
        # 存储价差配置
        self._spread_configs[name] = {
            "leg1": leg1,
            "leg2": leg2,
            "leg1_ratio": leg1_ratio,
            "leg2_ratio": leg2_ratio,
            "created_at": datetime.now().isoformat()
        }
        
        # 自动订阅腿合约
        if auto_subscribe:
            await self.subscribe_symbol(leg1)
            await self.subscribe_symbol(leg2)
        
        # 创建价差计算器
        self._spread_calculators[name] = SpreadCalculator(name, leg1, leg2, leg1_ratio, leg2_ratio)
        
        # 初始化计算一次
        try:
            leg1_data = await self.get_market_data(leg1)
            leg2_data = await self.get_market_data(leg2)
            
            spread_data = await self._spread_calculators[name].calculate(leg1_data, leg2_data)
            
            # 缓存价差数据
            cache_key = f"spread:{name}"
            await self._lru_cache.set(cache_key, spread_data, CACHE_TTL)
            
            # 记录到Redis
            if self._redis:
                try:
                    await self._redis.set(cache_key, json.dumps(spread_data), ex=CACHE_TTL)
                except Exception as e:
                    self.logger.warning(f"Redis缓存价差失败: {str(e)}")
            
            await self._metrics.increment("spreads", "created")
            return True
            
        except Exception as e:
            self.logger.error(f"初始化价差 {name} 失败: {str(e)}")
            return False
    
    async def get_spread(self, name: str, use_cache: bool = True) -> Dict:
        """
        获取价差数据
        
        Args:
            name: 价差名称
            use_cache: 是否使用缓存
            
        Returns:
            Dict: 价差数据
        """
        await self._metrics.increment("requests", "spreads")
        start_time = time.time()
        
        # 检查价差是否存在
        if name not in self._spread_configs:
            raise ValueError(f"价差 {name} 不存在")
        
        # 检查缓存
        if use_cache:
            cache_key = f"spread:{name}"
            
            # 检查内存缓存
            cached_data = await self._lru_cache.get(cache_key)
            if cached_data:
                await self._metrics.increment("cache", "hits")
                await self._metrics.set("latency", "spread_cache", (time.time() - start_time) * 1000)
                return copy.deepcopy(cached_data)
            
            # 检查Redis缓存
            if self._redis:
                try:
                    redis_data = await self._redis.get(cache_key)
                    if redis_data:
                        spread_data = json.loads(redis_data)
                        
                        # 更新内存缓存
                        await self._lru_cache.set(cache_key, spread_data, CACHE_TTL)
                        
                        await self._metrics.increment("cache", "redis_hits")
                        await self._metrics.set("latency", "spread_redis", (time.time() - start_time) * 1000)
                        return spread_data
                except Exception as e:
                    self.logger.warning(f"Redis缓存读取价差失败: {str(e)}")
        
        await self._metrics.increment("cache", "misses")
        
        # 获取价差配置
        config = self._spread_configs[name]
        leg1 = config["leg1"]
        leg2 = config["leg2"]
        
        # 获取实时行情数据
        leg1_data = await self.get_market_data(leg1, use_cache=use_cache)
        leg2_data = await self.get_market_data(leg2, use_cache=use_cache)
        
        # 计算价差
        spread_data = await self._spread_calculators[name].calculate(leg1_data, leg2_data)
        
        # 更新缓存
        cache_key = f"spread:{name}"
        await self._lru_cache.set(cache_key, spread_data, CACHE_TTL)
        
        # 更新Redis缓存
        if self._redis:
            try:
                await self._redis.set(cache_key, json.dumps(spread_data), ex=CACHE_TTL)
            except Exception as e:
                self.logger.warning(f"Redis缓存价差失败: {str(e)}")
        
        # 记录延迟
        await self._metrics.set("latency", "spread_calc", (time.time() - start_time) * 1000)
        
        return spread_data
    
    async def get_spread_klines(self, name: str, interval: str, count: int = 200,
                               start_time: Optional[datetime] = None, 
                               end_time: Optional[datetime] = None) -> pd.DataFrame:
        """
        获取价差K线数据
        
        Args:
            name: 价差名称
            interval: K线周期
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            pd.DataFrame: 价差K线数据
        """
        await self._metrics.increment("requests", "spread_klines")
        start_perf = time.time()
        
        # 检查价差是否存在
        if name not in self._spread_configs:
            raise ValueError(f"价差 {name} 不存在")
        
        config = self._spread_configs[name]
        leg1 = config["leg1"]
        leg2 = config["leg2"]
        leg1_ratio = config["leg1_ratio"]
        leg2_ratio = config["leg2_ratio"]
        
        # 获取腿合约K线数据
        leg1_klines = await self.get_klines(
            symbol=leg1,
            interval=interval,
            count=count,
            start_time=start_time,
            end_time=end_time
        )
        
        leg2_klines = await self.get_klines(
            symbol=leg2,
            interval=interval,
            count=count,
            start_time=start_time,
            end_time=end_time
        )
        
        # 同步两个K线的时间索引
        common_index = leg1_klines.index.intersection(leg2_klines.index)
        leg1_aligned = leg1_klines.loc[common_index]
        leg2_aligned = leg2_klines.loc[common_index]
        
        # 计算价差K线
        spread_klines = pd.DataFrame(index=common_index)
        spread_klines['open'] = leg1_aligned['open'] * leg1_ratio - leg2_aligned['open'] * leg2_ratio
        spread_klines['high'] = leg1_aligned['high'] * leg1_ratio - leg2_aligned['low'] * leg2_ratio  # 最大可能的价差
        spread_klines['low'] = leg1_aligned['low'] * leg1_ratio - leg2_aligned['high'] * leg2_ratio   # 最小可能的价差
        spread_klines['close'] = leg1_aligned['close'] * leg1_ratio - leg2_aligned['close'] * leg2_ratio
        spread_klines['volume'] = np.minimum(leg1_aligned['volume'], leg2_aligned['volume'])  # 取较小的交易量
        
        # 验证结果
        spread_klines = spread_klines.dropna()
        
        # 记录延迟
        await self._metrics.set("latency", "spread_klines", (time.time() - start_perf) * 1000)
        
        return spread_klines
    
    async def _process_market_data(self, data: Dict) -> None:
        """
        处理市场数据
        
        Args:
            data: 市场数据字典
        """
        symbol = data.get('symbol')
        if not symbol:
            return
        
        # 更新市场数据缓存
        self._update_market_data_cache(symbol, data)
        
        # 添加到Tick历史
        timestamp = data.get('datetime')
        if timestamp:
            # 创建Tick数据结构
            tick = self._create_tick_record(data)
            
            # 添加到历史队列
            self._tick_history[symbol].append(tick)
            
            # 记录数据接收延迟
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp)
                    recv_time = dt.timestamp()
                    await self._latency_monitor.record(recv_time)
                except (ValueError, TypeError):
                    pass
        
        # 通知订阅者
        callbacks = self._subscription_callbacks.get(symbol, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(data))
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"执行行情回调出错: {str(e)}")
        
        # 更新价差数据
        for spread_name, calculator in self._spread_calculators.items():
            config = self._spread_configs[spread_name]
            leg1 = config["leg1"]
            leg2 = config["leg2"]
            
            # 如果当前symbol是价差的一部分，则更新价差
            if symbol in [leg1, leg2]:
                try:
                    # 获取另一条腿的数据
                    other_leg = leg2 if symbol == leg1 else leg1
                    other_data = await self.get_market_data(other_leg, use_cache=True)
                    
                    # 确保两条腿都有数据
                    if symbol == leg1:
                        leg1_data, leg2_data = data, other_data
                    else:
                        leg1_data, leg2_data = other_data, data
                    
                    # 计算价差
                    spread_data = await calculator.calculate(leg1_data, leg2_data)
                    
                    # 更新缓存
                    cache_key = f"spread:{spread_name}"
                    await self._lru_cache.set(cache_key, spread_data, CACHE_TTL)
                    
                    # 更新Redis缓存
                    if self._redis and spread_data:
                        await self._redis.set(cache_key, json.dumps(spread_data), ex=CACHE_TTL)
                    
                    # 检查异常波动熔断
                    await self._check_spread_circuit_breaker(spread_name, spread_data)
                    
                except Exception as e:
                    self.logger.error(f"更新价差 {spread_name} 出错: {str(e)}")
    
    async def _check_spread_circuit_breaker(self, name: str, data: Dict) -> None:
        """
        检查价差异常波动熔断
        
        Args:
            name: 价差名称
            data: 价差数据
        """
        # 获取价差阈值配置
        if name not in self._spread_circuit_breakers:
            return
        
        threshold = self._spread_circuit_breakers[name]
        
        # 检查是否超过阈值
        if "change_pct" in data and abs(data["change_pct"]) > threshold:
            self.logger.warning(f"价差 {name} 异常波动: {data['change_pct']:.2%}, 触发熔断")
            
            # 记录熔断事件
            await self._metrics.increment("circuit_breakers", "triggered")
            
            # 触发熔断回调
            for callback in self._circuit_breaker_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(name, data))
                    else:
                        callback(name, data)
                except Exception as e:
                    self.logger.error(f"执行熔断回调出错: {str(e)}")
    
    def _update_market_data_cache(self, symbol: str, data: Dict) -> None:
        """
        更新市场数据缓存
        
        Args:
            symbol: 合约代码
            data: 市场数据
        """
        if not data:
            return
        
        # 使用异步互斥锁保护缓存更新
        asyncio.create_task(self._async_update_cache(symbol, data))
    
    async def _async_update_cache(self, symbol: str, data: Dict) -> None:
        """异步更新缓存"""
        # 更新内存缓存
        self._market_data_cache[symbol] = copy.deepcopy(data)
        
        # 更新LRU缓存
        cache_key = f"market:{symbol}"
        await self._lru_cache.set(cache_key, data, CACHE_TTL)
        
        # 更新Redis缓存
        if self._redis:
            try:
                await self._redis.set(cache_key, json.dumps(data), ex=CACHE_TTL)
            except Exception as e:
                self.logger.warning(f"Redis缓存市场数据失败: {str(e)}")
    
    async def _heartbeat_check(self) -> None:
        """心跳检测任务"""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                
                # 检查数据新鲜度
                if not await self._check_data_freshness():
                    self.logger.warning("检测到数据不新鲜，尝试恢复...")
                    await self._recovery_data()
                
                # 清理过期缓存
                expired_count = await self._lru_cache.clean_expired()
                if expired_count > 0:
                    self.logger.debug(f"清理了 {expired_count} 个过期缓存条目")
                
                # 更新性能指标
                latency_stats = await self._latency_monitor.get_statistics()
                for key, value in latency_stats.items():
                    await self._metrics.set("latency_stats", key, value)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳检测出错: {str(e)}")
    
    async def _check_data_freshness(self) -> bool:
        """
        检查数据新鲜度
        
        Returns:
            bool: 数据是否新鲜
        """
        now = time.time()
        
        # 检查订阅的合约
        for symbol in self._subscribed_symbols:
            # 获取市场数据
            data = self._market_data_cache.get(symbol)
            if not data:
                continue
            
            # 检查时间戳
            timestamp = data.get('updated_time')
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        dt = datetime.fromisoformat(timestamp)
                        data_time = dt.timestamp()
                    else:
                        data_time = timestamp
                    
                    # 如果数据超过阈值，视为不新鲜
                    if now - data_time > DATA_FRESHNESS_THRESHOLD:
                        return False
                except (ValueError, TypeError):
                    pass
        
        return True
    
    async def _recovery_data(self) -> None:
        """恢复数据"""
        # 记录恢复事件
        await self._metrics.increment("events", "recovery_attempts")
        
        try:
            # 重新订阅所有合约
            symbols = list(self._subscribed_symbols)
            if symbols:
                success = await self.broker_adapter.subscribe_market_data(symbols)
                if success:
                    self.logger.info(f"重新订阅了 {len(symbols)} 个合约")
                    await self._metrics.increment("events", "recovery_success")
                else:
                    self.logger.error("重新订阅合约失败")
                    await self._metrics.increment("events", "recovery_failed")
        except Exception as e:
            self.logger.error(f"恢复数据出错: {str(e)}")
            await self._metrics.increment("events", "recovery_errors")
    
    async def _generate_custom_klines(self, symbol: str, interval: str, count: int,
                                     start_time: Optional[datetime] = None, 
                                     end_time: Optional[datetime] = None) -> pd.DataFrame:
        """
        生成自定义周期K线
        
        Args:
            symbol: 合约代码
            interval: 自定义K线周期
            count: 数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            pd.DataFrame: 合成的K线数据
        """
        cache_key = f"kline:{symbol}:{interval}"
        
        # 检查是否已有K线合成器
        if cache_key not in self._kline_generators:
            # 创建新的K线合成器
            self._kline_generators[cache_key] = KlineGenerator(interval)
            
            # 获取基础K线数据来初始化合成器
            base_interval, multiplier = self._parse_custom_interval(interval)
            base_count = count * multiplier * 2  # 获取更多基础K线，以确保生成足够的合成K线
            
            # 获取基础K线
            base_klines = await self.get_klines(
                symbol=symbol,
                interval=base_interval,
                count=base_count,
                start_time=start_time,
                end_time=end_time
            )
            
            # 初始化合成器
            await self._kline_generators[cache_key].init(base_klines)
        else:
            # 获取最新的基础K线数据进行增量更新
            base_interval, _ = self._parse_custom_interval(interval)
            
            # 获取上次更新后的基础K线
            last_update = self._kline_generators[cache_key].last_update
            if last_update:
                # 获取自上次更新以来的新K线
                new_klines = await self.get_klines(
                    symbol=symbol,
                    interval=base_interval,
                    count=100,  # 获取最近的100条，应该足够覆盖更新
                    start_time=last_update
                )
                
                # 增量更新合成器
                if len(new_klines) > 0:
                    await self._kline_generators[cache_key].update(new_klines)
        
        # 获取合成的K线
        klines_df = await self._kline_generators[cache_key].get_klines()
        
        # 过滤时间范围
        if start_time:
            klines_df = klines_df[klines_df.index >= pd.Timestamp(start_time)]
        if end_time:
            klines_df = klines_df[klines_df.index <= pd.Timestamp(end_time)]
        
        # 返回指定数量的K线
        return klines_df.tail(count).copy()
    
    def _parse_custom_interval(self, interval: str) -> Tuple[str, int]:
        """
        解析自定义K线周期
        
        Args:
            interval: 自定义K线周期 (如 '3m', '45m', '6h')
            
        Returns:
            Tuple[str, int]: 基础周期和倍数
        """
        # 提取数字和单位
        import re
        match = re.match(r'(\d+)([mhdwM])', interval)
        if not match:
            raise ValueError(f"无效的K线周期格式: {interval}")
        
        multiplier = int(match.group(1))
        unit = match.group(2)
        
        # 确定基础周期
        if unit == 'm':
            if multiplier < 5:
                return '1m', multiplier
            elif multiplier < 15:
                return '5m', multiplier // 5
            elif multiplier < 30:
                return '15m', multiplier // 15
            else:
                return '30m', multiplier // 30
        elif unit == 'h':
            if multiplier < 2:
                return '1h', multiplier
            elif multiplier < 4:
                return '2h', multiplier // 2
            else:
                return '4h', multiplier // 4
        elif unit == 'd':
            return '1d', multiplier
        elif unit == 'w':
            return '1w', multiplier
        elif unit == 'M':
            return '1M', multiplier
        else:
            raise ValueError(f"不支持的K线周期单位: {unit}")
    
    def _is_custom_interval(self, interval: str) -> bool:
        """
        判断是否为自定义K线周期
        
        Args:
            interval: K线周期
            
        Returns:
            bool: 是否为自定义周期
        """
        # 标准周期列表
        standard_intervals = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w', '1M']
        return interval not in standard_intervals
    
    def _create_tick_record(self, market_data: Dict) -> Dict:
        """
        创建Tick记录
        
        Args:
            market_data: 市场数据
            
        Returns:
            Dict: Tick记录
        """
        # 提取关键字段，减少内存占用
        return {
            'timestamp': market_data.get('datetime', datetime.now().isoformat()),
            'last_price': market_data.get('last_price', 0),
            'volume': market_data.get('volume', 0),
            'ask_price1': market_data.get('ask_price1', 0),
            'ask_volume1': market_data.get('ask_volume1', 0),
            'bid_price1': market_data.get('bid_price1', 0),
            'bid_volume1': market_data.get('bid_volume1', 0)
        }
    
    def _validate_klines(self, klines: List[Dict]) -> bool:
        """
        验证K线数据
        
        Args:
            klines: K线数据列表
            
        Returns:
            bool: 数据是否有效
        """
        if not klines:
            return False
        
        # 基本验证
        for kline in klines:
            # 检查必要字段
            required_fields = ['datetime', 'open', 'high', 'low', 'close', 'volume']
            if not all(field in kline for field in required_fields):
                return False
            
            # 检查数据逻辑
            if (kline['high'] < kline['low'] or
                kline['open'] > kline['high'] or
                kline['open'] < kline['low'] or
                kline['close'] > kline['high'] or
                kline['close'] < kline['low']):
                
                self.logger.warning(f"异常K线数据: {kline}")
                return False
        
        return True
    
    async def _on_connection_state_change(self, old_state: ConnectionState, new_state: ConnectionState) -> None:
        """
        连接状态变化处理
        
        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        self.logger.info(f"连接状态变化: {old_state} -> {new_state}")
        
        # 如果连接恢复，重新订阅所有合约
        if new_state == ConnectionState.CONNECTED and old_state != ConnectionState.CONNECTED:
            self.logger.info("连接恢复，重新订阅合约")
            
            # 延迟执行，确保连接稳定
            await asyncio.sleep(1)
            
            # 重新订阅所有合约
            symbols = list(self._subscribed_symbols)
            if symbols:
                try:
                    await self.broker_adapter.subscribe_market_data(symbols)
                    self.logger.info(f"重新订阅了 {len(symbols)} 个合约")
                except Exception as e:
                    self.logger.error(f"重新订阅合约出错: {str(e)}")
    
    async def get_statistics(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        stats = {
            "subscribed_symbols": len(self._subscribed_symbols),
            "cached_market_data": len(self._market_data_cache),
            "cache_entries": len(self._lru_cache.cache),
            "kline_generators": len(self._kline_generators),
            "spread_configs": len(self._spread_configs),
            "metrics": {}
        }
        
        # 获取延迟统计
        latency_stats = await self._latency_monitor.get_statistics()
        stats["latency"] = latency_stats
        
        # 获取指标数据
        for category, metrics in self._metrics.metrics.items():
            stats["metrics"][category] = copy.deepcopy(metrics)
        
        return stats


class SpreadCalculator:
    """价差计算器"""
    
    def __init__(self, name: str, leg1: str, leg2: str, leg1_ratio: float = 1.0, leg2_ratio: float = 1.0):
        """
        初始化价差计算器
        
        Args:
            name: 价差名称
            leg1: 第一腿合约代码
            leg2: 第二腿合约代码
            leg1_ratio: 第一腿比例
            leg2_ratio: 第二腿比例
        """
        self.name = name
        self.leg1 = leg1
        self.leg2 = leg2
        self.leg1_ratio = leg1_ratio
        self.leg2_ratio = leg2_ratio
        self.logger = logging.getLogger(f"fst.core.market.spread_calculator.{name}")
        
        # 历史价差数据
        self.last_spread = None
    
    async def calculate(self, leg1_data: Dict, leg2_data: Dict) -> Dict:
        """
        计算价差
        
        Args:
            leg1_data: 第一腿行情数据
            leg2_data: 第二腿行情数据
            
        Returns:
            Dict: 价差数据
        """
        # 检查数据有效性
        if not leg1_data or not leg2_data:
            return {}
        
        # 获取价格
        leg1_price = leg1_data.get('last_price', 0)
        leg2_price = leg2_data.get('last_price', 0)
        
        if leg1_price <= 0 or leg2_price <= 0:
            return {}
        
        # 计算价差
        spread_value = leg1_price * self.leg1_ratio - leg2_price * self.leg2_ratio
        
        # 计算价差百分比
        leg1_value = leg1_price * self.leg1_ratio
        leg2_value = leg2_price * self.leg2_ratio
        spread_pct = spread_value / ((leg1_value + leg2_value) / 2)
        
        # 计算变化率
        change_pct = 0
        if self.last_spread:
            change_pct = (spread_value - self.last_spread) / abs(self.last_spread) if self.last_spread != 0 else 0
        
        # 更新历史数据
        self.last_spread = spread_value
        
        # 构建价差数据
        return {
            "name": self.name,
            "value": spread_value,
            "percent": spread_pct,
            "change_pct": change_pct,
            "leg1": {
                "symbol": self.leg1,
                "price": leg1_price,
                "ratio": self.leg1_ratio,
                "value": leg1_value
            },
            "leg2": {
                "symbol": self.leg2,
                "price": leg2_price,
                "ratio": self.leg2_ratio,
                "value": leg2_value
            },
            "updated_time": datetime.now().isoformat()
        }


class KlineGenerator:
    """K线合成器，用于生成自定义周期的K线"""
    
    def __init__(self, target_interval: str):
        """
        初始化K线合成器
        
        Args:
            target_interval: 目标K线周期
        """
        self.target_interval = target_interval
        self.logger = logging.getLogger("fst.core.market.kline_generator")
        
        # K线数据
        self.klines = pd.DataFrame()
        self.custom_klines = pd.DataFrame()
        
        # 最后更新时间
        self.last_update = None
        
        # 解析目标周期
        import re
        match = re.match(r'(\d+)([mhdwM])', target_interval)
        if not match:
            raise ValueError(f"无效的K线周期格式: {target_interval}")
        
        self.multiplier = int(match.group(1))
        self.unit = match.group(2)
        
        # 设置重采样规则
        self.resample_rule = self._get_resample_rule()
        
        self.logger.info(f"创建K线合成器: {target_interval}")
    
    async def init(self, klines: pd.DataFrame) -> None:
        """
        初始化K线数据
        
        Args:
            klines: 基础K线数据
        """
        if len(klines) == 0:
            return
        
        self.klines = klines.copy()
        await self._generate_custom_klines()
        self.last_update = datetime.now()
    
    async def update(self, new_klines: pd.DataFrame) -> None:
        """
        更新K线数据
        
        Args:
            new_klines: 新的K线数据
        """
        if len(new_klines) == 0:
            return
        
        # 合并新K线
        self.klines = pd.concat([self.klines, new_klines])
        self.klines = self.klines[~self.klines.index.duplicated(keep='last')]
        self.klines.sort_index(inplace=True)
        
        # 重新生成自定义K线
        await self._generate_custom_klines()
        self.last_update = datetime.now()
    
    async def get_klines(self) -> pd.DataFrame:
        """
        获取合成的K线数据
        
        Returns:
            pd.DataFrame: K线数据
        """
        return self.custom_klines
    
    async def _generate_custom_klines(self) -> None:
        """生成自定义周期K线"""
        if len(self.klines) == 0:
            return
        
        # 使用重采样生成新K线
        resampled = self.klines.resample(self.resample_rule)
        
        # 聚合函数
        custom_klines = pd.DataFrame({
            'open': resampled['open'].first(),
            'high': resampled['high'].max(),
            'low': resampled['low'].min(),
            'close': resampled['close'].last(),
            'volume': resampled['volume'].sum()
        })
        
        if 'open_interest' in self.klines.columns:
            custom_klines['open_interest'] = resampled['open_interest'].last()
        
        # 过滤掉包含NaN值的行
        self.custom_klines = custom_klines.dropna()
    
    def _get_resample_rule(self) -> str:
        """
        获取重采样规则
        
        Returns:
            str: pandas重采样规则
        """
        if self.unit == 'm':
            return f"{self.multiplier}T"  # 分钟
        elif self.unit == 'h':
            return f"{self.multiplier}H"  # 小时
        elif self.unit == 'd':
            return f"{self.multiplier}D"  # 天
        elif self.unit == 'w':
            return f"{self.multiplier}W"  # 周
        elif self.unit == 'M':
            return f"{self.multiplier}M"  # 月
        else:
            raise ValueError(f"不支持的K线周期单位: {self.unit}")