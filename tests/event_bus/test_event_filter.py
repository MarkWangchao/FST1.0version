#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件过滤器测试

测试内容:
- 事件过滤功能
- 事件转换功能
- 过滤器链式处理
- 过滤器管理
"""

import unittest
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventFilter
)

class TestEventFilter(AsyncTestCase):
    """事件过滤器测试"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.filter = EventFilter()
        self.test_events = []
        
        # 生成测试事件
        symbols = ['BTC/USDT', 'ETH/USDT']
        for symbol in symbols:
            for i in range(3):
                event = Event(
                    event_type=EventType.TICK,
                    data={
                        'symbol': symbol,
                        'price': 100 + i,
                        'volume': 1.0
                    },
                    source="test"
                )
                self.test_events.append(event)
    
    def test_filter_creation(self):
        """测试过滤器创建"""
        self.assertIsNotNone(self.filter)
        self.assertEqual(len(self.filter._filters), 0)
    
    @async_test()
    async def test_basic_filtering(self):
        """测试基本过滤功能"""
        # 添加过滤器: 只保留BTC/USDT的事件
        def btc_filter(event: Event) -> Optional[Event]:
            if event.data.get('symbol') == 'BTC/USDT':
                return event
            return None
            
        self.filter.add_filter(btc_filter)
        
        # 测试过滤
        filtered_events = []
        for event in self.test_events:
            result = self.filter.process(event)
            if result:
                filtered_events.append(result)
        
        # 验证结果
        self.assertEqual(len(filtered_events), 3)
        for event in filtered_events:
            self.assertEqual(event.data['symbol'], 'BTC/USDT')
    
    @async_test()
    async def test_event_transformation(self):
        """测试事件转换功能"""
        # 添加转换器: 将Tick转换为Bar
        def tick_to_bar(event: Event) -> Optional[Event]:
            if event.event_type == EventType.TICK:
                return Event(
                    event_type=EventType.BAR,
                    data={
                        'symbol': event.data['symbol'],
                        'open': event.data['price'],
                        'high': event.data['price'],
                        'low': event.data['price'],
                        'close': event.data['price'],
                        'volume': event.data['volume']
                    },
                    source=event.source
                )
            return event
            
        self.filter.add_filter(tick_to_bar)
        
        # 测试转换
        for event in self.test_events[:1]:  # 只测试一个事件
            result = self.filter.process(event)
            self.assertEqual(result.event_type, EventType.BAR)
            self.assertIn('open', result.data)
            self.assertIn('close', result.data)
    
    @async_test()
    async def test_filter_chain(self):
        """测试过滤器链式处理"""
        # 过滤器1: 只保留BTC/USDT
        def symbol_filter(event: Event) -> Optional[Event]:
            return event if event.data['symbol'] == 'BTC/USDT' else None
        
        # 过滤器2: 价格阈值过滤
        def price_filter(event: Event) -> Optional[Event]:
            return event if event.data['price'] > 101 else None
        
        # 过滤器3: 添加标记
        def mark_filter(event: Event) -> Optional[Event]:
            if event:
                event.data['marked'] = True
            return event
        
        # 添加过滤器链
        self.filter.add_filter(symbol_filter)
        self.filter.add_filter(price_filter)
        self.filter.add_filter(mark_filter)
        
        # 测试链式处理
        results = []
        for event in self.test_events:
            result = self.filter.process(event)
            if result:
                results.append(result)
        
        # 验证结果
        self.assertTrue(len(results) > 0)
        for result in results:
            self.assertEqual(result.data['symbol'], 'BTC/USDT')
            self.assertGreater(result.data['price'], 101)
            self.assertTrue(result.data['marked'])
    
    @async_test()
    async def test_filter_management(self):
        """测试过滤器管理功能"""
        # 定义测试过滤器
        def test_filter(event: Event) -> Optional[Event]:
            return event
        
        # 测试添加过滤器
        self.filter.add_filter(test_filter)
        self.assertEqual(len(self.filter._filters), 1)
        
        # 测试移除过滤器
        self.filter.remove_filter(test_filter)
        self.assertEqual(len(self.filter._filters), 0)
        
        # 测试重复添加
        self.filter.add_filter(test_filter)
        self.filter.add_filter(test_filter)
        self.assertEqual(len(self.filter._filters), 1)
    
    @async_test()
    async def test_error_handling(self):
        """测试错误处理"""
        # 添加可能抛出异常的过滤器
        def error_filter(event: Event) -> Optional[Event]:
            raise ValueError("Test error")
        
        self.filter.add_filter(error_filter)
        
        # 测试异常处理
        with self.assertRaises(ValueError):
            self.filter.process(self.test_events[0])
    
    @async_test()
    async def test_complex_filtering(self):
        """测试复杂过滤场景"""
        # 过滤器1: 数据增强
        def enhance_data(event: Event) -> Optional[Event]:
            event.data['timestamp'] = time.time()
            event.data['processed'] = True
            return event
        
        # 过滤器2: 条件过滤
        def conditional_filter(event: Event) -> Optional[Event]:
            if event.data['price'] > 100 and event.data['volume'] > 0:
                return event
            return None
        
        # 过滤器3: 数据转换
        def transform_data(event: Event) -> Optional[Event]:
            event.data['price_level'] = 'high' if event.data['price'] > 101 else 'low'
            return event
        
        # 添加过滤器链
        self.filter.add_filter(enhance_data)
        self.filter.add_filter(conditional_filter)
        self.filter.add_filter(transform_data)
        
        # 测试复杂处理
        results = []
        for event in self.test_events:
            result = self.filter.process(event)
            if result:
                results.append(result)
        
        # 验证结果
        for result in results:
            self.assertIn('timestamp', result.data)
            self.assertTrue(result.data['processed'])
            self.assertIn('price_level', result.data)
            self.assertGreater(result.data['price'], 100)
            self.assertGreater(result.data['volume'], 0)
    
    @async_test()
    async def test_performance(self):
        """测试性能"""
        # 添加简单过滤器
        def simple_filter(event: Event) -> Optional[Event]:
            return event if event.data['price'] > 0 else None
        
        self.filter.add_filter(simple_filter)
        
        # 生成大量测试数据
        large_test_events = []
        for i in range(1000):
            event = Event(
                event_type=EventType.TICK,
                data={
                    'symbol': 'BTC/USDT',
                    'price': 100 + i % 10,
                    'volume': 1.0
                }
            )
            large_test_events.append(event)
        
        # 测试处理性能
        start_time = time.time()
        for event in large_test_events:
            self.filter.process(event)
        end_time = time.time()
        
        # 验证处理时间
        processing_time = end_time - start_time
        self.assertLess(processing_time, 1.0)  # 确保1000个事件的处理时间小于1秒

if __name__ == '__main__':
    unittest.main()