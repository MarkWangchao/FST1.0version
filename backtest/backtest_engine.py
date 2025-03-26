#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 回测引擎

提供回测功能的核心实现，包括：
- 数据回放
- 策略执行
- 交易模拟
- 结果收集
"""

import os
import sys
import time
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from . import (
    BacktestMode,
    BacktestConfig,
    BacktestResult,
    BacktestMarketData,
    BacktestTradeExecutor
)

# 配置日志
logger = logging.getLogger(__name__)

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, config: BacktestConfig):
        """
        初始化回测引擎
        
        Args:
            config: 回测配置
        """
        self.config = config
        self.result = BacktestResult()
        
        # 初始化组件
        self.market_data = BacktestMarketData(config.data_path)
        self.trade_executor = BacktestTradeExecutor(
            commission_rate=config.commission_rate,
            slippage=config.slippage
        )
        
        # 回测状态
        self.current_time = None
        self.account = {
            'balance': config.initial_capital,
            'positions': {},
            'frozen': 0
        }
        
        # 性能统计
        self.stats = {
            'processed_bars': 0,
            'processed_ticks': 0,
            'generated_signals': 0,
            'executed_trades': 0,
            'processing_time': 0
        }
        
        logger.info("回测引擎初始化完成")
    
    async def run(self) -> BacktestResult:
        """
        运行回测
        
        Returns:
            BacktestResult: 回测结果
        """
        logger.info("开始回测...")
        start_time = time.time()
        
        try:
            # 加载数据
            for symbol in self.config.symbols:
                success = await self.market_data.load_data(
                    symbol,
                    self.config.start_time,
                    self.config.end_time
                )
                if not success:
                    logger.error(f"加载数据失败: {symbol}")
                    return self.result
            
            # 初始化策略
            self.strategies = await self._init_strategies()
            
            # 运行回测
            if self.config.mode == BacktestMode.BAR:
                await self._run_bar_backtest()
            else:
                await self._run_tick_backtest()
            
            # 计算回测结果
            await self._calculate_results()
            
            # 记录执行时间
            self.stats['processing_time'] = time.time() - start_time
            logger.info(f"回测完成，耗时: {self.stats['processing_time']:.2f}秒")
            
            return self.result
            
        except Exception as e:
            logger.error(f"回测执行出错: {str(e)}")
            return self.result
    
    async def _init_strategies(self) -> Dict:
        """初始化策略"""
        strategies = {}
        for strategy_id, config in self.config.strategy_configs.items():
            try:
                # 创建策略实例
                strategy_class = config['class']
                strategy = strategy_class(
                    strategy_id=strategy_id,
                    config=config['params']
                )
                
                # 注入回测接口
                strategy.place_order = self.trade_executor.place_order
                strategy.get_account_info = lambda: self.account
                strategy.get_position = lambda symbol: self.trade_executor.positions.get(symbol)
                
                strategies[strategy_id] = strategy
                logger.info(f"策略初始化成功: {strategy_id}")
                
            except Exception as e:
                logger.error(f"策略初始化失败 - {strategy_id}: {str(e)}")
                
        return strategies
    
    async def _run_bar_backtest(self):
        """运行K线回测"""
        # 获取时间范围内的所有K线时间点
        timestamps = set()
        for symbol in self.config.symbols:
            df = self.market_data.data_cache[symbol]
            timestamps.update(df['timestamp'].tolist())
        timestamps = sorted(timestamps)
        
        # 按时间顺序回放K线
        for timestamp in timestamps:
            self.current_time = timestamp
            self.market_data.current_time = timestamp
            
            # 获取当前K线数据
            bars = {}
            for symbol in self.config.symbols:
                bar_data = self.market_data.get_current_data(symbol)
                if bar_data:
                    bars[symbol] = bar_data
            
            if not bars:
                continue
            
            # 执行策略
            for strategy in self.strategies.values():
                try:
                    await strategy.on_bar(bars)
                    self.stats['processed_bars'] += len(bars)
                except Exception as e:
                    logger.error(f"策略执行出错 - {strategy.strategy_id}: {str(e)}")
            
            # 更新账户状态
            await self._update_account()
    
    async def _run_tick_backtest(self):
        """运行Tick回测"""
        # 获取时间范围内的所有Tick时间点
        timestamps = set()
        for symbol in self.config.symbols:
            df = self.market_data.data_cache[symbol]
            timestamps.update(df['timestamp'].tolist())
        timestamps = sorted(timestamps)
        
        # 按时间顺序回放Tick
        for timestamp in timestamps:
            self.current_time = timestamp
            self.market_data.current_time = timestamp
            
            # 获取当前Tick数据
            ticks = {}
            for symbol in self.config.symbols:
                tick_data = self.market_data.get_current_data(symbol)
                if tick_data:
                    ticks[symbol] = tick_data
            
            if not ticks:
                continue
            
            # 执行策略
            for strategy in self.strategies.values():
                try:
                    await strategy.on_tick(ticks)
                    self.stats['processed_ticks'] += len(ticks)
                except Exception as e:
                    logger.error(f"策略执行出错 - {strategy.strategy_id}: {str(e)}")
            
            # 更新账户状态
            await self._update_account()
    
    async def _update_account(self):
        """更新账户状态"""
        # 更新持仓盈亏
        total_pnl = 0
        for symbol, position in self.trade_executor.positions.items():
            current_data = self.market_data.get_current_data(symbol)
            if current_data and position['volume'] != 0:
                # 计算持仓盈亏
                current_price = current_data['price']
                position_value = position['volume'] * current_price
                cost_value = position['cost']
                pnl = position_value - cost_value
                total_pnl += pnl
        
        # 更新账户余额
        self.account['balance'] = self.config.initial_capital + total_pnl
        
        # 记录每日收益
        if self.current_time.hour == 0 and self.current_time.minute == 0:
            self.result.daily_returns.append({
                'date': self.current_time.date().isoformat(),
                'balance': self.account['balance'],
                'pnl': total_pnl
            })
    
    async def _calculate_results(self):
        """计算回测结果"""
        # 记录交易记录
        self.result.trades = self.trade_executor.trades
        
        # 计算收益率序列
        returns = []
        initial_balance = self.config.initial_capital
        for daily_return in self.result.daily_returns:
            returns.append(
                (daily_return['balance'] - initial_balance) / initial_balance
            )
        
        # 计算性能指标
        self.result.metrics = {
            # 基础指标
            'total_trades': len(self.result.trades),
            'total_returns': returns[-1] if returns else 0,
            'max_drawdown': self._calculate_max_drawdown(returns),
            'sharpe_ratio': self._calculate_sharpe_ratio(returns),
            
            # 交易统计
            'win_rate': self._calculate_win_rate(),
            'profit_factor': self._calculate_profit_factor(),
            'avg_trade_return': self._calculate_avg_trade_return(),
            
            # 执行统计
            'processed_bars': self.stats['processed_bars'],
            'processed_ticks': self.stats['processed_ticks'],
            'processing_time': self.stats['processing_time']
        }
    
    def _calculate_max_drawdown(self, returns: List[float]) -> float:
        """计算最大回撤"""
        if not returns:
            return 0
            
        cumulative = np.array([1 + r for r in returns]).cumprod()
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (running_max - cumulative) / running_max
        return float(np.max(drawdowns))
    
    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """计算夏普比率"""
        if not returns or len(returns) < 2:
            return 0
            
        # 假设无风险利率为0，计算年化夏普比率
        annual_factor = 252  # 交易日数量
        returns_std = np.std(returns) * np.sqrt(annual_factor)
        if returns_std == 0:
            return 0
            
        returns_mean = np.mean(returns) * annual_factor
        return float(returns_mean / returns_std)
    
    def _calculate_win_rate(self) -> float:
        """计算胜率"""
        if not self.result.trades:
            return 0
            
        winning_trades = sum(1 for t in self.result.trades if t['price'] * t['volume'] > t['cost'])
        return winning_trades / len(self.result.trades)
    
    def _calculate_profit_factor(self) -> float:
        """计算盈亏比"""
        gross_profit = sum(t['price'] * t['volume'] - t['cost'] 
                         for t in self.result.trades 
                         if t['price'] * t['volume'] > t['cost'])
        gross_loss = sum(t['cost'] - t['price'] * t['volume']
                        for t in self.result.trades
                        if t['price'] * t['volume'] < t['cost'])
        
        return gross_profit / abs(gross_loss) if gross_loss != 0 else float('inf')
    
    def _calculate_avg_trade_return(self) -> float:
        """计算平均每笔交易收益"""
        if not self.result.trades:
            return 0
            
        total_return = sum(t['price'] * t['volume'] - t['cost'] for t in self.result.trades)
        return total_return / len(self.result.trades)