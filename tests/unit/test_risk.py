#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 风险管理单元测试

测试风险管理相关功能:
- 风险检查
- 风险控制
- 风险监控
- 风险报告
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List

from tests.unit import UnitTestCase, TestDataBuilder, mock_dependency
from risk.risk_checker import RiskChecker
from risk.risk_controller import RiskController
from risk.risk_monitor import RiskMonitor
from risk.risk_reporter import RiskReporter

class TestRiskChecker(UnitTestCase):
    """风险检查测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.risk_checker = RiskChecker()
        
        # Mock依赖组件
        self.position_manager = self.add_mock('position_manager')
        self.account_manager = self.add_mock('account_manager')
    
    def test_position_limit(self):
        """测试持仓限制"""
        # 设置当前持仓
        self.position_manager.get_position.return_value = {
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 1.0
        }
        
        # 设置持仓限制
        self.risk_checker.set_position_limit('BTC/USDT', 2.0)
        
        # 测试有效订单
        result = self.risk_checker.check_position_limit(
            'BTC/USDT',
            'long',
            0.5
        )
        self.assertTrue(result['valid'])
        
        # 测试超出限制的订单
        result = self.risk_checker.check_position_limit(
            'BTC/USDT',
            'long',
            1.5
        )
        self.assertFalse(result['valid'])
        self.assertIn('超过持仓限制', result['message'])
    
    def test_margin_requirement(self):
        """测试保证金要求"""
        # 设置账户状态
        self.account_manager.get_account_summary.return_value = {
            'total_equity': 100000.0,
            'used_margin': 20000.0,
            'available_margin': 80000.0
        }
        
        # 测试有效保证金
        result = self.risk_checker.check_margin_requirement(
            'BTC/USDT',
            50000.0,  # 价格
            1.0,      # 数量
            0.2       # 保证金率
        )
        self.assertTrue(result['valid'])
        
        # 测试保证金不足
        result = self.risk_checker.check_margin_requirement(
            'BTC/USDT',
            50000.0,
            10.0,
            0.2
        )
        self.assertFalse(result['valid'])
        self.assertIn('保证金不足', result['message'])
    
    def test_risk_exposure(self):
        """测试风险敞口"""
        # 设置当前持仓
        self.position_manager.get_all_positions.return_value = [
            {
                'symbol': 'BTC/USDT',
                'direction': 'long',
                'volume': 1.0,
                'notional_value': 50000.0
            },
            {
                'symbol': 'ETH/USDT',
                'direction': 'short',
                'volume': 10.0,
                'notional_value': 30000.0
            }
        ]
        
        # 设置风险敞口限制
        self.risk_checker.set_exposure_limit(100000.0)
        
        # 测试有效敞口
        result = self.risk_checker.check_risk_exposure(
            'BTC/USDT',
            'long',
            0.5,
            50000.0
        )
        self.assertTrue(result['valid'])
        
        # 测试超出敞口限制
        result = self.risk_checker.check_risk_exposure(
            'BTC/USDT',
            'long',
            2.0,
            50000.0
        )
        self.assertFalse(result['valid'])
        self.assertIn('超过风险敞口限制', result['message'])

class TestRiskController(UnitTestCase):
    """风险控制测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.risk_controller = RiskController()
        
        # Mock依赖组件
        self.order_manager = self.add_async_mock('order_manager')
        self.position_manager = self.add_mock('position_manager')
    
    async def test_stop_loss(self):
        """测试止损控制"""
        # 设置持仓
        position = {
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 1.0,
            'open_price': 50000.0
        }
        self.position_manager.get_position.return_value = position
        
        # 设置止损价格
        self.risk_controller.set_stop_loss('BTC/USDT', 49000.0)
        
        # 触发止损
        await self.risk_controller.check_stop_loss('BTC/USDT', 48000.0)
        
        # 验证平仓订单
        self.order_manager.create_order.assert_called_once_with(
            symbol='BTC/USDT',
            direction='short',
            volume=1.0,
            order_type='MARKET'
        )
    
    async def test_take_profit(self):
        """测试止盈控制"""
        # 设置持仓
        position = {
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 1.0,
            'open_price': 50000.0
        }
        self.position_manager.get_position.return_value = position
        
        # 设置止盈价格
        self.risk_controller.set_take_profit('BTC/USDT', 51000.0)
        
        # 触发止盈
        await self.risk_controller.check_take_profit('BTC/USDT', 52000.0)
        
        # 验证平仓订单
        self.order_manager.create_order.assert_called_once_with(
            symbol='BTC/USDT',
            direction='short',
            volume=1.0,
            order_type='MARKET'
        )
    
    async def test_position_scaling(self):
        """测试仓位缩放"""
        # 设置持仓
        position = {
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 2.0,
            'open_price': 50000.0
        }
        self.position_manager.get_position.return_value = position
        
        # 设置缩放规则
        self.risk_controller.set_scaling_rules('BTC/USDT', [
            {'price': 49000.0, 'scale': 0.5},
            {'price': 48000.0, 'scale': 0.0}
        ])
        
        # 触发缩放
        await self.risk_controller.check_position_scaling('BTC/USDT', 49000.0)
        
        # 验证缩放订单
        self.order_manager.create_order.assert_called_once_with(
            symbol='BTC/USDT',
            direction='short',
            volume=1.0,
            order_type='MARKET'
        )

