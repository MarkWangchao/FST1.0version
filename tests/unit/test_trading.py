#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 交易功能单元测试

测试交易相关功能:
- 订单管理
- 持仓跟踪
- 交易执行
- 账户管理
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List

from tests.unit import UnitTestCase, TestDataBuilder, mock_dependency
from trading.order_manager import OrderManager
from trading.position_manager import PositionManager
from trading.account_manager import AccountManager
from trading.execution_engine import ExecutionEngine
from trading.risk_checker import RiskChecker

class TestOrderManager(UnitTestCase):
    """订单管理测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.order_manager = OrderManager()
        
        # Mock依赖组件
        self.risk_checker = self.add_mock('risk_checker')
        self.execution_engine = self.add_async_mock('execution_engine')
    
    async def test_order_creation(self):
        """测试订单创建"""
        # 创建订单
        order = await self.order_manager.create_order(
            symbol='BTC/USDT',
            direction='long',
            volume=1.0,
            price=50000.0,
            order_type='LIMIT'
        )
        
        # 验证订单属性
        self.assertIsNotNone(order['order_id'])
        self.assertEqual(order['symbol'], 'BTC/USDT')
        self.assertEqual(order['direction'], 'long')
        self.assertEqual(order['volume'], 1.0)
        self.assertEqual(order['price'], 50000.0)
        self.assertEqual(order['order_type'], 'LIMIT')
        self.assertEqual(order['status'], 'PENDING')
    
    async def test_order_validation(self):
        """测试订单验证"""
        # 设置风控检查结果
        self.risk_checker.validate_order.return_value = {
            'valid': True,
            'message': 'OK'
        }
        
        # 创建有效订单
        order = await self.order_manager.create_order(
            symbol='BTC/USDT',
            direction='long',
            volume=1.0,
            price=50000.0
        )
        
        # 验证订单状态
        self.assertEqual(order['status'], 'PENDING')
        
        # 设置风控检查失败
        self.risk_checker.validate_order.return_value = {
            'valid': False,
            'message': '超过持仓限制'
        }
        
        # 创建无效订单
        with self.assertRaises(ValueError) as context:
            await self.order_manager.create_order(
                symbol='BTC/USDT',
                direction='long',
                volume=10.0,
                price=50000.0
            )
        
        self.assertIn('超过持仓限制', str(context.exception))
    
    async def test_order_cancellation(self):
        """测试订单取消"""
        # 创建订单
        order = await self.order_manager.create_order(
            symbol='BTC/USDT',
            direction='long',
            volume=1.0,
            price=50000.0
        )
        
        # 取消订单
        cancelled_order = await self.order_manager.cancel_order(order['order_id'])
        
        # 验证订单状态
        self.assertEqual(cancelled_order['status'], 'CANCELLED')
        
        # 验证执行引擎调用
        self.execution_engine.cancel_order.assert_called_once_with(order['order_id'])
    
    async def test_order_modification(self):
        """测试订单修改"""
        # 创建订单
        order = await self.order_manager.create_order(
            symbol='BTC/USDT',
            direction='long',
            volume=1.0,
            price=50000.0
        )
        
        # 修改订单
        modified_order = await self.order_manager.modify_order(
            order['order_id'],
            price=51000.0,
            volume=2.0
        )
        
        # 验证修改后的订单
        self.assertEqual(modified_order['price'], 51000.0)
        self.assertEqual(modified_order['volume'], 2.0)
        
        # 验证执行引擎调用
        self.execution_engine.modify_order.assert_called_once()

class TestPositionManager(UnitTestCase):
    """持仓管理测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.position_manager = PositionManager()
    
    def test_position_update(self):
        """测试持仓更新"""
        # 更新持仓
        self.position_manager.update_position({
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 1.0,
            'open_price': 50000.0
        })
        
        # 获取持仓
        position = self.position_manager.get_position('BTC/USDT')
        
        # 验证持仓
        self.assertIsNotNone(position)
        self.assertEqual(position['direction'], 'long')
        self.assertEqual(position['volume'], 1.0)
        self.assertEqual(position['open_price'], 50000.0)
    
    def test_position_pnl(self):
        """测试持仓盈亏计算"""
        # 设置持仓
        self.position_manager.update_position({
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 2.0,
            'open_price': 50000.0
        })
        
        # 计算盈亏
        pnl = self.position_manager.calculate_pnl('BTC/USDT', 51000.0)
        
        # 验证盈亏
        self.assertEqual(pnl['realized_pnl'], 0)
        self.assertEqual(pnl['unrealized_pnl'], 2000.0)  # (51000 - 50000) * 2
        self.assertEqual(pnl['total_pnl'], 2000.0)
    
    def test_position_closure(self):
        """测试持仓平仓"""
        # 设置持仓
        self.position_manager.update_position({
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 2.0,
            'open_price': 50000.0
        })
        
        # 平仓
        self.position_manager.close_position('BTC/USDT')
        
        # 验证持仓已清空
        position = self.position_manager.get_position('BTC/USDT')
        self.assertIsNone(position)

