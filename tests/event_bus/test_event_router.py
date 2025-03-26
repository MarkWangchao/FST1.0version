#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件路由器测试

测试内容:
- 路由注册和移除
- 事件分发功能
- 模式匹配规则
- 多路由处理
- 错误处理
"""

import unittest
import asyncio
from typing import Dict, List, Set
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventRouter
)

class TestEventRouter(AsyncTestCase):
    """事件路由器测试"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.router = EventRouter()
        self.received_events = []
        
        # 生成测试事件
        self.test_events = [
            Event(
                event_type=EventType.TICK,
                data={'symbol': 'BTC/USDT', 'price': 50000},
                source="test"
            ),
            Event(
                event_type=EventType.BAR,
                data={'symbol': 'ETH/USDT', 'close': 3000},
                source="test"
            ),
            Event(
                event_type=EventType.TRADE,
                data={'symbol': 'BTC/USDT', 'volume': 1.5},
                source="test"
            )
        ]
    
    def test_router_creation(self):
        """测试路由器创建"""
        self.assertIsNotNone(self.router)
        self.assertEqual(len(self.router._routes), 0)
    
    @async_test()
    async def test_route_registration(self):
        """测试路由注册"""
        # 定义处理函数
        def handler(event: Event) -> None:
            self.received_events.append(event)
        
        # 测试添加路由
        self.router.add_route("TICK", handler)
        self.assertEqual(len(self.router._routes), 1)
        
        # 测试重复添加
        self.router.add_route("TICK", handler)
        self.assertEqual(len(self.router._routes), 1)
        
        # 测试移除路由
        self.router.remove_route("TICK")
        self.assertEqual(len(self.router._routes), 0)
        
        # 测试移除不存在的路由
        with self.assertRaises(KeyError):
            self.router.remove_route("NON_EXISTENT")
    
    @async_test()
    async def test_basic_routing(self):
        """测试基本路由功能"""
        received_types: Set[EventType] = set()
        
        def handler(event: Event) -> None:
            received_types.add(event.event_type)
        
        # 添加路由
        self.router.add_route("TICK", handler)
        self.router.add_route("BAR", handler)
        
        # 测试路由分发
        for event in self.test_events:
            self.router.route(event)
        
        # 验证结果
        self.assertEqual(len(received_types), 2)
        self.assertIn(EventType.TICK, received_types)
        self.assertIn(EventType.BAR, received_types)
    
    @async_test()
    async def test_pattern_matching(self):
        """测试模式匹配"""
        btc_events = []
        eth_events = []
        
        def btc_handler(event: Event) -> None:
            if event.data['symbol'] == 'BTC/USDT':
                btc_events.append(event)
                
        def eth_handler(event: Event) -> None:
            if event.data['symbol'] == 'ETH/USDT':
                eth_events.append(event)
        
        # 添加带模式的路由
        self.router.add_route("TICK:BTC/USDT", btc_handler)
        self.router.add_route("*:ETH/USDT", eth_handler)
        
        # 测试路由分发
        for event in self.test_events:
            self.router.route(event)
        
        # 验证结果
        self.assertEqual(len(btc_events), 1)
        self.assertEqual(len(eth_events), 1)
        self.assertEqual(btc_events[0].data['symbol'], 'BTC/USDT')
        self.assertEqual(eth_events[0].data['symbol'], 'ETH/USDT')
    
    @async_test()
    async def test_multiple_handlers(self):
        """测试多处理器"""
        handler1_events = []
        handler2_events = []
        
        def handler1(event: Event) -> None:
            handler1_events.append(event)
            
        def handler2(event: Event) -> None:
            handler2_events.append(event)
        
        # 为同一模式添加多个处理器
        self.router.add_route("TICK", handler1)
        self.router.add_route("TICK", handler2)
        
        # 测试路由分发
        tick_event = self.test_events[0]
        self.router.route(tick_event)
        
        # 验证结果
        self.assertEqual(len(handler1_events), 1)
        self.assertEqual(len(handler2_events), 1)
        self.assertEqual(handler1_events[0], tick_event)
        self.assertEqual(handler2_events[0], tick_event)
    
    @async_test()
    async def test_wildcard_routing(self):
        """测试通配符路由"""
        all_events = []
        market_events = []
        
        def all_handler(event: Event) -> None:
            all_events.append(event)
            
        def market_handler(event: Event) -> None:
            market_events.append(event)
        
        # 添加通配符路由
        self.router.add_route("*", all_handler)  # 匹配所有事件
        self.router.add_route("MARKET_*", market_handler)  # 匹配所有市场数据事件
        
        # 添加市场数据事件
        market_event = Event(
            event_type=EventType.MARKET_DATA,
            data={'type': 'depth'},
            source="test"
        )
        
        # 测试路由分发
        self.router.route(market_event)
        self.router.route(self.test_events[0])  # TICK事件
        
        # 验证结果
        self.assertEqual(len(all_events), 2)  # 应该收到所有事件
        self.assertEqual(len(market_events), 1)  # 只应该收到市场数据事件
    
    @async_test()
    async def test_error_handling(self):
        """测试错误处理"""
        error_events = []
        
        def error_handler(event: Event) -> None:
            raise ValueError("Test error")
            
        def fallback_handler(event: Event) -> None:
            error_events.append(event)
        
        # 添加会抛出异常的处理器和后备处理器
        self.router.add_route("TICK", error_handler)
        self.router.add_route("ERROR", fallback_handler)
        
        # 测试异常处理
        with self.assertRaises(ValueError):
            self.router.route(self.test_events[0])
    
    @async_test()
    async def test_route_removal(self):
        """测试路由移除"""
        events = []
        
        def handler(event: Event) -> None:
            events.append(event)
        
        # 添加并移除路由
        self.router.add_route("TICK", handler)
        self.router.remove_route("TICK")
        
        # 测试路由分发
        self.router.route(self.test_events[0])
        
        # 验证结果
        self.assertEqual(len(events), 0)
    
    @async_test()
    async def test_complex_routing(self):
        """测试复杂路由场景"""
        results = {
            'tick_btc': [],
            'tick_eth': [],
            'trade_all': [],
            'high_priority': []
        }
        
        def tick_btc_handler(event: Event) -> None:
            if event.event_type == EventType.TICK and event.data['symbol'] == 'BTC/USDT':
                results['tick_btc'].append(event)
                
        def tick_eth_handler(event: Event) -> None:
            if event.event_type == EventType.TICK and event.data['symbol'] == 'ETH/USDT':
                results['tick_eth'].append(event)
                
        def trade_handler(event: Event) -> None:
            if event.event_type == EventType.TRADE:
                results['trade_all'].append(event)
                
        def priority_handler(event: Event) -> None:
            if event.priority <= 5:  # 高优先级事件
                results['high_priority'].append(event)
        
        # 添加复杂路由规则
        self.router.add_route("TICK:BTC/USDT", tick_btc_handler)
        self.router.add_route("TICK:ETH/USDT", tick_eth_handler)
        self.router.add_route("TRADE:*", trade_handler)
        self.router.add_route("*", priority_handler)
        
        # 添加高优先级事件
        priority_event = Event(
            event_type=EventType.TICK,
            data={'symbol': 'BTC/USDT', 'price': 50000},
            source="test",
            priority=5
        )
        
        # 测试路由分发
        for event in self.test_events:
            self.router.route(event)
        self.router.route(priority_event)
        
        # 验证结果
        self.assertEqual(len(results['tick_btc']), 2)  # 包括优先级事件
        self.assertEqual(len(results['tick_eth']), 0)
        self.assertEqual(len(results['trade_all']), 1)
        self.assertEqual(len(results['high_priority']), 1)

if __name__ == '__main__':
    unittest.main()