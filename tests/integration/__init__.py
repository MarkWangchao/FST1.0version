#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 集成测试包

提供集成测试所需的基础设施:
- 集成测试基类
- 测试环境管理
- 测试数据生成器
- 测试结果验证器
"""

import os
import sys
import json
import time
import asyncio
import logging
import unittest
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

from tests import AsyncTestCase, async_test
from infrastructure.event_bus.event_manager import Event, EventType

# 配置日志
logger = logging.getLogger(__name__)

class IntegrationTestCase(AsyncTestCase):
    """集成测试基类"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_data = {}
        self.test_events = []
        self.cleanup_tasks = []
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.start_time = time.time()
        
        # 初始化测试环境
        await self._init_test_env()
        
        # 注册事件监听器
        await self._register_event_listeners()
    
    async def asyncTearDown(self):
        """异步测试清理"""
        # 执行清理任务
        for cleanup in self.cleanup_tasks:
            try:
                await cleanup()
            except Exception as e:
                logger.error(f"清理任务失败: {str(e)}")
        
        # 取消事件监听器
        await self._unregister_event_listeners()
        
        # 清理测试环境
        await self._cleanup_test_env()
        
        await super().asyncTearDown()
    
    async def _init_test_env(self):
        """初始化测试环境"""
        # 子类可以重写此方法以进行特定的环境初始化
        pass
    
    async def _cleanup_test_env(self):
        """清理测试环境"""
        # 子类可以重写此方法以进行特定的环境清理
        pass
    
    async def _register_event_listeners(self):
        """注册事件监听器"""
        # 子类可以重写此方法以注册特定的事件监听器
        pass
    
    async def _unregister_event_listeners(self):
        """取消事件监听器"""
        # 子类可以重写此方法以取消特定的事件监听器
        pass
    
    def add_cleanup(self, cleanup: Callable):
        """添加清理任务"""
        self.cleanup_tasks.append(cleanup)
    
    async def wait_for_event(self, event_type: EventType, timeout: float = 5.0) -> Optional[Event]:
        """等待特定类型的事件"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            for event in self.test_events:
                if event.event_type == event_type:
                    self.test_events.remove(event)
                    return event
            await asyncio.sleep(0.1)
        return None
    
    async def wait_for_condition(self, condition: Callable[[], bool], 
                               timeout: float = 5.0, 
                               message: str = None) -> bool:
        """等待条件满足"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition():
                return True
            await asyncio.sleep(0.1)
        
        if message:
            logger.warning(f"等待条件超时: {message}")
        return False

class TestEnvironment:
    """测试环境管理器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.resources = {}
        self.start_time = None
        self.end_time = None
    
    async def setup(self):
        """设置测试环境"""
        self.start_time = time.time()
        logger.info("正在设置测试环境...")
        
        # 初始化资源
        for resource_name, resource_config in self.config.get('resources', {}).items():
            try:
                await self._init_resource(resource_name, resource_config)
            except Exception as e:
                logger.error(f"初始化资源 {resource_name} 失败: {str(e)}")
                raise
    
    async def teardown(self):
        """清理测试环境"""
        logger.info("正在清理测试环境...")
        
        # 清理资源
        for resource_name in reversed(list(self.resources.keys())):
            try:
                await self._cleanup_resource(resource_name)
            except Exception as e:
                logger.error(f"清理资源 {resource_name} 失败: {str(e)}")
        
        self.end_time = time.time()
    
    async def _init_resource(self, name: str, config: Dict):
        """初始化资源"""
        # 子类应该实现具体的资源初始化逻辑
        pass
    
    async def _cleanup_resource(self, name: str):
        """清理资源"""
        # 子类应该实现具体的资源清理逻辑
        pass
    
    def get_resource(self, name: str) -> Any:
        """获取资源"""
        return self.resources.get(name)
    
    def get_stats(self) -> Dict:
        """获取环境统计信息"""
        return {
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.end_time - self.start_time if self.end_time else 0,
            'resources': list(self.resources.keys())
        }

class TestDataGenerator:
    """测试数据生成器"""
    
    @staticmethod
    def generate_market_data(symbol: str, 
                           start_time: datetime,
                           end_time: datetime,
                           interval: str = '1m') -> List[Dict]:
        """生成市场数据"""
        # TODO: 实现市场数据生成逻辑
        pass
    
    @staticmethod
    def generate_order_data(count: int = 10) -> List[Dict]:
        """生成订单数据"""
        # TODO: 实现订单数据生成逻辑
        pass
    
    @staticmethod
    def generate_trade_data(count: int = 10) -> List[Dict]:
        """生成成交数据"""
        # TODO: 实现成交数据生成逻辑
        pass

class TestResultValidator:
    """测试结果验证器"""
    
    def __init__(self):
        self.validations = []
        self.failures = []
    
    def add_validation(self, name: str, condition: Callable[[], bool], message: str = None):
        """添加验证条件"""
        self.validations.append({
            'name': name,
            'condition': condition,
            'message': message
        })
    
    def validate_all(self) -> bool:
        """执行所有验证"""
        self.failures.clear()
        success = True
        
        for validation in self.validations:
            try:
                if not validation['condition']():
                    self.failures.append({
                        'name': validation['name'],
                        'message': validation['message'] or '验证失败'
                    })
                    success = False
            except Exception as e:
                self.failures.append({
                    'name': validation['name'],
                    'message': f"验证过程出错: {str(e)}"
                })
                success = False
        
        return success
    
    def get_failures(self) -> List[Dict]:
        """获取失败的验证"""
        return self.failures

def integration_test(timeout: float = None):
    """集成测试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                if timeout:
                    return await asyncio.wait_for(func(*args, **kwargs), timeout)
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                logger.info(f"集成测试 {func.__name__} 执行完成，耗时: {duration:.2f}秒")
        return wrapper
    return decorator

@contextmanager
def mock_resource(resource_name: str, mock_obj: Any):
    """资源模拟上下文管理器"""
    original = None
    if hasattr(sys.modules[__name__], resource_name):
        original = getattr(sys.modules[__name__], resource_name)
    setattr(sys.modules[__name__], resource_name, mock_obj)
    try:
        yield mock_obj
    finally:
        if original is not None:
            setattr(sys.modules[__name__], resource_name, original)
        else:
            delattr(sys.modules[__name__], resource_name)

# 导出的类和函数
__all__ = [
    'IntegrationTestCase',
    'TestEnvironment',
    'TestDataGenerator',
    'TestResultValidator',
    'integration_test',
    'mock_resource'
]