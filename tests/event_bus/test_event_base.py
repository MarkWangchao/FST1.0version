#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件基础组件测试

测试内容:
- EventType枚举类
- Event基类
- EventRecorder记录器
"""

import unittest
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventRecorder
)

class TestEventType(unittest.TestCase):
    """事件类型测试"""
    
    def test_event_type_values(self):
        """测试事件类型枚举值"""
        # 测试市场数据事件类型
        self.assertEqual(EventType.MARKET_DATA.value, "MARKET_DATA")
        self.assertEqual(EventType.TICK.value, "TICK")
        self.assertEqual(EventType.BAR.value, "BAR")
        self.assertEqual(EventType.DEPTH.value, "DEPTH")
        
        # 测试交易事件类型
        self.assertEqual(EventType.ORDER.value, "ORDER")
        self.assertEqual(EventType.TRADE.value, "TRADE")
        self.assertEqual(EventType.POSITION.value, "POSITION")
        self.assertEqual(EventType.ACCOUNT.value, "ACCOUNT")
        
        # 测试策略事件类型
        self.assertEqual(EventType.STRATEGY.value, "STRATEGY")
        self.assertEqual(EventType.SIGNAL.value, "SIGNAL")
        
        # 测试系统事件类型
        self.assertEqual(EventType.SYSTEM.value, "SYSTEM")
        self.assertEqual(EventType.ERROR.value, "ERROR")
        self.assertEqual(EventType.EMERGENCY.value, "EMERGENCY")
    
    def test_event_type_comparison(self):
        """测试事件类型比较"""
        # 测试相等性
        self.assertEqual(EventType.TICK, EventType.TICK)
        self.assertNotEqual(EventType.TICK, EventType.BAR)
        
        # 测试字符串转换
        self.assertEqual(str(EventType.TICK), "TICK")
        self.assertEqual(EventType("TICK"), EventType.TICK)
        
        # 测试无效类型
        with self.assertRaises(ValueError):
            EventType("INVALID_TYPE")

class TestEvent(unittest.TestCase):
    """事件基类测试"""
    
    def setUp(self):
        """测试初始化"""
        self.event_data = {
            'symbol': 'BTC/USDT',
            'price': 50000.0,
            'volume': 1.5
        }
        self.event = Event(
            event_type=EventType.TICK,
            data=self.event_data,
            source="test_source",
            priority=1
        )
    
    def test_event_creation(self):
        """测试事件创建"""
        self.assertEqual(self.event.event_type, EventType.TICK)
        self.assertEqual(self.event.data, self.event_data)
        self.assertEqual(self.event.source, "test_source")
        self.assertEqual(self.event.priority, 1)
        self.assertIsNotNone(self.event.event_id)
        self.assertIsNotNone(self.event.timestamp)
        self.assertIsNotNone(self.event.trace_id)
    
    def test_event_serialization(self):
        """测试事件序列化"""
        # 测试转换为字典
        event_dict = self.event.to_dict()
        self.assertEqual(event_dict['event_type'], str(EventType.TICK))
        self.assertEqual(event_dict['data'], self.event_data)
        self.assertEqual(event_dict['source'], "test_source")
        
        # 测试转换为JSON
        event_json = self.event.to_json()
        event_from_json = Event.from_json(event_json)
        self.assertEqual(event_from_json.event_type, self.event.event_type)
        self.assertEqual(event_from_json.data, self.event.data)
        
        # 测试从字典创建
        event_from_dict = Event.from_dict(event_dict)
        self.assertEqual(event_from_dict.event_type, self.event.event_type)
        self.assertEqual(event_from_dict.data, self.event.data)
    
    def test_event_comparison(self):
        """测试事件比较"""
        event1 = Event(EventType.TICK, priority=1)
        event2 = Event(EventType.TICK, priority=2)
        event3 = Event(EventType.BAR, priority=1)
        
        # 测试优先级比较
        self.assertLess(event2, event1)  # 数字越小优先级越高
        
        # 测试相等性
        event4 = Event.from_dict(event1.to_dict())
        self.assertEqual(event1.event_id, event4.event_id)
    
    def test_event_validation(self):
        """测试事件验证"""
        # 测试必填字段
        with self.assertRaises(ValueError):
            Event(event_type=None)
        
        # 测试无效的事件类型
        with self.assertRaises(ValueError):
            Event(event_type="INVALID_TYPE")
        
        # 测试无效的优先级
        with self.assertRaises(ValueError):
            Event(EventType.TICK, priority=-1)

class TestEventRecorder(AsyncTestCase):
    """事件记录器测试"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.recorder = EventRecorder(max_records=100)
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
    
    @async_test()
    async def test_event_recording(self):
        """测试事件记录"""
        # 记录事件
        for event in self.test_events:
            self.recorder.record(event)
        
        # 验证记录数量
        self.assertEqual(len(self.recorder._records), 5)
        
        # 验证记录顺序
        records = self.recorder._records
        for i in range(1, len(records)):
            self.assertGreaterEqual(
                records[i].timestamp,
                records[i-1].timestamp
            )
    
    @async_test()
    async def test_event_replay(self):
        """测试事件回放"""
        # 记录事件
        for event in self.test_events:
            self.recorder.record(event)
        
        # 测试时间范围回放
        start_time = self.test_events[1].timestamp
        end_time = self.test_events[3].timestamp
        replayed = self.recorder.replay(
            start_time=start_time,
            end_time=end_time
        )
        self.assertEqual(len(replayed), 3)
        
        # 测试事件类型过滤
        replayed = self.recorder.replay(
            event_types=[EventType.BAR]
        )
        self.assertEqual(len(replayed), 0)
        
        # 测试限制数量
        replayed = self.recorder.replay(limit=2)
        self.assertEqual(len(replayed), 2)
    
    @async_test()
    async def test_recorder_management(self):
        """测试记录器管理功能"""
        # 测试清理记录
        self.recorder.clear()
        self.assertEqual(len(self.recorder._records), 0)
        
        # 测试启用/禁用记录
        self.recorder.set_recording(False)
        self.recorder.record(self.test_events[0])
        self.assertEqual(len(self.recorder._records), 0)
        
        self.recorder.set_recording(True)
        self.recorder.record(self.test_events[0])
        self.assertEqual(len(self.recorder._records), 1)
        
        # 测试最大记录数限制
        recorder = EventRecorder(max_records=3)
        for event in self.test_events:
            recorder.record(event)
        self.assertEqual(len(recorder._records), 3)
    
    @async_test()
    async def test_recorder_stats(self):
        """测试记录器统计信息"""
        # 记录不同类型的事件
        events = [
            Event(EventType.TICK, source="source1"),
            Event(EventType.BAR, source="source1"),
            Event(EventType.TICK, source="source2"),
            Event(EventType.TRADE, source="source1")
        ]
        for event in events:
            self.recorder.record(event)
        
        # 获取统计信息
        stats = self.recorder.get_stats()
        
        # 验证事件计数
        self.assertEqual(stats['total_records'], 4)
        self.assertEqual(stats['event_types']['TICK'], 2)
        self.assertEqual(stats['event_types']['BAR'], 1)
        self.assertEqual(stats['event_types']['TRADE'], 1)
        
        # 验证来源统计
        self.assertEqual(stats['sources']['source1'], 3)
        self.assertEqual(stats['sources']['source2'], 1)

if __name__ == '__main__':
    unittest.main()