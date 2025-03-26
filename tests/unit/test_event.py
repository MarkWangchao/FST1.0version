#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件系统单元测试

测试事件系统功能:
- 事件创建和属性
- 事件路由和分发
- 事件过滤和转换
- 事件处理和回调
"""

import unittest
import asyncio
from datetime import datetime
from typing import Dict, Optional

from tests.unit import UnitTestCase, TestDataBuilder, mock_dependency
from infrastructure.event_bus.event_manager import (
    Event, EventType, EventBus, EventFilter, EventRouter, 
    EventValidator, EventMetrics
)

class TestEvent(UnitTestCase):
    """事件基础功能测试"""
    
    def test_event_creation(self):
        """测试事件创建"""
        # 创建基本事件
        event = Event(
            event_type=EventType.MARKET_DATA,
            data={'symbol': 'BTC/USDT', 'price': 50000.0},
            source='test'
        )
        
        # 验证事件属性
        self.assertEqual(event.event_type, EventType.MARKET_DATA)
        self.assertEqual(event.data['symbol'], 'BTC/USDT')
        self.assertEqual(event.data['price'], 50000.0)
        self.assertEqual(event.source, 'test')
        self.assertIsNotNone(event.timestamp)
        self.assertIsNotNone(event.event_id)
        
        # 测试事件序列化
        event_dict = event.to_dict()
        self.assertEqual(event_dict['event_type'], EventType.MARKET_DATA)
        self.assertEqual(event_dict['data']['symbol'], 'BTC/USDT')
        
        # 测试事件反序列化
        new_event = Event.from_dict(event_dict)
        self.assertEqual(new_event.event_type, event.event_type)
        self.assertEqual(new_event.data, event.data)
    
    def test_event_comparison(self):
        """测试事件比较"""
        event1 = Event(EventType.TRADE, timestamp=1000)
        event2 = Event(EventType.TRADE, timestamp=2000)
        
        self.assertLess(event1, event2)
        self.assertGreater(event2, event1)

class TestEventFilter(UnitTestCase):
    """事件过滤器测试"""
    
    def setUp(self):
        super().setUp()
        self.filter = EventFilter()
    
    def test_filter_registration(self):
        """测试过滤器注册"""
        def test_filter(event: Event) -> Optional[Event]:
            return event if event.event_type == EventType.TRADE else None
        
        # 注册过滤器
        self.filter.add_filter(test_filter)
        self.assertEqual(len(self.filter._filters), 1)
        
        # 移除过滤器
        self.filter.remove_filter(test_filter)
        self.assertEqual(len(self.filter._filters), 0)
    
    async def test_filter_chain(self):
        """测试过滤器链"""
        # 定义过滤器
        def symbol_filter(event: Event) -> Optional[Event]:
            if event.data.get('symbol') == 'BTC/USDT':
                return event
            return None
        
        def price_filter(event: Event) -> Optional[Event]:
            if event.data.get('price', 0) > 1000:
                return event
            return None
        
        # 注册过滤器
        self.filter.add_filter(symbol_filter)
        self.filter.add_filter(price_filter)
        
        # 创建测试事件
        event1 = Event(EventType.MARKET_DATA, {
            'symbol': 'BTC/USDT',
            'price': 50000.0
        })
        event2 = Event(EventType.MARKET_DATA, {
            'symbol': 'ETH/USDT',
            'price': 50000.0
        })
        event3 = Event(EventType.MARKET_DATA, {
            'symbol': 'BTC/USDT',
            'price': 100.0
        })
        
        # 测试过滤器链
        self.assertIsNotNone(await self.filter.process(event1))
        self.assertIsNone(await self.filter.process(event2))
        self.assertIsNone(await self.filter.process(event3))

class TestEventRouter(UnitTestCase):
    """事件路由器测试"""
    
    def setUp(self):
        super().setUp()
        self.router = EventRouter()
    
    def test_route_registration(self):
        """测试路由注册"""
        def test_handler(event: Event):
            pass
        
        # 注册路由
        self.router.add_route('market_data.*', test_handler)
        self.assertEqual(len(self.router._routes), 1)
        
        # 移除路由
        self.router.remove_route('market_data.*')
        self.assertEqual(len(self.router._routes), 0)
    
    async def test_event_routing(self):
        """测试事件路由"""
        routed_events = []
        
        # 定义处理器
        def market_handler(event: Event):
            if event.event_type == EventType.MARKET_DATA:
                routed_events.append(event)
        
        def trade_handler(event: Event):
            if event.event_type == EventType.TRADE:
                routed_events.append(event)
        
        # 注册路由
        self.router.add_route('market_data.*', market_handler)
        self.router.add_route('trade.*', trade_handler)
        
        # 创建测试事件
        market_event = Event(EventType.MARKET_DATA, {
            'symbol': 'BTC/USDT',
            'price': 50000.0
        })
        trade_event = Event(EventType.TRADE, {
            'symbol': 'BTC/USDT',
            'volume': 1.0
        })
        
        # 测试路由
        await self.router.route(market_event)
        await self.router.route(trade_event)
        
        self.assertEqual(len(routed_events), 2)
        self.assertEqual(routed_events[0].event_type, EventType.MARKET_DATA)
        self.assertEqual(routed_events[1].event_type, EventType.TRADE)

class TestEventValidator(UnitTestCase):
    """事件验证器测试"""
    
    def setUp(self):
        super().setUp()
        self.validator = EventValidator()
    
    def test_schema_registration(self):
        """测试模式注册"""
        schema = {
            'type': 'object',
            'properties': {
                'symbol': {'type': 'string'},
                'price': {'type': 'number'}
            },
            'required': ['symbol', 'price']
        }
        
        # 注册模式
        self.validator.add_validator(EventType.MARKET_DATA, schema)
        self.assertEqual(len(self.validator._schemas), 1)
        
        # 移除模式
        self.validator.remove_validator(EventType.MARKET_DATA)
        self.assertEqual(len(self.validator._schemas), 0)
    
    def test_event_validation(self):
        """测试事件验证"""
        # 注册验证模式
        self.validator.add_validator(EventType.TRADE, {
            'type': 'object',
            'properties': {
                'symbol': {'type': 'string'},
                'volume': {'type': 'number', 'minimum': 0},
                'price': {'type': 'number', 'minimum': 0}
            },
            'required': ['symbol', 'volume', 'price']
        })
        
        # 测试有效事件
        valid_event = Event(EventType.TRADE, {
            'symbol': 'BTC/USDT',
            'volume': 1.0,
            'price': 50000.0
        })
        self.assertTrue(self.validator.validate(valid_event))
        
        # 测试无效事件
        invalid_event = Event(EventType.TRADE, {
            'symbol': 'BTC/USDT',
            'volume': -1.0,  # 无效的数量
            'price': 50000.0
        })
        self.assertFalse(self.validator.validate(invalid_event))

class TestEventMetrics(UnitTestCase):
    """事件指标测试"""
    
    def setUp(self):
        super().setUp()
        self.metrics = EventMetrics()
    
    def test_metric_recording(self):
        """测试指标记录"""
        # 记录计数指标
        self.metrics.record('events_total', 1)
        self.metrics.record('events_total', 1)
        
        # 记录带标签的指标
        self.metrics.record('event_processing_time', 0.1, {
            'event_type': 'market_data'
        })
        
        # 验证指标
        metrics_data = self.metrics.get_metrics()
        self.assertEqual(metrics_data['events_total'], 2)
        self.assertIn('event_processing_time', metrics_data)
    
    def test_metric_timing(self):
        """测试时间指标"""
        start_time = datetime.now().timestamp()
        
        # 记录处理时间
        self.metrics.record_time('processing_time', start_time, {
            'event_type': 'trade'
        })
        
        # 验证指标
        metrics_data = self.metrics.get_metrics()
        self.assertIn('processing_time', metrics_data)
        self.assertGreater(metrics_data['processing_time'], 0)

class TestEventBus(UnitTestCase):
    """事件总线测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.event_bus = EventBus()
        await self.event_bus.start()
    
    async def asyncTearDown(self):
        """异步测试清理"""
        await self.event_bus.stop()
        await super().asyncTearDown()
    
    async def test_event_publishing(self):
        """测试事件发布"""
        received_events = []
        
        # 注册处理器
        async def event_handler(event: Event):
            received_events.append(event)
        
        self.event_bus.subscribe(EventType.MARKET_DATA, event_handler)
        
        # 发布事件
        event = Event(EventType.MARKET_DATA, {
            'symbol': 'BTC/USDT',
            'price': 50000.0
        })
        await self.event_bus.publish(event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证事件接收
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].event_type, EventType.MARKET_DATA)
    
    async def test_event_filtering(self):
        """测试事件过滤"""
        received_events = []
        
        # 注册处理器和过滤器
        async def event_handler(event: Event):
            received_events.append(event)
        
        def price_filter(event: Event) -> Optional[Event]:
            if event.data.get('price', 0) > 1000:
                return event
            return None
        
        self.event_bus.subscribe(EventType.MARKET_DATA, event_handler)
        self.event_bus.add_filter(price_filter)
        
        # 发布事件
        event1 = Event(EventType.MARKET_DATA, {
            'symbol': 'BTC/USDT',
            'price': 50000.0
        })
        event2 = Event(EventType.MARKET_DATA, {
            'symbol': 'BTC/USDT',
            'price': 100.0
        })
        
        await self.event_bus.publish(event1)
        await self.event_bus.publish(event2)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证事件过滤
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].data['price'], 50000.0)
    
    async def test_event_error_handling(self):
        """测试事件错误处理"""
        error_events = []
        
        # 注册错误处理器
        async def error_handler(event: Event, error: Exception):
            error_events.append((event, error))
        
        # 注册会抛出异常的处理器
        async def failing_handler(event: Event):
            raise ValueError("测试异常")
        
        self.event_bus.subscribe(EventType.MARKET_DATA, failing_handler)
        self.event_bus.set_error_handler(error_handler)
        
        # 发布事件
        event = Event(EventType.MARKET_DATA, {
            'symbol': 'BTC/USDT',
            'price': 50000.0
        })
        await self.event_bus.publish(event)
        
        # 等待错误处理
        await asyncio.sleep(0.1)
        
        # 验证错误处理
        self.assertEqual(len(error_events), 1)
        self.assertIsInstance(error_events[0][1], ValueError)
    
    async def test_event_metrics(self):
        """测试事件指标"""
        # 发布多个事件
        for i in range(5):
            event = Event(EventType.MARKET_DATA, {
                'symbol': 'BTC/USDT',
                'price': 50000.0 + i
            })
            await self.event_bus.publish(event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 获取指标
        metrics = self.event_bus.get_metrics()
        
        # 验证指标
        self.assertEqual(metrics['events_published'], 5)
        self.assertIn('event_processing_time', metrics)
        self.assertIn('queue_size', metrics)

if __name__ == '__main__':
    unittest.main()