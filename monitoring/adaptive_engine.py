#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 自适应监控引擎

提供动态监控参数调整功能，基于：
- 市场波动率
- 系统负载
- 交易活跃度
"""

import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime
import numpy as np
from prometheus_client import Gauge

# 自适应指标
MONITORING_INTERVAL = Gauge('monitoring_interval_seconds', '监控间隔')
SCALING_FACTOR = Gauge('monitoring_scaling_factor', '缩放因子')

class AdaptiveEngine:
    """自适应监控引擎"""
    
    def __init__(self, config: Dict):
        """
        初始化自适应引擎
        
        Args:
            config: 自适应配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 基础配置
        self.base_interval = config.get('base_interval', 60)
        self.scaling_factors = config.get('scaling_factors', {
            'market_volatility': 0.5,
            'system_load': 0.3,
            'trading_activity': 0.2
        })
        
        # 状态变量
        self.current_interval = self.base_interval
        self.market_metrics = []
        self.system_metrics = []
        self.trading_metrics = []
        
        # 更新Prometheus指标
        MONITORING_INTERVAL.set(self.current_interval)
        
    async def start(self):
        """启动自适应引擎"""
        self.logger.info("自适应监控引擎已启动")
        while True:
            try:
                await self._adjust_monitoring_parameters()
                await asyncio.sleep(self.base_interval)
            except Exception as e:
                self.logger.error(f"自适应参数调整失败: {str(e)}")
                await asyncio.sleep(5)
                
    async def _adjust_monitoring_parameters(self):
        """调整监控参数"""
        try:
            # 计算各个因子的影响
            volatility_impact = self._calculate_volatility_impact()
            load_impact = self._calculate_load_impact()
            activity_impact = self._calculate_activity_impact()
            
            # 计算综合缩放因子
            scaling_factor = (
                volatility_impact * self.scaling_factors['market_volatility'] +
                load_impact * self.scaling_factors['system_load'] +
                activity_impact * self.scaling_factors['trading_activity']
            )
            
            # 更新监控间隔
            self.current_interval = max(1, min(
                self.base_interval * scaling_factor,
                self.base_interval * 2  # 最大不超过基础间隔的2倍
            ))
            
            # 更新Prometheus指标
            MONITORING_INTERVAL.set(self.current_interval)
            SCALING_FACTOR.set(scaling_factor)
            
            self.logger.debug(f"监控间隔已调整为: {self.current_interval}秒")
            
        except Exception as e:
            self.logger.error(f"调整监控参数失败: {str(e)}")
            
    def _calculate_volatility_impact(self) -> float:
        """计算市场波动率影响"""
        if not self.market_metrics:
            return 1.0
            
        try:
            # 使用最近的市场数据计算波动率
            returns = np.diff([m['price'] for m in self.market_metrics]) / \
                     np.array([m['price'] for m in self.market_metrics][:-1])
            volatility = np.std(returns) if len(returns) > 0 else 0
            
            # 将波动率映射到[0.5, 2.0]的范围
            return max(0.5, min(2.0, 1 + volatility * 10))
            
        except Exception:
            return 1.0
            
    def _calculate_load_impact(self) -> float:
        """计算系统负载影响"""
        if not self.system_metrics:
            return 1.0
            
        try:
            # 获取最新的系统指标
            latest = self.system_metrics[-1]
            cpu_usage = latest.get('cpu_percent', 0)
            memory_usage = latest.get('memory_percent', 0)
            
            # 根据资源使用情况计算影响因子
            cpu_factor = 1 + (cpu_usage / 100)
            memory_factor = 1 + (memory_usage / 100)
            
            return max(0.5, min(2.0, (cpu_factor + memory_factor) / 2))
            
        except Exception:
            return 1.0
            
    def _calculate_activity_impact(self) -> float:
        """计算交易活跃度影响"""
        if not self.trading_metrics:
            return 1.0
            
        try:
            # 计算最近的交易频率
            recent_trades = len([m for m in self.trading_metrics 
                               if (datetime.now() - datetime.fromisoformat(m['timestamp']))
                               .total_seconds() <= 300])
            
            # 将交易频率映射到影响因子
            return max(0.5, min(2.0, 1 + recent_trades / 100))
            
        except Exception:
            return 1.0
            
    # 数据更新接口
    def update_market_metrics(self, metrics: Dict):
        """更新市场指标"""
        self.market_metrics.append(metrics)
        if len(self.market_metrics) > 1000:
            self.market_metrics = self.market_metrics[-1000:]
            
    def update_system_metrics(self, metrics: Dict):
        """更新系统指标"""
        self.system_metrics.append(metrics)
        if len(self.system_metrics) > 100:
            self.system_metrics = self.system_metrics[-100:]
            
    def update_trading_metrics(self, metrics: Dict):
        """更新交易指标"""
        self.trading_metrics.append(metrics)
        if len(self.trading_metrics) > 500:
            self.trading_metrics = self.trading_metrics[-500:]
            
    # 查询接口
    def get_current_parameters(self) -> Dict:
        """获取当前监控参数"""
        return {
            'current_interval': self.current_interval,
            'base_interval': self.base_interval,
            'scaling_factors': self.scaling_factors,
            'market_impact': self._calculate_volatility_impact(),
            'load_impact': self._calculate_load_impact(),
            'activity_impact': self._calculate_activity_impact()
        }