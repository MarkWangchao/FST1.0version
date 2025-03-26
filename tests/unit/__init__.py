#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 单元测试包

提供单元测试所需的基础设施:
- 单元测试基类
- Mock工具
- 数据构建器
- 断言增强
"""

import os
import sys
import json
import asyncio
import logging
import unittest
from typing import Dict, List, Optional, Any, Callable, Type, Union
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from functools import wraps

from tests import AsyncTestCase, async_test

# 配置日志
logger = logging.getLogger(__name__)

class UnitTestCase(AsyncTestCase):
    """单元测试基类"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mocks = {}
        self.patches = []
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        # 初始化测试环境
        self._setup_mocks()
    
    async def asyncTearDown(self):
        """异步测试清理"""
        # 清理所有patch
        for p in self.patches:
            p.stop()
        self.patches.clear()
        
        # 清理所有mock
        self.mocks.clear()
        
        await super().asyncTearDown()
    
    def _setup_mocks(self):
        """设置Mock对象"""
        pass
    
    def add_mock(self, target: str, **kwargs) -> Mock:
        """添加Mock对象"""
        mock = Mock(**kwargs)
        self.mocks[target] = mock
        return mock
    
    def add_async_mock(self, target: str, **kwargs) -> AsyncMock:
        """添加异步Mock对象"""
        mock = AsyncMock(**kwargs)
        self.mocks[target] = mock
        return mock
    
    def patch_object(self, target: object, attribute: str, new: Any = None, **kwargs) -> Mock:
        """Patch对象的属性"""
        patcher = patch.object(target, attribute, new=new, **kwargs)
        mock = patcher.start()
        self.patches.append(patcher)
        return mock
    
    def patch_dict(self, target: Dict, values: Dict, clear: bool = False) -> None:
        """Patch字典"""
        patcher = patch.dict(target, values, clear=clear)
        patcher.start()
        self.patches.append(patcher)

class TestDataBuilder:
    """测试数据构建器"""
    
    @staticmethod
    def build_event(event_type: str, data: Dict = None, **kwargs) -> Dict:
        """构建事件数据"""
        return {
            'event_type': event_type,
            'data': data or {},
            'timestamp': datetime.now().isoformat(),
            'source': kwargs.get('source', 'test'),
            'version': kwargs.get('version', '1.0'),
            **kwargs
        }
    
    @staticmethod
    def build_order(symbol: str, direction: str, volume: float, **kwargs) -> Dict:
        """构建订单数据"""
        return {
            'order_id': kwargs.get('order_id', f"ORDER_{int(time.time()*1000)}"),
            'symbol': symbol,
            'direction': direction,
            'volume': volume,
            'price': kwargs.get('price'),
            'order_type': kwargs.get('order_type', 'LIMIT'),
            'status': kwargs.get('status', 'PENDING'),
            'create_time': kwargs.get('create_time', datetime.now().isoformat()),
            **kwargs
        }
    
    @staticmethod
    def build_trade(order: Dict, price: float, volume: float, **kwargs) -> Dict:
        """构建成交数据"""
        return {
            'trade_id': kwargs.get('trade_id', f"TRADE_{int(time.time()*1000)}"),
            'order_id': order['order_id'],
            'symbol': order['symbol'],
            'direction': order['direction'],
            'price': price,
            'volume': volume,
            'trade_time': kwargs.get('trade_time', datetime.now().isoformat()),
            **kwargs
        }
    
    @staticmethod
    def build_position(symbol: str, direction: str, volume: float, **kwargs) -> Dict:
        """构建持仓数据"""
        return {
            'symbol': symbol,
            'direction': direction,
            'volume': volume,
            'open_price': kwargs.get('open_price', 0.0),
            'position_time': kwargs.get('position_time', datetime.now().isoformat()),
            **kwargs
        }

class EnhancedAssertions:
    """增强的断言方法"""
    
    def assertDictContains(self, dict1: Dict, dict2: Dict, msg: str = None):
        """断言dict1包含dict2的所有键值对"""
        for key, value in dict2.items():
            self.assertIn(key, dict1, msg=msg)
            self.assertEqual(dict1[key], value, msg=msg)
    
    def assertDictMatches(self, dict1: Dict, pattern: Dict, msg: str = None):
        """断言字典匹配模式"""
        for key, pattern_value in pattern.items():
            self.assertIn(key, dict1, msg=msg)
            if isinstance(pattern_value, type):
                self.assertIsInstance(dict1[key], pattern_value, msg=msg)
            else:
                self.assertEqual(dict1[key], pattern_value, msg=msg)
    
    def assertListEqual(self, list1: List, list2: List, 
                       key: Union[str, Callable] = None, msg: str = None):
        """断言列表相等，支持自定义比较键"""
        self.assertEqual(len(list1), len(list2), msg=msg)
        
        if key is None:
            super().assertListEqual(list1, list2, msg=msg)
        else:
            if isinstance(key, str):
                key_func = lambda x: x[key]
            else:
                key_func = key
            
            sorted1 = sorted(list1, key=key_func)
            sorted2 = sorted(list2, key=key_func)
            super().assertListEqual(sorted1, sorted2, msg=msg)
    
    def assertDateTimeEqual(self, dt1: datetime, dt2: datetime, 
                          delta_seconds: float = 1.0, msg: str = None):
        """断言两个时间在允许的误差范围内相等"""
        diff = abs((dt1 - dt2).total_seconds())
        self.assertLessEqual(diff, delta_seconds, msg=msg)
    
    def assertRaises(self, expected_exception: Type[Exception], 
                    callable_obj: Callable = None, msg: str = None, **kwargs):
        """增强的异常断言，支持异常属性检查"""
        context = super().assertRaises(expected_exception, callable_obj, msg=msg)
        
        if kwargs and context.exception:
            for key, value in kwargs.items():
                self.assertTrue(hasattr(context.exception, key), 
                              f"异常缺少属性: {key}")
                self.assertEqual(getattr(context.exception, key), value,
                              f"异常属性值不匹配: {key}")
        
        return context

def mock_dependency(target: str):
    """Mock依赖装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            with patch(target) as mock:
                self.mocks[target] = mock
                return func(self, *args, **kwargs)
        return wrapper
    return decorator

def data_provider(*test_data):
    """数据驱动测试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(self):
            for data in test_data:
                if isinstance(data, tuple):
                    func(self, *data)
                else:
                    func(self, data)
        return wrapper
    return decorator

# 导出的类和函数
__all__ = [
    'UnitTestCase',
    'TestDataBuilder',
    'EnhancedAssertions',
    'mock_dependency',
    'data_provider'
]