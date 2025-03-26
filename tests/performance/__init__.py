#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 性能测试包

提供性能测试所需的基础设施:
- 性能测试基类
- 性能指标收集器
- 性能分析工具
- 负载生成器
"""

import os
import sys
import time
import psutil
import asyncio
import logging
import tracemalloc
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime
from functools import wraps
from contextlib import contextmanager
from statistics import mean, median, stdev
import numpy as np

from tests import AsyncTestCase, async_test
from prometheus_client import Counter, Gauge, Histogram

# 配置日志
logger = logging.getLogger(__name__)

# 性能指标
LATENCY_HISTOGRAM = Histogram('test_latency_seconds', '操作延迟分布', ['operation'])
MEMORY_GAUGE = Gauge('test_memory_bytes', '内存使用量', ['type'])
CPU_GAUGE = Gauge('test_cpu_percent', 'CPU使用率')
OPERATION_COUNTER = Counter('test_operations_total', '操作计数', ['operation'])

class PerformanceTestCase(AsyncTestCase):
    """性能测试基类"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = {}
        self.start_time = None
        self.tracemalloc_enabled = False
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.start_time = time.time()
        
        # 启动性能监控
        self._start_monitoring()
    
    async def asyncTearDown(self):
        """异步测试清理"""
        # 停止性能监控
        self._stop_monitoring()
        
        # 记录测试持续时间
        duration = time.time() - self.start_time
        logger.info(f"性能测试执行时间: {duration:.2f}秒")
        
        await super().asyncTearDown()
    
    def _start_monitoring(self):
        """启动性能监控"""
        # 启动内存跟踪
        tracemalloc.start()
        self.tracemalloc_enabled = True
        
        # 记录初始状态
        self.metrics['start'] = {
            'memory': psutil.Process().memory_info().rss,
            'cpu_percent': psutil.Process().cpu_percent(),
            'tracemalloc': tracemalloc.take_snapshot()
        }
        
        MEMORY_GAUGE.labels(type='start').set(self.metrics['start']['memory'])
    
    def _stop_monitoring(self):
        """停止性能监控"""
        # 记录最终状态
        self.metrics['end'] = {
            'memory': psutil.Process().memory_info().rss,
            'cpu_percent': psutil.Process().cpu_percent(),
            'tracemalloc': tracemalloc.take_snapshot()
        }
        
        MEMORY_GAUGE.labels(type='end').set(self.metrics['end']['memory'])
        
        # 停止内存跟踪
        if self.tracemalloc_enabled:
            tracemalloc.stop()
    
    def get_memory_stats(self) -> Dict:
        """获取内存统计信息"""
        if not self.tracemalloc_enabled:
            return {}
            
        current = self.metrics['end']['tracemalloc']
        start = self.metrics['start']['tracemalloc']
        diff = current.compare_to(start, 'lineno')
        
        return {
            'start_memory': self.metrics['start']['memory'],
            'end_memory': self.metrics['end']['memory'],
            'diff_memory': self.metrics['end']['memory'] - self.metrics['start']['memory'],
            'top_allocations': [
                {
                    'file': str(stat.traceback[0]),
                    'line': stat.traceback[0].lineno,
                    'size': stat.size,
                    'count': stat.count
                }
                for stat in diff[:10]  # 前10个最大的内存分配
            ]
        }
    
    def get_cpu_stats(self) -> Dict:
        """获取CPU统计信息"""
        return {
            'start_cpu': self.metrics['start']['cpu_percent'],
            'end_cpu': self.metrics['end']['cpu_percent'],
            'diff_cpu': self.metrics['end']['cpu_percent'] - self.metrics['start']['cpu_percent']
        }

