#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 断路器模块

实现交易系统的断路器功能，用于在系统出现异常情况时自动暂停交易活动，
防止可能的损失和风险，并在条件恢复后自动或手动恢复交易功能。

断路器状态：
- CLOSED: 正常状态，允许交易操作
- OPEN: 触发状态，阻止所有交易操作
- HALF_OPEN: 恢复探测状态，允许有限的交易操作以测试系统是否恢复正常

触发条件可以是：
- 连续失败次数超过阈值
- 失败率超过阈值
- 资金或持仓异常波动
- 外部市场异常信号
- 系统性能指标（如延迟）超过阈值
"""

import time
import logging
import threading
import functools
from enum import Enum
from typing import Optional, Callable, Dict, Any, List, Union, Tuple
from datetime import datetime, timedelta

from utils.logging_utils import get_logger

logger = get_logger("CircuitBreaker")


class CircuitState(Enum):
    """断路器状态枚举"""
    CLOSED = "CLOSED"        # 闭合状态 - 正常运行
    OPEN = "OPEN"            # 断开状态 - 阻断所有请求
    HALF_OPEN = "HALF_OPEN"  # 半开状态 - 尝试恢复


class CircuitBreaker:
    """交易系统断路器实现"""

    def __init__(self, 
                 failure_threshold: int = 5, 
                 recovery_timeout: int = 60,
                 half_open_max_calls: int = 3,
                 name: str = "default",
                 excluded_exceptions: Optional[List[Exception]] = None,
                 on_open: Optional[Callable] = None,
                 on_close: Optional[Callable] = None):
        """
        初始化断路器
        
        Args:
            failure_threshold: 连续失败阈值，达到此值将开启断路器
            recovery_timeout: 恢复超时(秒)，断路器开启后等待恢复的时间
            half_open_max_calls: 半开状态下允许的最大调用次数
            name: 断路器名称，用于日志和监控
            excluded_exceptions: 不计入失败的异常类型列表
            on_open: 断路器开启时的回调函数
            on_close: 断路器关闭时的回调函数
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.excluded_exceptions = excluded_exceptions or []
        self.on_open = on_open
        self.on_close = on_close

        # 断路器状态
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._successful_calls = 0
        self._half_open_calls = 0
        
        # 防止并发问题
        self._lock = threading.RLock()
        
        # 记录上次操作
        self._last_state_change = datetime.now()
        self._last_state_reason = "初始化"
        
        # 记录被阻断的操作
        self._blocked_operations = 0
        
        # 统计信息
        self._stats = {
            "total_failures": 0,
            "total_successes": 0,
            "open_triggers": 0,
            "blocked_operations": 0,
            "last_recovery_time": None,
            "state_changes": []  # [(timestamp, from_state, to_state, reason)]
        }
        
        logger.info(f"断路器[{self.name}]已初始化: 阈值={failure_threshold}, 恢复时间={recovery_timeout}秒")

    @property
    def state(self) -> CircuitState:
        """获取当前断路器状态"""
        return self._state
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取断路器统计信息"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "last_failure_time": self._last_failure_time,
                "last_state_change": self._last_state_change,
                "last_state_reason": self._last_state_reason,
                "blocked_operations": self._blocked_operations,
                "statistics": self._stats
            }

    def reset(self) -> None:
        """重置断路器状态"""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._successful_calls = 0
            self._half_open_calls = 0
            
            # 记录状态变化
            self._record_state_change(old_state, self._state, "手动重置")
            
            logger.info(f"断路器[{self.name}]已重置为CLOSED状态")

    def open(self, reason: str = "手动触发") -> None:
        """手动开启断路器"""
        with self._lock:
            if self._state != CircuitState.OPEN:
                old_state = self._state
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()
                
                # 记录状态变化
                self._record_state_change(old_state, self._state, reason)
                
                logger.warning(f"断路器[{self.name}]手动开启: {reason}")
                
                # 触发回调
                if self.on_open:
                    try:
                        self.on_open(self)
                    except Exception as e:
                        logger.error(f"断路器[{self.name}]开启回调发生异常: {str(e)}")

    def close(self, reason: str = "手动关闭") -> None:
        """手动关闭断路器"""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                old_state = self._state
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                
                # 记录状态变化
                self._record_state_change(old_state, self._state, reason)
                
                logger.info(f"断路器[{self.name}]手动关闭: {reason}")
                
                # 触发回调
                if self.on_close:
                    try:
                        self.on_close(self)
                    except Exception as e:
                        logger.error(f"断路器[{self.name}]关闭回调发生异常: {str(e)}")

    def half_open(self, reason: str = "手动半开") -> None:
        """手动设置断路器为半开状态"""
        with self._lock:
            if self._state != CircuitState.HALF_OPEN:
                old_state = self._state
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                
                # 记录状态变化
                self._record_state_change(old_state, self._state, reason)
                
                logger.info(f"断路器[{self.name}]设置为半开状态: {reason}")

    def _record_state_change(self, from_state: CircuitState, to_state: CircuitState, reason: str) -> None:
        """记录状态变化"""
        self._last_state_change = datetime.now()
        self._last_state_reason = reason
        self._stats["state_changes"].append((
            datetime.now(),
            from_state.value,
            to_state.value,
            reason
        ))
        
        # 保持状态变化历史在合理范围内
        if len(self._stats["state_changes"]) > 100:
            self._stats["state_changes"] = self._stats["state_changes"][-100:]

    def _check_state(self) -> bool:
        """
        检查断路器状态，判断是否允许操作
        
        Returns:
            bool: 是否允许操作
        """
        with self._lock:
            # 闭合状态直接允许
            if self._state == CircuitState.CLOSED:
                return True
                
            # 断开状态检查是否超过恢复时间
            if self._state == CircuitState.OPEN:
                if self._last_failure_time is None:
                    # 异常情况，重置为半开状态
                    old_state = self._state
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._record_state_change(old_state, self._state, "恢复时间记录丢失")
                    logger.warning(f"断路器[{self.name}]状态异常(无最后失败时间)，重置为半开状态")
                    return True
                
                # 检查是否达到恢复时间
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    # 达到恢复时间，切换到半开状态
                    old_state = self._state
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._record_state_change(old_state, self._state, f"达到恢复时间({self.recovery_timeout}秒)")
                    logger.info(f"断路器[{self.name}]切换到半开状态，开始尝试恢复")
                    return True
                else:
                    # 未达到恢复时间，继续阻断
                    self._blocked_operations += 1
                    self._stats["blocked_operations"] += 1
                    return False
            
            # 半开状态检查是否超过最大调用次数
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                else:
                    # 达到最大调用次数但未恢复，继续阻断
                    self._blocked_operations += 1
                    self._stats["blocked_operations"] += 1
                    return False
                
            # 未知状态，默认允许并记录警告
            logger.warning(f"断路器[{self.name}]状态未知: {self._state}")
            return True

    def _on_success(self) -> None:
        """处理成功调用"""
        with self._lock:
            self._stats["total_successes"] += 1
            
            # 闭合状态下重置失败计数
            if self._state == CircuitState.CLOSED:
                self._failure_count = 0
                return
                
            # 半开状态下增加成功计数
            if self._state == CircuitState.HALF_OPEN:
                self._successful_calls += 1
                
                # 达到恢复阈值，关闭断路器
                if self._successful_calls >= self.half_open_max_calls:
                    old_state = self._state
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._successful_calls = 0
                    self._half_open_calls = 0
                    self._stats["last_recovery_time"] = datetime.now()
                    
                    # 记录状态变化
                    self._record_state_change(old_state, self._state, "半开状态下成功恢复")
                    
                    logger.info(f"断路器[{self.name}]已恢复正常(关闭)")
                    
                    # 触发回调
                    if self.on_close:
                        try:
                            self.on_close(self)
                        except Exception as e:
                            logger.error(f"断路器[{self.name}]关闭回调发生异常: {str(e)}")

    def _on_failure(self, exception: Exception) -> None:
        """处理失败调用"""
        with self._lock:
            # 检查是否为排除的异常
            for excluded in self.excluded_exceptions:
                if isinstance(exception, excluded):
                    logger.debug(f"断路器[{self.name}]忽略排除的异常: {type(exception).__name__}")
                    return
                    
            self._stats["total_failures"] += 1
            self._last_failure_time = time.time()
            
            # 半开状态下失败立即开启断路器
            if self._state == CircuitState.HALF_OPEN:
                old_state = self._state
                self._state = CircuitState.OPEN
                self._stats["open_triggers"] += 1
                
                # 记录状态变化
                self._record_state_change(old_state, self._state, f"半开状态调用失败: {type(exception).__name__}")
                
                logger.warning(f"断路器[{self.name}]在半开状态下调用失败，重新开启: {str(exception)}")
                
                # 触发回调
                if self.on_open:
                    try:
                        self.on_open(self)
                    except Exception as e:
                        logger.error(f"断路器[{self.name}]开启回调发生异常: {str(e)}")
                return
                
            # 闭合状态下增加失败计数
            if self._state == CircuitState.CLOSED:
                self._failure_count += 1
                
                # 检查是否达到阈值
                if self._failure_count >= self.failure_threshold:
                    old_state = self._state
                    self._state = CircuitState.OPEN
                    self._stats["open_triggers"] += 1
                    
                    # 记录状态变化
                    self._record_state_change(
                        old_state, 
                        self._state, 
                        f"连续失败次数({self._failure_count})达到阈值({self.failure_threshold})"
                    )
                    
                    logger.warning(
                        f"断路器[{self.name}]开启: 连续失败{self._failure_count}次，最后错误: {type(exception).__name__}: {str(exception)}"
                    )
                    
                    # 触发回调
                    if self.on_open:
                        try:
                            self.on_open(self)
                        except Exception as e:
                            logger.error(f"断路器[{self.name}]开启回调发生异常: {str(e)}")

    def execute(self, func, *args, **kwargs):
        """执行函数并应用断路器逻辑"""
        if not self._check_state():
            raise CircuitBreakerError(f"断路器[{self.name}]开启状态，拒绝执行操作")
            
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise

    def __call__(self, func):
        """装饰器接口"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.execute(func, *args, **kwargs)
        return wrapper


class CircuitBreakerError(Exception):
    """断路器开启时的错误"""
    pass