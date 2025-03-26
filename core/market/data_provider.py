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
import os
from core.event.event_bus import EventBus, Event, EventType
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Set, Tuple, Callable, Any
from collections import defaultdict, deque
from functools import lru_cache
import copy
import numpy as np
import pandas as pd

# 使用uvloop提升异步性能
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False

try:
    from tqsdk import TqApi, TqAuth, TqAccount, TqSim, TqReplay
    HAS_TQSDK = True
except ImportError:
    HAS_TQSDK = False

# 导入基础设施
from infrastructure.api.broker_adapter import BrokerAdapter, ConnectionState

# 导入事件总线
from core.event.event_bus import EventBus, Event, EventType

# 连接池实现
class ConnectionPool:
    """异步连接池实现"""
    
    def __init__(self, maxsize=5, timeout=30, recycle=3600):
        """
        初始化连接池
        
        Args:
            maxsize: 最大连接数
            timeout: 获取连接超时时间(秒)
            recycle: 连接回收时间(秒)
        """
        self.maxsize = maxsize
        self.timeout = timeout
        self.recycle = recycle
        self._connections = []
        self._used = set()
        self._acquiring = 0
        self._cond = asyncio.Condition()
        self._closed = False
        
    async def acquire(self):
        """
        获取一个连接
        
        Returns:
            连接对象
        """
        async with self._cond:
            while True:
                # 检查已有空闲连接
                for i, conn in enumerate(self._connections):
                    if conn not in self._used and not self._should_recycle(conn):
                        self._used.add(conn)
                        return _PoolConnectionContext(self, conn)
                
                # 检查是否可以创建新连接
                if len(self._connections) < self.maxsize:
                    conn = await self._create_new_connection()
                    self._connections.append(conn)
                    self._used.add(conn)
                    return _PoolConnectionContext(self, conn)
                
                # 等待连接释放
                try:
                    await asyncio.wait_for(self._cond.wait(), self.timeout)
                except asyncio.TimeoutError:
                    raise TimeoutError("获取连接超时")
    
    async def release(self, conn):
        """
        释放连接回连接池
        
        Args:
            conn: 连接对象
        """
        async with self._cond:
            if conn in self._used:
                self._used.remove(conn)
                # 更新连接最后使用时间
                conn._last_used = time.time()
                self._cond.notify()
    
    async def close(self):
        """关闭所有连接"""
        async with self._cond:
            self._closed = True
            for conn in self._connections:
                await self._close_connection(conn)
            self._connections.clear()
            self._used.clear()
    
    async def _create_new_connection(self):
        """创建新连接"""
        conn = _PoolConnection()
        conn._last_used = time.time()
        return conn
    
    async def _close_connection(self, conn):
        """关闭连接"""
        if hasattr(conn, 'close') and callable(conn.close):
            await conn.close()
    
    def _should_recycle(self, conn):
        """检查连接是否应该回收"""
        return (time.time() - conn._last_used) > self.recycle


class _PoolConnection:
    """连接池管理的连接对象"""
    
    def __init__(self):
        self._last_used = time.time()
        self._api = None
    
    async def create_api(self):
        """创建API对象"""
        if not HAS_TQSDK:
            raise ImportError("未安装天勤SDK")
        
        if self._api is None:
            self._api = TqApi(TqSim())
        
        return self._api
    
    async def close(self):
        """关闭连接"""
        if self._api:
            await self._api.close()
            self._api = None


class _PoolConnectionContext:
    """连接池连接上下文管理器"""
    
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
    
    async def __aenter__(self):
        return self._conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._pool.release(self._conn)