class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self):
        self.latencies = defaultdict(list)
        self.memory_samples = []
        self.cpu_samples = []
        self.operation_counts = defaultdict(int)
    
    def record_latency(self, operation: str, latency: float):
        """记录延迟"""
        self.latencies[operation].append(latency)
        LATENCY_HISTOGRAM.labels(operation=operation).observe(latency)
    
    def record_memory(self, memory: int):
        """记录内存使用"""
        self.memory_samples.append(memory)
        MEMORY_GAUGE.labels(type='current').set(memory)
    
    def record_cpu(self, cpu_percent: float):
        """记录CPU使用率"""
        self.cpu_samples.append(cpu_percent)
        CPU_GAUGE.set(cpu_percent)
    
    def record_operation(self, operation: str):
        """记录操作计数"""
        self.operation_counts[operation] += 1
        OPERATION_COUNTER.labels(operation=operation).inc()
    
    def get_latency_stats(self, operation: str = None) -> Dict:
        """获取延迟统计信息"""
        if operation:
            samples = self.latencies[operation]
        else:
            samples = [lat for lats in self.latencies.values() for lat in lats]
            
        if not samples:
            return {}
            
        return {
            'min': min(samples),
            'max': max(samples),
            'mean': mean(samples),
            'median': median(samples),
            'stddev': stdev(samples) if len(samples) > 1 else 0,
            'p95': np.percentile(samples, 95),
            'p99': np.percentile(samples, 99),
            'count': len(samples)
        }
    
    def get_memory_stats(self) -> Dict:
        """获取内存统计信息"""
        if not self.memory_samples:
            return {}
            
        return {
            'min': min(self.memory_samples),
            'max': max(self.memory_samples),
            'mean': mean(self.memory_samples),
            'current': self.memory_samples[-1]
        }
    
    def get_cpu_stats(self) -> Dict:
        """获取CPU统计信息"""
        if not self.cpu_samples:
            return {}
            
        return {
            'min': min(self.cpu_samples),
            'max': max(self.cpu_samples),
            'mean': mean(self.cpu_samples),
            'current': self.cpu_samples[-1]
        }

class LoadGenerator:
    """负载生成器"""
    
    def __init__(self, metrics: PerformanceMetrics = None):
        self.metrics = metrics or PerformanceMetrics()
        self._running = False
    
    async def start_load(self, operations: List[Tuple[Callable, Dict]], 
                        duration: float = None,
                        rate: float = None):
        """
        启动负载生成
        
        Args:
            operations: 要执行的操作列表，每个元素是(函数, 参数字典)的元组
            duration: 持续时间（秒）
            rate: 每秒执行的操作数
        """
        self._running = True
        start_time = time.time()
        
        try:
            if rate:
                interval = 1.0 / rate
            else:
                interval = 0
                
            while self._running:
                if duration and time.time() - start_time > duration:
                    break
                    
                for op, params in operations:
                    if not self._running:
                        break
                        
                    try:
                        await op(**params)
                    except Exception as e:
                        logger.error(f"负载操作执行失败: {str(e)}")
                    
                    if interval:
                        await asyncio.sleep(interval)
                        
        finally:
            self._running = False
    
    def stop_load(self):
        """停止负载生成"""
        self._running = False

def measure_performance(operation: str = None):
    """性能测量装饰器"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not hasattr(args[0], 'metrics'):
                args[0].metrics = PerformanceMetrics()
            
            op_name = operation or func.__name__
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                args[0].metrics.record_latency(op_name, duration)
                args[0].metrics.record_operation(op_name)
                return result
            except Exception:
                args[0].metrics.record_operation(f"{op_name}_error")
                raise
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not hasattr(args[0], 'metrics'):
                args[0].metrics = PerformanceMetrics()
            
            op_name = operation or func.__name__
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                args[0].metrics.record_latency(op_name, duration)
                args[0].metrics.record_operation(op_name)
                return result
            except Exception:
                args[0].metrics.record_operation(f"{op_name}_error")
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

@contextmanager
def track_memory():
    """内存跟踪上下文管理器"""
    tracemalloc.start()
    start_snapshot = tracemalloc.take_snapshot()
    
    try:
        yield
    finally:
        end_snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()
        
        diff = end_snapshot.compare_to(start_snapshot, 'lineno')
        for stat in diff[:10]:  # 输出前10个最大的内存分配
            logger.info(f"{stat.size_diff} bytes: {stat.traceback[0]}")

# 导出的类和函数
__all__ = [
    'PerformanceTestCase',
    'PerformanceMetrics',
    'LoadGenerator',
    'measure_performance',
    'track_memory'
]