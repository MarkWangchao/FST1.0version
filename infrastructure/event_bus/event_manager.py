#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 高性能事件总线 v2.0

提供高性能、高可靠性的事件驱动架构支持，主要特性包括：
- 分片队列与优先级处理
- 内存池与零拷贝传输
- 混合执行模式(IO/CPU分离)
- 批量处理与流水线优化
- 自适应吞吐量控制
- 延迟热力图分析
- 故障注入测试
- 增强的天勤集成
"""

import asyncio
import concurrent.futures
import inspect
import json
import logging
import queue
import random
import threading
import time
import traceback
import uuid
import zlib
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import os
import psutil
import memoryview

# 尝试导入可选依赖
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

try:
    from prometheus_client import Counter, Gauge, Histogram
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

try:
    import tqsdk
    HAS_TQSDK = True
except ImportError:
    HAS_TQSDK = False

# 版本号
__version__ = "2.0.0"

# Prometheus指标定义
if HAS_PROMETHEUS:
    EVENT_QUEUE_SIZE = Gauge('fst_event_queue_size', 'Current event queue size', ['shard'])
    EVENT_URGENT_QUEUE_SIZE = Gauge('fst_event_urgent_queue_size', 'Current urgent queue size', ['shard'])
    EVENT_NORMAL_QUEUE_SIZE = Gauge('fst_event_normal_queue_size', 'Current normal queue size', ['shard'])
    EVENT_PROCESS_TIME = Histogram('fst_event_process_time', 'Event processing time distribution')
    EVENT_PUBLISH_COUNT = Counter('fst_event_publish_count', 'Published events count', ['event_type', 'priority'])
    EVENT_DROP_COUNT = Counter('fst_event_drop_count', 'Dropped events count', ['event_type', 'reason'])
    EVENT_ERROR_COUNT = Counter('fst_event_error_count', 'Event processing errors count', ['event_type'])
    CIRCUIT_BREAKER_STATE = Gauge('fst_circuit_breaker_state', 'Circuit breaker state (0=closed, 1=open, 2=half-open)')
    EVENT_FILTER_COUNT = Counter('fst_event_filter_count', 'Filtered events count', ['event_type', 'filter_name'])
    EVENT_VALIDATION_ERROR = Counter('fst_event_validation_error', 'Event validation errors', ['event_type', 'error_type'])
    EVENT_ROUTE_COUNT = Counter('fst_event_route_count', 'Routed events count', ['event_type', 'route_pattern'])
    MEMORY_POOL_SIZE = Gauge('fst_memory_pool_size', 'Memory pool size', ['event_type'])
    LATENCY_HEATMAP = Histogram('fst_latency_heatmap', 'Event processing latency heatmap')

class ShardedEventQueue:
    """分片队列提升并发性能"""
    
    def __init__(self, shard_num=8):
        self.shards = [asyncio.PriorityQueue() for _ in range(shard_num)]
        self.locks = [asyncio.Lock() for _ in range(shard_num)]
        self.shard_num = shard_num
        
    async def put(self, event):
        shard_id = hash(event.trace_id) % self.shard_num
        async with self.locks[shard_id]:
            await self.shards[shard_id].put((event.priority, time.time(), event))
            if HAS_PROMETHEUS:
                EVENT_QUEUE_SIZE.labels(shard=shard_id).inc()
    
    async def get(self, shard_id=None):
        if shard_id is None:
            # 轮询所有分片
            for i in range(self.shard_num):
                try:
                    async with self.locks[i]:
                        _, _, event = await self.shards[i].get()
                        if HAS_PROMETHEUS:
                            EVENT_QUEUE_SIZE.labels(shard=i).dec()
                        return event
                except asyncio.QueueEmpty:
                    continue
            raise asyncio.QueueEmpty()
        else:
            async with self.locks[shard_id]:
                _, _, event = await self.shards[shard_id].get()
                if HAS_PROMETHEUS:
                    EVENT_QUEUE_SIZE.labels(shard=shard_id).dec()
                return event
    
    def qsize(self):
        return sum(shard.qsize() for shard in self.shards)
    
    def empty(self):
        return all(shard.empty() for shard in self.shards)

class MemoryPool:
    """对象池减少GC压力"""
    
    _event_pool = defaultdict(deque)
    _max_pool_size = 10000
    
    @classmethod
    def acquire_event(cls, event_type):
        if cls._event_pool[event_type]:
            event = cls._event_pool[event_type].pop()
            if HAS_PROMETHEUS:
                MEMORY_POOL_SIZE.labels(event_type=str(event_type)).dec()
            return event
        return Event(event_type)
    
    @classmethod
    def release_event(cls, event):
        if len(cls._event_pool[event.event_type]) < cls._max_pool_size:
            event.reset()  # 清理事件数据
            cls._event_pool[event.event_type].append(event)
            if HAS_PROMETHEUS:
                MEMORY_POOL_SIZE.labels(event_type=str(event.event_type)).inc()

class HybridExecutor:
    """混合执行模式优化资源利用"""
    
    def __init__(self):
        self.io_executor = ThreadPoolExecutor(max_workers=8)
        self.cpu_executor = ProcessPoolExecutor(max_workers=4)
        self.logger = logging.getLogger("fst.event_bus.executor")
    
    async def dispatch(self, event):
        try:
            if event.is_io_bound:
                await asyncio.get_event_loop().run_in_executor(
                    self.io_executor, 
                    self._handle_io, 
                    event
                )
            else:
                await asyncio.get_event_loop().run_in_executor(
                    self.cpu_executor, 
                    self._handle_cpu, 
                    event
                )
        except Exception as e:
            self.logger.error(f"事件处理失败: {str(e)}")
            if HAS_PROMETHEUS:
                EVENT_ERROR_COUNT.labels(event_type=str(event.event_type)).inc()
    
    def _handle_io(self, event):
        # IO密集型事件处理
        pass
    
    def _handle_cpu(self, event):
        # CPU密集型事件处理
        pass
class ZeroCopyTransport:
    """零拷贝传输减少内存复制"""
    
    def __init__(self):
        self._buffers = []
        self._buffer_size = 4096
        self._current_buffer = memoryview(bytearray(self._buffer_size))
        self._current_position = 0
        self.logger = logging.getLogger("fst.event_bus.transport")
    
    def send_event(self, event):
        try:
            data = event.to_bytes()
            data_view = memoryview(data)
            
            if len(data) > self._buffer_size:
                # 大数据直接使用内存视图
                self._buffers.append(data_view)
            else:
                # 小数据合并到当前缓冲区
                remaining = self._buffer_size - self._current_position
                if len(data) > remaining:
                    self._merge_buffers()
                
                self._current_buffer[self._current_position:self._current_position + len(data)] = data_view
                self._current_position += len(data)
        except Exception as e:
            self.logger.error(f"事件发送失败: {str(e)}")
    
    def _merge_buffers(self):
        """合并缓冲区"""
        if self._current_position > 0:
            self._buffers.append(self._current_buffer[:self._current_position])
            self._current_buffer = memoryview(bytearray(self._buffer_size))
            self._current_position = 0
    
    def flush(self):
        """刷新所有缓冲区"""
        self._merge_buffers()
        data = b''.join(buffer.tobytes() for buffer in self._buffers)
        self._buffers.clear()
        return data

class LatencyHeatmap:
    """延迟热力图分析"""
    
    def __init__(self):
        self._latency_buckets = defaultdict(int)
        self._time_windows = [1, 5, 15, 30, 60]  # 秒
        self._start_time = time.time()
        self.logger = logging.getLogger("fst.event_bus.latency")
        
        # 初始化Prometheus直方图
        if HAS_PROMETHEUS:
            self._latency_histogram = Histogram(
                'event_latency_heatmap',
                'Event processing latency heatmap',
                buckets=self._time_windows
            )
    
    def record_latency(self, latency_ns):
        """记录延迟数据"""
        try:
            latency_s = latency_ns / 1e9  # 转换为秒
            
            # 更新内部统计
            for window in self._time_windows:
                if latency_s <= window:
                    self._latency_buckets[window] += 1
            
            # 更新Prometheus指标
            if HAS_PROMETHEUS:
                self._latency_histogram.observe(latency_s)
        except Exception as e:
            self.logger.error(f"记录延迟数据失败: {str(e)}")
    
    def get_hotspots(self):
        """获取延迟热点"""
        total_events = sum(self._latency_buckets.values())
        if total_events == 0:
            return []
        
        hotspots = []
        accumulated = 0
        for window in sorted(self._time_windows):
            count = self._latency_buckets[window]
            percentage = (count / total_events) * 100
            accumulated += count
            hotspots.append({
                'window': window,
                'count': count,
                'percentage': percentage,
                'accumulated_percentage': (accumulated / total_events) * 100
            })
        return hotspots
    
    def reset(self):
        """重置统计数据"""
        self._latency_buckets.clear()
        self._start_time = time.time()

class TqEventProxy:
    """天勤事件代理服务"""
    
    def __init__(self, event_bus):
        self._event_bus = event_bus
        self._queue = asyncio.Queue(maxsize=self._CACHE_SIZE)
        self._batch_size = 100
        self._active = False
        self.logger = logging.getLogger("fst.event_bus.tq_proxy")
        
        # 配置
        self._CACHE_SIZE = 100000
        self._BATCH_INTERVAL = 50  # 毫秒
        self._symbol_filters = set()  # 标的过滤
    
    async def start(self):
        """启动代理服务"""
        self._active = True
        asyncio.create_task(self._batch_events())
        self.logger.info("天勤事件代理服务已启动")
    
    async def stop(self):
        """停止代理服务"""
        self._active = False
        self.logger.info("天勤事件代理服务已停止")
    
    async def _batch_events(self):
        """批量聚合事件减少IO"""
        while self._active:
            try:
                await asyncio.sleep(self._BATCH_INTERVAL / 1000)
                batch = await self._get_batch()
                if batch:
                    await self._send_batch(batch)
            except Exception as e:
                self.logger.error(f"批量处理事件失败: {str(e)}")
    
    async def _get_batch(self):
        """获取批量事件"""
        batch = defaultdict(list)
        try:
            for _ in range(self._batch_size):
                try:
                    event = self._queue.get_nowait()
                    if event.metadata.get('symbol') in self._symbol_filters:
                        continue
                    key = f"{event.event_type}:{event.metadata.get('symbol', '')}"
                    batch[key].append(event)
                except asyncio.QueueEmpty:
                    break
        except Exception as e:
            self.logger.error(f"获取批量事件失败: {str(e)}")
        return batch
    
    async def _send_batch(self, batch):
        """发送批量事件"""
        try:
            for key, events in batch.items():
                if len(events) == 1:
                    await self._event_bus.publish(events[0])
                else:
                    # 合并相同类型和标的的事件
                    merged_event = self._merge_events(events)
                    await self._event_bus.publish(merged_event)
        except Exception as e:
            self.logger.error(f"发送批量事件失败: {str(e)}")
    
    def _merge_events(self, events):
        """合并同类事件"""
        base_event = events[0]
        if base_event.event_type == EventType.TICK:
            return self._merge_tick_events(events)
        elif base_event.event_type == EventType.BAR:
            return self._merge_bar_events(events)
        return base_event
    
    def _merge_tick_events(self, events):
        """合并Tick数据"""
        latest = events[-1]
        merged_data = latest.data.copy()
        merged_data['volume'] = sum(e.data['volume'] for e in events)
        merged_data['amount'] = sum(e.data['amount'] for e in events)
        latest.data = merged_data
        return latest
    
    def _merge_bar_events(self, events):
        """合并Bar数据"""
        latest = events[-1]
        merged_data = latest.data.copy()
        merged_data['volume'] = sum(e.data['volume'] for e in events)
        merged_data['amount'] = sum(e.data['amount'] for e in events)
        merged_data['high'] = max(e.data['high'] for e in events)
        merged_data['low'] = min(e.data['low'] for e in events)
        latest.data = merged_data
        return latest

class FailureInjector:
    """故障注入测试框架"""
    
    _FAILURE_TYPES = {
        'network_latency': lambda: time.sleep(random.uniform(0.1, 2.0)),
        'packet_loss': lambda: random.random() < 0.05,
        'cpu_spike': lambda: os.system('stress -c 1 -t 30s'),
        'memory_leak': lambda: [bytearray(1024*1024) for _ in range(100)],
        'disk_io': lambda: os.system('dd if=/dev/zero of=test.dat bs=1M count=100'),
    }
    
    def __init__(self):
        self._active_failures = set()
        self._failure_stats = defaultdict(int)
        self.logger = logging.getLogger("fst.event_bus.failure")
    
    def inject(self, failure_type):
        """注入故障"""
        try:
            if failure_type in self._FAILURE_TYPES:
                self._FAILURE_TYPES[failure_type]()
                self._active_failures.add(failure_type)
                self._failure_stats[failure_type] += 1
                self.logger.warning(f"注入故障: {failure_type}")
        except Exception as e:
            self.logger.error(f"注入故障失败: {str(e)}")
    
    def clear(self):
        """清除所有故障"""
        self._active_failures.clear()
        self.logger.info("已清除所有故障")
    
    def get_stats(self):
        """获取故障统计"""
        return dict(self._failure_stats)
class OptimizedEventBus:
    """
    优化版事件总线
    
    整合了所有性能优化特性:
    - 分片队列与内存池
    - 混合执行模式
    - 零拷贝传输
    - 延迟分析
    - 自适应控制
    """
    
    def __init__(self, name: str = "main", config_file: str = None):
        """
        初始化优化版事件总线
        
        Args:
            name: 实例名称
            config_file: 配置文件路径
        """
        self.name = name
        self.logger = logging.getLogger(f"fst.event_bus.{name}")
        
        # 加载配置
        self.config = EventBusConfig(config_file)
        config_errors = self.config.validate()
        if config_errors:
            raise ValueError(f"配置验证失败: {', '.join(config_errors)}")
        
        # 初始化核心组件
        self._init_components()
        
        # 运行状态
        self._active = False
        self._last_adjust_time = time.monotonic()
        self._stats = self._init_stats()
        
        self.logger.info(f"优化版事件总线初始化完成: {name}")
    
    def _init_components(self):
        """初始化核心组件"""
        # 事件队列 (分片)
        shard_num = self.config.get("queue.shard_num", 8)
        self._urgent_queue = ShardedEventQueue(shard_num)
        self._normal_queue = ShardedEventQueue(shard_num)
        
        # 执行器
        self._executor = HybridExecutor()
        
        # 传输层
        self._transport = ZeroCopyTransport()
        
        # 监控组件
        self._latency = LatencyHeatmap()
        
        # 内存管理
        self._memory_pool = MemoryPool()
        
        # 故障注入
        self._failure_injector = FailureInjector()
        
        # 事件处理组件
        self.filter = EventFilter()
        self.router = EventRouter()
        self.validator = EventValidator()
        self.metrics = EventMetrics()
        
        # 天勤集成
        if HAS_TQSDK:
            self.tq_proxy = TqEventProxy(self)
        
        # 性能参数
        self._batch_size = self.config.get("batch.size", 100)
        self._target_rate = self.config.get("batch.target_rate", 10000)  # 目标每秒处理事件数
        
        # 熔断器状态
        self._circuit_breaker = {
            "state": "CLOSED",
            "failure_count": 0,
            "last_failure_time": 0,
            "threshold": self.config.get("circuit_breaker.threshold", 50),
            "recovery_time": self.config.get("circuit_breaker.recovery_time", 30)
        }
    
    def _init_stats(self):
        """初始化统计数据"""
        return {
            "published": 0,
            "processed": 0,
            "dropped": 0,
            "errors": 0,
            "latency": {
                "min": float('inf'),
                "max": 0,
                "avg": 0,
                "total": 0
            },
            "throughput": {
                "current": 0,
                "peak": 0,
                "total": 0
            },
            "memory": {
                "pool_size": 0,
                "event_count": 0
            },
            "start_time": time.time()
        }
    
    async def start(self):
        """启动事件总线"""
        if self._active:
            return
            
        self._active = True
        
        # 启动各组件
        if HAS_TQSDK:
            await self.tq_proxy.start()
        
        # 启动主处理循环
        asyncio.create_task(self._event_loop())
        
        # 启动监控任务
        asyncio.create_task(self._monitor_loop())
        
        self.logger.info(f"事件总线已启动: {self.name}")
    
    async def stop(self):
        """停止事件总线"""
        if not self._active:
            return
            
        self._active = False
        
        # 停止各组件
        if HAS_TQSDK:
            await self.tq_proxy.stop()
        
        # 清理资源
        self._transport.flush()
        await self._cleanup()
        
        self.logger.info(f"事件总线已停止: {self.name}")
    
    async def publish(self, event: Event) -> bool:
        """
        发布事件
        
        Args:
            event: 要发布的事件
            
        Returns:
            bool: 是否成功发布
        """
        start_time = time.perf_counter_ns()
        
        try:
            # 检查熔断器状态
            if not self._check_circuit_breaker():
                if HAS_PROMETHEUS:
                    EVENT_DROP_COUNT.labels(
                        event_type=str(event.event_type),
                        reason="circuit_breaker"
                    ).inc()
                return False
            
            # 验证事件
            if self.config.get("validation.enabled", True):
                if not self.validator.validate(event):
                    if HAS_PROMETHEUS:
                        EVENT_VALIDATION_ERROR.labels(
                            event_type=str(event.event_type),
                            error_type="validation_failed"
                        ).inc()
                    return False
            
            # 过滤事件
            filtered_event = self.filter.process(event)
            if filtered_event is None:
                return False
            
            # 选择队列
            queue = self._urgent_queue if filtered_event.priority <= 5 else self._normal_queue
            
            # 发布事件
            await queue.put(filtered_event)
            
            # 更新统计
            self._stats["published"] += 1
            
            # 记录延迟
            latency = time.perf_counter_ns() - start_time
            self._latency.record_latency(latency)
            
            # 更新Prometheus指标
            if HAS_PROMETHEUS:
                EVENT_PUBLISH_COUNT.labels(
                    event_type=str(filtered_event.event_type),
                    priority=str(filtered_event.priority)
                ).inc()
            
            return True
            
        except Exception as e:
            self.logger.error(f"发布事件失败: {str(e)}")
            self._stats["errors"] += 1
            return False
    
    async def _event_loop(self):
        """优化的事件处理主循环"""
        while self._active:
            try:
                # 批量获取事件
                batch = await self._get_batch()
                if not batch:
                    await asyncio.sleep(0.001)
                    continue
                
                # 并行处理批次
                start_time = time.perf_counter_ns()
                
                # 使用流水线处理
                processed = await self._pipeline_process(batch)
                
                # 并行执行
                if processed:
                    await asyncio.gather(*[
                        self._executor.dispatch(event) 
                        for event in processed
                    ])
                
                # 计算并调整吞吐量
                elapsed = (time.perf_counter_ns() - start_time) / 1e9
                if elapsed > 0:
                    rate = len(processed) / elapsed
                    self._adjust_throughput(rate)
                
            except Exception as e:
                self.logger.error(f"事件循环异常: {str(e)}")
                await asyncio.sleep(1)
    
    async def _pipeline_process(self, batch):
        """流水线处理批次事件"""
        results = []
        for event in batch:
            try:
                # 验证
                if not self.validator.validate(event):
                    continue
                    
                # 过滤
                filtered = self.filter.process(event)
                if filtered is None:
                    continue
                    
                # 路由
                self.router.route(filtered)
                
                results.append(filtered)
                
            except Exception as e:
                self.logger.error(f"处理事件失败: {str(e)}")
                self._stats["errors"] += 1
                
        return results
    
    async def _get_batch(self):
        """批量获取事件"""
        batch = []
        
        # 优先处理紧急队列
        while len(batch) < self._batch_size and not self._urgent_queue.empty():
            try:
                event = await self._urgent_queue.get()
                batch.append(event)
            except asyncio.QueueEmpty:
                break
        
        # 处理普通队列
        while len(batch) < self._batch_size and not self._normal_queue.empty():
            try:
                event = await self._normal_queue.get()
                batch.append(event)
            except asyncio.QueueEmpty:
                break
        
        return batch
    
    def _adjust_throughput(self, current_rate):
        """动态调整吞吐量"""
        if current_rate > self._target_rate * 1.2:
            # 当前速率过高，增加批量大小
            self._batch_size = min(self._batch_size + 10, 1000)
        elif current_rate < self._target_rate * 0.8:
            # 当前速率过低，减少批量大小
            self._batch_size = max(self._batch_size - 10, 50)
        
        # 更新统计
        self._stats["throughput"]["current"] = current_rate
        self._stats["throughput"]["peak"] = max(
            self._stats["throughput"]["peak"],
            current_rate
        )
    
    async def _monitor_loop(self):
        """监控循环"""
        while self._active:
            try:
                # 收集系统指标
                cpu_usage = psutil.cpu_percent()
                memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
                
                # 更新统计
                self._stats["memory"]["pool_size"] = sum(
                    len(pool) for pool in self._memory_pool._event_pool.values()
                )
                
                # 更新Prometheus指标
                if HAS_PROMETHEUS:
                    MEMORY_POOL_SIZE.set(self._stats["memory"]["pool_size"])
                
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"监控循环异常: {str(e)}")
                await asyncio.sleep(5)
    
    def _check_circuit_breaker(self) -> bool:
        """检查熔断器状态"""
        if self._circuit_breaker["state"] == "OPEN":
            if time.time() - self._circuit_breaker["last_failure_time"] > self._circuit_breaker["recovery_time"]:
                self._circuit_breaker["state"] = "HALF_OPEN"
                return True
            return False
        return True
    
    async def _cleanup(self):
        """清理资源"""
        # 清空队列
        while not self._urgent_queue.empty():
            await self._urgent_queue.get()
        while not self._normal_queue.empty():
            await self._normal_queue.get()
        
        # 清理内存池
        self._memory_pool._event_pool.clear()
        
        # 重置统计
        self._stats = self._init_stats()
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "basic": self._stats,
            "latency": self._latency.get_hotspots(),
            "failures": self._failure_injector.get_stats(),
            "queues": {
                "urgent": self._urgent_queue.qsize(),
                "normal": self._normal_queue.qsize()
            }
        }
class EventProcessingPipeline:
    """事件处理流水线"""
    
    def __init__(self):
        self.stages = []
        self.logger = logging.getLogger("fst.event_bus.pipeline")
        
    def add_stage(self, name: str, processor: Callable):
        """添加处理阶段"""
        self.stages.append({
            'name': name,
            'processor': processor,
            'stats': {
                'processed': 0,
                'errors': 0,
                'total_time': 0
            }
        })
        
    async def process(self, event: Event) -> Optional[Event]:
        """流水线处理事件"""
        current_event = event
        for stage in self.stages:
            try:
                start_time = time.perf_counter_ns()
                current_event = await stage['processor'](current_event)
                elapsed = time.perf_counter_ns() - start_time
                
                # 更新统计
                stage['stats']['processed'] += 1
                stage['stats']['total_time'] += elapsed
                
                if current_event is None:
                    break
                    
            except Exception as e:
                stage['stats']['errors'] += 1
                self.logger.error(f"流水线阶段 {stage['name']} 处理失败: {str(e)}")
                return None
                
        return current_event
    
    def get_stats(self) -> Dict:
        """获取流水线统计信息"""
        return {
            stage['name']: {
                'processed': stage['stats']['processed'],
                'errors': stage['stats']['errors'],
                'avg_time': (stage['stats']['total_time'] / stage['stats']['processed'] 
                           if stage['stats']['processed'] > 0 else 0)
            }
            for stage in self.stages
        }

class AdaptiveController:
    """自适应控制器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.metrics_window = []
        self.window_size = config.get('metrics_window_size', 60)  # 60秒
        self.logger = logging.getLogger("fst.event_bus.controller")
        
        # 控制参数
        self.min_batch_size = config.get('min_batch_size', 50)
        self.max_batch_size = config.get('max_batch_size', 1000)
        self.target_latency = config.get('target_latency', 0.1)  # 100ms
        
    def update(self, metrics: Dict) -> Dict[str, Any]:
        """更新控制参数"""
        try:
            # 添加新指标
            self.metrics_window.append({
                'timestamp': time.time(),
                **metrics
            })
            
            # 移除旧指标
            cutoff_time = time.time() - self.window_size
            self.metrics_window = [
                m for m in self.metrics_window
                if m['timestamp'] > cutoff_time
            ]
            
            # 计算调整建议
            return self._calculate_adjustments()
            
        except Exception as e:
            self.logger.error(f"更新控制参数失败: {str(e)}")
            return {}
            
    def _calculate_adjustments(self) -> Dict[str, Any]:
        """计算参数调整建议"""
        if not self.metrics_window:
            return {}
            
        try:
            # 计算关键指标
            latencies = [m.get('latency', 0) for m in self.metrics_window]
            throughputs = [m.get('throughput', 0) for m in self.metrics_window]
            error_rates = [m.get('error_rate', 0) for m in self.metrics_window]
            
            avg_latency = sum(latencies) / len(latencies)
            avg_throughput = sum(throughputs) / len(throughputs)
            avg_error_rate = sum(error_rates) / len(error_rates)
            
            # 生成调整建议
            adjustments = {
                'batch_size': self._adjust_batch_size(avg_latency, avg_throughput),
                'worker_count': self._adjust_worker_count(avg_throughput, avg_error_rate),
                'queue_size': self._adjust_queue_size(avg_throughput)
            }
            
            return adjustments
            
        except Exception as e:
            self.logger.error(f"计算参数调整失败: {str(e)}")
            return {}
            
    def _adjust_batch_size(self, latency: float, throughput: float) -> int:
        """调整批处理大小"""
        if latency > self.target_latency * 1.2:
            # 延迟过高，减小批量
            return max(self.min_batch_size, 
                      int(self.current_batch_size * 0.8))
        elif latency < self.target_latency * 0.8:
            # 延迟较低，增加批量
            return min(self.max_batch_size,
                      int(self.current_batch_size * 1.2))
        return self.current_batch_size

