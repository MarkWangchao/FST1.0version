#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件指标测试

测试内容:
- 指标记录功能
- 时间统计功能
- 标签管理功能
- 指标聚合功能
- 指标清理功能
"""

import unittest
import time
from datetime import datetime, timedelta
from typing import Dict, List
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventMetrics
)

class TestEventMetrics(AsyncTestCase):
    """事件指标测试"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.metrics = EventMetrics()
        
        # 生成测试事件
        self.test_events = [
            Event(
                event_type=EventType.TICK,
                data={'symbol': 'BTC/USDT', 'price': 50000},
                source="test"
            ),
            Event(
                event_type=EventType.TRADE,
                data={'symbol': 'ETH/USDT', 'volume': 2.5},
                source="test"
            )
        ]
    
    def test_metrics_creation(self):
        """测试指标器创建"""
        self.assertIsNotNone(self.metrics)
        self.assertEqual(len(self.metrics._metrics), 0)
        self.assertEqual(len(self.metrics._timers), 0)
    
    @async_test()
    async def test_basic_metrics(self):
        """测试基本指标记录"""
        # 记录简单计数器
        self.metrics.record("event_count", 1)
        self.metrics.record("event_count", 1)
        
        # 记录带标签的指标
        self.metrics.record("tick_count", 1, {"symbol": "BTC/USDT"})
        self.metrics.record("tick_count", 1, {"symbol": "ETH/USDT"})
        
        # 获取指标数据
        metrics_data = self.metrics.get_metrics()
        
        # 验证结果
        self.assertEqual(metrics_data["event_count"], 2)
        self.assertEqual(
            metrics_data["tick_count"]["BTC/USDT"], 1
        )
        self.assertEqual(
            metrics_data["tick_count"]["ETH/USDT"], 1
        )
    
    @async_test()
    async def test_time_metrics(self):
        """测试时间指标记录"""
        # 记录处理时间
        start_time = time.time()
        time.sleep(0.1)  # 模拟处理时间
        self.metrics.record_time(
            "processing_time",
            start_time,
            {"event_type": "TICK"}
        )
        
        # 获取指标数据
        metrics_data = self.metrics.get_metrics()
        
        # 验证结果
        self.assertGreaterEqual(
            metrics_data["processing_time"]["TICK"],
            0.1
        )
    
    @async_test()
    async def test_label_management(self):
        """测试标签管理"""
        # 记录多个标签组合
        labels1 = {"symbol": "BTC/USDT", "type": "spot"}
        labels2 = {"symbol": "ETH/USDT", "type": "futures"}
        
        self.metrics.record("volume", 1.5, labels1)
        self.metrics.record("volume", 2.5, labels2)
        
        # 获取指标数据
        metrics_data = self.metrics.get_metrics()
        
        # 验证结果
        self.assertEqual(
            metrics_data["volume"]["BTC/USDT"]["spot"],
            1.5
        )
        self.assertEqual(
            metrics_data["volume"]["ETH/USDT"]["futures"],
            2.5
        )
    
    @async_test()
    async def test_metric_aggregation(self):
        """测试指标聚合"""
        # 记录多个数值
        self.metrics.record("price", 100.0, {"symbol": "BTC/USDT"})
        self.metrics.record("price", 200.0, {"symbol": "BTC/USDT"})
        self.metrics.record("price", 300.0, {"symbol": "BTC/USDT"})
        
        # 获取指标数据
        metrics_data = self.metrics.get_metrics()
        
        # 验证结果 - 默认是累加
        self.assertEqual(
            metrics_data["price"]["BTC/USDT"],
            600.0
        )
    
    @async_test()
    async def test_metric_types(self):
        """测试不同类型的指标"""
        # 测试计数器
        self.metrics.record("requests", 1)
        self.metrics.record("requests", 1)
        
        # 测试仪表盘
        self.metrics.record("memory_usage", 75.5)
        self.metrics.record("memory_usage", 80.0)
        
        # 测试直方图
        self.metrics.record("latency", 0.1)
        self.metrics.record("latency", 0.2)
        
        # 获取指标数据
        metrics_data = self.metrics.get_metrics()
        
        # 验证结果
        self.assertEqual(metrics_data["requests"], 2)
        self.assertEqual(metrics_data["memory_usage"], 80.0)  # 最新值
        self.assertEqual(metrics_data["latency"], 0.3)  # 累加值
    
    @async_test()
    async def test_metric_reset(self):
        """测试指标重置"""
        # 记录一些指标
        self.metrics.record("count", 1)
        self.metrics.record("value", 100, {"type": "A"})
        
        # 清理指标
        self.metrics.clear()
        
        # 验证结果
        metrics_data = self.metrics.get_metrics()
        self.assertEqual(len(metrics_data), 0)
        
        # 确认可以继续记录
        self.metrics.record("new_count", 1)
        metrics_data = self.metrics.get_metrics()
        self.assertEqual(metrics_data["new_count"], 1)
    
    @async_test()
    async def test_complex_metrics(self):
        """测试复杂指标场景"""
        # 模拟事件处理指标
        events_data = [
            {"type": "TICK", "symbol": "BTC/USDT", "latency": 0.001},
            {"type": "TICK", "symbol": "ETH/USDT", "latency": 0.002},
            {"type": "TRADE", "symbol": "BTC/USDT", "latency": 0.003},
            {"type": "ERROR", "symbol": "BTC/USDT", "latency": 0.005}
        ]
        
        # 记录不同类型的指标
        for data in events_data:
            # 事件计数
            self.metrics.record(
                "event_count",
                1,
                {"type": data["type"]}
            )
            
            # 延迟统计
            self.metrics.record(
                "latency",
                data["latency"],
                {"type": data["type"], "symbol": data["symbol"]}
            )
            
            # 错误计数
            if data["type"] == "ERROR":
                self.metrics.record(
                    "error_count",
                    1,
                    {"symbol": data["symbol"]}
                )
        
        # 获取指标数据
        metrics_data = self.metrics.get_metrics()
        
        # 验证事件计数
        self.assertEqual(
            metrics_data["event_count"]["TICK"],
            2
        )
        self.assertEqual(
            metrics_data["event_count"]["TRADE"],
            1
        )
        self.assertEqual(
            metrics_data["event_count"]["ERROR"],
            1
        )
        
        # 验证延迟统计
        self.assertEqual(
            metrics_data["latency"]["TICK"]["BTC/USDT"],
            0.001
        )
        self.assertEqual(
            metrics_data["latency"]["TICK"]["ETH/USDT"],
            0.002
        )
        
        # 验证错误计数
        self.assertEqual(
            metrics_data["error_count"]["BTC/USDT"],
            1
        )
    
    @async_test()
    async def test_performance_metrics(self):
        """测试性能指标"""
        # 生成大量测试数据
        test_data = []
        for i in range(1000):
            test_data.append({
                "type": "TICK" if i % 2 == 0 else "TRADE",
                "symbol": "BTC/USDT" if i % 3 == 0 else "ETH/USDT",
                "value": i
            })
        
        # 记录开始时间
        start_time = time.time()
        
        # 批量记录指标
        for data in test_data:
            self.metrics.record(
                "test_metric",
                data["value"],
                {
                    "type": data["type"],
                    "symbol": data["symbol"]
                }
            )
        
        # 计算处理时间
        processing_time = time.time() - start_time
        
        # 验证性能
        self.assertLess(processing_time, 1.0)  # 确保1000条记录的处理时间小于1秒
        
        # 验证数据正确性
        metrics_data = self.metrics.get_metrics()
        self.assertIn("test_metric", metrics_data)
        self.assertIn("TICK", metrics_data["test_metric"])
        self.assertIn("TRADE", metrics_data["test_metric"])

if __name__ == '__main__':
    unittest.main()