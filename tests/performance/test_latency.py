#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 延迟测试

测试内容:
- 事件处理延迟
- 策略执行延迟
- 订单处理延迟
- 数据访问延迟
- 网络通信延迟
"""

import unittest
import asyncio
import time
import statistics
from typing import Dict, List, Optional
from datetime import datetime
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventBus
)

class TestLatency(AsyncTestCase):
    """延迟测试类"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.event_bus = EventBus()
        self.latency_thresholds = {
            'event_processing': 0.001,  # 1ms
            'strategy_execution': 0.01,  # 10ms
            'order_processing': 0.05,   # 50ms
            'data_access': 0.005,       # 5ms
            'network_communication': 0.1 # 100ms
        }
        
    def test_latency_thresholds(self):
        """测试延迟阈值设置"""
        self.assertGreater(self.latency_thresholds['event_processing'], 0)
        self.assertGreater(self.latency_thresholds['strategy_execution'], 
                         self.latency_thresholds['event_processing'])
        self.assertGreater(self.latency_thresholds['order_processing'], 
                         self.latency_thresholds['strategy_execution'])
    
    @async_test()
    async def test_event_processing_latency(self):
        """测试事件处理延迟"""
        latencies = []
        n_events = 1000
        
        async def event_handler(event: Event):
            start_time = time.time()
            # 模拟事件处理
            await asyncio.sleep(0.0001)
            end_time = time.time()
            latencies.append(end_time - start_time)
        
        # 注册事件处理器
        self.event_bus.add_route("TICK", event_handler)
        
        # 生成并发布测试事件
        for i in range(n_events):
            event = Event(
                event_type=EventType.TICK,
                data={'price': 100 + i, 'volume': 1},
                source="test"
            )
            await self.event_bus.publish(event)
        
        # 等待所有事件处理完成
        await asyncio.sleep(0.1)
        
        # 计算延迟统计
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        
        # 验证延迟
        self.assertLess(avg_latency, self.latency_thresholds['event_processing'])
        self.assertLess(p95_latency, self.latency_thresholds['event_processing'] * 2)
        
        # 输出延迟统计
        print(f"\n事件处理延迟统计:")
        print(f"平均延迟: {avg_latency*1000:.2f}ms")
        print(f"最大延迟: {max_latency*1000:.2f}ms")
        print(f"95分位延迟: {p95_latency*1000:.2f}ms")
    
    @async_test()
    async def test_strategy_execution_latency(self):
        """测试策略执行延迟"""
        latencies = []
        n_executions = 100
        
        async def strategy_execution():
            start_time = time.time()
            # 模拟策略执行
            await asyncio.sleep(0.001)
            end_time = time.time()
            latencies.append(end_time - start_time)
        
        # 执行策略
        for _ in range(n_executions):
            await strategy_execution()
        
        # 计算延迟统计
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]
        
        # 验证延迟
        self.assertLess(avg_latency, self.latency_thresholds['strategy_execution'])
        self.assertLess(p95_latency, self.latency_thresholds['strategy_execution'] * 2)
        
        # 输出延迟统计
        print(f"\n策略执行延迟统计:")
        print(f"平均延迟: {avg_latency*1000:.2f}ms")
        print(f"最大延迟: {max_latency*1000:.2f}ms")
        print(f"95分位延迟: {p95_latency*1000:.2f}ms")
    
    @async_test()
    async def test_order_processing_latency(self):
        """测试订单处理延迟"""
        latencies = []
        n_orders = 100
        
        async def process_order(order_data: Dict):
            start_time = time.time()
            # 模拟订单处理
            await asyncio.sleep(0.005)
            end_time = time.time()
            latencies.append(end_time - start_time)
        
        # 处理订单
        for i in range(n_orders):
            order_data = {
                'order_id': f'order_{i}',
                'symbol': 'BTC/USDT',
                'price': 50000 + i,
                'volume': 0.1
            }
            await process_order(order_data)
        
        # 计算延迟统计
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]
        
        # 验证延迟
        self.assertLess(avg_latency, self.latency_thresholds['order_processing'])
        self.assertLess(p95_latency, self.latency_thresholds['order_processing'] * 2)
        
        # 输出延迟统计
        print(f"\n订单处理延迟统计:")
        print(f"平均延迟: {avg_latency*1000:.2f}ms")
        print(f"最大延迟: {max_latency*1000:.2f}ms")
        print(f"95分位延迟: {p95_latency*1000:.2f}ms")
    
    @async_test()
    async def test_data_access_latency(self):
        """测试数据访问延迟"""
        latencies = []
        n_queries = 1000
        
        async def query_data():
            start_time = time.time()
            # 模拟数据访问
            await asyncio.sleep(0.0005)
            end_time = time.time()
            latencies.append(end_time - start_time)
        
        # 执行数据查询
        for _ in range(n_queries):
            await query_data()
        
        # 计算延迟统计
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]
        
        # 验证延迟
        self.assertLess(avg_latency, self.latency_thresholds['data_access'])
        self.assertLess(p95_latency, self.latency_thresholds['data_access'] * 2)
        
        # 输出延迟统计
        print(f"\n数据访问延迟统计:")
        print(f"平均延迟: {avg_latency*1000:.2f}ms")
        print(f"最大延迟: {max_latency*1000:.2f}ms")
        print(f"95分位延迟: {p95_latency*1000:.2f}ms")
    
    @async_test()
    async def test_network_communication_latency(self):
        """测试网络通信延迟"""
        latencies = []
        n_requests = 100
        
        async def network_request():
            start_time = time.time()
            # 模拟网络请求
            await asyncio.sleep(0.01)
            end_time = time.time()
            latencies.append(end_time - start_time)
        
        # 执行网络请求
        for _ in range(n_requests):
            await network_request()
        
        # 计算延迟统计
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]
        
        # 验证延迟
        self.assertLess(avg_latency, self.latency_thresholds['network_communication'])
        self.assertLess(p95_latency, self.latency_thresholds['network_communication'] * 2)
        
        # 输出延迟统计
        print(f"\n网络通信延迟统计:")
        print(f"平均延迟: {avg_latency*1000:.2f}ms")
        print(f"最大延迟: {max_latency*1000:.2f}ms")
        print(f"95分位延迟: {p95_latency*1000:.2f}ms")
    
    @async_test()
    async def test_concurrent_operations_latency(self):
        """测试并发操作延迟"""
        latencies = []
        n_operations = 100
        n_concurrent = 10
        
        async def operation():
            start_time = time.time()
            # 模拟操作执行
            await asyncio.sleep(0.001)
            end_time = time.time()
            latencies.append(end_time - start_time)
        
        # 并发执行操作
        for _ in range(n_operations):
            tasks = [operation() for _ in range(n_concurrent)]
            await asyncio.gather(*tasks)
        
        # 计算延迟统计
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]
        
        # 验证延迟
        self.assertLess(avg_latency, self.latency_thresholds['event_processing'] * n_concurrent)
        self.assertLess(p95_latency, self.latency_thresholds['event_processing'] * n_concurrent * 2)
        
        # 输出延迟统计
        print(f"\n并发操作延迟统计:")
        print(f"平均延迟: {avg_latency*1000:.2f}ms")
        print(f"最大延迟: {max_latency*1000:.2f}ms")
        print(f"95分位延迟: {p95_latency*1000:.2f}ms")
    
    @async_test()
    async def test_system_under_load(self):
        """测试系统负载下的延迟"""
        latencies = []
        n_operations = 1000
        load_levels = [1, 2, 4, 8, 16]
        
        async def operation():
            start_time = time.time()
            # 模拟操作执行
            await asyncio.sleep(0.0005)
            end_time = time.time()
            latencies.append(end_time - start_time)
        
        # 在不同负载下测试
        for load in load_levels:
            print(f"\n测试负载级别: {load}")
            load_latencies = []
            
            for _ in range(n_operations):
                tasks = [operation() for _ in range(load)]
                await asyncio.gather(*tasks)
                load_latencies.append(statistics.mean([t.result() for t in tasks]))
            
            # 计算延迟统计
            avg_latency = statistics.mean(load_latencies)
            max_latency = max(load_latencies)
            p95_latency = statistics.quantiles(load_latencies, n=20)[18]
            
            # 输出延迟统计
            print(f"平均延迟: {avg_latency*1000:.2f}ms")
            print(f"最大延迟: {max_latency*1000:.2f}ms")
            print(f"95分位延迟: {p95_latency*1000:.2f}ms")
            
            # 验证延迟随负载增长
            if load > 1:
                self.assertGreater(avg_latency, latencies[-1])

if __name__ == '__main__':
    unittest.main()