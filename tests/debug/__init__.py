#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 调试测试包

提供调试和监控测试所需的通用工具和基础设施:
- 调试工具类
- 追踪装饰器
- 监控工具类
- 测试数据生成器
"""

import time
import logging
import functools
import traceback
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime
from contextlib import contextmanager

# 配置日志
logger = logging.getLogger(__name__)

class DebugMixin:
    """调试工具混入类"""
    
    def __init__(self):
        self._debug_enabled = False
        self._debug_logs = []
        self._debug_start_time = None
    
    def enable_debug(self):
        """启用调试模式"""
        self._debug_enabled = True
        self._debug_start_time = time.time()
        logger.info("调试模式已启用")
    
    def disable_debug(self):
        """禁用调试模式"""
        self._debug_enabled = False
        self._debug_start_time = None
        logger.info("调试模式已禁用")
    
    def log_debug(self, message: str, data: Dict = None):
        """记录调试日志"""
        if self._debug_enabled:
            timestamp = time.time()
            elapsed = timestamp - self._debug_start_time if self._debug_start_time else 0
            log_entry = {
                'timestamp': timestamp,
                'elapsed': elapsed,
                'message': message,
                'data': data or {}
            }
            self._debug_logs.append(log_entry)
            logger.debug(f"{message} - {data}")
    
    def get_debug_logs(self) -> List[Dict]:
        """获取调试日志"""
        return self._debug_logs
    
    def clear_debug_logs(self):
        """清除调试日志"""
        self._debug_logs.clear()

def trace(name: str = None):
    """函数追踪装饰器"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            trace_id = name or func.__name__
            logger.debug(f"[TRACE] {trace_id} - 开始执行")
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(f"[TRACE] {trace_id} - 执行完成 - 耗时: {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"[TRACE] {trace_id} - 执行异常 - 耗时: {elapsed:.3f}s")
                logger.error(f"异常信息: {str(e)}")
                logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            trace_id = name or func.__name__
            logger.debug(f"[TRACE] {trace_id} - 开始执行")
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(f"[TRACE] {trace_id} - 执行完成 - 耗时: {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"[TRACE] {trace_id} - 执行异常 - 耗时: {elapsed:.3f}s")
                logger.error(f"异常信息: {str(e)}")
                logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

class MonitoringMixin:
    """监控工具混入类"""
    
    def __init__(self):
        self._metrics = {}
        self._start_times = {}
        self._monitors = {}
    
    def start_monitor(self, name: str):
        """启动监控点"""
        self._start_times[name] = time.time()
    
    def end_monitor(self, name: str) -> float:
        """结束监控点并返回耗时"""
        if name in self._start_times:
            elapsed = time.time() - self._start_times[name]
            if name not in self._metrics:
                self._metrics[name] = []
            self._metrics[name].append(elapsed)
            return elapsed
        return 0
    
    def record_metric(self, name: str, value: float):
        """记录指标"""
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(value)
    
    def get_metrics(self, name: str = None) -> Union[List[float], Dict[str, List[float]]]:
        """获取指标"""
        if name:
            return self._metrics.get(name, [])
        return self._metrics
    
    def clear_metrics(self):
        """清除指标"""
        self._metrics.clear()
        self._start_times.clear()

@contextmanager
def monitor_block(name: str = None):
    """监控代码块的上下文管理器"""
    start_time = time.time()
    block_name = name or 'block'
    logger.debug(f"[MONITOR] {block_name} - 开始")
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        logger.debug(f"[MONITOR] {block_name} - 结束 - 耗时: {elapsed:.3f}s")

class TestDataGenerator:
    """测试数据生成器"""
    
    @staticmethod
    def generate_event_data(event_type: str, **kwargs) -> Dict:
        """生成事件数据"""
        return {
            'event_type': event_type,
            'timestamp': time.time(),
            'data': kwargs,
            'trace_id': f"trace_{int(time.time() * 1000)}"
        }
    
    @staticmethod
    def generate_metric_data(metric_type: str, value: float, **kwargs) -> Dict:
        """生成指标数据"""
        return {
            'metric_type': metric_type,
            'value': value,
            'timestamp': time.time(),
            'attributes': kwargs
        }
    
    @staticmethod
    def generate_monitor_data(monitor_type: str, status: str, **kwargs) -> Dict:
        """生成监控数据"""
        return {
            'monitor_type': monitor_type,
            'status': status,
            'timestamp': time.time(),
            'details': kwargs
        }

# 导入必要的模块
import asyncio
from tests import AsyncTestCase, async_test

__all__ = [
    'DebugMixin',
    'trace',
    'MonitoringMixin',
    'monitor_block',
    'TestDataGenerator',
    'AsyncTestCase',
    'async_test'
]