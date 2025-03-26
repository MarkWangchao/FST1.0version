#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件记录器测试

测试内容:
- 事件记录功能
- 事件回放功能
- 记录器管理功能
- 统计信息收集
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
    
    def test_recorder_creation(self):
        """测试记录器创建"""
        self.assertIsNotNone(self.recorder)
        self.assertEqual(self.recorder.max_records, 100)
        self.assertEqual(len(self.recorder._records), 0)
    
    @async_test()
    async def test_event_recording(self):
        """测试事件记录功能"""
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
        
        # 验证记录内容
        for i, event in enumerate(records):
            self.assertEqual(event.event_type, EventType.TICK)
            self.assertEqual(event.data['price'], 100 + i)
            self.assertEqual(event.data['volume'], 1)
            self.assertEqual(event.source, "test")
    
    @async_test()
    async def test_event_replay(self):
        """测试事件回放功能"""
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
        
        # 测试组合条件
        replayed = self.recorder.replay(
            start_time=start_time,
            end_time=end_time,
            event_types=[EventType.TICK],
            limit=2
        )
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
        
        # 验证最早的事件被移除
        self.assertEqual(recorder._records[0].data['price'], 102)
    
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
        
        # 验证时间范围
        self.assertIn('start_time', stats)
        self.assertIn('end_time', stats)
        self.assertLessEqual(stats['start_time'], stats['end_time'])
    
    @async_test()
    async def test_large_scale_recording(self):
        """测试大规模事件记录"""
        # 创建大容量记录器
        recorder = EventRecorder(max_records=1000)
        
        # 生成大量测试事件
        events = []
        for i in range(1500):
            event = Event(
                event_type=EventType.TICK,
                data={'price': 100 + i, 'volume': 1},
                source="test",
                timestamp=time.time() + i
            )
            events.append(event)
        
        # 记录事件
        start_time = time.time()
        for event in events:
            recorder.record(event)
        end_time = time.time()
        
        # 验证记录数量
        self.assertEqual(len(recorder._records), 1000)
        
        # 验证性能
        recording_time = end_time - start_time
        self.assertLess(recording_time, 1.0)  # 确保1500个事件的记录时间小于1秒
        
        # 验证最早的事件被移除
        self.assertEqual(recorder._records[0].data['price'], 500)
    
    @async_test()
    async def test_event_compression(self):
        """测试事件压缩功能"""
        # 创建带压缩的记录器
        recorder = EventRecorder(max_records=100, compression_level=6)
        
        # 记录事件
        for event in self.test_events:
            recorder.record(event)
        
        # 验证记录
        self.assertEqual(len(recorder._records), 5)
        
        # 验证事件数据完整性
        for i, event in enumerate(recorder._records):
            self.assertEqual(event.data['price'], 100 + i)
            self.assertEqual(event.data['volume'], 1)
    
    @async_test()
    async def test_error_handling(self):
        """测试错误处理"""
        # 测试无效事件
        with self.assertRaises(ValueError):
            self.recorder.record(None)
        
        # 测试无效时间范围
        replayed = self.recorder.replay(
            start_time=time.time() + 1000,
            end_time=time.time()
        )
        self.assertEqual(len(replayed), 0)
        
        # 测试无效事件类型
        replayed = self.recorder.replay(
            event_types=["INVALID_TYPE"]
        )
        self.assertEqual(len(replayed), 0)

if __name__ == '__main__':
    unittest.main()