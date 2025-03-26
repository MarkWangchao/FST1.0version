# tests/performance/test_stress.py

import unittest
import asyncio
import time
import psutil
import gc
from datetime import datetime, timedelta
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from prometheus_client import Counter, Histogram

from infrastructure.event_bus.event_manager import (
    Event, EventType, OptimizedEventBus
)

# 性能指标
LATENCY_HISTOGRAM = Histogram(
    'event_processing_latency_seconds',
    'Event processing latency in seconds',
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5]
)

class StressTests(unittest.TestCase):
    """性能压力测试"""
    
    def setUp(self):
        """测试准备"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # 初始化事件总线
        self.event_bus = OptimizedEventBus(
            name="stress_test",
            config_file="config/event_bus.testing.yaml"
        )
        
        # 性能统计
        self.stats = {
            'processed_events': 0,
            'total_latency': 0,
            'max_latency': 0,
            'min_latency': float('inf'),
            'latencies': []
        }
        
        # 内存基准
        self.initial_memory = psutil.Process().memory_info().rss
        
    def tearDown(self):
        """测试清理"""
        self.loop.run_until_complete(self.event_bus.stop())
        self.loop.close()
        
    def calculate_percentile(self, percentile: float) -> float:
        """计算延迟百分位数"""
        if not self.stats['latencies']:
            return 0
        return np.percentile(self.stats['latencies'], percentile)

    async def generate_events(self, 
                            count: int,
                            event_type: EventType,
                            interval: float = 0) -> None:
        """生成测试事件"""
        for i in range(count):
            event = Event(
                event_type=event_type,
                data={
                    'timestamp': time.time_ns(),
                    'sequence': i,
                    'payload': f"test_data_{i}" * 100  # 模拟实际数据大小
                }
            )
            await self.event_bus.publish(event)
            if interval > 0:
                await asyncio.sleep(interval)

    def test_high_throughput(self):
        """测试高吞吐量场景"""
        async def test():
            # 配置事件处理器
            async def event_handler(event):
                now = time.time_ns()
                latency = (now - event.data['timestamp']) / 1e9  # 转换为秒
                
                # 更新统计
                self.stats['processed_events'] += 1
                self.stats['total_latency'] += latency
                self.stats['max_latency'] = max(self.stats['max_latency'], latency)
                self.stats['min_latency'] = min(self.stats['min_latency'], latency)
                self.stats['latencies'].append(latency)
                
                LATENCY_HISTOGRAM.observe(latency)
            
            self.event_bus.router.add_route("*", event_handler)
            await self.event_bus.start()
            
            # 生成100万个事件
            start_time = time.time()
            await self.generate_events(1_000_000, EventType.TICK)
            
            # 等待处理完成
            while self.stats['processed_events'] < 1_000_000:
                await asyncio.sleep(0.1)
            
            duration = time.time() - start_time
            
            # 计算统计指标
            avg_latency = self.stats['total_latency'] / self.stats['processed_events']
            p99_latency = self.calculate_percentile(99)
            p999_latency = self.calculate_percentile(99.9)
            throughput = self.stats['processed_events'] / duration
            
            # 验证性能指标
            self.assertLess(p99_latency, 0.01)  # 99%延迟小于10ms
            self.assertLess(p999_latency, 0.05)  # 99.9%延迟小于50ms
            self.assertGreater(throughput, 50000)  # 吞吐量大于50K/s
            
            print(f"\n性能测试结果:")
            print(f"总事件数: {self.stats['processed_events']}")
            print(f"平均延迟: {avg_latency*1000:.2f}ms")
            print(f"最大延迟: {self.stats['max_latency']*1000:.2f}ms")
            print(f"最小延迟: {self.stats['min_latency']*1000:.2f}ms")
            print(f"P99延迟: {p99_latency*1000:.2f}ms")
            print(f"P99.9延迟: {p999_latency*1000:.2f}ms")
            print(f"吞吐量: {throughput:.2f} events/s")
            
        self.loop.run_until_complete(test())

    def test_mixed_priority_events(self):
        """测试混合优先级事件处理"""
        async def test():
            processed_events = []
            
            async def event_handler(event):
                processed_events.append({
                    'priority': event.priority,
                    'timestamp': time.time_ns()
                })
            
            self.event_bus.router.add_route("*", event_handler)
            await self.event_bus.start()
            
            # 生成不同优先级的事件
            events = []
            for i in range(1000):
                # 90% 普通事件, 10% 紧急事件
                priority = 1 if i % 10 == 0 else 10
                event = Event(
                    event_type=EventType.TICK,
                    data={'sequence': i},
                    priority=priority
                )
                events.append(event)
            
            # 乱序发送事件
            np.random.shuffle(events)
            for event in events:
                await self.event_bus.publish(event)
            
            # 等待处理完成
            while len(processed_events) < 1000:
                await asyncio.sleep(0.1)
            
            # 验证优先级处理
            high_priority_latencies = []
            normal_priority_latencies = []
            
            for i in range(len(processed_events)-1):
                if processed_events[i]['priority'] == 1:
                    high_priority_latencies.append(
                        processed_events[i+1]['timestamp'] - 
                        processed_events[i]['timestamp']
                    )
                else:
                    normal_priority_latencies.append(
                        processed_events[i+1]['timestamp'] - 
                        processed_events[i]['timestamp']
                    )
            
            avg_high_latency = np.mean(high_priority_latencies) if high_priority_latencies else 0
            avg_normal_latency = np.mean(normal_priority_latencies) if normal_priority_latencies else 0
            
            # 验证高优先级事件的平均处理延迟更低
            self.assertLess(avg_high_latency, avg_normal_latency)
            
        self.loop.run_until_complete(test())

    @unittest.skip("长时间运行测试")
    def test_memory_leak(self):
        """测试内存泄漏"""
        async def test():
            # 配置事件处理器
            async def event_handler(event):
                await asyncio.sleep(0.001)  # 模拟处理时间
            
            self.event_bus.router.add_route("*", event_handler)
            await self.event_bus.start()
            
            memory_samples = []
            start_time = time.time()
            
            # 运行1小时
            while time.time() - start_time < 3600:
                # 每分钟生成10万个事件
                await self.generate_events(100_000, EventType.TICK)
                
                # 强制GC
                gc.collect()
                
                # 记录内存使用
                memory_used = psutil.Process().memory_info().rss - self.initial_memory
                memory_samples.append(memory_used)
                
                # 检查内存增长趋势
                if len(memory_samples) > 10:
                    growth_rate = (memory_samples[-1] - memory_samples[-10]) / 10
                    self.assertLess(growth_rate, 1024 * 1024)  # 内存增长率小于1MB/分钟
                
                await asyncio.sleep(60)
            
        self.loop.run_until_complete(test())

    def test_burst_handling(self):
        """测试突发事件处理"""
        async def test():
            event_count = 0
            max_queue_size = 0
            
            async def event_handler(event):
                nonlocal event_count
                event_count += 1
                # 记录最大队列大小
                nonlocal max_queue_size
                current_size = self.event_bus.normal_queue.qsize()
                max_queue_size = max(max_queue_size, current_size)
                
            self.event_bus.router.add_route("*", event_handler)
            await self.event_bus.start()
            
            # 模拟突发事件
            bursts = [
                (10000, 0),    # 10K事件,无间隔
                (5000, 0.001), # 5K事件,1ms间隔
                (1000, 0.01)   # 1K事件,10ms间隔
            ]
            
            for count, interval in bursts:
                await self.generate_events(count, EventType.TICK, interval)
                # 等待队列处理
                while self.event_bus.normal_queue.qsize() > 0:
                    await asyncio.sleep(0.1)
            
            # 验证所有事件都被处理
            total_events = sum(count for count, _ in bursts)
            self.assertEqual(event_count, total_events)
            
            # 验证队列大小控制
            self.assertLess(max_queue_size, self.event_bus.normal_queue._maxsize)
            
        self.loop.run_until_complete(test())

if __name__ == '__main__':
    unittest.main()