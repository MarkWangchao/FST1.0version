# tests/event_bus/test_edge_cases.py

import unittest
import asyncio
import json
import random
import string
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import Mock, patch

from infrastructure.event_bus.event_manager import (
    Event, EventType, OptimizedEventBus, EventBusConfig,
    EventFilter, EventRouter, EventValidator
)

class EdgeCaseTests(unittest.TestCase):
    """边界条件测试"""
    
    def setUp(self):
        """测试准备"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # 初始化事件总线
        self.event_bus = OptimizedEventBus(
            name="edge_case_test",
            config_file="config/event_bus.testing.yaml"
        )
        
        # 记录测试事件
        self.received_events = []
        
    def tearDown(self):
        """测试清理"""
        self.loop.run_until_complete(self.event_bus.stop())
        self.loop.close()

    def generate_large_event(self, size_kb: int) -> Event:
        """生成指定大小的事件"""
        # 生成随机字符串作为payload
        payload = ''.join(random.choices(
            string.ascii_letters + string.digits,
            k=size_kb * 1024
        ))
        
        return Event(
            event_type=EventType.CUSTOM,
            data={'payload': payload}
        )

    def test_malformed_events(self):
        """测试格式错误的事件"""
        async def test():
            error_events = []
            def error_handler(event):
                if event.event_type == EventType.ERROR:
                    error_events.append(event)
            
            self.event_bus.router.add_route("ERROR", error_handler)
            await self.event_bus.start()
            
            # 测试各种异常情况
            test_cases = [
                # 缺少必需字段
                Event(event_type=EventType.TICK, data={}),
                
                # 无效的数据类型
                Event(event_type=EventType.TICK, data={
                    'price': 'not_a_number',
                    'volume': 'not_a_number'
                }),
                
                # 超出范围的值
                Event(event_type=EventType.TICK, data={
                    'price': float('inf'),
                    'volume': -1
                }),
                
                # 无效的JSON
                Event(event_type=EventType.CUSTOM, data="{invalid_json}"),
                
                # 特殊字符
                Event(event_type=EventType.CUSTOM, data={
                    'symbol': 'SHFE.rb2405\x00\x01\x02'
                })
            ]
            
            # 发送测试事件
            for event in test_cases:
                await self.event_bus.publish(event)
            
            await asyncio.sleep(0.1)
            
            # 验证错误处理
            self.assertEqual(len(error_events), len(test_cases))
            self.assertTrue(all(
                'validation_error' in e.data.get('reason', '')
                for e in error_events
            ))
            
        self.loop.run_until_complete(test())

    def test_high_frequency_events(self):
        """测试高频事件处理"""
        async def test():
            processed_count = 0
            dropped_count = 0
            
            def event_handler(event):
                nonlocal processed_count
                processed_count += 1
            
            def drop_handler(event):
                nonlocal dropped_count
                dropped_count += 1
            
            self.event_bus.router.add_route("TICK", event_handler)
            self.event_bus.router.add_route("ERROR", drop_handler)
            await self.event_bus.start()
            
            # 模拟每秒10万事件
            total_events = 100_000
            start_time = time.time()
            
            for i in range(total_events):
                event = Event(
                    event_type=EventType.TICK,
                    data={
                        'timestamp': time.time_ns(),
                        'price': 100.0,
                        'volume': 1
                    }
                )
                await self.event_bus.publish(event)
            
            duration = time.time() - start_time
            events_per_second = total_events / duration
            
            # 等待处理完成
            await asyncio.sleep(1)
            
            # 验证处理结果
            total_handled = processed_count + dropped_count
            self.assertEqual(total_handled, total_events)
            self.assertLess(dropped_count / total_events, 0.01)  # 丢弃率小于1%
            
            print(f"\n高频事件测试结果:")
            print(f"总事件数: {total_events}")
            print(f"处理事件数: {processed_count}")
            print(f"丢弃事件数: {dropped_count}")
            print(f"每秒事件数: {events_per_second:.2f}")
            
        self.loop.run_until_complete(test())

    def test_large_events(self):
        """测试大尺寸事件"""
        async def test():
            processed_events = []
            
            def event_handler(event):
                processed_events.append(event)
            
            self.event_bus.router.add_route("CUSTOM", event_handler)
            await self.event_bus.start()
            
            # 测试不同大小的事件
            sizes = [1, 10, 100, 1000]  # KB
            for size in sizes:
                event = self.generate_large_event(size)
                await self.event_bus.publish(event)
            
            await asyncio.sleep(0.5)
            
            # 验证处理结果
            self.assertEqual(len(processed_events), len(sizes))
            
            # 验证数据完整性
            for i, event in enumerate(processed_events):
                expected_size = sizes[i] * 1024
                actual_size = len(event.data['payload'])
                self.assertEqual(actual_size, expected_size)
            
        self.loop.run_until_complete(test())

    def test_concurrent_modifications(self):
        """测试并发修改"""
        async def test():
            # 模拟并发操作
            async def modify_routes():
                for i in range(100):
                    pattern = f"test_pattern_{i}"
                    handler = lambda e: None
                    self.event_bus.router.add_route(pattern, handler)
                    await asyncio.sleep(0.001)
                    self.event_bus.router.remove_route(pattern)
            
            async def modify_filters():
                for i in range(100):
                    filter_func = lambda e: e
                    self.event_bus.filter.add_filter(filter_func)
                    await asyncio.sleep(0.001)
                    self.event_bus.filter.remove_filter(filter_func)
            
            async def publish_events():
                for i in range(100):
                    event = Event(
                        event_type=EventType.CUSTOM,
                        data={'index': i}
                    )
                    await self.event_bus.publish(event)
                    await asyncio.sleep(0.001)
            
            # 同时执行并发操作
            await self.event_bus.start()
            await asyncio.gather(
                modify_routes(),
                modify_filters(),
                publish_events()
            )
            
            # 验证系统状态
            self.assertTrue(self.event_bus._running)
            self.assertEqual(len(self.event_bus.router.routes), 0)
            self.assertEqual(len(self.event_bus.filter.filters), 0)
            
        self.loop.run_until_complete(test())

    def test_error_recovery(self):
        """测试错误恢复"""
        async def test():
            error_count = 0
            recovery_count = 0
            
            def error_handler(event):
                nonlocal error_count
                error_count += 1
            
            def recovery_handler(event):
                nonlocal recovery_count
                recovery_count += 1
            
            self.event_bus.router.add_route("ERROR", error_handler)
            self.event_bus.router.add_route("SYSTEM", recovery_handler)
            await self.event_bus.start()
            
            # 模拟各种错误情况
            scenarios = [
                # 模拟处理器异常
                lambda: self.event_bus.router.add_route(
                    "TEST",
                    lambda e: 1/0  # 除零错误
                ),
                
                # 模拟队列满
                lambda: asyncio.gather(*[
                    self.event_bus.publish(Event(EventType.TICK))
                    for _ in range(10000)
                ]),
                
                # 模拟内存压力
                lambda: [
                    self.event_bus.publish(self.generate_large_event(1000))
                    for _ in range(10)
                ],
                
                # 模拟组件重启
                lambda: self.event_bus.router.routes.clear()
            ]
            
            # 执行错误场景
            for scenario in scenarios:
                try:
                    await scenario()
                except:
                    pass
                await asyncio.sleep(0.1)
            
            # 验证错误处理和恢复
            self.assertGreater(error_count, 0)
            self.assertGreater(recovery_count, 0)
            self.assertTrue(self.event_bus._running)
            
        self.loop.run_until_complete(test())

    def test_resource_limits(self):
        """测试资源限制"""
        async def test():
            # 配置资源限制
            original_queue_size = self.event_bus.normal_queue._maxsize
            self.event_bus.normal_queue._maxsize = 100
            
            dropped_events = []
            def drop_handler(event):
                if event.event_type == EventType.ERROR:
                    dropped_events.append(event)
            
            self.event_bus.router.add_route("ERROR", drop_handler)
            await self.event_bus.start()
            
            # 测试队列限制
            for i in range(200):  # 超过队列大小
                event = Event(
                    event_type=EventType.TICK,
                    data={'sequence': i}
                )
                await self.event_bus.publish(event)
            
            # 测试内存限制
            large_events = [
                self.generate_large_event(1000)  # 1MB事件
                for _ in range(10)
            ]
            for event in large_events:
                await self.event_bus.publish(event)
            
            await asyncio.sleep(0.5)
            
            # 恢复原始配置
            self.event_bus.normal_queue._maxsize = original_queue_size
            
            # 验证资源控制
            self.assertGreater(len(dropped_events), 0)
            self.assertLess(
                self.event_bus.normal_queue.qsize(),
                self.event_bus.normal_queue._maxsize
            )
            
        self.loop.run_until_complete(test())

    def test_invalid_configurations(self):
        """测试无效配置"""
        async def test():
            # 测试各种无效配置
            invalid_configs = [
                # 无效的队列大小
                {'queues.normal.max_size': -1},
                
                # 无效的工作线程数
                {'worker_threads': 0},
                
                # 无效的批处理大小
                {'queues.normal.batch_size': -100},
                
                # 无效的延迟阈值
                {'qos.target_latency': -1},
                
                # 无效的监控配置
                {'monitoring.metrics.collection_interval': 0}
            ]
            
            for invalid_config in invalid_configs:
                # 创建新的配置
                config = EventBusConfig()
                
                # 应用无效配置
                for key, value in invalid_config.items():
                    config.set(key, value)
                
                # 验证配置验证
                validation_errors = config.validate()
                self.assertGreater(len(validation_errors), 0)
            
        self.loop.run_until_complete(test())

if __name__ == '__main__':
    unittest.main()