#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 性能分析器

提供回测结果的分析和可视化功能，包括：
- 收益分析
- 风险分析
- 交易分析
- 图表生成
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

from . import BacktestResult

# 配置日志
logger = logging.getLogger(__name__)

# 配置绘图样式
plt.style.use('seaborn')
sns.set_palette("husl")

class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self, result: BacktestResult):
        """
        初始化性能分析器
        
        Args:
            result: 回测结果对象
        """
        self.result = result
        self.daily_returns_df = pd.DataFrame(result.daily_returns)
        self.trades_df = pd.DataFrame(result.trades)
        
        # 设置时间索引
        if not self.daily_returns_df.empty:
            self.daily_returns_df['date'] = pd.to_datetime(self.daily_returns_df['date'])
            self.daily_returns_df.set_index('date', inplace=True)
        
        if not self.trades_df.empty:
            self.trades_df['timestamp'] = pd.to_datetime(self.trades_df['timestamp'])
            self.trades_df.set_index('timestamp', inplace=True)
    
    def analyze(self) -> Dict[str, Any]:
        """
        执行完整的性能分析
        
        Returns:
            Dict[str, Any]: 分析结果字典
        """
        analysis = {}
        
        # 基础分析
        analysis['basic'] = self._analyze_basic_metrics()
        
        # 收益分析
        analysis['returns'] = self._analyze_returns()
        
        # 风险分析
        analysis['risk'] = self._analyze_risk()
        
        # 交易分析
        analysis['trading'] = self._analyze_trading()
        
        return analysis
    
    def _analyze_basic_metrics(self) -> Dict[str, Any]:
        """分析基础指标"""
        metrics = self.result.metrics.copy()
        
        # 添加年化收益率
        if len(self.daily_returns_df) > 1:
            days = (self.daily_returns_df.index[-1] - self.daily_returns_df.index[0]).days
            annual_return = (1 + metrics['total_returns']) ** (365/days) - 1
            metrics['annual_return'] = float(annual_return)
        
        # 添加交易频率
        if len(self.trades_df) > 0:
            trading_days = len(self.daily_returns_df)
            trades_per_day = len(self.trades_df) / trading_days
            metrics['trades_per_day'] = float(trades_per_day)
        
        return metrics
    
    def _analyze_returns(self) -> Dict[str, Any]:
        """分析收益表现"""
        if self.daily_returns_df.empty:
            return {}
            
        # 计算每日收益率
        daily_returns = self.daily_returns_df['balance'].pct_change()
        
        # 计算累积收益率
        cumulative_returns = (1 + daily_returns).cumprod()
        
        # 计算月度收益率
        monthly_returns = self.daily_returns_df['balance'].resample('M').last().pct_change()
        
        # 计算收益统计
        returns_stats = {
            'mean_daily_return': float(daily_returns.mean()),
            'std_daily_return': float(daily_returns.std()),
            'skewness': float(daily_returns.skew()),
            'kurtosis': float(daily_returns.kurtosis()),
            'best_day': float(daily_returns.max()),
            'worst_day': float(daily_returns.min()),
            'monthly_returns': monthly_returns.to_dict(),
            'cumulative_returns': cumulative_returns.to_dict()
        }
        
        return returns_stats
    
    def _analyze_risk(self) -> Dict[str, Any]:
        """分析风险指标"""
        if self.daily_returns_df.empty:
            return {}
            
        # 计算每日收益率
        daily_returns = self.daily_returns_df['balance'].pct_change()
        
        # 计算波动率
        volatility = daily_returns.std() * np.sqrt(252)
        
        # 计算下行波动率
        downside_returns = daily_returns[daily_returns < 0]
        downside_volatility = downside_returns.std() * np.sqrt(252)
        
        # 计算最大回撤持续期
        cumulative_returns = (1 + daily_returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdowns = (running_max - cumulative_returns) / running_max
        max_drawdown_duration = self._calculate_max_drawdown_duration(drawdowns)
        
        # 计算VaR和CVaR
        var_95 = float(np.percentile(daily_returns, 5))
        cvar_95 = float(daily_returns[daily_returns <= var_95].mean())
        
        risk_stats = {
            'volatility': float(volatility),
            'downside_volatility': float(downside_volatility),
            'var_95': var_95,
            'cvar_95': cvar_95,
            'max_drawdown': float(drawdowns.max()),
            'max_drawdown_duration': max_drawdown_duration,
            'calmar_ratio': float(self.result.metrics['annual_return'] / drawdowns.max()) if drawdowns.max() > 0 else np.inf
        }
        
        return risk_stats
    
    def _analyze_trading(self) -> Dict[str, Any]:
        """分析交易表现"""
        if self.trades_df.empty:
            return {}
            
        # 计算每笔交易的收益
        self.trades_df['return'] = (self.trades_df['price'] * self.trades_df['volume'] - self.trades_df['cost']) / self.trades_df['cost']
        
        # 分析交易方向
        long_trades = self.trades_df[self.trades_df['volume'] > 0]
        short_trades = self.trades_df[self.trades_df['volume'] < 0]
        
        # 计算交易统计
        trading_stats = {
            'total_trades': len(self.trades_df),
            'long_trades': len(long_trades),
            'short_trades': len(short_trades),
            'avg_trade_return': float(self.trades_df['return'].mean()),
            'std_trade_return': float(self.trades_df['return'].std()),
            'max_trade_return': float(self.trades_df['return'].max()),
            'min_trade_return': float(self.trades_df['return'].min()),
            'avg_trade_duration': self._calculate_avg_trade_duration(),
            'profit_factor': self._calculate_profit_factor(),
            'win_rate': float(len(self.trades_df[self.trades_df['return'] > 0]) / len(self.trades_df))
        }
        
        return trading_stats
    
    def generate_report(self, output_path: str):
        """
        生成回测报告
        
        Args:
            output_path: 报告输出路径
        """
        # 创建输出目录
        os.makedirs(output_path, exist_ok=True)
        
        # 生成分析结果
        analysis = self.analyze()
        
        # 保存分析结果
        with open(os.path.join(output_path, 'analysis.json'), 'w') as f:
            json.dump(analysis, f, indent=4)
        
        # 生成图表
        self._plot_equity_curve(output_path)
        self._plot_drawdown_curve(output_path)
        self._plot_monthly_returns_heatmap(output_path)
        self._plot_trade_analysis(output_path)
        
        logger.info(f"回测报告已生成: {output_path}")
    
    def _plot_equity_curve(self, output_path: str):
        """绘制权益曲线"""
        if self.daily_returns_df.empty:
            return
            
        plt.figure(figsize=(12, 6))
        plt.plot(self.daily_returns_df.index, self.daily_returns_df['balance'])
        plt.title('Equity Curve')
        plt.xlabel('Date')
        plt.ylabel('Portfolio Value')
        plt.grid(True)
        plt.savefig(os.path.join(output_path, 'equity_curve.png'))
        plt.close()
    
    def _plot_drawdown_curve(self, output_path: str):
        """绘制回撤曲线"""
        if self.daily_returns_df.empty:
            return
            
        returns = self.daily_returns_df['balance'].pct_change()
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdowns = (running_max - cumulative) / running_max
        
        plt.figure(figsize=(12, 6))
        plt.plot(drawdowns.index, drawdowns * 100)
        plt.title('Drawdown Curve')
        plt.xlabel('Date')
        plt.ylabel('Drawdown (%)')
        plt.grid(True)
        plt.savefig(os.path.join(output_path, 'drawdown_curve.png'))
        plt.close()
    
    def _plot_monthly_returns_heatmap(self, output_path: str):
        """绘制月度收益热力图"""
        if self.daily_returns_df.empty:
            return
            
        returns = self.daily_returns_df['balance'].pct_change()
        monthly_returns = returns.groupby([returns.index.year, returns.index.month]).sum()
        monthly_returns = monthly_returns.unstack()
        
        plt.figure(figsize=(12, 8))
        sns.heatmap(monthly_returns, annot=True, fmt='.2%', cmap='RdYlGn')
        plt.title('Monthly Returns Heatmap')
        plt.savefig(os.path.join(output_path, 'monthly_returns_heatmap.png'))
        plt.close()
    
    def _plot_trade_analysis(self, output_path: str):
        """绘制交易分析图"""
        if self.trades_df.empty:
            return
            
        # 绘制交易收益分布
        plt.figure(figsize=(12, 6))
        sns.histplot(self.trades_df['return'], bins=50)
        plt.title('Trade Returns Distribution')
        plt.xlabel('Return')
        plt.ylabel('Frequency')
        plt.savefig(os.path.join(output_path, 'trade_returns_dist.png'))
        plt.close()
        
        # 绘制交易量随时间变化
        plt.figure(figsize=(12, 6))
        self.trades_df['volume'].abs().plot()
        plt.title('Trading Volume Over Time')
        plt.xlabel('Date')
        plt.ylabel('Volume')
        plt.grid(True)
        plt.savefig(os.path.join(output_path, 'trading_volume.png'))
        plt.close()
    
    def _calculate_max_drawdown_duration(self, drawdowns: pd.Series) -> int:
        """计算最大回撤持续期"""
        if drawdowns.empty:
            return 0
            
        # 找到结束点
        end = drawdowns.idxmax()
        
        # 找到开始点
        temp = drawdowns[:end]
        start = temp[temp == 0].index[-1] if len(temp[temp == 0]) > 0 else temp.index[0]
        
        return (end - start).days
    
    def _calculate_avg_trade_duration(self) -> float:
        """计算平均交易持续时间(分钟)"""
        if len(self.trades_df) < 2:
            return 0
            
        trade_times = self.trades_df.index.to_series()
        durations = trade_times.diff().dt.total_seconds() / 60  # 转换为分钟
        return float(durations.mean())
    
    def _calculate_profit_factor(self) -> float:
        """计算盈亏比"""
        if self.trades_df.empty:
            return 0
            
        profits = self.trades_df[self.trades_df['return'] > 0]['return'].sum()
        losses = abs(self.trades_df[self.trades_df['return'] < 0]['return'].sum())
        
        return float(profits / losses) if losses != 0 else float('inf')