# 熔断器实现
class CircuitBreaker:
    """数据源熔断器，保护系统免受频繁失败的影响"""
    
    def __init__(self, failure_threshold=5, recovery_timeout=30, half_open_timeout=5):
        """
        初始化熔断器
        
        Args:
            failure_threshold: 触发熔断的连续失败次数
            recovery_timeout: 从熔断状态恢复的超时时间(秒)
            half_open_timeout: 半开状态测试超时时间(秒)
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_timeout = half_open_timeout
        
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    def record_success(self):
        """记录成功操作"""
        self.failure_count = 0
        if self.state != "closed":
            self.state = "closed"
    
    def record_failure(self):
        """记录失败操作"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        # 检查是否超过阈值
        if self.state == "closed" and self.failure_count >= self.failure_threshold:
            self.state = "open"
    
    def allow_request(self):
        """
        检查是否允许请求
        
        Returns:
            bool: 是否允许请求
        """
        if self.state == "closed":
            return True
        
        current_time = time.time()
        
        if self.state == "open":
            # 检查是否达到恢复超时时间
            if current_time - self.last_failure_time >= self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        
        if self.state == "half-open":
            # 半开状态下，仅允许少量请求通过进行测试
            if current_time - self.last_failure_time >= self.half_open_timeout:
                return True
            return False
        
        return True
    
    def get_state(self):
        """获取熔断器状态"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "elapsed_since_last_failure": time.time() - self.last_failure_time if self.last_failure_time > 0 else None
        }


# 数据质量检测器
class DataQualityChecker:
    """数据质量检测器，用于检测异常行情数据"""
    
    def __init__(self, event_bus=None):
        """
        初始化数据质量检测器
        
        Args:
            event_bus: 事件总线，用于发布异常事件
        """
        self.logger = logging.getLogger("fst.core.market.data_quality")
        self.event_bus = event_bus
        
        # 历史数据缓存，用于检测异常
        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=100))
        self.volatility_history = defaultdict(lambda: deque(maxlen=20))
        
        # 最后触发异常时间，防止频繁触发
        self.last_alert_time = defaultdict(lambda: {})
        
        # 价格跳空阈值，百分比
        self.price_gap_threshold = 0.05  # 5%
        # 成交量剧增阈值，倍数
        self.volume_spike_threshold = 10  # 10倍
        # 波动率异常阈值，标准差倍数
        self.volatility_threshold = 3  # 3倍标准差
        # 重复行情次数阈值
        self.duplicate_threshold = 5  # 连续5次完全相同
        
        # 最小告警间隔，秒
        self.min_alert_interval = 60
    
    def check_market_data(self, symbol, data):
        """
        检查市场数据质量
        
        Args:
            symbol: 合约代码
            data: 市场数据
            
        Returns:
            bool: 数据是否正常
        """
        issues = []
        
        # 获取关键数据
        last_price = data.get("last_price")
        if last_price is None:
            return True  # 无法检查
        
        volume = data.get("volume", 0)
        timestamp = data.get("datetime")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now()
        
        # 检查价格异常
        if self.price_history[symbol]:
            last_prices = list(self.price_history[symbol])
            avg_price = sum(last_prices) / len(last_prices)
            
            # 检查价格跳空
            if abs(last_price - avg_price) / avg_price > self.price_gap_threshold:
                # 避免频繁触发
                last_alert = self.last_alert_time[symbol].get('price_gap', 0)
                if time.time() - last_alert > self.min_alert_interval:
                    self.last_alert_time[symbol]['price_gap'] = time.time()
                    issues.append({
                        "type": "price_gap",
                        "value": last_price,
                        "avg": avg_price,
                        "deviation": (last_price - avg_price) / avg_price
                    })
        
        # 检查成交量异常
        if self.volume_history[symbol]:
            last_volumes = list(self.volume_history[symbol])
            avg_volume = sum(last_volumes) / len(last_volumes)
            
            # 检查成交量剧增
            if avg_volume > 0 and volume / avg_volume > self.volume_spike_threshold:
                last_alert = self.last_alert_time[symbol].get('volume_spike', 0)
                if time.time() - last_alert > self.min_alert_interval:
                    self.last_alert_time[symbol]['volume_spike'] = time.time()
                    issues.append({
                        "type": "volume_spike",
                        "value": volume,
                        "avg": avg_volume,
                        "times": volume / avg_volume
                    })
        
        # 更新历史数据
        self.price_history[symbol].append(last_price)
        self.volume_history[symbol].append(volume)
        
        # 如果检测到问题，记录并发送事件
        if issues and self.event_bus:
            issue_data = {
                "symbol": symbol,
                "timestamp": timestamp,
                "issues": issues,
                "data": {
                    "last_price": last_price,
                    "volume": volume
                }
            }
            
            self.logger.warning(f"检测到异常数据: {json.dumps(issue_data, default=str)}")
            
            # 发送事件
            try:
                asyncio.create_task(self.event_bus.publish(Event(
                    event_type=EventType.DATA_ABNORMAL,
                    data=issue_data
                )))
            except Exception as e:
                self.logger.error(f"发布数据异常事件失败: {e}")
        
        return len(issues) == 0
    
    def check_klines(self, symbol, interval, klines):
        """
        检查K线数据质量
        
        Args:
            symbol: 合约代码
            interval: K线周期
            klines: K线数据
            
        Returns:
            bool: 数据是否正常
        """
        if len(klines) < 3:
            return True  # 数据不足，无法检查
        
        issues = []
        key = f"{symbol}_{interval}"
        
        # 检查K线连续性
        previous_time = None
        expected_time_diff = self._convert_interval_to_seconds(interval)
        
        for i, kline in enumerate(klines):
            if i == 0:
                continue
                
            current_time = kline.get('datetime')
            if isinstance(current_time, str):
                try:
                    current_time = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
                except:
                    continue
            
            previous_time = klines[i-1].get('datetime')
            if isinstance(previous_time, str):
                try:
                    previous_time = datetime.fromisoformat(previous_time.replace('Z', '+00:00'))
                except:
                    continue
            
            if previous_time and current_time:
                time_diff = (current_time - previous_time).total_seconds()
                
                # 检查时间间隔是否异常
                if abs(time_diff - expected_time_diff) > expected_time_diff * 0.1:  # 允许10%误差
                    last_alert = self.last_alert_time[key].get('kline_gap', 0)
                    if time.time() - last_alert > self.min_alert_interval:
                        self.last_alert_time[key]['kline_gap'] = time.time()
                        issues.append({
                            "type": "kline_gap",
                            "expected_diff": expected_time_diff,
                            "actual_diff": time_diff,
                            "index": i
                        })
        
        # 检查异常波动
        returns = []
        for i in range(1, len(klines)):
            prev_close = klines[i-1].get('close')
            curr_close = klines[i].get('close')
            
            if prev_close and curr_close and prev_close > 0:
                returns.append((curr_close - prev_close) / prev_close)
        
        if returns:
            self.volatility_history[key].append(np.std(returns))
            
            if len(self.volatility_history[key]) >= 5:
                avg_volatility = sum(self.volatility_history[key]) / len(self.volatility_history[key])
                current_volatility = np.std(returns)
                
                if current_volatility > avg_volatility * self.volatility_threshold:
                    last_alert = self.last_alert_time[key].get('volatility_spike', 0)
                    if time.time() - last_alert > self.min_alert_interval:
                        self.last_alert_time[key]['volatility_spike'] = time.time()
                        issues.append({
                            "type": "volatility_spike",
                            "value": current_volatility,
                            "avg": avg_volatility,
                            "times": current_volatility / avg_volatility
                        })
        
        # 发送事件
        if issues and self.event_bus:
            issue_data = {
                "symbol": symbol,
                "interval": interval,
                "issues": issues
            }
            
            self.logger.warning(f"检测到K线异常: {json.dumps(issue_data, default=str)}")
            
            # 发送事件
            try:
                asyncio.create_task(self.event_bus.publish(Event(
                    event_type=EventType.DATA_ABNORMAL,
                    data=issue_data
                )))
            except Exception as e:
                self.logger.error(f"发布K线异常事件失败: {e}")
        
        return len(issues) == 0
    
    def _convert_interval_to_seconds(self, interval):
        """
        将K线周期转换为秒数
        
        Args:
            interval: K线周期字符串
            
        Returns:
            int: 周期秒数
        """
        if interval == '1m':
            return 60
        elif interval == '5m':
            return 300
        elif interval == '15m':
            return 900
        elif interval == '30m':
            return 1800
        elif interval == '1h':
            return 3600
        elif interval == '2h':
            return 7200
        elif interval == '4h':
            return 14400
        elif interval == '1d':
            return 86400
        elif interval == '1w':
            return 604800
        elif interval == '1M':
            return 2592000
        
        # 尝试解析自定义格式
        import re
        match = re.match(r'(\d+)([mhdwM])', interval)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            
            if unit == 'm':
                return value * 60
            elif unit == 'h':
                return value * 3600
            elif unit == 'd':
                return value * 86400
            elif unit == 'w':
                return value * 604800
            elif unit == 'M':
                return value * 2592000
        
        # 默认返回1分钟
        return 60


class DataProviderStats:
    """数据提供者性能统计"""
    
    def __init__(self):
        """初始化性能统计"""
        # 请求统计
        self.requests = 0
        self.errors = 0
        self.cache_hits = 0
        self.cache_misses = 0
        
        # 数据统计
        self.symbols_tracked = set()
        self.kline_requests = defaultdict(int)
        self.market_data_requests = defaultdict(int)
        
        # 延迟统计
        self.latency_samples = deque(maxlen=1000)
        
        # 启动时间
        self.start_time = time.time()
    
    def record_request(self, request_type, symbol=None, success=True):
        """记录请求"""
        self.requests += 1
        
        if not success:
            self.errors += 1
        
        if symbol:
            self.symbols_tracked.add(symbol)
            
            if request_type == 'market_data':
                self.market_data_requests[symbol] += 1
            elif request_type.startswith('kline_'):
                interval = request_type.split('_')[1]
                self.kline_requests[(symbol, interval)] += 1
    
    def record_cache(self, hit):
        """记录缓存命中情况"""
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
    
    def record_latency(self, latency_ms):
        """记录延迟"""
        self.latency_samples.append(latency_ms)
    
    def get_stats(self):
        """获取统计信息"""
        uptime = time.time() - self.start_time
        requests_per_second = self.requests / uptime if uptime > 0 else 0
        error_rate = self.errors / self.requests if self.requests > 0 else 0
        cache_hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0
        
        # 延迟统计
        latency_stats = {}
        if self.latency_samples:
            samples = np.array(self.latency_samples)
            latency_stats = {
                "avg": np.mean(samples),
                "p50": np.percentile(samples, 50),
                "p95": np.percentile(samples, 95),
                "p99": np.percentile(samples, 99),
                "max": np.max(samples),
                "min": np.min(samples)
            }
        
        # 获取热门请求
        top_symbols = sorted(
            [(s, self.market_data_requests[s]) for s in self.symbols_tracked],
            key=lambda x: x[1], reverse=True
        )[:10]
        
        top_klines = sorted(
            [((s, i), self.kline_requests[(s, i)]) for s, i in self.kline_requests],
            key=lambda x: x[1], reverse=True
        )[:10]
        
        return {
            "uptime": uptime,
            "requests": self.requests,
            "errors": self.errors,
            "error_rate": error_rate,
            "requests_per_second": requests_per_second,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": cache_hit_rate,
            "symbols_tracked": len(self.symbols_tracked),
            "latency": latency_stats,
            "top_symbols": top_symbols,
            "top_kline_requests": top_klines
        }


class TqsdkDataSource:
    """天勤SDK数据源实现"""
    
    # 定义连接池
    _CONNECTION_POOL = ConnectionPool(
        maxsize=5,   # 最大连接数
        timeout=30,  # 超时时间
        recycle=3600 # 连接回收时间
    )
    
    def __init__(self, config=None, event_bus=None):
        """
        初始化天勤SDK数据源
        
        Args:
            config: 配置参数
            event_bus: 事件总线
        """
        self.logger = logging.getLogger("fst.core.market.tqsdk")
        self.config = config or {}
        self.event_bus = event_bus
        
        # API实例
        self.api = None
        self.running = False
        
        # 熔断器
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            half_open_timeout=10
        )
        
        # 订阅管理
        self.subscribed_symbols = set()
        self.kline_serials = {}
        
        # 数据质量检测
        self.data_quality_checker = DataQualityChecker(event_bus)
        
        # 延迟监控
        self.latency_stats = defaultdict(list)
        
        # 账户同步任务
        self.account_sync_task = None
    
    async def connect(self) -> bool:
        """
        连接数据源
        
        Returns:
            bool: 是否成功
        """
        try:
            async with TqsdkDataSource._CONNECTION_POOL.acquire() as conn:
                self.api = await conn.create_api()
                self.running = True
                
                # 启动处理任务
                asyncio.create_task(self._process_api_updates())
                
                # 启动账户同步任务
                if self.config.get("sync_account", True):
                    self.account_sync_task = asyncio.create_task(self._sync_account_status())
                
                self.logger.info("天勤数据源连接成功")
                
                # 记录熔断器成功
                self.circuit_breaker.record_success()
                
                return True
                
        except Exception as e:
            self.logger.error(f"天勤数据源连接失败: {str(e)}")
            
            # 记录熔断器失败
            self.circuit_breaker.record_failure()
            
            return False
    
    async def disconnect(self) -> None:
        """断开连接"""
        self.running = False
        
        # 取消账户同步任务
        if self.account_sync_task and not self.account_sync_task.done():
            self.account_sync_task.cancel()
            try:
                await self.account_sync_task
            except asyncio.CancelledError:
                pass
        
        # 关闭API
        if self.api:
            try:
                await self.api.close()
            except:
                pass
            self.api = None
        
        self.logger.info("天勤数据源已断开连接")
    
    async def _process_api_updates(self) -> None:
        """处理API更新数据"""
        try:
            while self.running and self.api:
                # 批量获取更新合约
                updated_symbols = self._get_updated_quotes()
                
                if updated_symbols:
                    # 批量处理更新的合约
                    batch_data = {}
                    for symbol in updated_symbols:
                        if symbol in self.subscribed_symbols:
                            batch_data[symbol] = self.api.get_quote(symbol)
                    
                    # 批量处理行情数据
                    if batch_data:
                        await self._batch_handle_ticks(batch_data)
                
                # 等待API更新
                await self.api.wait_update()
                
        except asyncio.CancelledError:
            self.logger.info("数据处理任务已取消")
        except Exception as e:
            self.logger.error(f"处理API更新出错: {str(e)}")
            self.circuit_breaker.record_failure()
    
    def _get_updated_quotes(self) -> List[str]:
        """
        获取已更新的合约行情
        
        Returns:
            List[str]: 已更新的合约列表
        """
        # 这个方法需要根据天勤SDK的实际API实现
        # 此处为示例实现
        updated = []
        
        for symbol in self.subscribed_symbols:
            try:
                # 检查是否有更新
                if self.api and self.api.is_changing(self.api.get_quote(symbol)):
                    updated.append(symbol)
            except:
                pass
        
        return updated
    
    async def _batch_handle_ticks(self, batch_data: Dict[str, Any]) -> None:
        """
        批量处理行情数据
        
        Args:
            batch_data: 批量行情数据 {symbol: quote_data}
        """
        for symbol, quote in batch_data.items():
            try:
                # 记录数据接收时间
                recv_time = time.time()
                
                # 转换为标准格式
                market_data = self._convert_quote_to_market_data(quote)
                
                # 记录行情延迟
                self._record_latency(symbol, recv_time, market_data)
                
                # 检查数据质量
                if not self.data_quality_checker.check_market_data(symbol, market_data):
                    self.logger.warning(f"合约 {symbol} 数据质量异常")
                
                # 发布市场数据更新事件
                if self.event_bus:
                    await self.event_bus.publish(Event(
                        event_type=EventType.MARKET_DATA_UPDATE,
                        data={
                            "symbol": symbol,
                            "data": market_data
                        }
                    ))
                
            except Exception as e:
                self.logger.error(f"处理合约 {symbol} 行情数据出错: {str(e)}")
    
    def _convert_quote_to_market_data(self, quote) -> Dict[str, Any]:
        """
        将天勤行情数据转换为标准格式
        
        Args:
            quote: 天勤行情数据
            
        Returns:
            Dict: 标准格式市场数据
        """
        return {
            "symbol": quote.instrument_id,
            "exchange": quote.exchange_id,
            "datetime": datetime.fromtimestamp(quote.datetime / 1e9).isoformat(),
            "last_price": quote.last_price,
            "open": quote.open,
            "high": quote.high,
            "low": quote.low,
            "close": quote.close or quote.last_price,
            "volume": quote.volume,
            "amount": quote.amount,
            "open_interest": quote.open_interest,
            "bid_price1": quote.bid_price1,
            "bid_volume1": quote.bid_volume1,
            "ask_price1": quote.ask_price1,
            "ask_volume1": quote.ask_volume1,
            "limit_up": quote.upper_limit,
            "limit_down": quote.lower_limit,
            "pre_close": quote.pre_close,
            "pre_settlement": quote.pre_settlement,
            "update_time": time.time()
        }
    
    def _record_latency(self, symbol: str, recv_time: float, market_data: Dict[str, Any]) -> None:
        """
        记录行情延迟
        
        Args:
            symbol: 合约代码
            recv_time: 接收时间戳
            market_data: 市场数据
        """
        try:
            # 获取行情时间
            data_time = market_data.get("datetime")
            if isinstance(data_time, str):
                data_time = datetime.fromisoformat(data_time.replace('Z', '+00:00')).timestamp()
            
            # 计算延迟(毫秒)
            latency_ms = (recv_time - data_time) * 1000
            
            # 记录延迟
            self.latency_stats[symbol].append(latency_ms)
            if len(self.latency_stats[symbol]) > 1000:
                self.latency_stats[symbol] = self.latency_stats[symbol][-1000:]
            
            # 如果延迟异常，记录日志
            if latency_ms > 1000:  # 1秒以上算异常
                self.logger.warning(f"合约 {symbol} 行情延迟较高: {latency_ms:.2f}ms")
                
        except Exception as e:
            pass  # 忽略延迟计算错误
    
    async def _sync_account_status(self) -> None:
        """同步账户状态任务"""
        while self.running and self.api:
            try:
                # 获取账户信息
                account = self.api.get_account()
                
                # 转换为标准格式
                account_data = {
                    "balance": account.balance,
                    "available": account.available,
                    "margin": account.margin,
                    "frozen": account.frozen_margin,
                    "commission": account.commission,
                    "risk_ratio": account.risk_ratio,
                    "update_time": time.time()
                }
                
                # 发布账户更新事件
                if self.event_bus:
                    await self.event_bus.publish(Event(
                        event_type=EventType.ACCOUNT_UPDATE,
                        data=account_data
                    ))
                
                # 每5秒同步一次
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"同步账户状态出错: {str(e)}")
                await asyncio.sleep(5)  # 出错后等待5秒再重试
    
    @lru_cache(maxsize=1000)
    def _convert_interval(self, interval: str) -> int:
        """
        将K线周期转换为秒数(使用缓存提高性能)
        
        Args:
            interval: K线周期字符串
            
        Returns:
            int: 周期秒数
        """
        return self.data_quality_checker._convert_interval_to_seconds(interval)
    
    async def enable_playback(self, start_dt: datetime, end_dt: datetime, speed: float = 1.0) -> bool:
        """
        启用回放模式
        
        Args:
            start_dt: 开始时间
            end_dt: 结束时间
            speed: 回放速度因子
            
        Returns:
            bool: 是否成功
        """
        if not HAS_TQSDK:
            self.logger.error("缺少天勤SDK，无法启用回放模式")
            return False
        
        try:
            # 断开现有连接
            await self.disconnect()
            
            # 创建回放API
            self.api = TqReplay(start_dt, end_dt)
            self.running = True
            
            # 启动回放处理任务
            asyncio.create_task(self._playback_loop(speed))
            
            self.logger.info(f"已启用回放模式: {start_dt} 至 {end_dt}, 速度 {speed}x")
            return True
            
        except Exception as e:
            self.logger.error(f"启用回放模式失败: {str(e)}")
            return False
    
    async def _playback_loop(self, speed: float) -> None:
        """
        回放处理循环
        
        Args:
            speed: 回放速度因子
        """
        try:
            counter = 0
            while self.running and self.api:
                # 处理API更新
                await self.api.wait_update()
                
                # 获取当前回放时间
                now = datetime.fromtimestamp(self.api.get_server_datetime() / 1e9)
                
                # 按计数控制事件发布频率
                counter += 1
                if counter % 10 == 0:  # 每10次更新发布一次进度事件
                    if self.event_bus:
                        await self.event_bus.publish(Event(
                            event_type=EventType.PLAYBACK_PROGRESS,
                            data={
                                "timestamp": now.isoformat(),
                                "progress": (now - self.api.replay_get_start_datetime()) / 
                                          (self.api.replay_get_end_datetime() - self.api.replay_get_start_datetime())
                            }
                        ))
                
                # 处理已更新的行情
                await self._process_api_updates()
                
                # 根据速度控制回放速度
                                
                if speed < 10:  # 低于10倍速时才进行延迟
                    await asyncio.sleep(0.1 / speed)
                
        except asyncio.CancelledError:
            self.logger.info("回放任务已取消")
        except Exception as e:
            self.logger.error(f"回放任务出错: {str(e)}")
            self.running = False
    
    async def subscribe(self, symbol: str) -> bool:
        """
        订阅合约
        
        Args:
            symbol: 合约代码
            
        Returns:
            bool: 是否成功
        """
        if not self.api or not self.running:
            self.logger.warning("数据源未连接，无法订阅")
            return False
        
        if symbol in self.subscribed_symbols:
            return True
        
        try:
            # 添加到订阅列表
            self.subscribed_symbols.add(symbol)
            
            # 创建行情订阅
            self.api.get_quote(symbol)
            
            self.logger.info(f"已订阅合约: {symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"订阅合约 {symbol} 失败: {str(e)}")
            self.subscribed_symbols.discard(symbol)
            self.circuit_breaker.record_failure()
            return False
    
    async def subscribe_klines(self, symbol: str, interval: str) -> bool:
        """
        订阅K线
        
        Args:
            symbol: 合约代码
            interval: K线周期
            
        Returns:
            bool: 是否成功
        """
        if not self.api or not self.running:
            self.logger.warning("数据源未连接，无法订阅K线")
            return False
        
        key = f"{symbol}_{interval}"
        if key in self.kline_serials:
            return True
        
        try:
            # 转换天勤K线周期格式
            duration_seconds = self._convert_interval(interval)
            
            # 创建K线序列
            klines = self.api.get_kline_serial(symbol, duration_seconds=duration_seconds)
            self.kline_serials[key] = klines
            
            self.logger.info(f"已订阅K线: {symbol} {interval}")
            return True
            
        except Exception as e:
            self.logger.error(f"订阅K线 {symbol} {interval} 失败: {str(e)}")
            self.circuit_breaker.record_failure()
            return False
    
    async def unsubscribe(self, symbol: str) -> bool:
        """
        取消订阅合约
        
        Args:
            symbol: 合约代码
            
        Returns:
            bool: 是否成功
        """
        if symbol in self.subscribed_symbols:
            self.subscribed_symbols.discard(symbol)
            
            # 清理相关K线订阅
            for key in list(self.kline_serials.keys()):
                if key.startswith(f"{symbol}_"):
                    del self.kline_serials[key]
            
            self.logger.info(f"已取消订阅合约: {symbol}")
        
        return True
    
    async def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取市场行情数据
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 市场数据
        """
        if not self.api or not self.running:
            self.logger.warning("数据源未连接，无法获取行情")
            return {}
        
        # 检查熔断器状态
        if not self.circuit_breaker.allow_request():
            self.logger.warning(f"熔断器已触发，拒绝获取 {symbol} 行情")
            return {}
        
        try:
            # 确保已订阅
            if symbol not in self.subscribed_symbols:
                await self.subscribe(symbol)
            
            # 获取行情
            quote = self.api.get_quote(symbol)
            if not quote:
                return {}
            
            # 转换为标准格式
            market_data = self._convert_quote_to_market_data(quote)
            
            # 记录熔断器成功
            self.circuit_breaker.record_success()
            
            return market_data
            
        except Exception as e:
            self.logger.error(f"获取 {symbol} 行情失败: {str(e)}")
            self.circuit_breaker.record_failure()
            return {}
    
    async def get_klines(self, symbol: str, interval: str, count: int = 200,
                        start_time: Optional[datetime] = None, 
                        end_time: Optional[datetime] = None) -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            interval: K线周期
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            pd.DataFrame: K线数据
        """
        if not self.api or not self.running:
            self.logger.warning("数据源未连接，无法获取K线")
            return pd.DataFrame()
        
        # 检查熔断器状态
        if not self.circuit_breaker.allow_request():
            self.logger.warning(f"熔断器已触发，拒绝获取 {symbol} {interval} K线")
            return pd.DataFrame()
        
        key = f"{symbol}_{interval}"
        
        try:
            # 确保已订阅
            if key not in self.kline_serials:
                await self.subscribe_klines(symbol, interval)
            
            # 获取K线数据
            klines = self.kline_serials.get(key)
            if klines is None:
                return pd.DataFrame()
            
            # 转换为DataFrame
            df = pd.DataFrame(klines)
            if df.empty:
                return df
            
            # 设置时间索引
            df['datetime'] = pd.to_datetime(df['datetime'] / 1e9, unit='s')
            df.set_index('datetime', inplace=True)
            
            # 过滤时间范围
            if start_time:
                df = df[df.index >= pd.Timestamp(start_time)]
            if end_time:
                df = df[df.index <= pd.Timestamp(end_time)]
            
            # 限制数量
            df = df.tail(count)
            
            # 检查数据质量
            data_list = df.reset_index().to_dict('records')
            self.data_quality_checker.check_klines(symbol, interval, data_list)
            
            # 记录熔断器成功
            self.circuit_breaker.record_success()
            
            return df
            
        except Exception as e:
            self.logger.error(f"获取 {symbol} {interval} K线失败: {str(e)}")
            self.circuit_breaker.record_failure()
            return pd.DataFrame()
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        stats = {
            "subscribed_symbols": len(self.subscribed_symbols),
            "kline_serials": len(self.kline_serials),
            "is_connected": self.api is not None and self.running,
            "circuit_breaker": self.circuit_breaker.get_state(),
        }
        
        # 添加延迟统计
        latency_stats = {}
        for symbol, latencies in self.latency_stats.items():
            if latencies:
                latency_stats[symbol] = {
                    "avg": sum(latencies) / len(latencies),
                    "max": max(latencies),
                    "min": min(latencies),
                    "samples": len(latencies)
                }
        
        stats["latency"] = latency_stats
        
        return stats


class DataProvider:
    """数据提供者，提供市场数据接口"""
    
    def __init__(self, broker_adapter: Optional[BrokerAdapter] = None,
                 cache_size: int = 10000,
                 enable_redis: bool = False, 
                 redis_url: Optional[str] = None,
                 event_bus: Optional[EventBus] = None):
        """
        初始化数据提供者
        
        Args:
            broker_adapter: 券商适配器，用于获取行情数据
            cache_size: 缓存大小
            enable_redis: 是否启用Redis缓存
            redis_url: Redis连接URL
            event_bus: 事件总线
        """
        self.logger = logging.getLogger("fst.core.market.provider")
        self.broker_adapter = broker_adapter
        self.cache_size = cache_size
        self.event_bus = event_bus
        
        # 数据源配置
        self.data_sources = {}
        self.source_priorities = {}
        
        # 数据缓存
        self.market_data_cache = {}
        self.kline_cache = {}
        self.instrument_cache = {}
        self.cache_ttl = 60  # 缓存过期时间(秒)
        
        # Redis缓存
        self.enable_redis = enable_redis and REDIS_AVAILABLE
        self.redis_url = redis_url
        self.redis = None
        
        # 运行状态
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # 心跳检测
        self.heartbeat_interval = 30  # 心跳间隔(秒)
        self.heartbeat_task = None
        
        # 订阅管理
        self.subscribed_symbols = set()
        self.callbacks = {}
        
        # 数据源活跃状态跟踪
        self.last_active_time = {}
        
        # 数据质量检查
        self.data_quality_checker = DataQualityChecker(event_bus)
        
        # 缓存数据保存路径
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".fst", "cache")
        
        # 性能统计
        self.stats = {
            "market_requests": 0,
            "kline_requests": 0,
            "errors": 0,
            "cache_hits": 0,
            "callback_errors": 0
        }
    
    async def start(self) -> bool:
        """
        启动数据提供者
        
        Returns:
            bool: 是否成功启动
        """
        if self.running:
            return True
        
        self.logger.info("启动数据提供者")
        self.running = True
        self.shutdown_event.clear()
        
        try:
            # 连接Redis
            if self.enable_redis:
                await self._init_redis()
            
            # 加载合约信息缓存
            await self._load_instrument_cache()
            
            # 初始化数据源
            await self._init_data_sources()
            
            # 启动心跳检测
            self.heartbeat_task = asyncio.create_task(self._heartbeat_task())
            
            self.logger.info("数据提供者启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动数据提供者失败: {e}")
            self.running = False
            return False
    
    async def stop(self) -> None:
        """停止数据提供者"""
        if not self.running:
            return
        
        self.logger.info("停止数据提供者")
        self.running = False
        self.shutdown_event.set()
        
        # 停止心跳任务
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # 断开数据源
        for source_id in list(self.data_sources.keys()):
            await self._disconnect_data_source(source_id)
        
        # 断开Redis连接
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()
            self.redis = None
        
        # 保存合约信息缓存
        await self._save_instrument_cache()
        
        self.logger.info("数据提供者已停止")
    
    async def _init_redis(self) -> None:
        """初始化Redis连接"""
        if not REDIS_AVAILABLE:
            self.logger.warning("Redis模块未安装，禁用Redis缓存")
            self.enable_redis = False
            return
        
        try:
            self.redis = await aioredis.from_url(
                self.redis_url or "redis://localhost:6379/0",
                encoding="utf-8",
                decode_responses=True
            )
            self.logger.info("Redis连接成功")
        except Exception as e:
            self.logger.error(f"Redis连接失败: {e}")
            self.enable_redis = False
    
    async def _init_data_sources(self) -> None:
        """初始化数据源"""
        # 添加券商数据源
        if self.broker_adapter:
            await self._add_broker_data_source()
        
        # 添加天勤SDK数据源
        if HAS_TQSDK:
            await self._add_tqsdk_data_source()
    
    async def _add_broker_data_source(self) -> None:
        """添加券商数据源"""
        # 检查券商适配器连接状态
        if self.broker_adapter.get_connection_state() != ConnectionState.CONNECTED:
            try:
                await self.broker_adapter.connect()
            except Exception as e:
                self.logger.error(f"券商适配器连接失败: {e}")
                return
        
        # 注册数据源
        source_id = "broker"
        self.data_sources[source_id] = {
            "type": "broker",
            "adapter": self.broker_adapter,
            "priority": 10  # 优先级，数值越高优先级越高
        }
        self.source_priorities[source_id] = 10
        self.last_active_time[source_id] = time.time()
        
        self.logger.info(f"已添加券商数据源: {self.broker_adapter.get_name()}")
    
    async def _add_tqsdk_data_source(self) -> None:
        """添加天勤SDK数据源"""
        try:
            # 创建天勤数据源
            tqsdk_source = TqsdkDataSource(
                config={
                    "auth": {
                        "username": os.environ.get("TQSDK_USERNAME"),
                        "password": os.environ.get("TQSDK_PASSWORD")
                    },
                    "sync_account": False
                },
                event_bus=self.event_bus
            )
            
            # 连接数据源
            success = await tqsdk_source.connect()
            if success:
                # 注册数据源
                source_id = "tqsdk"
                self.data_sources[source_id] = {
                    "type": "tqsdk",
                    "source": tqsdk_source,
                    "priority": 5  # 优先级
                }
                self.source_priorities[source_id] = 5
                self.last_active_time[source_id] = time.time()
                
                self.logger.info("已添加天勤SDK数据源")
            else:
                self.logger.warning("天勤SDK数据源连接失败")
                
        except Exception as e:
            self.logger.error(f"添加天勤SDK数据源失败: {e}")
    
    async def _disconnect_data_source(self, source_id: str) -> None:
        """
        断开数据源连接
        
        Args:
            source_id: 数据源ID
        """
        source_info = self.data_sources.get(source_id)
        if not source_info:
            return
        
        try:
            if source_info["type"] == "tqsdk":
                tqsdk_source = source_info.get("source")
                if tqsdk_source:
                    await tqsdk_source.disconnect()
            
            # 从数据源列表移除
            del self.data_sources[source_id]
            if source_id in self.source_priorities:
                del self.source_priorities[source_id]
            if source_id in self.last_active_time:
                del self.last_active_time[source_id]
                
            self.logger.info(f"已断开数据源: {source_id}")
            
        except Exception as e:
            self.logger.error(f"断开数据源 {source_id} 失败: {e}")
    
    async def get_market_data(self, symbol: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取市场行情数据
        
        Args:
            symbol: 合约代码
            use_cache: 是否使用缓存
            
        Returns:
            Dict: 市场数据
        """
        self.stats["market_requests"] += 1
        
        # 检查缓存
        if use_cache and symbol in self.market_data_cache:
            cached_data = self.market_data_cache[symbol]
            
            # 检查缓存是否过期
            if time.time() - cached_data.get("_update_time", 0) < self.cache_ttl:
                self.stats["cache_hits"] += 1
                return copy.deepcopy(cached_data)
        
        # 按优先级排序的数据源ID列表
        sorted_sources = sorted(
            self.data_sources.keys(),
            key=lambda source_id: self.source_priorities.get(source_id, 0),
            reverse=True  # 优先级高的排在前面
        )
        
        # 尝试从各数据源获取
        errors = []
        for source_id in sorted_sources:
            source_info = self.data_sources[source_id]
            
            try:
                market_data = {}
                
                if source_info["type"] == "broker":
                    # 从券商适配器获取
                    adapter = source_info.get("adapter")
                    if not adapter:
                        continue
                    
                    quote = await adapter.get_quote(symbol)
                    if not quote:
                        continue
                    
                    # 转换为标准格式
                    market_data = {
                        "symbol": symbol,
                        "datetime": quote.get("datetime", datetime.now().isoformat()),
                        "last_price": quote.get("last_price", 0),
                        "open": quote.get("open", 0),
                        "high": quote.get("high", 0),
                        "low": quote.get("low", 0),
                        "close": quote.get("last_price", 0),
                        "volume": quote.get("volume", 0),
                        "turnover": quote.get("turnover", 0),
                        "open_interest": quote.get("open_interest", 0),
                        "bid_price1": quote.get("bid_price1", 0),
                        "bid_volume1": quote.get("bid_volume1", 0),
                        "ask_price1": quote.get("ask_price1", 0),
                        "ask_volume1": quote.get("ask_volume1", 0),
                        "limit_up": quote.get("limit_up", 0),
                        "limit_down": quote.get("limit_down", 0),
                    }
                
                elif source_info["type"] == "tqsdk":
                    # 从天勤SDK获取
                    tqsdk_source = source_info.get("source")
                    if not tqsdk_source:
                        continue
                    
                    market_data = await tqsdk_source.get_market_data(symbol)
                
                if market_data:
                    # 添加数据源信息
                    market_data["_source"] = source_id
                    market_data["_update_time"] = time.time()
                    
                    # 更新缓存
                    self.market_data_cache[symbol] = copy.deepcopy(market_data)
                    
                    # 更新最后活跃时间
                    self.last_active_time[source_id] = time.time()
                    
                    # 如果使用Redis缓存，保存到Redis
                    if self.enable_redis and self.redis:
                        cache_key = f"market:{symbol}"
                        try:
                            await self.redis.setex(
                                cache_key,
                                self.cache_ttl * 2,  # Redis缓存时间稍长
                                json.dumps(market_data, default=str)
                            )
                        except Exception as e:
                            self.logger.error(f"保存市场数据到Redis失败: {e}")
                    
                    # 检查数据质量
                    self.data_quality_checker.check_market_data(symbol, market_data)
                    
                    return market_data
                    
            except Exception as e:
                error_msg = f"从数据源 {source_id} 获取 {symbol} 行情失败: {e}"
                self.logger.warning(error_msg)
                errors.append(error_msg)
                self.stats["errors"] += 1
        
        # 所有数据源都失败，尝试从Redis获取
        if self.enable_redis and self.redis:
            try:
                cache_key = f"market:{symbol}"
                cached_data = await self.redis.get(cache_key)
                if cached_data:
                    market_data = json.loads(cached_data)
                    self.logger.info(f"从Redis缓存获取 {symbol} 行情")
                    return market_data
            except Exception as e:
                self.logger.error(f"从Redis获取市场数据失败: {e}")
        
        # 所有数据源都失败
        if errors:
            self.logger.error(f"获取 {symbol} 行情失败: {errors}")
            
        # 返回缓存中的旧数据，即使已过期
        if symbol in self.market_data_cache:
            self.logger.warning(f"返回过期缓存数据: {symbol}")
            return copy.deepcopy(self.market_data_cache[symbol])
            
        return {}
    
    async def get_klines(self, symbol: str, interval: str, count: int = 200,
                         start_time: Optional[datetime] = None, 
                         end_time: Optional[datetime] = None,
                         use_cache: bool = True) -> Optional[pd.DataFrame]:
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
            pd.DataFrame: K线数据DataFrame
        """
        self.stats["kline_requests"] += 1
        
        # 检查缓存
        cache_key = f"{symbol}:{interval}"
        if use_cache and cache_key in self.kline_cache:
            cached_klines, update_time = self.kline_cache[cache_key]
            
            if time.time() - update_time < self.cache_ttl:
                # 过滤时间范围
                filtered_klines = cached_klines
                if start_time:
                    filtered_klines = filtered_klines[filtered_klines.index >= pd.Timestamp(start_time)]
                if end_time:
                    filtered_klines = filtered_klines[filtered_klines.index <= pd.Timestamp(end_time)]
                
                # 如果缓存数据足够，直接返回
                if len(filtered_klines) >= count:
                    self.stats["cache_hits"] += 1
                    return filtered_klines.tail(count).copy()
        
        # 按优先级排序的数据源ID列表
        sorted_sources = sorted(
            self.data_sources.keys(),
            key=lambda source_id: self.source_priorities.get(source_id, 0),
            reverse=True
        )
        
        # 尝试从各数据源获取
        errors = []
        for source_id in sorted_sources:
            source_info = self.data_sources[source_id]
            
            try:
                if source_info["type"] == "broker":
                    # 从券商适配器获取
                    adapter = source_info.get("adapter")
                    if not adapter:
                        continue
                    
                    klines = await adapter.get_klines(
                        symbol=symbol,
                        interval=interval,
                        count=count,
                        start_dt=start_time,
                        end_dt=end_time
                    )
                    
                    if not klines or len(klines) == 0:
                        continue
                    
                    # 转换为DataFrame
                    klines_df = pd.DataFrame(klines)
                    
                    # 设置时间索引
                    if 'datetime' in klines_df.columns:
                        klines_df['datetime'] = pd.to_datetime(klines_df['datetime'])
                        klines_df.set_index('datetime', inplace=True)
                
                elif source_info["type"] == "tqsdk":
                    # 从天勤SDK获取
                    tqsdk_source = source_info.get("source")
                    if not tqsdk_source:
                        continue
                    
                    klines_df = await tqsdk_source.get_klines(
                        symbol=symbol,
                        interval=interval,
                        count=count,
                        start_time=start_time,
                        end_time=end_time
                    )
                
                else:
                    continue
                
                if klines_df is not None and not klines_df.empty:
                    # 更新缓存
                    self.kline_cache[cache_key] = (klines_df, time.time())
                    
                    # 更新最后活跃时间
                    self.last_active_time[source_id] = time.time()
                    
                    # 如果使用Redis缓存，保存到Redis
                    if self.enable_redis and self.redis:
                        try:
                            # 将DataFrame转换为JSON
                            klines_json = klines_df.reset_index().to_json(orient='records', date_format='iso')
                            
                            # 保存到Redis
                            redis_key = f"klines:{symbol}:{interval}"
                            await self.redis.setex(
                                redis_key,
                                self.cache_ttl * 5,  # K线缓存时间更长
                                klines_json
                            )
                        except Exception as e:
                            self.logger.error(f"保存K线数据到Redis失败: {e}")
                    
                    # 检查数据质量
                    klines_list = klines_df.reset_index().to_dict('records')
                    self.data_quality_checker.check_klines(symbol, interval, klines_list)
                    
                    return klines_df
                    
            except Exception as e:
                error_msg = f"从数据源 {source_id} 获取 {symbol} K线失败: {e}"
                self.logger.warning(error_msg)
                errors.append(error_msg)
                self.stats["errors"] += 1
        
        # 所有数据源都失败，尝试从Redis获取
        if self.enable_redis and self.redis:
            try:
                redis_key = f"klines:{symbol}:{interval}"
                cached_data = await self.redis.get(redis_key)
                if cached_data:
                    # 解析JSON为DataFrame
                    klines_df = pd.read_json(cached_data, orient='records')
                    if 'datetime' in klines_df.columns:
                        klines_df['datetime'] = pd.to_datetime(klines_df['datetime'])
                        klines_df.set_index('datetime', inplace=True)
                    
                    self.logger.info(f"从Redis缓存获取 {symbol} {interval} K线")
                    
                    # 过滤时间范围
                    if start_time:
                        klines_df = klines_df[klines_df.index >= pd.Timestamp(start_time)]
                    if end_time:
                        klines_df = klines_df[klines_df.index <= pd.Timestamp(end_time)]
                    
                    # 限制数量
                    return klines_df.tail(count)
            except Exception as e:
                self.logger.error(f"从Redis获取K线数据失败: {e}")
        
        # 所有数据源都失败
        if errors:
            self.logger.error(f"获取 {symbol} {interval} K线失败: {errors}")
            
        # 返回缓存中的旧数据，即使已过期
        if cache_key in self.kline_cache:
            self.logger.warning(f"返回过期缓存K线数据: {cache_key}")
            klines_df, _ = self.kline_cache[cache_key]
            
            # 过滤时间范围
            if start_time:
                klines_df = klines_df[klines_df.index >= pd.Timestamp(start_time)]
            if end_time:
                klines_df = klines_df[klines_df.index <= pd.Timestamp(end_time)]
                
            return klines_df.tail(count).copy()
            
        return None
    
    async def subscribe_symbol(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        """
        订阅合约行情
        
        Args:
            symbol: 合约代码
            callback: 行情更新回调函数
            
        Returns:
            bool: 是否成功订阅
        """
        if symbol in self.subscribed_symbols:
            # 如果提供了回调，添加到回调列表
            if callback and callback not in self.callbacks.get(symbol, []):
                if symbol not in self.callbacks:
                    self.callbacks[symbol] = []
                self.callbacks[symbol].append(callback)
            
            return True
        
        self.logger.info(f"订阅合约: {symbol}")
        
        # 添加到订阅列表
        self.subscribed_symbols.add(symbol)
        
        # 添加回调
        if callback:
            if symbol not in self.callbacks:
                self.callbacks[symbol] = []
            self.callbacks[symbol].append(callback)
        
        # 在所有数据源上订阅
        success = False
        for source_id, source_info in self.data_sources.items():
            try:
                if source_info["type"] == "broker":
                    adapter = source_info.get("adapter")
                    if adapter:
                        await adapter.subscribe(symbol)
                        success = True
                
                elif source_info["type"] == "tqsdk":
                    tqsdk_source = source_info.get("source")
                    if tqsdk_source:
                        source_success = await tqsdk_source.subscribe(symbol)
                        if source_success:
                            success = True
                
            except Exception as e:
                self.logger.error(f"在数据源 {source_id} 上订阅 {symbol} 失败: {e}")
                self.stats["errors"] += 1
        
        if not success:
            self.logger.warning(f"所有数据源都无法订阅 {symbol}")
            self.subscribed_symbols.remove(symbol)
            if symbol in self.callbacks:
                del self.callbacks[symbol]
            return False
        
        # 订阅成功，立即获取一次数据
        try:
            market_data = await self.get_market_data(symbol, use_cache=False)
            if market_data:
                # 通知回调
                await self._notify_callbacks(symbol, market_data)
        except Exception as e:
            self.logger.error(f"获取 {symbol} 初始市场数据失败: {e}")
        
        return success
    
    async def unsubscribe_symbol(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        """
        取消订阅合约行情
        
        Args:
            symbol: 合约代码
            callback: 要移除的回调函数，None表示移除所有回调
            
        Returns:
            bool: 是否成功取消订阅
        """
        if symbol not in self.subscribed_symbols:
            return True
        
        # 处理回调
        if callback is not None and symbol in self.callbacks:
            # 移除特定回调
            if callback in self.callbacks[symbol]:
                self.callbacks[symbol].remove(callback)
            
            # 如果还有其他回调，不取消订阅
            if self.callbacks[symbol]:
                return True
        
        self.logger.info(f"取消订阅合约: {symbol}")
        
        # 在所有数据源上取消订阅
        for source_id, source_info in self.data_sources.items():
            try:
                if source_info["type"] == "broker":
                    adapter = source_info.get("adapter")
                    if adapter:
                        await adapter.unsubscribe(symbol)
                
                elif source_info["type"] == "tqsdk":
                    tqsdk_source = source_info.get("source")
                    if tqsdk_source:
                        await tqsdk_source.unsubscribe(symbol)
                
            except Exception as e:
                self.logger.error(f"在数据源 {source_id} 上取消订阅 {symbol} 失败: {e}")
                self.stats["errors"] += 1
        
        # 移除订阅记录
        self.subscribed_symbols.discard(symbol)
        if symbol in self.callbacks:
            del self.callbacks[symbol]
        
        return True
    
    async def _notify_callbacks(self, symbol: str, data: Dict[str, Any]) -> None:
        """
        通知回调函数
        
        Args:
            symbol: 合约代码
            data: 市场数据
        """
        if symbol not in self.callbacks:
            return
        
        callbacks = self.callbacks[symbol]
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"执行 {symbol} 回调函数出错: {e}")
                self.stats["callback_errors"] += 1
    
    async def _heartbeat_task(self) -> None:
        """心跳检测任务"""
        while not self.shutdown_event.is_set():
            try:
                now = time.time()
                
                # 检查数据源健康状态
                for source_id, source_info in list(self.data_sources.items()):
                    last_active = self.last_active_time.get(source_id, 0)
                    
                    # 如果长时间未收到数据更新，则尝试重新连接
                    if now - last_active > self.heartbeat_interval * 3:
                        self.logger.warning(f"数据源 {source_id} 长时间未活动，尝试重新连接")
                        
                        try:
                            # 断开连接
                            await self._disconnect_data_source(source_id)
                            
                            # 重新初始化数据源
                                                        # 重新初始化数据源
                            if source_id == "broker":
                                await self._add_broker_data_source()
                            elif source_id == "tqsdk":
                                await self._add_tqsdk_data_source()
                            
                        except Exception as e:
                            self.logger.error(f"重新连接数据源 {source_id} 失败: {e}")
                
                # 定期自动保存合约缓存
                if (now // 3600) % 24 == 0:  # 每天大约保存一次
                    await self._save_instrument_cache()
                
                # 等待下一次心跳检测
                await asyncio.sleep(self.heartbeat_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳检测任务出错: {e}")
                await asyncio.sleep(self.heartbeat_interval)  # 出错后等待一段时间再重试
    
    async def _load_instrument_cache(self) -> None:
        """加载合约信息缓存"""
        try:
            # 确保缓存目录存在
            os.makedirs(self.cache_dir, exist_ok=True)
            
            cache_file = os.path.join(self.cache_dir, "instruments.json")
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    
                    # 检查缓存是否过期 (超过7天)
                    if time.time() - cached_data.get("update_time", 0) < 7 * 86400:
                        self.instrument_cache = cached_data.get("instruments", {})
                        self.logger.info(f"从缓存加载了 {len(self.instrument_cache)} 个合约信息")
                    else:
                        self.logger.info("合约缓存已过期，将重新获取")
                        
        except Exception as e:
            self.logger.error(f"加载合约缓存失败: {e}")
    
    async def _save_instrument_cache(self) -> None:
        """保存合约信息缓存"""
        if not self.instrument_cache:
            return
            
        try:
            # 确保缓存目录存在
            os.makedirs(self.cache_dir, exist_ok=True)
            
            cache_file = os.path.join(self.cache_dir, "instruments.json")
            
            # 保存到临时文件，然后重命名，防止保存过程中崩溃导致缓存文件损坏
            temp_file = cache_file + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({
                    "update_time": time.time(),
                    "instruments": self.instrument_cache
                }, f, ensure_ascii=False, indent=2)
            
            # 重命名临时文件
            os.replace(temp_file, cache_file)
            
            self.logger.info(f"已保存 {len(self.instrument_cache)} 个合约信息到缓存")
            
        except Exception as e:
            self.logger.error(f"保存合约缓存失败: {e}")
    
    async def calculate_price_difference(self, symbol1: str, symbol2: str) -> Dict[str, Any]:
        """
        计算两个合约的价差
        
        Args:
            symbol1: 第一个合约代码
            symbol2: 第二个合约代码
            
        Returns:
            Dict: 价差信息
        """
        try:
            # 获取两个合约的行情
            data1 = await self.get_market_data(symbol1)
            data2 = await self.get_market_data(symbol2)
            
            if not data1 or not data2:
                return {}
            
            last_price1 = data1.get("last_price", 0)
            last_price2 = data2.get("last_price", 0)
            
            if last_price1 == 0 or last_price2 == 0:
                return {}
            
            # 计算价差
            price_diff = last_price1 - last_price2
            percent_diff = price_diff / last_price1 * 100
            
            return {
                "symbol1": symbol1,
                "symbol2": symbol2,
                "price1": last_price1,
                "price2": last_price2,
                "diff": price_diff,
                "diff_percent": percent_diff,
                "update_time": time.time()
            }
            
        except Exception as e:
            self.logger.error(f"计算价差失败: {e}")
            return {}
    
    async def calculate_volatility(self, symbol: str, interval: str = '1d', 
                                  periods: int = 20) -> Dict[str, Any]:
        """
        计算合约波动率
        
        Args:
            symbol: 合约代码
            interval: K线周期
            periods: 周期数量
            
        Returns:
            Dict: 波动率信息
        """
        try:
            # 获取K线数据
            klines = await self.get_klines(symbol, interval, count=periods+10)
            if klines is None or len(klines) < periods:
                return {}
            
            # 计算对数收益率
            returns = np.log(klines['close'] / klines['close'].shift(1)).dropna()
            
            # 计算波动率 (年化)
            yearly_factor = {
                '1m': 252 * 24 * 60,
                '5m': 252 * 24 * 12,
                '15m': 252 * 24 * 4,
                '30m': 252 * 24 * 2,
                '1h': 252 * 24,
                '2h': 252 * 12,
                '4h': 252 * 6,
                '1d': 252,
                '1w': 52,
                '1M': 12
            }.get(interval, 252)
            
            volatility = returns.std() * np.sqrt(yearly_factor)
            
            return {
                "symbol": symbol,
                "interval": interval,
                "periods": periods,
                "volatility": float(volatility),
                "returns": float(returns.mean()),
                "max_return": float(returns.max()),
                "min_return": float(returns.min()),
                "update_time": time.time()
            }
            
        except Exception as e:
            self.logger.error(f"计算波动率失败: {e}")
            return {}
    
    async def get_instruments(self, exchange: Optional[str] = None,
                             force_update: bool = False) -> Dict[str, Any]:
        """
        获取合约列表
        
        Args:
            exchange: 交易所代码，为None时获取所有交易所
            force_update: 是否强制更新
            
        Returns:
            Dict: 合约信息字典 {symbol: info}
        """
        # 如果有缓存且不强制更新，返回缓存
        if self.instrument_cache and not force_update:
            if exchange:
                # 过滤特定交易所的合约
                return {s: info for s, info in self.instrument_cache.items() 
                       if info.get("exchange") == exchange}
            else:
                return self.instrument_cache
        
        # 尝试从各数据源获取
        for source_id, source_info in self.data_sources.items():
            try:
                instruments = {}
                
                if source_info["type"] == "broker":
                    # 从券商适配器获取
                    adapter = source_info.get("adapter")
                    if not adapter:
                        continue
                    
                    raw_instruments = await adapter.get_instruments(exchange)
                    if raw_instruments:
                        # 转换为标准格式
                        for inst in raw_instruments:
                            symbol = inst.get("symbol")
                            if symbol:
                                instruments[symbol] = inst
                
                elif source_info["type"] == "tqsdk":
                    # 从天勤SDK获取
                    tqsdk_source = source_info.get("source")
                    if not tqsdk_source or not tqsdk_source.api:
                        continue
                    
                    # 获取天勤合约信息(具体API可能不同)
                    try:
                        if exchange:
                            raw_instruments = tqsdk_source.api.query_quotes(exchange_id=exchange)
                        else:
                            raw_instruments = tqsdk_source.api.query_quotes()
                            
                        for symbol, inst in raw_instruments.items():
                            instruments[symbol] = {
                                "symbol": symbol,
                                "exchange": inst.get("exchange_id", ""),
                                "name": inst.get("ins_name", ""),
                                "product": inst.get("product_id", ""),
                                "price_tick": inst.get("price_tick", 0),
                                "multiplier": inst.get("volume_multiple", 0),
                                "max_market_order_volume": inst.get("max_market_order_volume", 0),
                                "min_market_order_volume": inst.get("min_market_order_volume", 0),
                                "expire_date": inst.get("expire_datetime", ""),
                                "is_trading": inst.get("expired", False) == False
                            }
                    except:
                        # 天勤可能使用不同的API结构
                        pass
                
                if instruments:
                    # 更新缓存
                    if exchange:
                        # 只更新指定交易所的合约
                        for symbol, info in instruments.items():
                            self.instrument_cache[symbol] = info
                    else:
                        # 更新所有合约
                        self.instrument_cache = instruments
                    
                    # 保存缓存
                    await self._save_instrument_cache()
                    
                    self.logger.info(f"从数据源 {source_id} 获取了 {len(instruments)} 个合约信息")
                    
                    # 更新最后活跃时间
                    self.last_active_time[source_id] = time.time()
                    
                    return instruments
                    
            except Exception as e:
                self.logger.error(f"从数据源 {source_id} 获取合约列表失败: {e}")
                self.stats["errors"] += 1
        
        # 所有数据源都失败，返回现有缓存
        self.logger.warning("所有数据源获取合约列表失败，返回缓存")
        
        if exchange:
            return {s: info for s, info in self.instrument_cache.items() 
                   if info.get("exchange") == exchange}
        else:
            return self.instrument_cache
    
    async def get_historical_ticks(self, symbol: str, 
                                 count: int = 1000, 
                                 start_time: Optional[datetime] = None, 
                                 end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        获取历史Tick数据
        
        Args:
            symbol: 合约代码
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[Dict]: Tick数据列表
        """
        # 尝试从各数据源获取
        for source_id, source_info in self.data_sources.items():
            try:
                if source_info["type"] == "broker":
                    # 从券商适配器获取
                    adapter = source_info.get("adapter")
                    if not adapter:
                        continue
                    
                    ticks = await adapter.get_ticks(symbol, count, start_time, end_time)
                    if ticks:
                        # 更新最后活跃时间
                        self.last_active_time[source_id] = time.time()
                        return ticks
                
                # 天勤SDK可能不支持直接获取历史Tick
                
            except Exception as e:
                self.logger.error(f"从数据源 {source_id} 获取历史Tick失败: {e}")
                self.stats["errors"] += 1
        
        # 所有数据源都失败
        self.logger.warning(f"所有数据源获取 {symbol} 历史Tick失败")
        return []
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取数据提供者统计信息
        
        Returns:
            Dict: 统计信息
        """
        stats = {
            "subscribed_symbols": len(self.subscribed_symbols),
            "data_sources": [
                {
                    "id": source_id,
                    "type": source_info["type"],
                    "priority": self.source_priorities.get(source_id, 0),
                    "last_active": time.time() - self.last_active_time.get(source_id, 0)
                }
                for source_id, source_info in self.data_sources.items()
            ],
            "cache": {
                "market_data": len(self.market_data_cache),
                "klines": len(self.kline_cache),
                "instruments": len(self.instrument_cache)
            },
            "requests": {
                "market_data": self.stats["market_requests"],
                "klines": self.stats["kline_requests"],
                "errors": self.stats["errors"],
                "cache_hits": self.stats["cache_hits"],
                "callback_errors": self.stats["callback_errors"]
            },
            "uptime": time.time() - (self.start_time if hasattr(self, 'start_time') else time.time())
        }
        
        # 获取各数据源的统计信息
        source_stats = {}
        for source_id, source_info in self.data_sources.items():
            try:
                if source_info["type"] == "tqsdk":
                    tqsdk_source = source_info.get("source")
                    if tqsdk_source:
                        source_stats[source_id] = await tqsdk_source.get_statistics()
            except Exception as e:
                self.logger.error(f"获取数据源 {source_id} 统计信息失败: {e}")
        
        stats["source_stats"] = source_stats
        
        return stats