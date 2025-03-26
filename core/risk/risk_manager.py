#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 高性能风险管理器

风险管理器负责所有交易前和交易后的风险控制，具有以下增强特性:
- 多层次风险检查与冷却机制
- 天勤API无缝集成
- 动态风险阈值调整
- 异步并行风险评估
- 熔断与自动恢复
- 实时风险监控与可视化
- 基于机器学习的风险预测
"""

import asyncio
import datetime
import json
import logging
import os
import time
import uuid
import traceback
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache, wraps

# 版本号
__version__ = "1.2.0"

# 尝试导入依赖
try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_VISUALIZATION = True
except ImportError:
    HAS_VISUALIZATION = False

# 尝试导入Prometheus
try:
    from prometheus_client import Counter, Gauge, Histogram, Summary
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

# 尝试导入天勤SDK
try:
    from tqsdk import TqApi, TqAccount
    HAS_TQSDK = True
except ImportError:
    HAS_TQSDK = False

# 尝试导入机器学习库
try:
    import joblib
    from sklearn.ensemble import IsolationForest
    HAS_ML = True
except ImportError:
    HAS_ML = False

# 初始化Prometheus指标
if HAS_PROMETHEUS:
    RISK_LEVEL = Gauge('fst_risk_level', 'Current risk level', ['symbol'])
    RULE_TRIGGERS = Counter('fst_risk_rule_triggers', 'Rule trigger count', ['rule_id', 'level'])
    RULE_CHECK_TIME = Histogram('fst_risk_check_time', 'Rule check execution time', ['rule_id'])
    ORDER_CHECK_TIME = Summary('fst_order_check_time', 'Order risk check time')
    REJECTED_ORDERS = Counter('fst_rejected_orders', 'Orders rejected by risk control', ['reason'])
    CIRCUIT_BREAKER_STATUS = Gauge('fst_circuit_breaker_status', 'Circuit breaker status (0=off, 1=on)')


class RiskLevel(str, Enum):
    """风险级别枚举"""
    LOW = "LOW"           # 低风险
    MEDIUM = "MEDIUM"     # 中等风险
    HIGH = "HIGH"         # 高风险
    CRITICAL = "CRITICAL" # 严重风险


class RiskActionType(str, Enum):
    """风险操作类型枚举"""
    ALERT = "ALERT"           # 仅警告
    REJECT = "REJECT"         # 拒绝操作
    REDUCE = "REDUCE"         # 减仓
    LIQUIDATE = "LIQUIDATE"   # 平仓
    DISABLE = "DISABLE"       # 禁用交易
    CUSTOM = "CUSTOM"         # 自定义操作


class RiskRule:
    """
    风险规则基类 - 增强版
    
    定义了所有风险规则的通用接口，增加了作用域检查、冷却期和异步支持
    """
    
    # 规则模式版本
    SCHEMA_VERSION = "1.0"
    
    def __init__(self,
                 rule_id: str = None,
                 name: str = "",
                 description: str = "",
                 enabled: bool = True,
                 risk_level: RiskLevel = RiskLevel.MEDIUM,
                 action_type: RiskActionType = RiskActionType.ALERT,
                 action_params: Dict[str, Any] = None,
                 scope: Dict[str, Any] = None,
                 cooldown_period: int = 0):  # 冷却期(秒)
        """
        初始化风险规则
        
        Args:
            rule_id: 规则ID
            name: 规则名称
            description: 规则描述
            enabled: 是否启用
            risk_level: 风险级别
            action_type: 触发动作类型
            action_params: 动作参数
            scope: 规则作用范围
            cooldown_period: 冷却期(秒)
        """
        self.rule_id = rule_id or f"risk_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.description = description
        self.enabled = enabled
        self.risk_level = risk_level
        self.action_type = action_type
        self.action_params = action_params or {}
        self.scope = scope or {"global": True}
        self.cooldown_period = cooldown_period
        
        # 触发状态
        self.last_triggered = None
        self.trigger_count = 0
        self.last_check_time = 0
        self.check_count = 0
        
        # 日志器
        self.logger = logging.getLogger(f"fst.risk.rule.{self.rule_id}")
        
    def check(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        检查风险规则
        
        Args:
            context: 风险检查上下文，包含账户、订单等信息
            
        Returns:
            Tuple[bool, Dict]: (是否触发风险规则, 附加信息)
        """
        start_time = time.time()
        self.check_count += 1
        
        try:
            # 检查规则是否启用
            if not self.enabled:
                return False, {"reason": "Rule disabled"}
                
            # 检查规则作用域
            if not self._check_scope(context):
                return False, {"reason": "Scope mismatch"}
                
            # 检查冷却期
            if self._in_cooldown():
                return False, {"reason": "In cooldown period"}
                
            # 执行实际检查（子类实现）
            result, info = self._check_impl(context)
            
            # 更新触发状态
            if result:
                self.update_trigger_status()
                
                # 更新Prometheus指标
                if HAS_PROMETHEUS:
                    RULE_TRIGGERS.labels(
                        rule_id=self.rule_id, 
                        level=self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level)
                    ).inc()
            
            return result, info
            
        finally:
            # 记录执行时间
            execution_time = time.time() - start_time
            self.last_check_time = execution_time
            
            # 更新Prometheus指标
            if HAS_PROMETHEUS:
                RULE_CHECK_TIME.labels(rule_id=self.rule_id).observe(execution_time)
                
    async def async_check(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        异步检查风险规则（用于计算密集型规则）
        
        Args:
            context: 风险检查上下文
            
        Returns:
            Tuple[bool, Dict]: (是否触发风险规则, 附加信息)
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.check, context)
        
    def _check_impl(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        具体检查实现（由子类重写）
        
        Args:
            context: 风险检查上下文
            
        Returns:
            Tuple[bool, Dict]: (是否触发风险规则, 附加信息)
        """
        # 基类不做具体检查，由子类实现
        return False, {}
        
    def _check_scope(self, context: Dict[str, Any]) -> bool:
        """
        检查规则是否适用于当前上下文
        
        Args:
            context: 风险检查上下文
            
        Returns:
            bool: 是否适用
        """
        # 全局规则适用于所有情况
        if self.scope.get("global", False):
            return True
            
        # 检查交易对象范围
        if "symbols" in self.scope and "symbol" in context:
            symbols = self.scope["symbols"]
            if isinstance(symbols, list) and context["symbol"] not in symbols:
                return False
                
        # 检查账户范围
        if "accounts" in self.scope and "account_id" in context:
            accounts = self.scope["accounts"]
            if isinstance(accounts, list) and context["account_id"] not in accounts:
                return False
                
        # 检查策略范围
        if "strategies" in self.scope and "strategy_id" in context:
            strategies = self.scope["strategies"]
            if isinstance(strategies, list) and context["strategy_id"] not in strategies:
                return False
                
        # 检查时间范围
        if "time_range" in self.scope:
            now = datetime.datetime.now().time()
            time_range = self.scope["time_range"]
            
            if "start" in time_range and "end" in time_range:
                start_parts = time_range["start"]
                end_parts = time_range["end"]
                
                if isinstance(start_parts, list) and len(start_parts) >= 2:
                    start = datetime.time(start_parts[0], start_parts[1])
                    end = datetime.time(end_parts[0], end_parts[1])
                    
                    # 检查当前时间是否在范围内
                    if not (start <= now <= end):
                        return False
        
        return True
        
    def _in_cooldown(self) -> bool:
        """
        检查是否处于冷却期
        
        Returns:
            bool: 是否处于冷却期
        """
        if self.cooldown_period <= 0 or self.last_triggered is None:
            return False
            
        # 解析上次触发时间
        try:
            last_time = datetime.datetime.fromisoformat(self.last_triggered)
            elapsed = (datetime.datetime.now() - last_time).total_seconds()
            return elapsed < self.cooldown_period
        except (ValueError, TypeError):
            return False
        
    def update_trigger_status(self):
        """更新触发状态"""
        self.last_triggered = datetime.datetime.now().isoformat()
        self.trigger_count += 1
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else self.risk_level,
            "action_type": self.action_type.value if isinstance(self.action_type, RiskActionType) else self.action_type,
            "action_params": self.action_params,
            "scope": self.scope,
            "cooldown_period": self.cooldown_period,
            "last_triggered": self.last_triggered,
            "trigger_count": self.trigger_count,
            "schema_version": self.SCHEMA_VERSION
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskRule':
        """从字典创建风险规则"""
        # 检查模式版本
        schema_version = data.get("schema_version", "1.0")
        if schema_version != cls.SCHEMA_VERSION:
            raise ValueError(f"不兼容的规则版本: 需要 {cls.SCHEMA_VERSION}, 获取到 {schema_version}")
            
        rule = cls(
            rule_id=data.get("rule_id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            risk_level=data.get("risk_level", RiskLevel.MEDIUM),
            action_type=data.get("action_type", RiskActionType.ALERT),
            action_params=data.get("action_params", {}),
            scope=data.get("scope", {"global": True}),
            cooldown_period=data.get("cooldown_period", 0)
        )
        
        # 恢复触发状态
        rule.last_triggered = data.get("last_triggered")
        rule.trigger_count = data.get("trigger_count", 0)
        
        return rule
        
    def __str__(self) -> str:
        return f"RiskRule(id={self.rule_id}, name='{self.name}', level={self.risk_level}, enabled={self.enabled})"


class CircuitBreakerRule(RiskRule):
    """
    熔断器规则
    
    当系统检测到持续异常时触发熔断，停止交易活动
    """
    
    def __init__(self, 
                 rule_id: str = None,
                 threshold: int = 3,           # 触发阈值(连续失败次数)
                 recovery_time: int = 300,     # 恢复时间(秒)
                 scope: Dict[str, Any] = None):
        """
        初始化熔断器规则
        
        Args:
            rule_id: 规则ID
            threshold: 触发阈值（连续失败次数）
            recovery_time: 恢复时间（秒）
            scope: 规则作用范围
        """
        super().__init__(
            rule_id=rule_id,
            name="Trading Circuit Breaker",
            description=f"当连续失败次数达到{threshold}次时触发熔断，{recovery_time}秒后自动恢复",
            risk_level=RiskLevel.CRITICAL,
            action_type=RiskActionType.DISABLE,
            scope=scope or {"global": True}
        )
        
        self.threshold = threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.tripped = False
        self.tripped_time = None
        
    def _check_impl(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        检查是否需要触发熔断
        
        Args:
            context: 包含失败信息的上下文
            
        Returns:
            Tuple[bool, Dict]: (是否触发熔断, 附加信息)
        """
        # 检查是否已经触发熔断
        if self.tripped:
            # 检查是否可以恢复
            elapsed = time.time() - self.tripped_time
            if elapsed >= self.recovery_time:
                self.logger.info(f"熔断器恢复正常，经过{elapsed:.1f}秒")
                self.tripped = False
                self.failure_count = 0
                self.tripped_time = None
                
                # 更新Prometheus指标
                if HAS_PROMETHEUS:
                    CIRCUIT_BREAKER_STATUS.set(0)
                
                return False, {"status": "BREAKER_RESET"}
            else:
                return True, {
                    "status": "BREAKER_TRIPPED",
                    "remaining_time": self.recovery_time - elapsed
                }
                
        # 检查是否有新的失败
        if context.get("failure", False):
            self.failure_count += 1
            
            if self.failure_count >= self.threshold:
                self.logger.warning(f"触发熔断器！连续失败次数: {self.failure_count}")
                self.tripped = True
                self.tripped_time = time.time()
                
                # 更新Prometheus指标
                if HAS_PROMETHEUS:
                    CIRCUIT_BREAKER_STATUS.set(1)
                
                return True, {"status": "BREAKER_TRIPPED", "failures": self.failure_count}
        else:
            # 如果本次检查没有失败，重置计数器
            self.failure_count = 0
                
        return False, {"failure_count": self.failure_count}
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data.update({
            "threshold": self.threshold,
            "recovery_time": self.recovery_time,
            "failure_count": self.failure_count,
            "tripped": self.tripped,
            "tripped_time": self.tripped_time
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CircuitBreakerRule':
        """从字典创建熔断器规则"""
        rule = super().from_dict(data)
        rule.threshold = data.get("threshold", 3)
        rule.recovery_time = data.get("recovery_time", 300)
        rule.failure_count = data.get("failure_count", 0)
        rule.tripped = data.get("tripped", False)
        rule.tripped_time = data.get("tripped_time")
        return rule


class DynamicRiskRule(RiskRule):
    """
    动态风险规则
    
    根据市场状况动态调整风险参数
    """
    
    def __init__(self,
                 rule_id: str = None,
                 name: str = "Dynamic Risk Rule",
                 base_threshold: float = 1.0,
                 volatility_factor: float = 1.0,
                 lookback_periods: int = 20,
                 update_interval: int = 3600,  # 更新间隔(秒)
                 scope: Dict[str, Any] = None):
        """
        初始化动态风险规则
        
        Args:
            rule_id: 规则ID
            name: 规则名称
            base_threshold: 基础阈值
            volatility_factor: 波动率因子
            lookback_periods: 回溯周期数
            update_interval: 更新间隔(秒)
            scope: 规则作用范围
        """
        super().__init__(
            rule_id=rule_id,
            name=name,
            description=f"根据市场波动率动态调整风险阈值",
            risk_level=RiskLevel.MEDIUM,
            scope=scope
        )
        
        self.base_threshold = base_threshold
        self.volatility_factor = volatility_factor
        self.lookback_periods = lookback_periods
        self.update_interval = update_interval
        
        self.last_update_time = 0
        self.volatility_history = {}  # {symbol: [历史波动率值]}
        
        # 天勤API引用(由风险管理器注入)
        self.api = None
        
    def set_api(self, api):
        """设置天勤API引用"""
        self.api = api
        
    def _check_impl(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        具体检查实现
        
        Args:
            context: 风险检查上下文
            
        Returns:
            Tuple[bool, Dict]: (是否触发风险规则, 附加信息)
        """
        # 子类需要重写此方法
        return False, {}
        
    def update_volatility(self, symbol: str) -> float:
        """
        更新波动率值
        
        Args:
            symbol: 交易品种
            
        Returns:
            float: 最新波动率
        """
        # 检查是否需要更新
        now = time.time()
        if now - self.last_update_time < self.update_interval:
            # 使用缓存的波动率值
            if symbol in self.volatility_history and self.volatility_history[symbol]:
                return self.volatility_history[symbol][-1]
                
        # 需要更新波动率
        try:
            if self.api and HAS_TQSDK:
                # 获取K线数据
                klines = self.api.get_kline_serial(symbol, 60, self.lookback_periods + 10)
                
                if HAS_PANDAS and len(klines) > self.lookback_periods:
                    df = pd.DataFrame(klines)
                    # 计算收益率
                    returns = np.log(df['close'] / df['close'].shift(1)).dropna()
                    # 计算波动率(年化)
                    vol = returns.std() * np.sqrt(252 * 24)
                    
                    # 更新波动率历史
                    if symbol not in self.volatility_history:
                        self.volatility_history[symbol] = []
                        
                    self.volatility_history[symbol].append(float(vol))
                    
                    # 保留最近100个值
                    if len(self.volatility_history[symbol]) > 100:
                        self.volatility_history[symbol] = self.volatility_history[symbol][-100:]
                        
                    self.last_update_time = now
                    self.volatility_factor = float(vol)
                    
                    return float(vol)
        except Exception as e:
            self.logger.error(f"更新波动率异常: {str(e)}")
            
        # 默认返回1.0
        return 1.0
        
    def get_adjusted_threshold(self, symbol: str) -> float:
        """
        获取调整后的阈值
        
        Args:
            symbol: 交易品种
            
        Returns:
            float: 调整后的阈值
        """
        vol = self.update_volatility(symbol)
        return self.base_threshold * vol
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data.update({
            "base_threshold": self.base_threshold,
            "volatility_factor": self.volatility_factor,
            "lookback_periods": self.lookback_periods,
            "update_interval": self.update_interval,
            "last_update_time": self.last_update_time
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DynamicRiskRule':
        """从字典创建动态风险规则"""
        rule = super().from_dict(data)
        rule.base_threshold = data.get("base_threshold", 1.0)
        rule.volatility_factor = data.get("volatility_factor", 1.0)
        rule.lookback_periods = data.get("lookback_periods", 20)
        rule.update_interval = data.get("update_interval", 3600)
        rule.last_update_time = data.get("last_update_time", 0)
        return rule


class MaxOrderValueRule(DynamicRiskRule):
    """
    最大订单价值规则
    
    限制单笔订单的最大价值，可根据市场波动率动态调整
    """
    
    def __init__(self,
                 rule_id: str = None,
                 max_value: float = 100000.0,  # 最大订单价值
                 adjust_by_volatility: bool = True,  # 是否根据波动率调整
                 scope: Dict[str, Any] = None):
        """
        初始化最大订单价值规则
        
        Args:
            rule_id: 规则ID
            max_value: 最大订单价值
            adjust_by_volatility: 是否根据波动率调整
            scope: 规则作用范围
        """
        super().__init__(
            rule_id=rule_id,
            name="Maximum Order Value",
            description=f"限制单笔订单最大价值不超过{max_value}",
            base_threshold=max_value,
            scope=scope
        )
        
        self.max_value = max_value
        self.adjust_by_volatility = adjust_by_volatility
        
    def _check_impl(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        检查订单价值是否超过限制
        
        Args:
            context: 风险检查上下文
            
        Returns:
            Tuple[bool, Dict]: (是否超过限制, 附加信息)
        """
        order = context.get("order", {})
        symbol = order.get("symbol", "")
        price = order.get("price", 0.0)
        volume = order.get("volume", 0)
        
        # 计算订单价值
        order_value = price * volume
        
        # 获取当前最大限制
        current_limit = self.max_value
        if self.adjust_by_volatility and symbol:
            # 根据波动率调整限制
            vol_factor = self.update_volatility(symbol)
            # 波动率高时降低限制
            current_limit = self.max_value / vol_factor
            
        # 检查是否超过限制
        if order_value > current_limit:
            return True, {
                "order_value": order_value,
                "current_limit": current_limit,
                "volatility_factor": self.volatility_factor
            }
            
        return False, {
            "order_value": order_value,
            "current_limit": current_limit
        }
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data.update({
            "max_value": self.max_value,
            "adjust_by_volatility": self.adjust_by_volatility
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MaxOrderValueRule':
        """从字典创建规则"""
        rule = super().from_dict(data)
        rule.max_value = data.get("max_value", 100000.0)
        rule.adjust_by_volatility = data.get("adjust_by_volatility", True)
        return rule


class AnomalyDetectionRule(RiskRule):
    """
    异常检测规则
    
    使用机器学习模型检测交易异常
    """
    
    def __init__(self,
                 rule_id: str = None,
                 model_path: str = None,
                 threshold: float = 0.9,
                 scope: Dict[str, Any] = None):
        """
        初始化异常检测规则
        
        Args:
            rule_id: 规则ID
            model_path: 模型路径
            threshold: 异常阈值
            scope: 规则作用范围
        """
        super().__init__(
            rule_id=rule_id,
            name="Anomaly Detection",
            description="使用机器学习模型检测交易异常",
            risk_level=RiskLevel.HIGH,
            scope=scope
        )
        
        self.model_path = model_path
        self.threshold = threshold
        self.model = None
        
        # 尝试加载模型
        if HAS_ML and model_path and os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                self.logger.info(f"已加载异常检测模型: {model_path}")
            except Exception as e:
                self.logger.error(f"加载模型异常: {str(e)}")
        
    def _extract_features(self, context: Dict[str, Any]) -> List[float]:
        """
        从上下文提取特征
        
        Args:
            context: 风险检查上下文
            
        Returns:
            List[float]: 特征向量
        """
        # 从订单中提取特征
        order = context.get("order", {})
        account = context.get("account", {})
        
        features = []
        
        # 订单特征
        order_price = float(order.get("price", 0))
        order_volume = float(order.get("volume", 0))
        order_value = order_price * order_volume
        
        # 账户特征
        account_balance = float(account.get("balance", 0))
        available = float(account.get("available", 0))
        margin = float(account.get("margin", 0))
        
        # 构建特征向量
        if account_balance > 0:
            features.extend([
                order_value / account_balance if account_balance else 0,
                margin / account_balance if account_balance else 0,
                available / account_balance if account_balance else 0
            ])
        else:
            features.extend([0, 0, 0])
            
        # 添加时间特征
        now = datetime.datetime.now()
        features.extend([
            now.hour + now.minute / 60,  # 一天中的时间
            now.weekday()                # 星期几
        ])
        
        return features
        
    def _check_impl(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        检查是否存在异常
        
        Args:
            context: 风险检查上下文
            
        Returns:
            Tuple[bool, Dict]: (是否存在异常, 附加信息)
        """
        if not HAS_ML or self.model is None:
            return False, {"reason": "No model available"}
            
        try:
            # 提取特征
            features = self._extract_features(context)
            
            # 预测异常
            if hasattr(self.model, "predict_proba"):
                # 概率预测
                proba = self.model.predict_proba([features])
                score = proba[0][1] if len(proba[0]) > 1 else proba[0][0]
                is_anomaly = score > self.threshold
            else:
                # 直接预测
                prediction = self.model.predict([features])
                is_anomaly = prediction[0] == -1  # 通常-1表示异常
                score = self.model.decision_function([features])[0]
                
            return is_anomaly, {
                "anomaly_score": score,
                "threshold": self.threshold,
                "features": features
            }
                
        except Exception as e:
            self.logger.error(f"异常检测失败: {str(e)}")
            return False, {"reason": f"Detection failed: {str(e)}"}
            
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data.update({
            "model_path": self.model_path,
            "threshold": self.threshold
        })
        return data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnomalyDetectionRule':
        """从字典创建规则"""
        rule = super().from_dict(data)
        rule.model_path = data.get("model_path")
        rule.threshold = data.get("threshold", 0.9)
        
        # 尝试加载模型
        if HAS_ML and rule.model_path and os.path.exists(rule.model_path):
            try:
                rule.model = joblib.load(rule.model_path)
            except Exception as e:
                rule.logger.error(f"加载模型异常: {str(e)}")
                
        return rule


class RiskManager:
    """
    风险管理器
    
    负责管理风险规则和执行风险检查
    """
    
    def __init__(self, api=None, config_path: str = None):
        """
        初始化风险管理器
        
        Args:
            api: 天勤API实例
            config_path: 配置文件路径
        """
        # 规则集合
        self.rules = []
        self.rule_map = {}  # {rule_id: rule}
        
        # 状态标志
        self.enabled = True
        self.in_emergency = False
        
        # 天勤API
        self.api = api
        
        # 配置
        self.config_path = config_path
        self.config = {
            "check_orders": True,          # 是否检查订单
            "check_executions": True,      # 是否检查成交
            "check_positions": True,       # 是否检查持仓
            "enable_circuit_breaker": True, # 是否启用熔断
            "parallel_check": True,        # 是否并行检查
            "max_workers": 4,              # 最大工作线程数
            "log_all_checks": False,       # 是否记录所有检查
            "save_interval": 3600          # 配置保存间隔(秒)
        }
        
        # 加载配置
        if config_path and os.path.exists(config_path):
            self._load_config()
            
        # 性能统计
        self.stats = {
            "total_checks": 0,
            "passed_checks": 0,
            "rejected_checks": 0,
            "check_time_total": 0,
            "check_time_avg": 0,
            "last_save_time": 0
        }
        
        # 锁对象
        self._lock = threading.RLock()
        
        # 线程池
        self._executor = ThreadPoolExecutor(max_workers=self.config["max_workers"]) if self.config["parallel_check"] else None
        
        # 日志器
        self.logger = logging.getLogger("fst.risk_manager")
        
        # 绑定天勤API
        if api is not None:
            self.set_api(api)
            
    def set_api(self, api):
        """
        设置天勤API
        
        Args:
            api: 天勤API实例
        """
        self.api = api
        
        # 将API传递给需要的规则
        for rule in self.rules:
            if isinstance(rule, DynamicRiskRule):
                rule.set_api(api)
                
    def add_rule(self, rule: RiskRule) -> bool:
        """
        添加风险规则
        
        Args:
            rule: 风险规则
            
        Returns:
            bool: 是否成功添加
        """
        with self._lock:
            # 检查是否已存在
            if rule.rule_id in self.rule_map:
                self.logger.warning(f"规则已存在: {rule.rule_id}")
                return False
                
            self.rules.append(rule)
            self.rule_map[rule.rule_id] = rule
            
            # 如果是动态规则且API存在，设置API
            if isinstance(rule, DynamicRiskRule) and self.api is not None:
                rule.set_api(self.api)
                
            self.logger.info(f"添加规则: {rule}")
            return True
            
    def remove_rule(self, rule_id: str) -> bool:
        """
        移除风险规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            if rule_id not in self.rule_map:
                return False
                
            rule = self.rule_map[rule_id]
            self.rules.remove(rule)
            del self.rule_map[rule_id]
            
            self.logger.info(f"移除规则: {rule}")
            return True
            
    def get_rule(self, rule_id: str) -> Optional[RiskRule]:
        """
        获取规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            RiskRule: 规则对象
        """
        return self.rule_map.get(rule_id)
        
    def enable_rule(self, rule_id: str, enabled: bool = True) -> bool:
        
        """
        启用或禁用规则
        
        Args:
            rule_id: 规则ID
            enabled: 是否启用
            
        Returns:
            bool: 是否成功修改
        """
        rule = self.get_rule(rule_id)
        if not rule:
            return False
            
        rule.enabled = enabled
        self.logger.info(f"{'启用' if enabled else '禁用'}规则: {rule}")
        return True
    
    def get_all_rules(self) -> List[RiskRule]:
        """
        获取所有规则
        
        Returns:
            List[RiskRule]: 规则列表
        """
        return copy.copy(self.rules)
    
    def reset(self) -> None:
        """重置风险管理器"""
        with self._lock:
            self.rules.clear()
            self.rule_map.clear()
            self.in_emergency = False
            self.enabled = True
            self.stats = {
                "total_checks": 0,
                "passed_checks": 0,
                "rejected_checks": 0,
                "check_time_total": 0,
                "check_time_avg": 0,
                "last_save_time": 0
            }
            
            if HAS_PROMETHEUS:
                CIRCUIT_BREAKER_STATUS.set(0)
            
            self.logger.info("风险管理器已重置")
    
    def check_order(self, order: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        检查订单是否符合风险规则
        
        Args:
            order: 订单信息
            context: 额外的上下文信息
            
        Returns:
            Tuple[bool, Dict]: (是否通过检查, 附加信息)
        """
        if not self.enabled or not self.config["check_orders"]:
            return True, {}
            
        # 更新天勤账户信息（如果可用）
        if HAS_TQSDK and self.api is not None:
            try:
                account = self.api.get_account()
                account._fetch_balances()  # 获取最新账户余额
            except Exception as e:
                self.logger.warning(f"获取天勤账户信息失败: {e}")
        
        # 准备检查上下文
        full_context = {
            "order": order,
            "symbol": order.get("symbol", ""),
            "direction": order.get("direction", ""),
            "offset": order.get("offset", ""),
            "volume": order.get("volume", 0),
            "price": order.get("price", 0),
            "account_info": getattr(self, "account", None),
            "timestamp": datetime.datetime.now().timestamp()
        }
        
        # 添加额外上下文
        if context:
            full_context.update(context)
            
        # 使用Prometheus计时（如果可用）
        if HAS_PROMETHEUS:
            timer = ORDER_CHECK_TIME.time()
            
        # 记录开始时间
        start_time = time.time()
        
        # 检查是否处于紧急状态
        if self.in_emergency:
            self.logger.warning(f"处于紧急状态，拒绝订单: {order}")
            if HAS_PROMETHEUS:
                REJECTED_ORDERS.labels(reason="emergency_state").inc()
            return False, {"reason": "emergency_state"}
            
        # 执行规则检查
        rejected = False
        triggered_rules = []
        rejected_info = {}
        
        if self.config["parallel_check"] and self._executor:
            # 并行检查
            futures = []
            for rule in self.rules:
                if not rule.enabled:
                    continue
                futures.append(self._executor.submit(self._check_single_rule, rule, full_context))
                
            # 等待所有检查完成
            for future in futures:
                result = future.result()
                if result["triggered"]:
                    triggered_rules.append(result["rule"])
                    # 只要有一个REJECT规则触发，就拒绝订单
                    if result["rule"].action_type == RiskActionType.REJECT:
                        rejected = True
                        rejected_info = result["info"]
        else:
            # 串行检查
            for rule in self.rules:
                if not rule.enabled:
                    continue
                    
                # 检查规则
                result = self._check_single_rule(rule, full_context)
                if result["triggered"]:
                    triggered_rules.append(result["rule"])
                    # 只要有一个REJECT规则触发，就拒绝订单
                    if result["rule"].action_type == RiskActionType.REJECT:
                        rejected = True
                        rejected_info = result["info"]
                        break
        
        # 更新统计信息
        elapsed = time.time() - start_time
        with self._lock:
            self.stats["total_checks"] += 1
            self.stats["check_time_total"] += elapsed
            self.stats["check_time_avg"] = self.stats["check_time_total"] / self.stats["total_checks"]
            
            if rejected:
                self.stats["rejected_checks"] += 1
            else:
                self.stats["passed_checks"] += 1
        
        # 如果有触发的规则，记录信息并发送通知
        if triggered_rules:
            # 记录信息
            log_msg = f"风险规则触发: {len(triggered_rules)}个规则, " \
                    f"订单{'' if rejected else '未'}被拒绝, " \
                    f"symbol={full_context['symbol']}, " \
                    f"规则=[{', '.join(r.name for r in triggered_rules)}]"
                    
            if rejected:
                self.logger.warning(log_msg)
                if HAS_PROMETHEUS:
                    REJECTED_ORDERS.labels(reason=rejected_info.get("reason", "rule_triggered")).inc()
            else:
                self.logger.info(log_msg)
                
            # 如果触发的规则中有CRITICAL级别，设置紧急状态
            if any(r.risk_level == RiskLevel.CRITICAL for r in triggered_rules):
                self._set_emergency_state(True)
                
        # 更新Prometheus指标
        if HAS_PROMETHEUS:
            # 使用symbol作为标签时要小心，以避免cardinality explosion
            symbol_group = full_context.get("symbol", "").split(".")[0] if "." in full_context.get("symbol", "") else "unknown"
            RISK_LEVEL.labels(symbol=symbol_group).set(self._calculate_risk_level_value())
            timer.observe()  # 结束计时
            
        # 定期保存配置
        if time.time() - self.stats["last_save_time"] > self.config["save_interval"]:
            self._save_config()
            
        return not rejected, {"triggered_rules": [r.rule_id for r in triggered_rules], "info": rejected_info}
    
    async def async_check_order(self, order: Dict[str, Any], context: Dict[str, Any] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        异步检查订单是否符合风险规则
        
        Args:
            order: 订单信息
            context: 额外的上下文信息
            
        Returns:
            Tuple[bool, Dict]: (是否通过检查, 附加信息)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.check_order, order, context)
    
    def _check_single_rule(self, rule: RiskRule, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查单个规则
        
        Args:
            rule: 规则对象
            context: 检查上下文
            
        Returns:
            Dict: 检查结果
        """
        try:
            # 使用Prometheus计时（如果可用）
            if HAS_PROMETHEUS:
                with RULE_CHECK_TIME.labels(rule_id=rule.rule_id).time():
                    triggered, info = rule.check(context)
            else:
                triggered, info = rule.check(context)
                
            if triggered:
                rule.update_trigger_status()
                
                # 更新Prometheus指标
                if HAS_PROMETHEUS:
                    RULE_TRIGGERS.labels(rule_id=rule.rule_id, level=rule.risk_level.value).inc()
                
                return {
                    "triggered": True,
                    "rule": rule,
                    "info": info
                }
            
            return {"triggered": False}
            
        except Exception as e:
            error_msg = f"检查规则 {rule.name} 时发生错误: {str(e)}"
            self.logger.error(error_msg)
            self.logger.debug(traceback.format_exc())
            
            # 如果配置了忽略错误，则不触发规则
            return {"triggered": False}
    
    def _calculate_risk_level_value(self) -> float:
        """
        计算当前风险值
        
        Returns:
            float: 风险值 (0-100)
        """
        # 简单实现：根据已触发规则的级别加权计算
        weights = {
            RiskLevel.LOW: 0.2,
            RiskLevel.MEDIUM: 0.5,
            RiskLevel.HIGH: 0.8,
            RiskLevel.CRITICAL: 1.0
        }
        
        total_weight = 0
        for rule in self.rules:
            if rule.trigger_count > 0:
                total_weight += weights.get(rule.risk_level, 0.5)
                
        # 归一化到0-100
        normalized = min(100, total_weight * 20)
        return normalized
    
    def _set_emergency_state(self, state: bool) -> None:
        """
        设置紧急状态
        
        Args:
            state: 是否进入紧急状态
        """
        if state == self.in_emergency:
            return
            
        self.in_emergency = state
        self.logger.warning(f"{'进入' if state else '退出'}紧急状态")
        
        if HAS_PROMETHEUS:
            CIRCUIT_BREAKER_STATUS.set(1 if state else 0)
    
    def _load_config(self) -> None:
        """加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 更新配置
            if "config" in data:
                self.config.update(data["config"])
                
            # 加载规则
            if "rules" in data:
                for rule_data in data["rules"]:
                    # 根据类型创建规则
                    rule_type = rule_data.pop("type", "RiskRule")
                    rule_cls = globals().get(rule_type, RiskRule)
                    
                    if rule_cls:
                        try:
                            rule = rule_cls.from_dict(rule_data)
                            self.add_rule(rule)
                        except Exception as e:
                            self.logger.error(f"加载规则 {rule_data.get('name', '未知')} 失败: {e}")
                
            self.logger.info(f"从 {self.config_path} 加载配置成功，共 {len(self.rules)} 条规则")
            
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")
    
    def _save_config(self) -> None:
        """保存配置"""
        if not self.config_path:
            return
            
        try:
            data = {
                "config": self.config,
                "rules": []
            }
            
            # 保存规则
            for rule in self.rules:
                rule_data = rule.to_dict()
                rule_data["type"] = rule.__class__.__name__
                data["rules"].append(rule_data)
                
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            self.stats["last_save_time"] = time.time()
            self.logger.debug(f"配置已保存到 {self.config_path}")
            
        except Exception as e:
            self.logger.error(f"保存配置失败: {e}")
    
    def generate_risk_report(self) -> Dict[str, Any]:
        """
        生成风险报告
        
        Returns:
            Dict: 风险报告
        """
        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "risk_level": self._calculate_risk_level_value(),
            "in_emergency": self.in_emergency,
            "stats": copy.deepcopy(self.stats),
            "rules": [],
            "triggered_rules": []
        }
        
        for rule in self.rules:
            rule_info = {
                "id": rule.rule_id,
                "name": rule.name,
                "risk_level": rule.risk_level.value if isinstance(rule.risk_level, RiskLevel) else rule.risk_level,
                "enabled": rule.enabled,
                "trigger_count": rule.trigger_count,
                "last_triggered": rule.last_triggered
            }
            
            report["rules"].append(rule_info)
            
            if rule.trigger_count > 0:
                report["triggered_rules"].append(rule_info)
                
        return report
    
    def generate_risk_heatmap(self, output_path: str = "risk_heatmap.png") -> bool:
        """
        生成风险热力图
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            bool: 是否成功生成
        """
        if not HAS_PANDAS or not HAS_VISUALIZATION:
            self.logger.warning("生成风险热力图需要pandas、matplotlib和seaborn")
            return False
            
        try:
            # 准备数据
            data = []
            for rule in self.rules:
                data.append({
                    "rule_name": rule.name,
                    "risk_level": rule.risk_level.value if isinstance(rule.risk_level, RiskLevel) else rule.risk_level,
                    "trigger_count": rule.trigger_count
                })
                
            df = pd.DataFrame(data)
            
            # 创建透视表
            pivot = df.pivot_table(
                index="risk_level", 
                columns="rule_name", 
                values="trigger_count", 
                aggfunc="sum",
                fill_value=0
            )
            
            # 绘制热力图
            plt.figure(figsize=(12, 8))
            sns.heatmap(pivot, annot=True, cmap="YlOrRd", linewidths=.5)
            plt.title("风险触发热力图")
            plt.tight_layout()
            plt.savefig(output_path)
            plt.close()
            
            self.logger.info(f"风险热力图已保存到 {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"生成风险热力图失败: {e}")
            return False
    
    def __str__(self) -> str:
        return f"RiskManager(rules={len(self.rules)}, enabled={self.enabled}, emergency={self.in_emergency})"


# 单例模式
_RISK_MANAGER_INSTANCE = None

def get_risk_manager(api=None, config_path=None):
    """
    获取风险管理器单例
    
    Args:
        api: 天勤API实例
        config_path: 配置文件路径
        
    Returns:
        RiskManager: 风险管理器实例
    """
    global _RISK_MANAGER_INSTANCE
    if _RISK_MANAGER_INSTANCE is None:
        _RISK_MANAGER_INSTANCE = RiskManager(api, config_path)
    elif api is not None:
        _RISK_MANAGER_INSTANCE.set_api(api)
    return _RISK_MANAGER_INSTANCE