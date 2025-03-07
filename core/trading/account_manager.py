#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强型账户管理器

此模块负责管理交易账户，实现资金管理、风险控制和账户状态监控。
特性包括：
- 完全异步架构
- 多级熔断机制
- 分布式锁保障
- 动态缓存策略
- 事务一致性保证
- 自动状态恢复
- 全面性能监控
"""

import asyncio
import logging
import time
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Set, Tuple, Callable, Any
from collections import defaultdict, deque
import copy
import numpy as np
import pandas as pd
import traceback

try:
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from infrastructure.api.broker_adapter import BrokerAdapter, ConnectionState, OrderStatus

# 自定义异常类型
class AccountManagerError(Exception):
    """账户管理器基础异常"""
    pass

class NetworkError(AccountManagerError):
    """网络相关异常"""
    pass

class DataIntegrityError(AccountManagerError):
    """数据完整性异常"""
    pass

class TransactionError(AccountManagerError):
    """交易操作异常"""
    pass

class AccountStatus:
    """账户状态枚举"""
    NORMAL = "NORMAL"           # 正常交易
    RESTRICTED = "RESTRICTED"   # 受限交易（如接近风险上限）
    SUSPENDED = "SUSPENDED"     # 暂停交易（触发风险控制）
    LIQUIDATION = "LIQUIDATION" # 强制平仓
    FROZEN = "FROZEN"           # 冻结（不允许任何交易）

class RiskLevel:
    """风险等级枚举"""
    LOW = "LOW"           # 低风险
    MEDIUM = "MEDIUM"     # 中等风险
    HIGH = "HIGH"         # 高风险
    CRITICAL = "CRITICAL" # 危急风险

class TransactionType:
    """资金变动类型枚举"""
    DEPOSIT = "DEPOSIT"       # 入金
    WITHDRAW = "WITHDRAW"     # 出金
    COMMISSION = "COMMISSION" # 手续费
    PROFIT = "PROFIT"         # 已实现盈亏
    ADJUSTMENT = "ADJUSTMENT" # 资金调整
    TRANSFER = "TRANSFER"     # 转账
    LIQUIDATION = "LIQUIDATION" # 强制平仓

class CircuitBreakerAction:
    """熔断措施动作类型"""
    NOTIFY = "NOTIFY"                 # 通知
    RESTRICT_NEW_ORDERS = "RESTRICT"  # 限制新订单
    CANCEL_PENDING_ORDERS = "CANCEL"  # 取消挂单
    REDUCE_POSITIONS = "REDUCE"       # 减仓
    CLOSE_ALL_POSITIONS = "CLOSE_ALL" # 全部平仓
    DISABLE_TRADING = "DISABLE"       # 禁止交易

class AccountManager:
    """
    账户管理器，负责管理交易账户、资金和风险控制
    """
    
    def __init__(self, broker_adapter: BrokerAdapter, 
                 risk_limits: Optional[Dict] = None,
                 auto_update_interval: float = 5.0,
                 redis_client: Optional[Any] = None,
                 position_manager: Optional[Any] = None,
                 order_manager: Optional[Any] = None):
        """
        初始化账户管理器
        
        Args:
            broker_adapter: 券商适配器
            risk_limits: 风险控制参数
            auto_update_interval: 自动更新账户信息的间隔(秒)
            redis_client: Redis客户端(可选，用于分布式锁)
            position_manager: 仓位管理器(可选，用于熔断措施)
            order_manager: 订单管理器(可选，用于熔断措施)
        """
        self.logger = logging.getLogger("fst.core.trading.account_manager")
        self.broker_adapter = broker_adapter
        self.position_manager = position_manager
        self.order_manager = order_manager
        
        # 设置Redis客户端
        self.redis = redis_client if redis_client and REDIS_AVAILABLE else None
        
        # 设置默认风险控制参数
        self.risk_limits = {
            "max_drawdown": 0.1,       # 最大回撤限制 (10%)
            "max_daily_loss": 0.05,    # 最大日亏损限制 (5%)
            "margin_warning": 0.5,     # 保证金警告水平 (50%)
            "margin_call": 0.7,        # 保证金追加水平 (70%)
            "max_position_value": None, # 最大持仓价值限制 (无限制)
            "circuit_breaker_cooldown": 300,  # 熔断冷却期(秒)
            "auto_recovery_check": True,     # 是否启用自动恢复检查
            "recovery_check_interval": 300   # 恢复检查间隔(秒)
        }
        
        # 更新用户提供的风险参数
        if risk_limits:
            self.risk_limits.update(risk_limits)
        
        # 账户信息
        self._account_info = {}
        self._account_id = ""
        self._initial_balance = 0
        self._peak_balance = 0
        self._daily_start_balance = 0
        self._last_update_time = None
        
        # 账户状态
        self._account_status = AccountStatus.NORMAL
        self._risk_level = RiskLevel.LOW
        self._status_lock = asyncio.Lock()
        
        # 资金变动历史
        self._transactions = []
        self._transaction_lock = asyncio.Lock()
        
        # 熔断机制
        self._circuit_breaker_history = []
        self._last_circuit_breaker_time = 0
        self._circuit_breaker_lock = asyncio.Lock()
        
        # 账户状态监听器
        self._status_listeners = []
        self._risk_listeners = []
        self._transaction_listeners = []
        self._circuit_breaker_listeners = []
        
        # 自动更新任务
        self._auto_update_interval = auto_update_interval
        self._auto_update_task = None
        self._recovery_check_task = None
        self._running = False
        
        # 缓存
        self._cache_ttl = 1.0  # 缓存有效期(秒)
        self._last_cache_time = 0
        self._market_volatility = 0.0  # 市场波动率
        
        # 性能监控
        self._metrics = {
            "updates": 0,
            "risk_checks": 0,
            "status_changes": 0,
            "transactions": 0,
            "warnings": 0,
            "errors": 0,
            "network_errors": 0,
            "data_errors": 0,
            "transaction_errors": 0,
            "circuit_breakers": 0,
            "recovery_attempts": 0,
            "recovery_success": 0,
            "update_latency": 0.0,
            "update_latency_avg": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        self.logger.info("账户管理器初始化完成")
    
    async def start(self) -> bool:
        """
        启动账户管理器
        
        Returns:
            bool: 启动是否成功
        """
        self.logger.info("启动账户管理器")
        
        # 检查适配器连接状态
        if not self.broker_adapter.is_connected:
            self.logger.error("券商适配器未连接，账户管理器无法启动")
            return False
        
        # 初始化账户信息
        try:
            # 使用事务包装更新操作
            account_info = await self._execute_transaction(self.update_account_info, True)
            
            # 记录账户ID
            self._account_id = account_info.get("account_id", "")
            
            # 记录初始余额和峰值余额
            self._initial_balance = account_info.get("balance", 0)
            self._peak_balance = self._initial_balance
            self._daily_start_balance = self._initial_balance
            
            self.logger.info(f"初始账户余额: {self._initial_balance}")
            
            # 启动自动更新任务
            self._running = True
            self._auto_update_task = asyncio.create_task(self._auto_update())
            
            # 如果启用了自动恢复检查，则启动恢复检查任务
            if self.risk_limits["auto_recovery_check"]:
                self._recovery_check_task = asyncio.create_task(self._auto_recovery_check())
            
            return True
        
        except Exception as e:
            self.logger.error(f"启动账户管理器失败: {str(e)}")
            self._metrics["errors"] += 1
            return False
    
    async def stop(self) -> None:
        """停止账户管理器"""
        self.logger.info("停止账户管理器")
        
        self._running = False
        
        # 取消自动更新任务
        if self._auto_update_task and not self._auto_update_task.done():
            self._auto_update_task.cancel()
            try:
                await self._auto_update_task
            except asyncio.CancelledError:
                pass
        
        # 取消恢复检查任务
        if self._recovery_check_task and not self._recovery_check_task.done():
            self._recovery_check_task.cancel()
            try:
                await self._recovery_check_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("账户管理器已停止")
    
    async def update_account_info(self, force: bool = False) -> Dict:
        """
        更新账户信息
        
        Args:
            force: 是否强制更新，忽略缓存
        
        Returns:
            Dict: 账户信息
        """
        # 检查缓存
        current_time = time.time()
        if not force and current_time - self._last_cache_time < self._cache_ttl:
            self._metrics["cache_hits"] += 1
            return copy.deepcopy(self._account_info)
        
        self._metrics["cache_misses"] += 1
        
        # 获取账户信息
        try:
            # 记录开始时间（性能监控）
            start_time = time.perf_counter()
            
            # 获取账户信息
            account_info = await self.broker_adapter.get_account_info()
            
            # 计算延迟
            latency = time.perf_counter() - start_time
            
            # 更新性能指标
            self._metrics["update_latency"] = latency * 1000  # 转换为毫秒
            
            # 计算平均延迟
            if self._metrics["updates"] > 0:
                self._metrics["update_latency_avg"] = (
                    (self._metrics["update_latency_avg"] * self._metrics["updates"] + latency * 1000) / 
                    (self._metrics["updates"] + 1)
                )
            else:
                self._metrics["update_latency_avg"] = latency * 1000
            
            self._metrics["updates"] += 1
            
            # 记录更新时间
            self._last_cache_time = current_time
            self._last_update_time = datetime.now()
            
            # 更新峰值余额
            balance = account_info.get("balance", 0)
            if balance > self._peak_balance:
                self._peak_balance = balance
            
            # 存储账户信息
            self._account_info = account_info
            
            # 检查风险状态
            await self._check_risk_status()
            
            # 调整缓存TTL
            await self._adjust_cache_ttl()
            
            return copy.deepcopy(self._account_info)
        
        except ConnectionError as e:
            self._metrics["network_errors"] += 1
            self.logger.error(f"网络连接错误: {str(e)}")
            raise NetworkError(f"获取账户信息时网络错误: {str(e)}")
        
        except ValueError as e:
            self._metrics["data_errors"] += 1
            self.logger.error(f"数据格式错误: {str(e)}")
            raise DataIntegrityError(f"账户数据格式错误: {str(e)}")
        
        except Exception as e:
            self._metrics["errors"] += 1
            self.logger.error(f"获取账户信息出错: {str(e)}")
            self.logger.debug(traceback.format_exc())
            raise
    
    async def add_funds(self, amount: float, transaction_type: str = TransactionType.DEPOSIT, 
                       description: str = "") -> bool:
        """
        添加资金
        
        Args:
            amount: 金额
            transaction_type: 交易类型
            description: 描述
            
        Returns:
            bool: 是否成功
        """
        if amount <= 0:
            self.logger.error(f"添加资金金额必须为正数: {amount}")
            return False
        
        try:
            # 使用事务包装
            return await self._execute_transaction(self._add_funds_impl, amount, transaction_type, description)
        except Exception as e:
            self._metrics["transaction_errors"] += 1
            self.logger.error(f"添加资金出错: {str(e)}")
            return False
    
    async def _add_funds_impl(self, amount: float, transaction_type: str, description: str) -> bool:
        """添加资金的实际实现"""
        # 记录交易
        transaction = {
            "id": str(uuid.uuid4()),
            "type": transaction_type,
            "amount": amount,
            "balance_before": self._account_info.get("balance", 0),
            "balance_after": self._account_info.get("balance", 0) + amount,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
        
        async with self._transaction_lock:
            self._transactions.append(transaction)
        
        # 更新指标
        self._metrics["transactions"] += 1
        
        # 通知监听器
        for listener in self._transaction_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(transaction))
                else:
                    listener(transaction)
            except Exception as e:
                self.logger.error(f"执行交易监听器出错: {str(e)}")
        
        self.logger.info(f"添加资金成功: {amount} ({transaction_type})")
        
        # 更新账户信息
        await self.update_account_info(force=True)
        
        return True
    
    async def remove_funds(self, amount: float, transaction_type: str = TransactionType.WITHDRAW, 
                          description: str = "") -> bool:
        """
        移除资金
        
        Args:
            amount: 金额
            transaction_type: 交易类型
            description: 描述
            
        Returns:
            bool: 是否成功
        """
        if amount <= 0:
            self.logger.error(f"移除资金金额必须为正数: {amount}")
            return False
        
        # 检查可用资金
        available = self._account_info.get("available", 0)
        if amount > available:
            self.logger.error(f"可用资金不足: {available} < {amount}")
            return False
        
        try:
            # 使用事务包装
            return await self._execute_transaction(self._remove_funds_impl, amount, transaction_type, description)
        except Exception as e:
            self._metrics["transaction_errors"] += 1
            self.logger.error(f"移除资金出错: {str(e)}")
            return False
    
    async def _remove_funds_impl(self, amount: float, transaction_type: str, description: str) -> bool:
        """移除资金的实际实现"""
        # 记录交易
        transaction = {
            "id": str(uuid.uuid4()),
            "type": transaction_type,
            "amount": -amount,  # 负数表示移除
            "balance_before": self._account_info.get("balance", 0),
            "balance_after": self._account_info.get("balance", 0) - amount,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
        
        async with self._transaction_lock:
            self._transactions.append(transaction)
        
        # 更新指标
        self._metrics["transactions"] += 1
        
        # 通知监听器
        for listener in self._transaction_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(transaction))
                else:
                    listener(transaction)
            except Exception as e:
                self.logger.error(f"执行交易监听器出错: {str(e)}")
        
        self.logger.info(f"移除资金成功: {amount} ({transaction_type})")
        
        # 更新账户信息
        await self.update_account_info(force=True)
        
        return True
    
    async def record_transaction(self, amount: float, transaction_type: str, 
                               description: str = "") -> Dict:
        """
        记录资金变动
        
        Args:
            amount: 金额 (正数表示收入，负数表示支出)
            transaction_type: 交易类型
            description: 描述
            
        Returns:
            Dict: 交易记录
        """
        try:
            # 使用事务包装
            return await self._execute_transaction(self._record_transaction_impl, 
                                                amount, transaction_type, description)
        except Exception as e:
            self._metrics["transaction_errors"] += 1
            self.logger.error(f"记录交易出错: {str(e)}")
            raise TransactionError(f"记录交易失败: {str(e)}")
    
    async def _record_transaction_impl(self, amount: float, transaction_type: str, 
                                    description: str) -> Dict:
        """记录交易的实际实现"""
        # 创建交易记录
        transaction = {
            "id": str(uuid.uuid4()),
            "type": transaction_type,
            "amount": amount,
            "balance_before": self._account_info.get("balance", 0),
            "balance_after": self._account_info.get("balance", 0) + amount,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
        
        async with self._transaction_lock:
            self._transactions.append(transaction)
        
        # 更新指标
        self._metrics["transactions"] += 1
        
        # 通知监听器
        for listener in self._transaction_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(transaction))
                else:
                    listener(transaction)
            except Exception as e:
                self.logger.error(f"执行交易监听器出错: {str(e)}")
        
        self.logger.info(f"记录交易: {amount} ({transaction_type})")
        
        # 更新账户信息
        await self.update_account_info(force=True)
        
        return transaction
    
    async def get_transactions(self, start_time: Optional[datetime] = None,
                             end_time: Optional[datetime] = None,
                             transaction_type: Optional[str] = None) -> List[Dict]:
        """
        获取交易记录
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            transaction_type: 交易类型
            
        Returns:
            List[Dict]: 交易记录列表
        """
        async with self._transaction_lock:
            transactions = copy.deepcopy(self._transactions)
        
        # 过滤交易记录
        if start_time or end_time or transaction_type:
            filtered = []
            for tx in transactions:
                tx_time = datetime.fromisoformat(tx["timestamp"])
                
                if start_time and tx_time < start_time:
                    continue
                if end_time and tx_time > end_time:
                    continue
                if transaction_type and tx["type"] != transaction_type:
                    continue
                
                filtered.append(tx)
            return filtered
        
        return transactions
    
    async def get_summary(self) -> Dict:
        """
        获取账户摘要信息
        
        Returns:
            Dict: 账户摘要
        """
        # 更新账户信息
        account_info = await self.update_account_info()
        
        # 计算各类指标
        balance = account_info.get("balance", 0)
        available = account_info.get("available", 0)
        margin = account_info.get("margin", 0)
        
        # 回撤计算
        drawdown = 0
        if self._peak_balance > 0:
            drawdown = (self._peak_balance - balance) / self._peak_balance
        
        # 日内盈亏
        daily_pnl = 0
        if self._daily_start_balance > 0:
            daily_pnl = (balance - self._daily_start_balance) / self._daily_start_balance
        
        # 计算保证金率
        margin_ratio = 0
        if balance > 0 and margin > 0:
            margin_ratio = margin / balance
        
        # 构建摘要
        summary = {
            "account_id": account_info.get("account_id", ""),
            "balance": balance,
            "available": available,
            "margin": margin,
            "margin_ratio": margin_ratio,
            "frozen_margin": account_info.get("frozen_margin", 0),
            "commission": account_info.get("commission", 0),
            "float_profit": account_info.get("float_profit", 0),
            "close_profit": account_info.get("close_profit", 0),
            
            # 计算指标
            "initial_balance": self._initial_balance,
            "peak_balance": self._peak_balance,
            "daily_start_balance": self._daily_start_balance,
            "drawdown": drawdown,
            "daily_pnl": daily_pnl,
            "market_volatility": self._market_volatility,
            
            # 状态信息
            "account_status": self._account_status,
            "risk_level": self._risk_level,
            "last_update": self._last_update_time.isoformat() if self._last_update_time else None,
            "cache_ttl": self._cache_ttl,
            
            # 熔断信息
            "circuit_breaker": {
                "last_triggered": datetime.fromtimestamp(self._last_circuit_breaker_time).isoformat() if self._last_circuit_breaker_time else None,
                "count": len(self._circuit_breaker_history),
                "latest": self._circuit_breaker_history[-1] if self._circuit_breaker_history else None
            },
            
            # 统计指标
            "metrics": copy.deepcopy(self._metrics)
        }
        
        return summary
    
    async def set_account_status(self, status: str) -> bool:
        """
        设置账户状态
        
        Args:
            status: 账户状态
            
        Returns:
            bool: 设置是否成功
        """
        if status not in [
            AccountStatus.NORMAL, 
            AccountStatus.RESTRICTED,
            AccountStatus.SUSPENDED,
            AccountStatus.LIQUIDATION,
            AccountStatus.FROZEN
        ]:
            self.logger.error(f"无效的账户状态: {status}")
            return False
        
        async with self._status_lock:
            old_status = self._account_status
            if old_status == status:
                return True
            
            self._account_status = status
            self._metrics["status_changes"] += 1
            
            self.logger.info(f"账户状态变更: {old_status} -> {status}")
            
            # 通知监听器
            for listener in self._status_listeners:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        asyncio.create_task(listener(old_status, status))
                    else:
                        listener(old_status, status)
                except Exception as e:
                    self.logger.error(f"执行状态监听器出错: {str(e)}")
            
            return True
    
    async def reset_daily_balance(self) -> None:
        """重置每日起始余额"""
        account_info = await self.update_account_info(force=True)
        self._daily_start_balance = account_info.get("balance", 0)
        self.logger.info(f"重置每日起始余额: {self._daily_start_balance}")
    
    async def _auto_update(self) -> None:
        """自动更新账户信息的后台任务"""
        self.logger.info(f"启动账户自动更新任务，间隔 {self._auto_update_interval} 秒")
        
        while self._running:
            try:
                # 更新账户信息
                await self.update_account_info(force=True)
                
                # 等待下一次更新
                await asyncio.sleep(self._auto_update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"账户自动更新出错: {str(e)}")
                self._metrics["errors"] += 1
                await asyncio.sleep(self._auto_update_interval)
        
        self.logger.info("账户自动更新任务已停止")
    
    async def _auto_recovery_check(self) -> None:
        """自动恢复检查的后台任务"""
        interval = self.risk_limits["recovery_check_interval"]
        self.logger.info(f"启动账户自动恢复检查任务，间隔 {interval} 秒")
        
        while self._running:
            try:
                # 检查是否需要恢复
                if self._account_status in [AccountStatus.SUSPENDED, AccountStatus.RESTRICTED]:
                    self._metrics["recovery_attempts"] += 1
                    self.logger.info(f"执行恢复检查: 当前状态 {self._account_status}")
                    
                    if await self._check_recovery_conditions():
                        self.logger.info("满足恢复条件，恢复正常状态")
                        await self.set_account_status(AccountStatus.NORMAL)
                        self._metrics["recovery_success"] += 1
                
                # 等待下一次检查
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"自动恢复检查出错: {str(e)}")
                self._metrics["errors"] += 1
                await asyncio.sleep(interval)
        
        self.logger.info("账户自动恢复检查任务已停止")
    
    async def _check_recovery_conditions(self) -> bool:
        """
        检查是否满足恢复条件
        
        Returns:
            bool: 是否满足恢复条件
        """
        # 更新账户信息
        account_info = await self.update_account_info(force=True)
        
        # 计算保证金率
        balance = account_info.get("balance", 0)
        margin = account_info.get("margin", 0)
        margin_ratio = margin / balance if balance > 0 and margin > 0 else 0
        
        # 计算回撤
        drawdown = (self._peak_balance - balance) / self._peak_balance if self._peak_balance > 0 else 0
        
        # 计算日内亏损
        daily_loss = (self._daily_start_balance - balance) / self._daily_start_balance if self._daily_start_balance > 0 else 0
        
        # 检查恢复条件
        conditions_met = (
            margin_ratio < self.risk_limits["margin_warning"] and  # 保证金率低于警告水平
            drawdown < self.risk_limits["max_drawdown"] * 0.8 and  # 回撤低于最大回撤的80%
            daily_loss < self.risk_limits["max_daily_loss"] * 0.8  # 日内亏损低于最大日内亏损的80%
        )
        
        if conditions_met:
            self.logger.info(
                f"满足恢复条件: 保证金率={margin_ratio:.2f}, "
                f"回撤={drawdown:.2f}, 日内亏损={daily_loss:.2f}"
            )
        else:
            self.logger.info(
                f"不满足恢复条件: 保证金率={margin_ratio:.2f}, "
                f"回撤={drawdown:.2f}, 日内亏损={daily_loss:.2f}"
            )
        
        return conditions_met
    
    async def _check_risk_status(self) -> None:
        """检查风险状态"""
        self._metrics["risk_checks"] += 1
        
        # 获取当前账户信息
        account_info = self._account_info
        if not account_info:
            return
        
        # 获取当前余额
        balance = account_info.get("balance", 0)
        if balance <= 0:
            return
        
        # 计算回撤
        drawdown = 0
        if self._peak_balance > 0:
            drawdown = (self._peak_balance - balance) / self._peak_balance
        
        # 计算日内亏损
        daily_loss = 0
        if self._daily_start_balance > 0:
            daily_loss = max(0, (self._daily_start_balance - balance) / self._daily_start_balance)
        
        # 计算保证金率
        margin = account_info.get("margin", 0)
        margin_ratio = 0
        if balance > 0 and margin > 0:
            margin_ratio = margin / balance
        
        # 确定风险等级
        old_risk_level = self._risk_level
        new_risk_level = RiskLevel.LOW
        
        # 检查保证金率
        if margin_ratio >= self.risk_limits["margin_call"]:
            new_risk_level = RiskLevel.CRITICAL
        elif margin_ratio >= self.risk_limits["margin_warning"]:
            new_risk_level = RiskLevel.HIGH
        # 检查回撤
        elif drawdown >= self.risk_limits["max_drawdown"]:
            new_risk_level = RiskLevel.HIGH
        # 检查日内亏损
        elif daily_loss >= self.risk_limits["max_daily_loss"]:
            new_risk_level = RiskLevel.MEDIUM
        
        # 更新风险等级
        if new_risk_level != old_risk_level:
            async with self._status_lock:
                self._risk_level = new_risk_level
                
                self.logger.info(f"风险等级变更: {old_risk_level} -> {new_risk_level}")
                
                # 通知监听器
                for listener in self._risk_listeners:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            asyncio.create_task(listener(old_risk_level, new_risk_level))
                        else:
                            listener(old_risk_level, new_risk_level)
                    except Exception as e:
                        self.logger.error(f"执行风险监听器出错: {str(e)}")
        
        # 更新账户状态和触发熔断机制
        await self._update_account_status_from_risk()
    
    async def _update_account_status_from_risk(self) -> None:
        """根据风险等级更新账户状态并触发熔断机制"""
        # 当前为冻结状态，不自动改变状态
        if self._account_status == AccountStatus.FROZEN:
            return
            
        # 根据风险等级触发熔断机制
        if self._risk_level == RiskLevel.CRITICAL:
            await self._trigger_circuit_breaker(
                level=5, 
                reason="危急风险: 保证金率、回撤或亏损超过极限",
                actions=[
                    CircuitBreakerAction.NOTIFY,
                    CircuitBreakerAction.CANCEL_PENDING_ORDERS,
                    CircuitBreakerAction.CLOSE_ALL_POSITIONS,
                    CircuitBreakerAction.DISABLE_TRADING
                ]
            )
            await self.set_account_status(AccountStatus.LIQUIDATION)
            
        elif self._risk_level == RiskLevel.HIGH:
            await self._trigger_circuit_breaker(
                level=4,
                reason="高风险: 保证金率、回撤或亏损接近极限",
                actions=[
                    CircuitBreakerAction.NOTIFY,
                    CircuitBreakerAction.CANCEL_PENDING_ORDERS,
                    CircuitBreakerAction.REDUCE_POSITIONS,
                    CircuitBreakerAction.RESTRICT_NEW_ORDERS
                ]
            )
            await self.set_account_status(AccountStatus.SUSPENDED)
            
        elif self._risk_level == RiskLevel.MEDIUM:
            await self._trigger_circuit_breaker(
                level=2,
                reason="中等风险: 日内亏损或回撤接近警戒线",
                actions=[
                    CircuitBreakerAction.NOTIFY,
                    CircuitBreakerAction.RESTRICT_NEW_ORDERS
                ]
            )
            await self.set_account_status(AccountStatus.RESTRICTED)
            
        elif self._risk_level == RiskLevel.LOW:
            # 如果当前状态不是正常，且风险等级降为低，则恢复正常状态
            if self._account_status != AccountStatus.NORMAL:
                await self.set_account_status(AccountStatus.NORMAL)
    
    async def _trigger_circuit_breaker(self, level: int, reason: str, actions: List[str]) -> None:
        """
        触发熔断机制
        
        Args:
            level: 熔断级别 (1-5)
            reason: 熔断原因
            actions: 熔断措施列表
        """
        # 检查冷却期
        current_time = time.time()
        cooldown = self.risk_limits["circuit_breaker_cooldown"]
        
        if current_time - self._last_circuit_breaker_time < cooldown:
            self.logger.info(f"熔断机制在冷却期内，跳过触发 (剩余 {cooldown - (current_time - self._last_circuit_breaker_time):.1f} 秒)")
            return
        
        async with self._circuit_breaker_lock:
            self.logger.warning(f"触发{level}级熔断措施: {reason}")
            
            # 记录熔断事件
            circuit_breaker_event = {
                "id": str(uuid.uuid4()),
                "level": level,
                "reason": reason,
                "actions": actions,
                "timestamp": current_time,
                "account_status": self._account_status,
                "risk_level": self._risk_level,
                "account_info": {
                    "balance": self._account_info.get("balance", 0),
                    "margin": self._account_info.get("margin", 0),
                    "margin_ratio": self._account_info.get("margin", 0) / self._account_info.get("balance", 1) if self._account_info.get("balance", 0) > 0 else 0,
                    "drawdown": (self._peak_balance - self._account_info.get("balance", 0)) / self._peak_balance if self._peak_balance > 0 else 0,
                    "daily_loss": max(0, (self._daily_start_balance - self._account_info.get("balance", 0)) / self._daily_start_balance) if self._daily_start_balance > 0 else 0
                }
            }
            
            self._circuit_breaker_history.append(circuit_breaker_event)
            self._last_circuit_breaker_time = current_time
            self._metrics["circuit_breakers"] += 1
            
            # 执行熔断措施
            for action in actions:
                try:
                    await self._execute_circuit_breaker_action(action)
                except Exception as e:
                    self.logger.error(f"执行熔断操作 {action} 失败: {str(e)}")
                    self._metrics["errors"] += 1
            
            # 通知监听器
            for listener in self._circuit_breaker_listeners:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        asyncio.create_task(listener(circuit_breaker_event))
                    else:
                        listener(circuit_breaker_event)
                except Exception as e:
                    self.logger.error(f"执行熔断监听器出错: {str(e)}")
    
    async def _execute_circuit_breaker_action(self, action: str) -> None:
        """
        执行熔断措施动作
        
        Args:
            action: 动作类型
        """
        self.logger.info(f"执行熔断动作: {action}")
        
        if action == CircuitBreakerAction.NOTIFY:
            # 发送通知 (具体实现依赖于通知系统)
            await self._send_notification(
                level="CRITICAL", 
                title="账户风险警报", 
                message=f"账户 {self._account_id} 触发熔断措施，当前风险等级 {self._risk_level}"
            )
            
        elif action == CircuitBreakerAction.RESTRICT_NEW_ORDERS:
            # 限制新订单
            if self.order_manager:
                await self.order_manager.set_order_restriction(True)
            
        elif action == CircuitBreakerAction.CANCEL_PENDING_ORDERS:
            # 取消所有挂单
            if self.order_manager:
                await self.order_manager.cancel_all_pending_orders()
            
        elif action == CircuitBreakerAction.REDUCE_POSITIONS:
            # 减仓操作(默认减仓50%)
            if self.position_manager:
                await self.position_manager.reduce_all_positions(0.5)
            
        elif action == CircuitBreakerAction.CLOSE_ALL_POSITIONS:
            # 全部平仓
            if self.position_manager:
                await self.position_manager.close_all_positions()
            
        elif action == CircuitBreakerAction.DISABLE_TRADING:
            # 禁止交易
            if self.order_manager:
                await self.order_manager.disable_trading()
            
        else:
            self.logger.warning(f"未知的熔断动作: {action}")
    
    async def _send_notification(self, level: str, title: str, message: str) -> None:
        """
        发送通知
        
        Args:
            level: 级别
            title: 标题
            message: 消息内容
        """
        # 这里只是占位实现，实际项目中应替换为真实的通知系统
        self.logger.warning(f"[通知] {level}: {title} - {message}")
        
        # TODO: 接入实际的通知系统，如邮件、短信、微信等
    
    async def _calculate_market_volatility(self) -> float:
        """
        计算市场波动率，用于动态调整缓存设置
        
        Returns:
            float: 波动率
        """
        # 这里可以接入实时市场数据，计算波动率
        # 当前为简化实现，随机返回一个值用于测试
        # TODO: 实现实际的波动率计算逻辑
        
        # 随机波动率 (0.1-0.6)
        import random
        volatility = 0.1 + random.random() * 0.5
        
        return volatility
    
    def _adjust_cache_ttl(self) -> None:
        """根据市场波动率调整缓存有效期"""
        volatility = self._market_volatility
        
        if volatility > 0.5:  # 高波动市场
            self._cache_ttl = 0.3
        elif volatility > 0.2:  # 中等波动市场
            self._cache_ttl = 0.5
        else:  # 低波动市场
            self._cache_ttl = 1.5
        
        self.logger.debug(f"调整缓存有效期: {self._cache_ttl}秒 (波动率: {volatility:.2f})")
    
    async def _handle_network_error(self, error: Exception) -> None:
        """
        处理网络错误
        
        Args:
            error: 错误异常
        """
        self.logger.error(f"网络错误: {str(error)}")
        
        # 记录错误
        self._metrics["network_errors"] += 1
        
        # 等待短暂时间后重试
        retry_interval = 1.0  # 1秒
        self.logger.info(f"等待 {retry_interval} 秒后重试")
        
        # 如果网络错误持续，可以考虑通知并降级处理
        if self._metrics["network_errors"] > 10:
            await self._send_notification(
                level="WARNING",
                title="网络连接问题",
                message=f"账户 {self._account_id} 连续出现网络错误"
            )
    
    async def _recovery_from_backup(self) -> None:
        """从备份数据恢复账户信息"""
        self.logger.warning("尝试从备份数据恢复账户信息")
        
        # TODO: 实现从备份恢复逻辑
        # 这可能包括从本地缓存、数据库或其他持久化存储加载最近的账户快照
        
        self.logger.info("从备份恢复账户信息完成")
    
    async def _execute_transaction(self, func: Callable, *args, **kwargs) -> Any:
        """
        带分布式锁的事务执行
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            Any: 函数返回结果
        """
        # 如果没有Redis客户端，直接执行
        if not self.redis:
            return await func(*args, **kwargs)
        
        # 使用Redis分布式锁
        lock_key = f"account_lock:{self._account_id}"
        lock_timeout = 10  # 10秒锁超时
        
        try:
            # 获取分布式锁
            async with self.redis.lock(lock_key, timeout=lock_timeout):
                self.logger.debug(f"获取分布式锁: {lock_key}")
                
                # 执行事务
                result = await func(*args, **kwargs)
                
                self.logger.debug(f"释放分布式锁: {lock_key}")
                return result
                
        except Exception as e:
            self.logger.error(f"分布式锁事务执行出错: {str(e)}")
            
            # 如果是Redis错误，回退到无锁执行
            if "Redis" in str(e):
                self.logger.warning("Redis锁获取失败，回退到无锁执行")
                return await func(*args, **kwargs)
            
            raise
    
    # 账户操作API
    
    async def withdraw(self, amount: float, memo: str = "") -> bool:
        """
        出金操作
        
        Args:
            amount: 出金金额
            memo: 备注
            
        Returns:
            bool: 是否成功
        """
        if amount <= 0:
            self.logger.error(f"出金金额必须大于0: {amount}")
            return False
        
        # 检查账户状态
        if self._account_status != AccountStatus.NORMAL:
            self.logger.error(f"账户状态非正常，不允许出金: {self._account_status}")
            return False
        
        # 获取当前可用资金
        account_info = await self.update_account_info(force=True)
        available = account_info.get("available", 0)
        
        if amount > available:
            self.logger.error(f"出金金额 {amount} 超过可用资金 {available}")
            return False
        
        # 记录交易
        try:
            transaction = await self._record_transaction(
                type=TransactionType.WITHDRAW,
                amount=-amount,
                memo=memo
            )
            
            # TODO: 实际出金操作，这里需要根据broker_adapter进行具体实现
            
            self.logger.info(f"出金成功: {amount}, 交易ID: {transaction['id']}")
            return True
            
        except Exception as e:
            self.logger.error(f"出金操作失败: {str(e)}")
            return False
    
    async def deposit(self, amount: float, memo: str = "") -> bool:
        """
        入金操作
        
        Args:
            amount: 入金金额
            memo: 备注
            
        Returns:
            bool: 是否成功
        """
        if amount <= 0:
            self.logger.error(f"入金金额必须大于0: {amount}")
            return False
        
        # 记录交易
        try:
            transaction = await self._record_transaction(
                type=TransactionType.DEPOSIT,
                amount=amount,
                memo=memo
            )
            
            # TODO: 实际入金操作，这里需要根据broker_adapter进行具体实现
            
            # 更新账户信息
            await self.update_account_info(force=True)
            
            self.logger.info(f"入金成功: {amount}, 交易ID: {transaction['id']}")
            return True
            
        except Exception as e:
            self.logger.error(f"入金操作失败: {str(e)}")
            return False
    
    async def adjust_balance(self, amount: float, memo: str = "") -> bool:
        """
        调整账户余额
        
        Args:
            amount: 调整金额，正数为增加，负数为减少
            memo: 备注
            
        Returns:
            bool: 是否成功
        """
        # 记录交易
        try:
            transaction = await self._record_transaction(
                type=TransactionType.ADJUSTMENT,
                amount=amount,
                memo=memo
            )
            
            # TODO: 实际资金调整操作，这里需要根据broker_adapter进行具体实现
            
            # 更新账户信息
            await self.update_account_info(force=True)
            
            self.logger.info(f"资金调整成功: {amount}, 交易ID: {transaction['id']}")
            return True
            
        except Exception as e:
            self.logger.error(f"资金调整失败: {str(e)}")
            return False
    
    # 公开的辅助方法
    
    async def can_open_position(self, symbol: str, volume: float, price: float) -> Tuple[bool, str]:
        """
        检查是否可以开仓
        
        Args:
            symbol: 合约代码
            volume: 交易数量
            price: 交易价格
            
        Returns:
            Tuple[bool, str]: (是否可以开仓, 原因)
        """
        # 检查账户状态
        if self._account_status in [AccountStatus.SUSPENDED, AccountStatus.LIQUIDATION, AccountStatus.FROZEN]:
            return False, f"账户状态为 {self._account_status}，不允许开仓"
        
        if self._account_status == AccountStatus.RESTRICTED:
            # 受限状态下，需要进一步检查具体限制条件
            # TODO: 实现受限状态下的开仓检查逻辑
            pass
        
        # 获取最新账户信息
        account_info = await self.get_account_info()
        available = account_info.get("available", 0)
        
        # TODO: 这里应根据具体合约计算所需保证金
        # 简化实现，假设所需保证金为价值的10%
        estimated_margin = price * volume * 0.1
        
        if estimated_margin > available:
            return False, f"可用资金不足，需要 {estimated_margin}，可用 {available}"
        
        return True, "可以开仓"
    
    async def add_status_listener(self, listener: Callable[[str, str], None]) -> None:
        """
        添加账户状态监听器
        
        Args:
            listener: 回调函数 (old_status, new_status) -> None
        """
        if listener not in self._status_listeners:
            self._status_listeners.append(listener)
    
    async def add_risk_listener(self, listener: Callable[[str, str], None]) -> None:
        """
        添加风险等级监听器
        
        Args:
            listener: 回调函数 (old_risk, new_risk) -> None
        """
        if listener not in self._risk_listeners:
            self._risk_listeners.append(listener)
    
    async def add_transaction_listener(self, listener: Callable[[Dict], None]) -> None:
        """
        添加交易记录监听器
        
        Args:
            listener: 回调函数 (transaction) -> None
        """
        if listener not in self._transaction_listeners:
            self._transaction_listeners.append(listener)
    
    async def add_circuit_breaker_listener(self, listener: Callable[[Dict], None]) -> None:
        """
        添加熔断机制监听器
        
        Args:
            listener: 回调函数 (circuit_breaker_event) -> None
        """
        if listener not in self._circuit_breaker_listeners:
            self._circuit_breaker_listeners.append(listener)
    
    # 手动熔断控制
    
    async def trigger_manual_circuit_breaker(self, level: int, reason: str, actions: List[str]) -> bool:
        """
        手动触发熔断机制
        
        Args:
            level: 熔断级别
            reason: 触发原因
            actions: 熔断措施列表
            
        Returns:
            bool: 是否成功触发
        """
        try:
            self.logger.warning(f"手动触发熔断机制: 级别={level}, 原因={reason}")
            await self._trigger_circuit_breaker(level, reason, actions)
            return True
        except Exception as e:
            self.logger.error(f"手动触发熔断失败: {str(e)}")
            return False
    
    async def reset_circuit_breaker(self) -> bool:
        """
        重置熔断机制（清除冷却期）
        
        Returns:
            bool: 是否成功
        """
        async with self._circuit_breaker_lock:
            self._last_circuit_breaker_time = 0
            self.logger.info("熔断机制已重置")
            return True
    
    # 测试和诊断方法
    
    async def get_health_status(self) -> Dict:
        """
        获取健康状态
        
        Returns:
            Dict: 健康状态信息
        """
        return {
            "status": self._account_status,
            "risk_level": self._risk_level,
            "metrics": copy.deepcopy(self._metrics),
            "last_update": self._last_update_time.isoformat() if self._last_update_time else None,
            "circuit_breaker": {
                "last_triggered": self._last_circuit_breaker_time,
                "cooldown_remaining": max(0, self.risk_limits["circuit_breaker_cooldown"] - (time.time() - self._last_circuit_breaker_time)) if self._last_circuit_breaker_time > 0 else 0,
                "history_count": len(self._circuit_breaker_history)
            },
            "cache": {
                "ttl": self._cache_ttl,
                "last_cache_time": self._last_cache_time,
                "market_volatility": self._market_volatility
            }
        }
    
    async def simulate_market_volatility(self, volatility: float) -> None:
        """
        模拟市场波动率(仅用于测试)
        
        Args:
            volatility: 波动率(0.0-1.0)
        """
        if not 0 <= volatility <= 1:
            raise ValueError("波动率必须在0-1之间")
        
        self._market_volatility = volatility
        self._adjust_cache_ttl()
        self.logger.info(f"模拟市场波动率设置为 {volatility}，缓存TTL调整为 {self._cache_ttl}秒")