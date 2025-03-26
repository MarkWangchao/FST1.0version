#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件追踪测试

测试内容:
- 事件链路追踪
- 事件上下文传递
- 事件处理时序
- 异常追踪
- 性能追踪点
"""

import unittest
import asyncio
import time
import uuid
from typing import Dict, List, Optional
from datetime import datetime
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventBus
)

class TestTracing(AsyncTestCase):
    """事件追踪测试类"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.event_bus = EventBus()
        self.traces = []
        
    def record_trace(self, trace_point: str, data: Dict):
        """记录追踪点"""
        self.traces.append({
            'timestamp': time.time(),
            'trace_point': trace_point,
            'data': data
        })
    
    @async_test()
    async def test_event_chain_tracing(self):
        """测试事件链路追踪"""
        trace_id = str(uuid.uuid4())
        processed_events = []
        
        # 定义事件处理器链
        async def handler1(event: Event):
            self.record_trace('handler1_start', {'event_id': event.event_id})
            await asyncio.sleep(0.001)  # 模拟处理时间
            event.data['handler1_processed'] = True
            processed_events.append(('handler1', event))
            self.record_trace('handler1_end', {'event_id': event.event_id})
            
        async def handler2(event: Event):
            self.record_trace('handler2_start', {'event_id': event.event_id})
            await asyncio.sleep(0.002)  # 模拟处理时间
            event.data['handler2_processed'] = True
            processed_events.append(('handler2', event))
            self.record_trace('handler2_end', {'event_id': event.event_id})
            
        async def handler3(event: Event):
            self.record_trace('handler3_start', {'event_id': event.event_id})
            await asyncio.sleep(0.001)  # 模拟处理时间
            event.data['handler3_processed'] = True
            processed_events.append(('handler3', event))
            self.record_trace('handler3_end', {'event_id': event.event_id})
        
        # 注册事件处理器
        self.event_bus.add_route("TEST_EVENT", handler1)
        self.event_bus.add_route("TEST_EVENT", handler2)
        self.event_bus.add_route("TEST_EVENT", handler3)
        
        # 发布测试事件
        event = Event(
            event_type="TEST_EVENT",
            data={'trace_id': trace_id},
            source="test"
        )
        await self.event_bus.publish(event)
        
        # 等待事件处理完成
        await asyncio.sleep(0.01)
        
        # 验证事件处理顺序
        self.assertEqual(len(processed_events), 3)
        self.assertEqual(processed_events[0][0], 'handler1')
        self.assertEqual(processed_events[1][0], 'handler2')
        self.assertEqual(processed_events[2][0], 'handler3')
        
        # 验证事件处理标记
        final_event = processed_events[-1][1]
        self.assertTrue(final_event.data['handler1_processed'])
        self.assertTrue(final_event.data['handler2_processed'])
        self.assertTrue(final_event.data['handler3_processed'])
        
        # 验证追踪点
        trace_points = [t['trace_point'] for t in self.traces]
        self.assertEqual(trace_points, [
            'handler1_start', 'handler1_end',
            'handler2_start', 'handler2_end',
            'handler3_start', 'handler3_end'
        ])
    
    @async_test()
    async def test_context_propagation(self):
        """测试上下文传递"""
        context = {
            'request_id': str(uuid.uuid4()),
            'user_id': 'test_user',
            'timestamp': time.time()
        }
        
        async def context_handler(event: Event):
            # 验证上下文信息
            self.assertEqual(event.data['context']['request_id'], context['request_id'])
            self.assertEqual(event.data['context']['user_id'], context['user_id'])
            # 添加处理器信息
            event.data['context']['handler_timestamp'] = time.time()
            self.record_trace('context_handler', event.data['context'])
        
        # 注册处理器
        self.event_bus.add_route("CONTEXT_TEST", context_handler)
        
        # 发布带上下文的事件
        event = Event(
            event_type="CONTEXT_TEST",
            data={'context': context},
            source="test"
        )
        await self.event_bus.publish(event)
        
        # 等待处理完成
        await asyncio.sleep(0.01)
        
        # 验证追踪记录
        self.assertEqual(len(self.traces), 1)
        trace = self.traces[0]
        self.assertEqual(trace['trace_point'], 'context_handler')
        self.assertEqual(trace['data']['request_id'], context['request_id'])
    
    @async_test()
    async def test_exception_tracing(self):
        """测试异常追踪"""
        async def error_handler(event: Event):
            self.record_trace('error_handler_start', {'event_id': event.event_id})
            raise ValueError("测试异常")
        
        # 注册异常处理器
        async def exception_handler(event: Event, error: Exception):
            self.record_trace('exception_handler', {
                'event_id': event.event_id,
                'error_type': type(error).__name__,
                'error_msg': str(error)
            })
        
        self.event_bus.add_route("ERROR_TEST", error_handler)
        self.event_bus.set_exception_handler(exception_handler)
        
        # 发布测试事件
        event = Event(
            event_type="ERROR_TEST",
            data={'test': 'data'},
            source="test"
        )
        await self.event_bus.publish(event)
        
        # 等待处理完成
        await asyncio.sleep(0.01)
        
        # 验证追踪记录
        self.assertEqual(len(self.traces), 2)
        self.assertEqual(self.traces[0]['trace_point'], 'error_handler_start')
        self.assertEqual(self.traces[1]['trace_point'], 'exception_handler')
        self.assertEqual(self.traces[1]['data']['error_type'], 'ValueError')
    
    @async_test()
    async def test_performance_tracing(self):
        """测试性能追踪点"""
        async def slow_handler(event: Event):
            self.record_trace('slow_handler_start', {
                'event_id': event.event_id,
                'start_time': time.time()
            })
            await asyncio.sleep(0.1)  # 模拟耗时操作
            self.record_trace('slow_handler_end', {
                'event_id': event.event_id,
                'end_time': time.time()
            })
        
        # 注册处理器
        self.event_bus.add_route("PERF_TEST", slow_handler)
        
        # 发布测试事件
        event = Event(
            event_type="PERF_TEST",
            data={'test': 'data'},
            source="test"
        )
        
        # 记录开始时间
        start_time = time.time()
        await self.event_bus.publish(event)
        
        # 等待处理完成
        await asyncio.sleep(0.2)
        end_time = time.time()
        
        # 验证追踪记录
        self.assertEqual(len(self.traces), 2)
        
        # 验证处理时间
        handler_start = self.traces[0]['data']['start_time']
        handler_end = self.traces[1]['data']['end_time']
        processing_time = handler_end - handler_start
        
        # 验证处理时间在预期范围内 (100ms ± 50ms)
        self.assertGreater(processing_time, 0.05)
        self.assertLess(processing_time, 0.15)
    
    @async_test()
    async def test_concurrent_tracing(self):
        """测试并发追踪"""
        n_events = 5
        events_processed = set()
        
        async def concurrent_handler(event: Event):
            self.record_trace('concurrent_handler_start', {
                'event_id': event.event_id
            })
            await asyncio.sleep(0.01)  # 模拟处理时间
            events_processed.add(event.event_id)
            self.record_trace('concurrent_handler_end', {
                'event_id': event.event_id
            })
        
        # 注册处理器
        self.event_bus.add_route("CONCURRENT_TEST", concurrent_handler)
        
        # 并发发布多个事件
        events = []
        for i in range(n_events):
            event = Event(
                event_type="CONCURRENT_TEST",
                data={'index': i},
                source="test"
            )
            events.append(event)
        
        # 并发发布事件
        await asyncio.gather(*[
            self.event_bus.publish(event)
            for event in events
        ])
        
        # 等待所有事件处理完成
        await asyncio.sleep(0.1)
        
        # 验证所有事件都被处理
        self.assertEqual(len(events_processed), n_events)
        
        # 验证追踪记录
        self.assertEqual(len(self.traces), n_events * 2)  # 每个事件有开始和结束两个追踪点
        
        # 验证追踪点配对
        start_traces = [t for t in self.traces if t['trace_point'] == 'concurrent_handler_start']
        end_traces = [t for t in self.traces if t['trace_point'] == 'concurrent_handler_end']
        self.assertEqual(len(start_traces), len(end_traces))
        
        # 验证每个事件的开始和结束追踪点都存在
        for event in events:
            start_found = any(t['data']['event_id'] == event.event_id for t in start_traces)
            end_found = any(t['data']['event_id'] == event.event_id for t in end_traces)
            self.assertTrue(start_found and end_found)

if __name__ == '__main__':
    unittest.main()