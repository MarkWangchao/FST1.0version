#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 监控工具测试

测试内容:
- 系统监控
- 交易监控
- 策略监控
- 性能监控
- 资源监控
"""

import unittest
import asyncio
import time
import psutil
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from tests import AsyncTestCase, async_test, DataGenerator
from monitoring.monitor_service import MonitorService
from monitoring.system_monitor import SystemMonitor
from monitoring.trading_monitor import TradingMonitor
from monitoring.strategy_monitor import StrategyMonitor
from monitoring.market_monitor import MarketMonitor
from monitoring.compliance_monitor import ComplianceMonitor

class TestMonitoring(AsyncTestCase):
    """监控工具测试类"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.config = {
            'system_monitor': {
                'interval': 1,
                'thresholds': {
                    'cpu_percent': 80,
                    'memory_percent': 80,
                    'disk_percent': 90
                }
            },
            'trading_monitor': {
                'interval': 1,
                'thresholds': {
                    'order_timeout': 30,
                    'max_drawdown': 0.1,
                    'min_balance': 10000
                }
            },
            'strategy_monitor': {
                'interval': 1,
                'thresholds': {
                    'min_sharpe': 0.5,
                    'max_drawdown': 0.2,
                    'cpu_percent': 80,
                    'memory_mb': 1024
                }
            },
            'market_monitor': {
                'interval': 1,
                'symbols': ['BTC/USDT', 'ETH/USDT'],
                'thresholds': {
                    'price_deviation': 0.05,
                    'volume_deviation': 0.1
                }
            },
            'compliance_monitor': {
                'interval': 1,
                'rules': {
                    'max_position_value': 1000000,
                    'max_order_value': 100000,
                    'max_daily_trades': 1000
                }
            }
        }
        
        # 初始化监控服务
        self.monitor_service = MonitorService(self.config)
        
    @async_test()
    async def test_system_monitoring(self):
        """测试系统监控"""
        system_monitor = SystemMonitor(self.config['system_monitor'])
        
        # 收集系统指标
        metrics = system_monitor.get_current_metrics()
        
        # 验证基本指标
        self.assertIn('cpu_percent', metrics)
        self.assertIn('memory_percent', metrics)
        self.assertIn('disk_percent', metrics)
        self.assertIn('network', metrics)
        
        # 验证指标范围
        self.assertGreaterEqual(metrics['cpu_percent'], 0)
        self.assertLessEqual(metrics['cpu_percent'], 100)
        self.assertGreaterEqual(metrics['memory_percent'], 0)
        self.assertLessEqual(metrics['memory_percent'], 100)
        
        # 测试告警检测
        await system_monitor._check_alerts(metrics)
        alerts = system_monitor.get_alerts()
        
        # 验证告警格式
        for alert in alerts:
            self.assertIn('timestamp', alert)
            self.assertIn('type', alert)
            self.assertIn('level', alert)
            self.assertIn('message', alert)
    
    @async_test()
    async def test_trading_monitoring(self):
        """测试交易监控"""
        trading_monitor = TradingMonitor(self.config['trading_monitor'])
        
        # 模拟订单数据
        order_data = {
            'order_id': 'test_order',
            'symbol': 'BTC/USDT',
            'type': 'limit',
            'side': 'buy',
            'price': 50000,
            'amount': 1.0,
            'status': 'pending',
            'timestamp': time.time()
        }
        trading_monitor.update_order('test_order', order_data)
        
        # 获取订单指标
        metrics = trading_monitor._get_order_metrics()
        
        # 验证订单指标
        self.assertEqual(len(metrics['active_orders']), 1)
        self.assertEqual(metrics['active_orders'][0]['order_id'], 'test_order')
        
        # 测试持仓监控
        position_data = {
            'symbol': 'BTC/USDT',
            'amount': 1.0,
            'avg_price': 50000,
            'unrealized_pnl': 1000
        }
        trading_monitor.update_position('BTC/USDT', position_data)
        
        # 获取持仓指标
        position_metrics = trading_monitor._get_position_metrics()
        self.assertEqual(len(position_metrics['positions']), 1)
        self.assertEqual(position_metrics['positions'][0]['symbol'], 'BTC/USDT')
    
    @async_test()
    async def test_strategy_monitoring(self):
        """测试策略监控"""
        strategy_monitor = StrategyMonitor(self.config['strategy_monitor'])
        
        # 模拟策略状态
        strategy_data = {
            'strategy_id': 'test_strategy',
            'status': 'running',
            'positions': {'BTC/USDT': 1.0},
            'pnl': 1000,
            'sharpe_ratio': 0.8,
            'max_drawdown': 0.15
        }
        strategy_monitor.update_strategy_state('test_strategy', strategy_data)
        
        # 获取策略指标
        metrics = strategy_monitor.get_strategy_metrics(strategy_id='test_strategy')
        
        # 验证策略指标
        self.assertTrue(len(metrics) > 0)
        latest_metric = metrics[0]
        self.assertEqual(latest_metric['strategy_id'], 'test_strategy')
        self.assertEqual(latest_metric['status'], 'running')
        
        # 测试性能指标计算
        returns = [0.01, -0.005, 0.008, -0.002, 0.015]
        sharpe = strategy_monitor._calculate_sharpe(returns)
        self.assertIsInstance(sharpe, float)
        
        drawdown = strategy_monitor._calculate_drawdown(returns)
        self.assertIsInstance(drawdown, float)
    
    @async_test()
    async def test_market_monitoring(self):
        """测试市场监控"""
        market_monitor = MarketMonitor(self.config['market_monitor'])
        
        # 模拟市场数据
        market_data = {
            'symbol': 'BTC/USDT',
            'price': 50000,
            'volume': 100,
            'bid': 49900,
            'ask': 50100,
            'timestamp': time.time()
        }
        market_monitor.update_market_data('BTC/USDT', market_data)
        
        # 获取市场指标
        metrics = market_monitor.get_market_metrics('BTC/USDT')
        
        # 验证市场指标
        self.assertIn('price', metrics)
        self.assertIn('volume', metrics)
        self.assertIn('spread', metrics)
        
        # 测试数据质量评分
        quality_score = market_monitor._calculate_quality_score('BTC/USDT')
        self.assertGreaterEqual(quality_score, 0)
        self.assertLessEqual(quality_score, 1)
    
    @async_test()
    async def test_compliance_monitoring(self):
        """测试合规监控"""
        compliance_monitor = ComplianceMonitor(self.config['compliance_monitor'])
        
        # 模拟交易数据
        trade_data = {
            'trade_id': 'test_trade',
            'symbol': 'BTC/USDT',
            'side': 'buy',
            'price': 50000,
            'amount': 1.0,
            'value': 50000,
            'timestamp': time.time()
        }
        compliance_monitor.add_trade(trade_data)
        
        # 检查合规违规
        violations = compliance_monitor.get_violations()
        
        # 验证违规记录格式
        for violation in violations:
            self.assertIn('timestamp', violation)
            self.assertIn('type', violation)
            self.assertIn('details', violation)
    
    @async_test()
    async def test_monitor_service_integration(self):
        """测试监控服务集成"""
        # 启动监控服务
        await self.monitor_service.start()
        
        # 等待数据收集
        await asyncio.sleep(2)
        
        # 生成测试报告
        await self.monitor_service._generate_report()
        
        # 获取监控数据
        system_metrics = self.monitor_service.get_system_metrics()
        trading_metrics = self.monitor_service.get_trading_metrics()
        strategy_metrics = self.monitor_service.get_strategy_metrics()
        
        # 验证数据完整性
        self.assertTrue(len(system_metrics) > 0)
        self.assertIsInstance(trading_metrics, list)
        self.assertIsInstance(strategy_metrics, list)
        
        # 获取告警信息
        alerts = self.monitor_service.get_all_alerts()
        self.assertIsInstance(alerts, dict)
        self.assertIn('system', alerts)
        self.assertIn('trading', alerts)
        self.assertIn('strategy', alerts)
        
        # 停止监控服务
        await self.monitor_service.stop()
    
    @async_test()
    async def test_performance_monitoring(self):
        """测试性能监控"""
        # 模拟高负载场景
        async def generate_load():
            # CPU负载
            start_time = time.time()
            while time.time() - start_time < 1:
                _ = [i * i for i in range(1000)]
            
            # 内存负载
            data = []
            for _ in range(1000):
                data.append('x' * 1000)
            
            # I/O负载
            for _ in range(100):
                with open('test.tmp', 'w') as f:
                    f.write('test' * 1000)
                
        # 执行负载测试
        await generate_load()
        
        # 获取性能指标
        metrics = self.monitor_service._get_system_status()
        
        # 验证性能指标
        self.assertIn('cpu_usage', metrics)
        self.assertIn('memory_usage', metrics)
        self.assertIn('disk_usage', metrics)
        self.assertIn('network', metrics)
        
        # 清理测试文件
        import os
        if os.path.exists('test.tmp'):
            os.remove('test.tmp')
    
    @async_test()
    async def test_resource_monitoring(self):
        """测试资源监控"""
        # 获取进程信息
        process = psutil.Process()
        
        # 记录初始资源使用
        initial_cpu = process.cpu_percent()
        initial_memory = process.memory_info().rss
        
        # 模拟资源消耗
        data = []
        for _ in range(100000):
            data.append('x' * 100)
        
        # 等待资源统计更新
        await asyncio.sleep(1)
        
        # 获取当前资源使用
        current_cpu = process.cpu_percent()
        current_memory = process.memory_info().rss
        
        # 验证资源变化
        self.assertGreaterEqual(current_memory, initial_memory)
        
        # 清理资源
        data.clear()

if __name__ == '__main__':
    unittest.main()