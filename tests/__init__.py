#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 测试包

提供测试所需的通用工具和基础设施:
- 测试用例基类
- 异步测试支持
- 测试数据生成
- 测试工具函数
"""

import os
import sys
import json
import time
import asyncio
import logging
import unittest
import functools
from typing import Dict, List, Optional, Callable, Any, Type, Union
from datetime import datetime, timedelta
from contextlib import contextmanager
from unittest.mock import Mock, AsyncMock, patch

# 配置日志
logger = logging.getLogger(__name__)

class TestCase(unittest.TestCase):
    """测试用例基类"""
    
    @classmethod
    def setUpClass(cls):
        """类级别的测试准备"""
        super().setUpClass()
        cls.start_time = time.time()
        logger.info(f"开始测试类: {cls.__name__}")
        
        # 设置测试环境变量
        os.environ['FST_TEST_MODE'] = 'true'
        os.environ['FST_CONFIG_ENV'] = 'test'
        
        # 初始化测试目录
        cls.test_dir = os.path.dirname(os.path.abspath(__file__))
        cls.project_dir = os.path.dirname(cls.test_dir)
        cls.data_dir = os.path.join(cls.test_dir, 'data')
        os.makedirs(cls.data_dir, exist_ok=True)
    
    @classmethod
    def tearDownClass(cls):
        """类级别的测试清理"""
        super().tearDownClass()
        duration = time.time() - cls.start_time
        logger.info(f"完成测试类: {cls.__name__} - 耗时: {duration:.2f}秒")
    
    def setUp(self):
        """测试准备"""
        super().setUp()
        self.start_time = time.time()
    
    def tearDown(self):
        """测试清理"""
        super().tearDown()
        duration = time.time() - self.start_time
        logger.info(f"完成测试: {self._testMethodName} - 耗时: {duration:.2f}秒")
    
    async def asyncSetUp(self):
        """异步测试准备"""
        pass
    
    async def asyncTearDown(self):
        """异步测试清理"""
        pass
    
    def run_async(self, coro):
        """运行异步代码"""
        return asyncio.get_event_loop().run_until_complete(coro)

class AsyncTestCase(TestCase):
    """异步测试用例基类"""
    
    def setUp(self):
        """设置异步测试环境"""
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.asyncSetUp())
    
    def tearDown(self):
        """清理异步测试环境"""
        self.loop.run_until_complete(self.asyncTearDown())
        self.loop.close()
        super().tearDown()

def async_test(timeout: int = None):
    """异步测试装饰器"""
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            async def _run_test():
                # 设置超时
                if timeout:
                    try:
                        async with asyncio.timeout(timeout):
                            return await func(*args, **kwargs)
                    except asyncio.TimeoutError:
                        raise AssertionError(f"测试超时 ({timeout}秒)")
                else:
                    return await func(*args, **kwargs)
            
            return asyncio.get_event_loop().run_until_complete(_run_test())
        return wrapper
    return decorator

def retry_on_failure(max_retries: int = None, 
                    retry_interval: int = None):
    """失败重试装饰器"""
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = max_retries or 3
            interval = retry_interval or 1
            
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except AssertionError as e:
                    if i == retries - 1:  # 最后一次重试
                        raise
                    logger.warning(f"测试失败，{interval}秒后重试: {str(e)}")
                    time.sleep(interval)
            
        return wrapper
    return decorator

@contextmanager
def temp_file(content: str = None, suffix: str = '.txt'):
    """临时文件上下文管理器"""
    import tempfile
    
    # 创建临时文件
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        if content:
            temp.write(content.encode('utf-8'))
        temp.close()
        yield temp.name
    finally:
        # 清理临时文件
        try:
            os.unlink(temp.name)
        except OSError:
            pass

class DataGenerator:
    """测试数据生成器"""
    
    @staticmethod
    def generate_market_data(symbol: str,
                           start_time: datetime,
                           end_time: datetime,
                           interval: str = '1m') -> List[Dict]:
        """生成市场数据"""
        data = []
        current_time = start_time
        
        # 解析时间间隔
        if interval.endswith('m'):
            delta = timedelta(minutes=int(interval[:-1]))
        elif interval.endswith('h'):
            delta = timedelta(hours=int(interval[:-1]))
        elif interval.endswith('d'):
            delta = timedelta(days=int(interval[:-1]))
        else:
            raise ValueError(f"不支持的时间间隔: {interval}")
        
        # 生成数据
        while current_time <= end_time:
            data.append({
                'symbol': symbol,
                'timestamp': current_time.timestamp(),
                'open': 100 + (hash(str(current_time)) % 100),
                'high': 150 + (hash(str(current_time)) % 100),
                'low': 50 + (hash(str(current_time)) % 100),
                'close': 100 + (hash(str(current_time)) % 100),
                'volume': 1000 + (hash(str(current_time)) % 1000)
            })
            current_time += delta
        
        return data
    
    @staticmethod
    def generate_order_data(n_orders: int = 10) -> List[Dict]:
        """生成订单数据"""
        orders = []
        symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
        directions = ['long', 'short']
        
        for i in range(n_orders):
            order = {
                'order_id': f"ORDER_{i}",
                'symbol': symbols[i % len(symbols)],
                'direction': directions[i % len(directions)],
                'price': 1000 + (i * 100),
                'volume': 1.0 + (i * 0.1),
                'status': 'pending',
                'create_time': time.time() - (i * 60)
            }
            orders.append(order)
        
        return orders

def load_test_config(config_file: str):
    """加载测试配置"""
    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_test_report(name: str, data: Dict):
    """保存测试报告"""
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    os.makedirs(report_dir, exist_ok=True)
    
    report_file = os.path.join(report_dir, f"{name}_{int(time.time())}.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"测试报告已保存: {report_file}")
    return report_file

# 导出的类和函数
__all__ = [
    'TestCase',
    'AsyncTestCase',
    'async_test',
    'retry_on_failure',
    'temp_file',
    'DataGenerator',
    'load_test_config',
    'save_test_report'
]