#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 回测模块

提供回测功能所需的基础设施:
- 回测引擎
- 性能分析器
- 数据回放
- 结果可视化
"""

import os
import sys
import json
import time
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum

# 配置日志
logger = logging.getLogger(__name__)

class BacktestMode(Enum):
    """回测模式"""
    TICK = "tick"  # Tick级别回测
    BAR = "bar"    # K线级别回测

@dataclass
class BacktestConfig:
    """回测配置"""
    start_time: datetime           # 回测开始时间
    end_time: datetime            # 回测结束时间
    initial_capital: float        # 初始资金
    commission_rate: float        # 手续费率
    slippage: float              # 滑点设置
    mode: BacktestMode           # 回测模式
    symbols: List[str]           # 交易品种
    strategy_configs: Dict       # 策略配置
    data_path: str              # 数据路径
    report_path: str            # 报告路径

class BacktestResult:
    """回测结果"""
    
    def __init__(self):
        self.trades = []          # 交易记录
        self.positions = []       # 持仓记录
        self.daily_returns = []   # 每日收益
        self.metrics = {}         # 性能指标
        self.logs = []           # 回测日志
        
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'trades': self.trades,
            'positions': self.positions,
            'daily_returns': self.daily_returns,
            'metrics': self.metrics,
            'logs': self.logs
        }
    
    def save(self, file_path: str):
        """保存回测结果"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"回测结果已保存: {file_path}")

class BacktestMarketData:
    """回测市场数据管理器"""
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.data_cache = {}
        self.current_time = None
    
    async def load_data(self, symbol: str, start_time: datetime, end_time: datetime) -> bool:
        """加载市场数据"""
        try:
            file_path = os.path.join(self.data_path, f"{symbol}.parquet")
            if not os.path.exists(file_path):
                logger.error(f"数据文件不存在: {file_path}")
                return False
            
            # 加载数据
            df = pd.read_parquet(file_path)
            
            # 过滤时间范围
            df = df[(df['timestamp'] >= start_time) & (df['timestamp'] <= end_time)]
            
            # 缓存数据
            self.data_cache[symbol] = df
            return True
            
        except Exception as e:
            logger.error(f"加载市场数据失败: {str(e)}")
            return False
    
    def get_current_data(self, symbol: str) -> Optional[Dict]:
        """获取当前时间点的市场数据"""
        if symbol not in self.data_cache or self.current_time is None:
            return None
            
        df = self.data_cache[symbol]
        current_data = df[df['timestamp'] == self.current_time]
        
        if len(current_data) == 0:
            return None
            
        return current_data.iloc[0].to_dict()

class BacktestTradeExecutor:
    """回测交易执行器"""
    
    def __init__(self, commission_rate: float, slippage: float):
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.orders = []
        self.trades = []
        self.positions = {}
    
    async def place_order(self, order: Dict) -> Dict:
        """下单"""
        # 计算滑点和手续费
        price = order['price']
        if order['direction'] == 'buy':
            executed_price = price * (1 + self.slippage)
        else:
            executed_price = price * (1 - self.slippage)
            
        commission = executed_price * order['volume'] * self.commission_rate
        
        # 创建成交记录
        trade = {
            'order_id': order['order_id'],
            'symbol': order['symbol'],
            'direction': order['direction'],
            'price': executed_price,
            'volume': order['volume'],
            'commission': commission,
            'timestamp': order['timestamp']
        }
        
        # 更新持仓
        self._update_position(trade)
        
        # 记录订单和成交
        self.orders.append(order)
        self.trades.append(trade)
        
        return trade
    
    def _update_position(self, trade: Dict):
        """更新持仓"""
        symbol = trade['symbol']
        if symbol not in self.positions:
            self.positions[symbol] = {
                'volume': 0,
                'cost': 0
            }
            
        position = self.positions[symbol]
        
        if trade['direction'] == 'buy':
            position['volume'] += trade['volume']
            position['cost'] += trade['price'] * trade['volume']
        else:
            position['volume'] -= trade['volume']
            position['cost'] -= trade['price'] * trade['volume']
            
        # 如果持仓量为0，清除持仓记录
        if position['volume'] == 0:
            del self.positions[symbol]

# 导出的类和函数
__all__ = [
    'BacktestMode',
    'BacktestConfig',
    'BacktestResult',
    'BacktestMarketData',
    'BacktestTradeExecutor'
]