class TestRiskMonitor(UnitTestCase):
    """风险监控测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.risk_monitor = RiskMonitor()
        
        # Mock依赖组件
        self.position_manager = self.add_mock('position_manager')
        self.account_manager = self.add_mock('account_manager')
    
    def test_drawdown_monitoring(self):
        """测试回撤监控"""
        # 设置账户数据
        self.account_manager.get_account_history.return_value = [
            {'timestamp': '2024-01-01', 'equity': 100000.0},
            {'timestamp': '2024-01-02', 'equity': 95000.0},
            {'timestamp': '2024-01-03', 'equity': 90000.0}
        ]
        
        # 计算回撤
        drawdown = self.risk_monitor.calculate_drawdown()
        
        # 验证回撤计算
        self.assertEqual(drawdown['max_drawdown'], 0.1)  # 10%回撤
        self.assertEqual(drawdown['current_drawdown'], 0.1)
        self.assertEqual(drawdown['drawdown_start'], '2024-01-01')
    
    def test_volatility_monitoring(self):
        """测试波动率监控"""
        # 设置价格数据
        price_data = [
            {'timestamp': '2024-01-01', 'price': 50000.0},
            {'timestamp': '2024-01-02', 'price': 51000.0},
            {'timestamp': '2024-01-03', 'price': 49000.0}
        ]
        
        # 计算波动率
        volatility = self.risk_monitor.calculate_volatility('BTC/USDT', price_data)
        
        # 验证波动率计算
        self.assertIsInstance(volatility['daily_volatility'], float)
        self.assertIsInstance(volatility['annualized_volatility'], float)
    
    def test_correlation_monitoring(self):
        """测试相关性监控"""
        # 设置价格数据
        price_data = {
            'BTC/USDT': [50000.0, 51000.0, 49000.0],
            'ETH/USDT': [3000.0, 3100.0, 2900.0]
        }
        
        # 计算相关性
        correlation = self.risk_monitor.calculate_correlation(price_data)
        
        # 验证相关性计算
        self.assertIsInstance(correlation['BTC/USDT-ETH/USDT'], float)
        self.assertTrue(-1 <= correlation['BTC/USDT-ETH/USDT'] <= 1)

class TestRiskReporter(UnitTestCase):
    """风险报告测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.risk_reporter = RiskReporter()
        
        # Mock依赖组件
        self.risk_monitor = self.add_mock('risk_monitor')
        self.position_manager = self.add_mock('position_manager')
        self.account_manager = self.add_mock('account_manager')
    
    def test_risk_metrics_report(self):
        """测试风险指标报告"""
        # 设置风险数据
        self.risk_monitor.get_risk_metrics.return_value = {
            'drawdown': {'max_drawdown': 0.1, 'current_drawdown': 0.05},
            'volatility': {'daily_volatility': 0.02, 'annualized_volatility': 0.32},
            'sharpe_ratio': 1.5,
            'var_95': 10000.0
        }
        
        # 生成报告
        report = self.risk_reporter.generate_risk_metrics_report()
        
        # 验证报告内容
        self.assertIn('drawdown', report)
        self.assertIn('volatility', report)
        self.assertIn('sharpe_ratio', report)
        self.assertIn('var_95', report)
    
    def test_exposure_report(self):
        """测试敞口报告"""
        # 设置持仓数据
        self.position_manager.get_all_positions.return_value = [
            {
                'symbol': 'BTC/USDT',
                'direction': 'long',
                'volume': 1.0,
                'notional_value': 50000.0
            },
            {
                'symbol': 'ETH/USDT',
                'direction': 'short',
                'volume': 10.0,
                'notional_value': 30000.0
            }
        ]
        
        # 生成报告
        report = self.risk_reporter.generate_exposure_report()
        
        # 验证报告内容
        self.assertIn('total_exposure', report)
        self.assertIn('exposure_by_symbol', report)
        self.assertIn('exposure_by_direction', report)
    
    def test_limit_usage_report(self):
        """测试限额使用报告"""
        # 设置限额数据
        self.risk_monitor.get_limit_usage.return_value = {
            'position_limit': {'used': 0.6, 'remaining': 0.4},
            'margin_limit': {'used': 0.4, 'remaining': 0.6},
            'exposure_limit': {'used': 0.5, 'remaining': 0.5}
        }
        
        # 生成报告
        report = self.risk_reporter.generate_limit_usage_report()
        
        # 验证报告内容
        self.assertIn('position_limit', report)
        self.assertIn('margin_limit', report)
        self.assertIn('exposure_limit', report)

if __name__ == '__main__':
    unittest.main()