class EventBusCluster:
    """事件总线集群"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.nodes = {}
        self.leader = None
        self.logger = logging.getLogger("fst.event_bus.cluster")
        
        # 集群配置
        self.heartbeat_interval = config.get('heartbeat_interval', 5)
        self.node_timeout = config.get('node_timeout', 15)
        
    async def start(self):
        """启动集群"""
        # 启动心跳检测
        asyncio.create_task(self._heartbeat_loop())
        
        # 启动领导者选举
        asyncio.create_task(self._leader_election_loop())
        
        self.logger.info("事件总线集群已启动")
        
    async def stop(self):
        """停止集群"""
        # 清理资源
        self.nodes.clear()
        self.leader = None
        
        self.logger.info("事件总线集群已停止")
        
    async def _heartbeat_loop(self):
        """心跳检测循环"""
        while True:
            try:
                await self._check_nodes()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"心跳检测失败: {str(e)}")
                await asyncio.sleep(1)
                
    async def _leader_election_loop(self):
        """领导者选举循环"""
        while True:
            try:
                if not self.leader or self.leader not in self.nodes:
                    await self._elect_leader()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"领导者选举失败: {str(e)}")
                await asyncio.sleep(1)

class EventBusMetrics:
    """事件总线指标收集器"""
    
    def __init__(self):
        self.metrics = defaultdict(float)
        self.dimensions = defaultdict(set)
        self.logger = logging.getLogger("fst.event_bus.metrics")
        
    def record(self, name: str, value: float, dimensions: Dict[str, str] = None):
        """记录指标"""
        try:
            # 生成指标键
            key = name
            if dimensions:
                dimension_str = ','.join(f"{k}={v}" for k, v in sorted(dimensions.items()))
                key = f"{name}[{dimension_str}]"
                
                # 记录维度值
                for k, v in dimensions.items():
                    self.dimensions[k].add(v)
            
            # 更新指标值
            self.metrics[key] = value
            
        except Exception as e:
            self.logger.error(f"记录指标失败: {str(e)}")
            
    def get_metrics(self) -> Dict:
        """获取所有指标"""
        return dict(self.metrics)
    
    def get_dimensions(self) -> Dict:
        """获取所有维度"""
        return {k: list(v) for k, v in self.dimensions.items()}
    
    def clear(self):
        """清除所有指标"""
        self.metrics.clear()
        self.dimensions.clear()

def setup_event_bus(env: str = None) -> OptimizedEventBus:
    """
    设置事件总线
    
    Args:
        env: 运行环境('development', 'production', 'testing')
        
    Returns:
        OptimizedEventBus: 事件总线实例
    """
    # 确定配置文件路径
    if env:
        config_file = f"config/event_bus.{env}.yaml"
    else:
        config_file = "config/event_bus.yaml"
    
    # 初始化日志
    init_logging()
    
    # 设置Prometheus指标导出
    if HAS_PROMETHEUS:
        setup_prometheus()
    
    # 创建事件总线实例
    event_bus = OptimizedEventBus(config_file=config_file)
    
    # 注册默认处理器
    _register_default_handlers(event_bus)
    
    return event_bus

def _register_default_handlers(event_bus: OptimizedEventBus):
    """注册默认事件处理器"""
    # 系统事件处理器
    @event_bus.router.add_route("SYSTEM.*")
    def handle_system_event(event):
        logging.info(f"系统事件: {event}")
    
    # 错误事件处理器
    @event_bus.router.add_route("ERROR")
    def handle_error_event(event):
        logging.error(f"错误事件: {event}")
    
    # 紧急事件处理器
    @event_bus.router.add_route("EMERGENCY")
    def handle_emergency_event(event):
        logging.critical(f"紧急事件: {event}")

if __name__ == "__main__":
    # 设置事件总线
    event_bus = setup_event_bus("config/event_bus.yaml")
    
    try:
        # 启动事件总线
        asyncio.run(event_bus.start())
        
        # 等待终止信号
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        # 停止事件总线
        asyncio.run(event_bus.stop())
        logging.info("事件总线已停止")
class OptimizedEventBus(EventBus):
    async def start(self):
        """启动事件总线"""
        try:
            # 初始化组件
            self.logger.info(f"正在启动事件总线: {self.name}")
            
            # 启动集群（如果启用）
            if self.config.get('cluster.enabled', False):
                await self.cluster.start()
            
            # 启动工作线程池
            self.worker_pool = ThreadPoolExecutor(
                max_workers=self.config.get('worker_threads', 4),
                thread_name_prefix=f"event_bus_{self.name}"
            )
            
            # 启动处理循环
            self._running = True
            self.processing_task = asyncio.create_task(self._processing_loop())
            
            # 启动QoS控制器
            self.qos_task = asyncio.create_task(self._qos_loop())
            
            # 启动指标收集
            if HAS_PROMETHEUS:
                self.metrics_task = asyncio.create_task(self._metrics_loop())
            
            self.logger.info(f"事件总线已启动: {self.name}")
            
        except Exception as e:
            self.logger.error(f"启动事件总线失败: {str(e)}")
            raise

    async def stop(self):
        """停止事件总线"""
        try:
            self.logger.info(f"正在停止事件总线: {self.name}")
            
            # 停止处理循环
            self._running = False
            
            # 等待任务完成
            if hasattr(self, 'processing_task'):
                await self.processing_task
            if hasattr(self, 'qos_task'):
                await self.qos_task
            if hasattr(self, 'metrics_task'):
                await self.metrics_task
            
            # 停止集群
            if hasattr(self, 'cluster'):
                await self.cluster.stop()
            
            # 关闭工作线程池
            if hasattr(self, 'worker_pool'):
                self.worker_pool.shutdown(wait=True)
            
            # 清理资源
            self.urgent_queue.clear()
            self.normal_queue.clear()
            self.handlers.clear()
            
            self.logger.info(f"事件总线已停止: {self.name}")
            
        except Exception as e:
            self.logger.error(f"停止事件总线失败: {str(e)}")
            raise
class OptimizedEventBus(EventBus):
    async def _processing_loop(self):
        """事件处理主循环"""
        while self._running:
            try:
                # 处理紧急队列
                while not self.urgent_queue.empty():
                    event = await self.urgent_queue.get()
                    await self._process_event(event, is_urgent=True)
                
                # 处理普通队列
                if not self.normal_queue.empty():
                    # 批量处理
                    batch = []
                    batch_size = self.current_batch_size
                    
                    while len(batch) < batch_size and not self.normal_queue.empty():
                        event = await self.normal_queue.get()
                        batch.append(event)
                    
                    # 并行处理批次
                    await asyncio.gather(*[
                        self._process_event(event)
                        for event in batch
                    ])
                
                # 短暂休眠以避免CPU过载
                await asyncio.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"事件处理循环异常: {str(e)}")
                await asyncio.sleep(1)

    async def _process_event(self, event: Event, is_urgent: bool = False):
        """处理单个事件"""
        try:
            start_time = time.perf_counter()
            
            # 事件验证
            if not self.validator.validate(event):
                self.logger.warning(f"事件验证失败: {event}")
                return
            
            # 事件过滤
            event = self.filter.process(event)
            if not event:
                return
            
            # 事件路由和处理
            await self.router.route(event)
            
            # 记录处理时间
            processing_time = time.perf_counter() - start_time
            self.metrics.record_time(
                'event_processing_time',
                processing_time,
                {'event_type': event.event_type, 'urgent': is_urgent}
            )
            
        except Exception as e:
            self.logger.error(f"处理事件失败: {str(e)}")
            self.metrics.record('event_processing_errors', 1)
class OptimizedEventBus(EventBus):
    async def _qos_loop(self):
        """QoS控制循环"""
        while self._running:
            try:
                # 收集指标
                metrics = {
                    'urgent_queue_size': self.urgent_queue.qsize(),
                    'normal_queue_size': self.normal_queue.qsize(),
                    'processing_time': self.metrics.get_metrics().get('event_processing_time', 0),
                    'error_rate': self.metrics.get_metrics().get('event_processing_errors', 0) / \
                                max(1, self.metrics.get_metrics().get('events_processed', 1))
                }
                
                # 更新控制参数
                adjustments = self.adaptive_controller.update(metrics)
                
                # 应用调整
                if 'batch_size' in adjustments:
                    self.current_batch_size = adjustments['batch_size']
                
                await asyncio.sleep(1)  # 每秒更新一次
                
            except Exception as e:
                self.logger.error(f"QoS控制循环异常: {str(e)}")
                await asyncio.sleep(1)
class OptimizedEventBus(EventBus):
    async def _metrics_loop(self):
        """指标收集循环"""
        while self._running:
            try:
                # 更新Prometheus指标
                QUEUE_SIZE.labels(queue='urgent').set(self.urgent_queue.qsize())
                QUEUE_SIZE.labels(queue='normal').set(self.normal_queue.qsize())
                
                metrics = self.metrics.get_metrics()
                for name, value in metrics.items():
                    if isinstance(value, (int, float)):
                        EVENT_BUS_METRICS.labels(metric=name).set(value)
                
                await asyncio.sleep(1)  # 每秒更新一次
                
            except Exception as e:
                self.logger.error(f"指标收集循环异常: {str(e)}")
                await asyncio.sleep(1)