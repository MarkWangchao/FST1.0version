#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 策略单元测试

测试策略相关功能:
- 策略初始化和配置
- 信号生成和处理
- 持仓管理
- 性能计算
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List

from tests.unit import UnitTestCase, TestDataBuilder, mock_dependency, data_provider
from strategies.strategy_factory import StrategyFactory
from strategies.base_strategy import BaseStrategy
from strategies.high_frequency.tick_momentum_strategy import TickMomentumStrategy
from strategies.trend.trend_following_strategy import TrendFollowingStrategy

class TestStrategy(UnitTestCase):
    """策略功能测试"""
    
    async def asyncSetUp(self):
        """异步测试准备"""
        await super().asyncSetUp()
        
        # 初始化策略工厂
        self.strategy_factory = StrategyFactory()
        
        # 创建测试策略实例
        self.strategy_config = {
            'strategy_id': 'test_strategy',
            'symbol': 'BTC/USDT',
            'timeframe': '1m',
            'parameters': {
                'window': 20,
                'threshold': 0.01,
                'stop_loss': 0.02,
                'take_profit': 0.03
            }
        }
        
        # Mock市场数据和交易接口
        self.market_data_mock = self.add_async_mock('market_data')
        self.trading_api_mock = self.add_async_mock('trading_api')
    
    @mock_dependency('infrastructure.event_bus.event_manager.EventBus')
    async def test_strategy_initialization(self):
        """测试策略初始化"""
        # 创建策略实例
        strategy = await self.strategy_factory.create_strategy(
            'TickMomentumStrategy',
            self.strategy_config
        )
        
        # 验证策略属性
        self.assertEqual(strategy.strategy_id, 'test_strategy')
        self.assertEqual(strategy.symbol, 'BTC/USDT')
        self.assertEqual(strategy.timeframe, '1m')
        self.assertDictEqual(strategy.parameters, self.strategy_config['parameters'])
        
        # 验证事件订阅
        self.assertTrue(hasattr(strategy, 'on_tick'))
        self.assertTrue(hasattr(strategy, 'on_bar'))
        self.assertTrue(hasattr(strategy, 'on_trade'))
    
    @data_provider(
        ('BTC/USDT', 'long', 1.0, 50000.0),
        ('ETH/USDT', 'short', 2.0, 3000.0)
    )
    async def test_signal_generation(self, symbol: str, direction: str, 
                                   volume: float, price: float):
        """测试信号生成"""
        # 创建策略实例
        strategy = await self.strategy_factory.create_strategy(
            'TrendFollowingStrategy',
            {**self.strategy_config, 'symbol': symbol}
        )
        
        # 模拟市场数据
        market_data = TestDataBuilder.build_event('MARKET_DATA', {
            'symbol': symbol,
            'price': price,
            'volume': volume * 10,
            'timestamp': datetime.now().isoformat()
        })
        
        # 触发信号生成
        signal = await strategy._generate_trading_signals(market_data['data'])
        
        # 验证信号
        self.assertIsNotNone(signal)
        self.assertEqual(signal['symbol'], symbol)
        self.assertEqual(signal['direction'], direction)
        self.assertEqual(signal['volume'], volume)
        self.assertIn('price', signal)
        self.assertIn('timestamp', signal)
    
    async def test_position_management(self):
        """测试持仓管理"""
        # 创建策略实例
        strategy = await self.strategy_factory.create_strategy(
            'TickMomentumStrategy',
            self.strategy_config
        )
        
        # 模拟开仓
        order = TestDataBuilder.build_order(
            'BTC/USDT', 'long', 1.0,
            price=50000.0,
            order_type='LIMIT'
        )
        trade = TestDataBuilder.build_trade(order, 50000.0, 1.0)
        
        # 更新持仓
        await strategy.on_trade(trade)
        
        # 验证持仓状态
        position = strategy.get_position('BTC/USDT')
        self.assertIsNotNone(position)
        self.assertEqual(position['direction'], 'long')
        self.assertEqual(position['volume'], 1.0)
        self.assertEqual(position['open_price'], 50000.0)
        
        # 模拟平仓
        close_order = TestDataBuilder.build_order(
            'BTC/USDT', 'short', 1.0,
            price=51000.0,
            order_type='LIMIT'
        )
        close_trade = TestDataBuilder.build_trade(close_order, 51000.0, 1.0)
        
        # 更新持仓
        await strategy.on_trade(close_trade)
        
        # 验证持仓已清空
        position = strategy.get_position('BTC/USDT')
        self.assertIsNone(position)
    
    async def test_performance_calculation(self):
        """测试性能计算"""
        # 创建策略实例
        strategy = await self.strategy_factory.create_strategy(
            'TrendFollowingStrategy',
            self.strategy_config
        )
        
        # 模拟一系列交易
        trades = [
            # 盈利交易
            {
                'open': TestDataBuilder.build_trade(
                    TestDataBuilder.build_order('BTC/USDT', 'long', 1.0, price=50000.0),
                    50000.0, 1.0
                ),
                'close': TestDataBuilder.build_trade(
                    TestDataBuilder.build_order('BTC/USDT', 'short', 1.0, price=51000.0),
                    51000.0, 1.0
                )
            },
            # 亏损交易
            {
                'open': TestDataBuilder.build_trade(
                    TestDataBuilder.build_order('BTC/USDT', 'long', 1.0, price=51000.0),
                    51000.0, 1.0
                ),
                'close': TestDataBuilder.build_trade(
                    TestDataBuilder.build_order('BTC/USDT', 'short', 1.0, price=50500.0),
                    50500.0, 1.0
                )
            }
        ]
        
        # 执行交易
        for trade in trades:
            await strategy.on_trade(trade['open'])
            await strategy.on_trade(trade['close'])
        
        # 获取性能指标
        performance = strategy.get_performance()
        
        # 验证性能指标
        self.assertIn('total_trades', performance)
        self.assertEqual(performance['total_trades'], 2)
        self.assertIn('win_rate', performance)
        self.assertEqual(performance['win_rate'], 0.5)
        self.assertIn('profit_loss', performance)
        self.assertEqual(performance['profit_loss'], 500.0)  # (1000 - 500)
        self.assertIn('max_drawdown', performance)
        self.assertIn('sharpe_ratio', performance)
    
    async def test_strategy_risk_control(self):
        """测试策略风控"""
        # 创建策略实例
        strategy = await self.strategy_factory.create_strategy(
            'TickMomentumStrategy',
            self.strategy_config
        )
        
        # 设置风控参数
        strategy.set_risk_params({
            'max_position': 2.0,
            'max_drawdown': 0.1,
            'daily_limit': 100000.0
        })
        
        # 测试持仓限制
        order = TestDataBuilder.build_order(
            'BTC/USDT', 'long', 3.0,  # 超过最大持仓
            price=50000.0
        )
        
        # 验证订单被拒绝
        result = await strategy.validate_order(order)
        self.assertFalse(result['valid'])
        self.assertIn('超过最大持仓限制', result['message'])
        
        # 测试止损
        position_data = TestDataBuilder.build_position(
            'BTC/USDT', 'long', 1.0,
            open_price=50000.0
        )
        strategy.update_position(position_data)
        
        # 模拟价格下跌超过止损线
        market_data = TestDataBuilder.build_event('MARKET_DATA', {
            'symbol': 'BTC/USDT',
            'price': 49000.0,  # 下跌2%，触发止损
            'timestamp': datetime.now().isoformat()
        })
        
        # 验证触发止损
        signal = await strategy._check_stop_conditions(market_data['data'])
        self.assertIsNotNone(signal)
        self.assertEqual(signal['type'], 'stop_loss')
        self.assertEqual(signal['direction'], 'short')
    
    async def test_strategy_persistence(self):
        """测试策略状态持久化"""
        # 创建策略实例
        strategy = await self.strategy_factory.create_strategy(
            'TrendFollowingStrategy',
            self.strategy_config
        )
        
        # 设置策略状态
        test_state = {
            'positions': {
                'BTC/USDT': {
                    'direction': 'long',
                    'volume': 1.0,
                    'open_price': 50000.0
                }
            },
            'parameters': {
                'window': 20,
                'threshold': 0.01
            },
            'performance': {
                'total_trades': 10,
                'win_rate': 0.6
            }
        }
        
        # 保存状态
        await strategy.save_state(test_state)
        
        # 加载状态
        loaded_state = await strategy.load_state()
        
        # 验证状态
        self.assertDictEqual(loaded_state, test_state)
    
    async def test_strategy_events(self):
        """测试策略事件处理"""
        # 创建策略实例
        strategy = await self.strategy_factory.create_strategy(
            'TickMomentumStrategy',
            self.strategy_config
        )
        
        # 记录事件
        events = []
        def event_callback(event):
            events.append(event)
        
        # 注册事件回调
        strategy.register_callback('on_signal', event_callback)
        strategy.register_callback('on_order', event_callback)
        strategy.register_callback('on_trade', event_callback)
        
        # 触发信号生成
        signal_data = {
            'symbol': 'BTC/USDT',
            'direction': 'long',
            'volume': 1.0,
            'price': 50000.0
        }
        await strategy.generate_signal(signal_data)
        
        # 验证事件
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'signal')
        self.assertDictEqual(events[0]['data'], signal_data)
        
        # 清理事件
        events.clear()
        
        # 触发订单更新
        order_data = TestDataBuilder.build_order(
            'BTC/USDT', 'long', 1.0,
            price=50000.0
        )
        await strategy.on_order(order_data)
        
        # 验证事件
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'order')
        self.assertEqual(events[0]['data']['order_id'], order_data['order_id'])

if __name__ == '__main__':
    unittest.main()