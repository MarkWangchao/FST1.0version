#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 内存使用测试

测试内容:
- 基础内存使用
- 内存分配和释放
- 内存泄漏检测
- 内存峰值测试
- 内存使用效率
"""

import unittest
import asyncio
import gc
import os
import psutil
import time
import tracemalloc
from typing import Dict, List, Optional
from datetime import datetime
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventBus
)

class TestMemory(AsyncTestCase):
    """内存使用测试类"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.event_bus = EventBus()
        self.process = psutil.Process(os.getpid())
        self.memory_thresholds = {
            'base_usage': 100 * 1024 * 1024,      # 基础内存使用限制 100MB
            'peak_usage': 500 * 1024 * 1024,      # 峰值内存使用限制 500MB
            'leak_threshold': 1 * 1024 * 1024,    # 内存泄漏阈值 1MB
            'allocation_limit': 50 * 1024 * 1024  # 单次分配限制 50MB
        }
        
        # 启动内存跟踪
        tracemalloc.start()
    
    def tearDown(self):
        """测试清理"""
        super().tearDown()
        tracemalloc.stop()
        gc.collect()
    
    def get_memory_usage(self) -> int:
        """获取当前内存使用量"""
        return self.process.memory_info().rss
    
    def test_base_memory_usage(self):
        """测试基础内存使用"""
        # 获取初始内存使用
        initial_memory = self.get_memory_usage()
        
        # 验证基础内存使用是否在限制范围内
        self.assertLess(initial_memory, self.memory_thresholds['base_usage'])
        
        # 输出内存使用信息
        print(f"\n基础内存使用: {initial_memory / 1024 / 1024:.2f}MB")
    
    @async_test()
    async def test_memory_allocation(self):
        """测试内存分配和释放"""
        # 记录初始内存
        initial_memory = self.get_memory_usage()
        
        # 分配大量数据
        data = []
        allocation_size = 1000000  # 每次分配1MB
        n_allocations = 10
        
        memory_points = []
        for i in range(n_allocations):
            data.append(bytearray(allocation_size))
            current_memory = self.get_memory_usage()
            memory_points.append(current_memory)
            
            # 验证单次分配是否超限
            memory_increase = current_memory - initial_memory
            self.assertLess(memory_increase, self.memory_thresholds['allocation_limit'])
        
        # 验证总体内存增长
        peak_memory = max(memory_points)
        self.assertLess(peak_memory - initial_memory, 
                       self.memory_thresholds['allocation_limit'])
        
        # 释放内存
        data.clear()
        gc.collect()
        
        # 验证内存释放
        final_memory = self.get_memory_usage()
        memory_diff = abs(final_memory - initial_memory)
        self.assertLess(memory_diff, self.memory_thresholds['leak_threshold'])
        
        # 输出内存变化
        print(f"\n内存分配测试:")
        print(f"初始内存: {initial_memory / 1024 / 1024:.2f}MB")
        print(f"峰值内存: {peak_memory / 1024 / 1024:.2f}MB")
        print(f"最终内存: {final_memory / 1024 / 1024:.2f}MB")
    
    @async_test()
    async def test_memory_leak_detection(self):
        """测试内存泄漏检测"""
        snapshot1 = tracemalloc.take_snapshot()
        
        # 执行可能导致内存泄漏的操作
        leaky_list = []
        for _ in range(1000):
            # 模拟内存泄漏场景
            event = Event(
                event_type=EventType.TICK,
                data={'price': 100, 'volume': 1},
                source="test"
            )
            leaky_list.append(event)
            await asyncio.sleep(0)
        
        snapshot2 = tracemalloc.take_snapshot()
        
        # 分析内存差异
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        # 输出内存差异统计
        print("\n内存泄漏检测:")
        for stat in top_stats[:3]:  # 只显示前3个最大的内存差异
            print(f"{stat}")
        
        # 验证内存泄漏
        total_leak = sum(stat.size_diff for stat in top_stats)
        self.assertLess(total_leak, self.memory_thresholds['leak_threshold'])
        
        # 清理
        leaky_list.clear()
        gc.collect()
    
    @async_test()
    async def test_peak_memory_usage(self):
        """测试内存峰值使用"""
        initial_memory = self.get_memory_usage()
        peak_memory = initial_memory
        
        # 创建大量事件并发布
        n_events = 10000
        events = []
        
        for i in range(n_events):
            event = Event(
                event_type=EventType.TICK,
                data={
                    'symbol': f'BTC/USDT_{i%100}',
                    'price': 100 + i,
                    'volume': 1,
                    'timestamp': time.time()
                },
                source="test"
            )
            events.append(event)
            
            if i % 1000 == 0:
                current_memory = self.get_memory_usage()
                peak_memory = max(peak_memory, current_memory)
                await asyncio.sleep(0)
        
        # 验证峰值内存
        self.assertLess(peak_memory - initial_memory, 
                       self.memory_thresholds['peak_usage'])
        
        # 清理
        events.clear()
        gc.collect()
        
        # 验证内存释放
        final_memory = self.get_memory_usage()
        memory_diff = abs(final_memory - initial_memory)
        self.assertLess(memory_diff, self.memory_thresholds['leak_threshold'])
        
        # 输出内存使用统计
        print(f"\n峰值内存测试:")
        print(f"初始内存: {initial_memory / 1024 / 1024:.2f}MB")
        print(f"峰值内存: {peak_memory / 1024 / 1024:.2f}MB")
        print(f"最终内存: {final_memory / 1024 / 1024:.2f}MB")
    
    @async_test()
    async def test_memory_efficiency(self):
        """测试内存使用效率"""
        initial_memory = self.get_memory_usage()
        memory_samples = []
        
        # 测试不同大小的数据处理
        data_sizes = [1000, 5000, 10000, 50000]
        
        for size in data_sizes:
            # 生成测试数据
            test_data = [
                {
                    'symbol': f'BTC/USDT_{i%100}',
                    'price': 100 + i,
                    'volume': 1,
                    'timestamp': time.time()
                }
                for i in range(size)
            ]
            
            # 记录处理前内存
            before_memory = self.get_memory_usage()
            
            # 处理数据
            processed_data = []
            for item in test_data:
                processed_data.append({
                    'symbol': item['symbol'],
                    'value': item['price'] * item['volume']
                })
            
            # 记录处理后内存
            after_memory = self.get_memory_usage()
            memory_impact = after_memory - before_memory
            memory_per_item = memory_impact / size
            
            memory_samples.append({
                'size': size,
                'total_memory': memory_impact,
                'memory_per_item': memory_per_item
            })
            
            # 清理
            test_data.clear()
            processed_data.clear()
            gc.collect()
            
            await asyncio.sleep(0)
        
        # 输出内存效率统计
        print("\n内存使用效率测试:")
        for sample in memory_samples:
            print(f"数据大小: {sample['size']}")
            print(f"总内存使用: {sample['total_memory'] / 1024:.2f}KB")
            print(f"每项内存使用: {sample['memory_per_item']:.2f}字节")
            print("---")
        
        # 验证内存效率
        # 检查每项内存使用是否相对稳定（不应随数据量显著增长）
        memory_per_items = [s['memory_per_item'] for s in memory_samples]
        variation = max(memory_per_items) / min(memory_per_items)
        self.assertLess(variation, 2.0)  # 内存使用效率变化不应超过2倍
    
    @async_test()
    async def test_gc_effectiveness(self):
        """测试垃圾回收效果"""
        initial_memory = self.get_memory_usage()
        gc_stats_before = gc.get_stats()
        
        # 创建并删除大量对象
        for _ in range(10):
            data = []
            for i in range(10000):
                data.append({
                    'id': i,
                    'data': bytearray(100)  # 每个对象100字节
                })
            data.clear()
            await asyncio.sleep(0)
        
        # 强制垃圾回收
        gc.collect()
        
        # 获取GC统计信息
        gc_stats_after = gc.get_stats()
        final_memory = self.get_memory_usage()
        
        # 输出GC统计
        print("\n垃圾回收测试:")
        for i, (before, after) in enumerate(zip(gc_stats_before, gc_stats_after)):
            collections = after['collections'] - before['collections']
            collected = after['collected'] - before['collected']
            print(f"代数 {i}:")
            print(f"  收集次数: {collections}")
            print(f"  收集对象数: {collected}")
        
        # 验证内存回收
        memory_diff = abs(final_memory - initial_memory)
        self.assertLess(memory_diff, self.memory_thresholds['leak_threshold'])
        
        print(f"内存差异: {memory_diff / 1024:.2f}KB")

if __name__ == '__main__':
    unittest.main()