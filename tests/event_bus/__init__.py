#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 测试框架

提供测试基础设施:
- 测试配置管理
- 测试基类
- 测试工具函数
- 测试数据生成器
- 测试装饰器
"""

import os
import sys
import unittest
import asyncio
import logging
import json
import yaml
import random
import time
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager
import numpy as np
import pandas as pd
from prometheus_client import CollectorRegistry

# 添加项目根目录到Python路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# 测试配置
TEST_CONFIG = {
    'env': 'testing',
    'log_level': 'INFO',
    'test_data_dir': 'tests/data',
    'temp_dir': 'tests/temp',
    'report_dir': 'tests/reports',
    'timeout': 30,  # 测试超时时间(秒)
    'async_timeout': 60,  # 异步测试超时时间(秒)
    'retry_times': 3,  # 测试重试次数
    'retry_interval': 1,  # 重试间隔(秒)
}

class TestCase(unittest.TestCase):
    """测试基类"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        # 设置日志
        logging.basicConfig(
            level=getattr(logging, TEST_CONFIG['log_level']),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        cls.logger = logging.getLogger(cls.__name__)
        
        # 创建必要的目录
        for dir_path in [TEST_CONFIG['test_data_dir'], 
                        TEST_CONFIG['temp_dir'],
                        TEST_CONFIG['report_dir']]:
            os.makedirs(dir_path, exist_ok=True)
        
        # 初始化事件循环
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        
        # 重置Prometheus注册表
        cls.registry = CollectorRegistry()
    
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        cls.loop.close()
    
    def setUp(self):
        """测试用例初始化"""
        self.start_time = time.time()
    
    def tearDown(self):
        """测试用例清理"""
        duration = time.time() - self.start_time
        self.logger.info(f"测试用例执行时间: {duration:.2f}秒")
    
    async def asyncSetUp(self):
        """异步测试用例初始化"""
        pass
    
    async def asyncTearDown(self):
        """异步测试用例清理"""
        pass
    
    def run_async(self, coro):
        """运行异步代码"""
        return self.loop.run_until_complete(coro)

class AsyncTestCase(TestCase):
    """异步测试基类"""
    
    def setUp(self):
        """设置异步测试环境"""
        super().setUp()
        self.loop.run_until_complete(self.asyncSetUp())
    
    def tearDown(self):
        """清理异步测试环境"""
        self.loop.run_until_complete(self.asyncTearDown())
        super().tearDown()

def async_test(timeout: int = None):
    """异步测试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            async def _run_test():
                return await func(*args, **kwargs)
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                asyncio.wait_for(_run_test(), 
                               timeout or TEST_CONFIG['async_timeout'])
            )
        return wrapper
    return decorator

def retry_on_failure(max_retries: int = None, 
                    retry_interval: int = None):
    """失败重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = max_retries or TEST_CONFIG['retry_times']
            interval = retry_interval or TEST_CONFIG['retry_interval']
            last_error = None
            
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if i < retries - 1:
                        time.sleep(interval)
            
            raise last_error
        return wrapper
    return decorator

@contextmanager
def temp_file(content: str = None, suffix: str = '.txt'):
    """临时文件上下文管理器"""
    import tempfile
    
    temp = tempfile.NamedTemporaryFile(
        dir=TEST_CONFIG['temp_dir'],
        suffix=suffix,
        delete=False
    )
    try:
        if content:
            temp.write(content.encode())
        temp.close()
        yield temp.name
    finally:
        os.unlink(temp.name)

class DataGenerator:
    """测试数据生成器"""
    
    @staticmethod
    def generate_market_data(symbol: str,
                           start_time: datetime,
                           end_time: datetime,
                           interval: str = '1m') -> pd.DataFrame:
        """生成模拟行情数据"""
        # 生成时间索引
        freq_map = {'1m': 'T', '5m': '5T', '15m': '15T', '1h': 'H', '1d': 'D'}
        dates = pd.date_range(start_time, end_time, freq=freq_map[interval])
        
        # 生成OHLCV数据
        n = len(dates)
        base_price = 100
        price_volatility = 0.02
        volume_mean = 1000
        volume_std = 200
        
        data = pd.DataFrame({
            'timestamp': dates,
            'open': base_price + np.random.normal(0, price_volatility, n).cumsum(),
            'high': 0.0,
            'low': 0.0,
            'close': 0.0,
            'volume': np.random.normal(volume_mean, volume_std, n).clip(min=0)
        })
        
        # 计算high和low
        data['close'] = data['open'].shift(-1)
        data['high'] = pd.concat([data['open'], data['close']], axis=1).max(axis=1)
        data['low'] = pd.concat([data['open'], data['close']], axis=1).min(axis=1)
        
        # 添加随机波动
        data['high'] += abs(np.random.normal(0, price_volatility, n))
        data['low'] -= abs(np.random.normal(0, price_volatility, n))
        
        return data.set_index('timestamp')
    
    @staticmethod
    def generate_tick_data(symbol: str,
                          duration: int,
                          frequency: float = 1.0) -> List[Dict]:
        """生成模拟Tick数据"""
        ticks = []
        base_price = 100
        price_volatility = 0.01
        volume_mean = 100
        volume_std = 20
        
        current_time = time.time()
        end_time = current_time + duration
        
        while current_time < end_time:
            # 生成价格和成交量
            price = base_price + np.random.normal(0, price_volatility)
            volume = int(np.random.normal(volume_mean, volume_std).clip(min=1))
            
            tick = {
                'symbol': symbol,
                'price': price,
                'volume': volume,
                'timestamp': current_time,
                'bid_price': price - price_volatility,
                'ask_price': price + price_volatility,
                'bid_volume': int(volume * 0.8),
                'ask_volume': int(volume * 1.2)
            }
            ticks.append(tick)
            
            # 更新时间
            current_time += 1 / frequency
        
        return ticks
    
    @staticmethod
    def generate_order_data(n_orders: int = 10) -> List[Dict]:
        """生成模拟订单数据"""
        orders = []
        symbols = ['BTC/USDT', 'ETH/USDT', 'AAPL', 'GOOGL']
        sides = ['buy', 'sell']
        types = ['market', 'limit']
        statuses = ['pending', 'filled', 'cancelled']
        
        for i in range(n_orders):
            price = random.uniform(100, 1000)
            volume = random.randint(1, 100)
            
            order = {
                'order_id': f'ORDER_{i}',
                'symbol': random.choice(symbols),
                'side': random.choice(sides),
                'type': random.choice(types),
                'price': price,
                'volume': volume,
                'status': random.choice(statuses),
                'create_time': time.time() - random.uniform(0, 3600),
                'update_time': time.time()
            }
            orders.append(order)
        
        return orders

def load_test_config(config_file: str):
    """加载测试配置"""
    if not os.path.exists(config_file):
        return
        
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
        TEST_CONFIG.update(config)

def save_test_report(name: str, data: Dict):
    """保存测试报告"""
    report_file = os.path.join(
        TEST_CONFIG['report_dir'],
        f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    
    with open(report_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    return report_file