class TestAccountManager(UnitTestCase):
    """账户管理测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.account_manager = AccountManager()
    
    def test_account_balance(self):
        """测试账户余额"""
        # 设置初始余额
        self.account_manager.update_balance('USDT', 100000.0)
        
        # 验证余额
        balance = self.account_manager.get_balance('USDT')
        self.assertEqual(balance, 100000.0)
        
        # 冻结资金
        self.account_manager.freeze_balance('USDT', 50000.0)
        
        # 验证可用余额
        available = self.account_manager.get_available_balance('USDT')
        self.assertEqual(available, 50000.0)
    
    def test_margin_calculation(self):
        """测试保证金计算"""
        # 设置账户状态
        self.account_manager.update_balance('USDT', 100000.0)
        self.account_manager.update_position({
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 2.0,
            'open_price': 50000.0
        })
        
        # 计算保证金
        margin = self.account_manager.calculate_margin()
        
        # 验证保证金
        self.assertEqual(margin['used_margin'], 20000.0)  # 假设保证金率为20%
        self.assertEqual(margin['available_margin'], 80000.0)
    
    def test_account_summary(self):
        """测试账户汇总"""
        # 设置账户数据
        self.account_manager.update_balance('USDT', 100000.0)
        self.account_manager.update_position({
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 1.0,
            'open_price': 50000.0
        })
        
        # 获取账户汇总
        summary = self.account_manager.get_account_summary()
        
        # 验证汇总信息
        self.assertEqual(summary['total_equity'], 100000.0)
        self.assertIn('available_balance', summary)
        self.assertIn('positions_value', summary)
        self.assertIn('margin_ratio', summary)

class TestExecutionEngine(UnitTestCase):
    """执行引擎测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        self.execution_engine = ExecutionEngine()
        
        # Mock交易接口
        self.trading_api = self.add_async_mock('trading_api')
    
    async def test_order_execution(self):
        """测试订单执行"""
        # 创建订单
        order = TestDataBuilder.build_order(
            'BTC/USDT', 'long', 1.0,
            price=50000.0,
            order_type='LIMIT'
        )
        
        # 设置API响应
        self.trading_api.place_order.return_value = {
            'order_id': order['order_id'],
            'status': 'FILLED',
            'filled_price': 50000.0,
            'filled_volume': 1.0
        }
        
        # 执行订单
        result = await self.execution_engine.execute_order(order)
        
        # 验证执行结果
        self.assertEqual(result['status'], 'FILLED')
        self.assertEqual(result['filled_price'], 50000.0)
        self.assertEqual(result['filled_volume'], 1.0)
    
    async def test_order_tracking(self):
        """测试订单跟踪"""
        # 创建订单
        order = TestDataBuilder.build_order(
            'BTC/USDT', 'long', 1.0,
            price=50000.0
        )
        
        # 设置API响应序列
        self.trading_api.get_order_status.side_effect = [
            {'status': 'PENDING'},
            {'status': 'PARTIALLY_FILLED', 'filled_volume': 0.5},
            {'status': 'FILLED', 'filled_volume': 1.0}
        ]
        
        # 跟踪订单状态
        status1 = await self.execution_engine.get_order_status(order['order_id'])
        self.assertEqual(status1['status'], 'PENDING')
        
        status2 = await self.execution_engine.get_order_status(order['order_id'])
        self.assertEqual(status2['status'], 'PARTIALLY_FILLED')
        
        status3 = await self.execution_engine.get_order_status(order['order_id'])
        self.assertEqual(status3['status'], 'FILLED')
    
    async def test_execution_strategy(self):
        """测试执行策略"""
        # 创建大单订单
        order = TestDataBuilder.build_order(
            'BTC/USDT', 'long', 10.0,
            price=50000.0
        )
        
        # 执行TWAP策略
        await self.execution_engine.execute_with_strategy(
            order,
            strategy='TWAP',
            duration=timedelta(minutes=10)
        )
        
        # 验证订单拆分
        self.assertEqual(self.trading_api.place_order.call_count, 10)
        
        # 验证每个子订单的数量
        for call in self.trading_api.place_order.call_args_list:
            args = call[0][0]
            self.assertEqual(args['volume'], 1.0)

if __name__ == '__main__':
    unittest.main()