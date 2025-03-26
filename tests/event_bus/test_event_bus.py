#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件总线集成测试

测试内容:
- 事件总线创建和配置
- 事件发布和订阅
- 事件路由和过滤
- QoS控制
- 错误处理
"""

import unittest
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventBus, EventBusConfig,
    TqEventAdapter
)

class TestEventBus(AsyncTestCase):
    """事件总线集成测试"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.event_bus = EventBus(name="test_bus")
        self.received_events = []
        self.test_events = []
        
        # 生成测试事件
        for i in range(5):
            event = Event(
                event_type=EventType.TICK,
                data={'price': 100 + i, 'volume': 1},
                source="test",
                timestamp=time.time() + i
            )
            self.test_events.append(event)
    
    def test_bus_creation(self):
        """测试事件总线创建"""
        self.assertIsNotNone(self.event_bus)
        self.assertEqual(self.event_bus.name, "test_bus")
        self.assertIsNotNone(self.event_bus.config)
        self.assertIsNotNone(self.event_bus.router)
        self.assertIsNotNone(self.event_bus.filter)
        self.assertIsNotNone(self.event_bus.validator)
        self.assertIsNotNone(self.event_bus.metrics)
        self.assertIsNotNone(self.event_bus.recorder)
    
    @async_test()
    async def test_event_publishing(self):
        """测试事件发布功能"""
        # 创建事件处理器
        async def event_handler(event: Event):
            self.received_events.append(event)
        
        # 订阅事件
        self.event_bus.subscribe(EventType.TICK, event_handler)
        
        # 发布事件
        for event in self.test_events:
            await self.event_bus.publish(event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证事件处理
        self.assertEqual(len(self.received_events), 5)
        for i, event in enumerate(self.received_events):
            self.assertEqual(event.event_type, EventType.TICK)
            self.assertEqual(event.data['price'], 100 + i)
    
    @async_test()
    async def test_event_subscription(self):
        """测试事件订阅功能"""
        # 创建事件处理器
        async def event_handler(event: Event):
            self.received_events.append(event)
        
        # 测试订阅
        self.event_bus.subscribe(EventType.TICK, event_handler)
        self.event_bus.subscribe(EventType.BAR, event_handler)
        
        # 发布不同类型的事件
        tick_event = Event(EventType.TICK, data={'price': 100})
        bar_event = Event(EventType.BAR, data={'open': 100})
        
        await self.event_bus.publish(tick_event)
        await self.event_bus.publish(bar_event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证事件处理
        self.assertEqual(len(self.received_events), 2)
        self.assertEqual(self.received_events[0].event_type, EventType.TICK)
        self.assertEqual(self.received_events[1].event_type, EventType.BAR)
        
        # 测试取消订阅
        self.event_bus.unsubscribe(EventType.TICK, event_handler)
        await self.event_bus.publish(tick_event)
        await asyncio.sleep(0.1)
        self.assertEqual(len(self.received_events), 2)  # 数量应该不变
    
    @async_test()
    async def test_event_routing(self):
        """测试事件路由功能"""
        # 创建事件处理器
        async def tick_handler(event: Event):
            self.received_events.append(('tick', event))
        
        async def bar_handler(event: Event):
            self.received_events.append(('bar', event))
        
        # 设置路由规则
        self.event_bus.router.add_route("TICK.*", tick_handler)
        self.event_bus.router.add_route("BAR.*", bar_handler)
        
        # 发布事件
        tick_event = Event(EventType.TICK, data={'price': 100})
        bar_event = Event(EventType.BAR, data={'open': 100})
        
        await self.event_bus.publish(tick_event)
        await self.event_bus.publish(bar_event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证路由
        self.assertEqual(len(self.received_events), 2)
        self.assertEqual(self.received_events[0][0], 'tick')
        self.assertEqual(self.received_events[1][0], 'bar')
    
    @async_test()
    async def test_event_filtering(self):
        """测试事件过滤功能"""
        # 创建过滤器
        def price_filter(event: Event) -> Optional[Event]:
            if event.data.get('price', 0) > 102:
                return event
            return None
        
        self.event_bus.filter.add_filter(price_filter)
        
        # 创建事件处理器
        async def event_handler(event: Event):
            self.received_events.append(event)
        
        # 订阅事件
        self.event_bus.subscribe(EventType.TICK, event_handler)
        
        # 发布事件
        for event in self.test_events:
            await self.event_bus.publish(event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证过滤结果
        self.assertEqual(len(self.received_events), 3)  # 只有价格>102的事件
        for event in self.received_events:
            self.assertGreater(event.data['price'], 102)
    
    @async_test()
    async def test_qos_control(self):
        """测试QoS控制功能"""
        # 创建事件处理器
        async def event_handler(event: Event):
            self.received_events.append(event)
            await asyncio.sleep(0.01)  # 模拟处理延迟
        
        # 订阅事件
        self.event_bus.subscribe(EventType.TICK, event_handler)
        
        # 发布大量事件
        events = []
        for i in range(100):
            event = Event(
                EventType.TICK,
                data={'price': 100 + i},
                priority=i % 5  # 不同优先级
            )
            events.append(event)
        
        # 记录开始时间
        start_time = time.time()
        
        # 发布事件
        for event in events:
            await self.event_bus.publish(event)
        
        # 等待事件处理
        await asyncio.sleep(1)
        
        # 验证QoS控制
        self.assertLess(len(self.received_events), 100)  # 应该有事件被丢弃
        self.assertGreater(len(self.received_events), 0)  # 应该有事件被处理
        
        # 验证优先级处理
        if len(self.received_events) > 1:
            for i in range(1, len(self.received_events)):
                self.assertGreaterEqual(
                    self.received_events[i-1].priority,
                    self.received_events[i].priority
                )
    
    @async_test()
    async def test_event_validation(self):
        """测试事件验证功能"""
        # 定义验证规则
        schema = {
            'type': 'object',
            'properties': {
                'price': {'type': 'number', 'minimum': 0},
                'volume': {'type': 'number', 'minimum': 0}
            },
            'required': ['price', 'volume']
        }
        
        self.event_bus.validator.add_validator(EventType.TICK, schema)
        
        # 创建事件处理器
        async def event_handler(event: Event):
            self.received_events.append(event)
        
        # 订阅事件
        self.event_bus.subscribe(EventType.TICK, event_handler)
        
        # 发布有效事件
        valid_event = Event(
            EventType.TICK,
            data={'price': 100, 'volume': 1}
        )
        await self.event_bus.publish(valid_event)
        
        # 发布无效事件
        invalid_event = Event(
            EventType.TICK,
            data={'price': -100, 'volume': 1}
        )
        await self.event_bus.publish(invalid_event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证结果
        self.assertEqual(len(self.received_events), 1)
        self.assertEqual(self.received_events[0].data['price'], 100)
    
    @async_test()
    async def test_error_handling(self):
        """测试错误处理"""
        # 创建抛出异常的事件处理器
        async def error_handler(event: Event):
            raise ValueError("Test error")
        
        # 订阅事件
        self.event_bus.subscribe(EventType.TICK, error_handler)
        
        # 发布事件
        event = Event(EventType.TICK, data={'price': 100})
        await self.event_bus.publish(event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证错误处理
        self.assertEqual(len(self.received_events), 0)
        
        # 验证错误事件
        error_events = self.event_bus.recorder.replay(
            event_types=[EventType.ERROR]
        )
        self.assertEqual(len(error_events), 1)
        self.assertEqual(error_events[0].event_type, EventType.ERROR)
    
    @async_test()
    async def test_tq_event_adapter(self):
        """测试Tq事件适配器"""
        # 创建适配器
        adapter = TqEventAdapter(self.event_bus)
        
        # 创建事件处理器
        async def event_handler(event: Event):
            self.received_events.append(event)
        
        # 订阅事件
        self.event_bus.subscribe(EventType.TICK, event_handler)
        self.event_bus.subscribe(EventType.BAR, event_handler)
        self.event_bus.subscribe(EventType.ORDER, event_handler)
        
        # 模拟Tq事件
        tick_data = {
            'symbol': 'BTC/USDT',
            'price': 50000,
            'volume': 1.0
        }
        bar_data = {
            'symbol': 'BTC/USDT',
            'open': 50000,
            'high': 51000,
            'low': 49000,
            'close': 50500,
            'volume': 10.0
        }
        order_data = {
            'order_id': '123',
            'symbol': 'BTC/USDT',
            'direction': 'buy',
            'price': 50000,
            'volume': 1.0,
            'status': 'pending'
        }
        
        # 处理事件
        await adapter.on_tick_event(tick_data)
        await adapter.on_bar_event(bar_data)
        await adapter.on_order_event(order_data)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 验证事件转换
        self.assertEqual(len(self.received_events), 3)
        self.assertEqual(self.received_events[0].event_type, EventType.TICK)
        self.assertEqual(self.received_events[1].event_type, EventType.BAR)
        self.assertEqual(self.received_events[2].event_type, EventType.ORDER)

if __name__ == '__main__':
    unittest.main()