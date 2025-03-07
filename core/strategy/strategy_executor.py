#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 策略执行器

此模块负责加载、管理和执行交易策略，处理市场数据和交易信号。
特性包括：
- 策略生命周期管理
- 动态策略加载和热更新
- 多策略并行执行
- 策略风险隔离
- 性能监控和资源管理
"""

import asyncio
import logging
import time
import importlib
import inspect
import uuid
import os
import sys
import json
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Set, Tuple, Callable, Any, Type
from collections import defaultdict, deque
import copy
import signal
import threading

# 核心组件
from core.trading.account_manager import AccountManager
from core.trading.order_manager import OrderManager
from core.trading.position_manager import PositionManager
from core.market.data_provider import DataProvider

# 基础设施
from infrastructure.api.broker_adapter import BrokerAdapter, ConnectionState

# 策略基类
class Strategy:
    """
    交易策略基类，所有策略都应继承此类
    """
    
    def __init__(self, strategy_id: str, name: str, params: Dict = None):
        """
        初始化策略
        
        Args:
            strategy_id: 策略唯一ID
            name: 策略名称
            params: 策略参数
        """
        self.strategy_id = strategy_id
        self.name = name
        self.params = params or {}
        self.logger = logging.getLogger(f"fst.strategy.{strategy_id}")
        
        # 运行状态
        self.is_running = False
        self.is_initialized = False
        
        # 组件引用，由执行器设置
        self.executor = None
        self.account_manager = None
        self.order_manager = None
        self.position_manager = None
        self.data_provider = None
        
        # 订阅的合约
        self.subscribed_symbols = set()
        
        # 上次运行时间
        self.last_run_time = None
        
        # 策略状态和统计
        self.status = "stopped"
        self.metrics = {
            "runs": 0,
            "signals": 0,
            "orders": 0,
            "errors": 0,
            "avg_run_time": 0,
            "max_run_time": 0,
            "last_run_time": 0,
            "total_pnl": 0
        }
    
    async def initialize(self) -> bool:
        """
        初始化策略
        
        Returns:
            bool: 初始化是否成功
        """
        self.logger.info(f"初始化策略 {self.name}")
        self.is_initialized = True
        return True
    
    async def start(self) -> bool:
        """
        启动策略
        
        Returns:
            bool: 启动是否成功
        """
        if not self.is_initialized:
            await self.initialize()
            
        self.logger.info(f"启动策略 {self.name}")
        self.is_running = True
        self.status = "running"
        return True
    
    async def stop(self) -> bool:
        """
        停止策略
        
        Returns:
            bool: 停止是否成功
        """
        self.logger.info(f"停止策略 {self.name}")
        self.is_running = False
        self.status = "stopped"
        return True
    
    async def subscribe_symbols(self, symbols: List[str]) -> bool:
        """
        订阅合约
        
        Args:
            symbols: 合约列表
            
        Returns:
            bool: 订阅是否成功
        """
        if not self.data_provider:
            self.logger.error("数据提供者未设置，无法订阅合约")
            return False
        
        for symbol in symbols:
            success = await self.data_provider.subscribe_symbol(symbol)
            if success:
                self.subscribed_symbols.add(symbol)
                self.logger.info(f"订阅合约成功: {symbol}")
            else:
                self.logger.error(f"订阅合约失败: {symbol}")
                return False
        
        return True
    
    async def unsubscribe_symbols(self, symbols: List[str]) -> bool:
        """
        取消订阅合约
        
        Args:
            symbols: 合约列表
            
        Returns:
            bool: 取消订阅是否成功
        """
        if not self.data_provider:
            self.logger.error("数据提供者未设置，无法取消订阅合约")
            return False
        
        for symbol in symbols:
            success = await self.data_provider.unsubscribe_symbol(symbol)
            if success:
                self.subscribed_symbols.discard(symbol)
                self.logger.info(f"取消订阅合约成功: {symbol}")
            else:
                self.logger.error(f"取消订阅合约失败: {symbol}")
                return False
        
        return True
    
    async def on_market_data(self, data: Dict) -> None:
        """
        市场数据回调
        
        Args:
            data: 市场数据
        """
        pass
    
    async def on_bar(self, symbol: str, bar: Dict) -> None:
        """
        K线数据回调
        
        Args:
            symbol: 合约代码
            bar: K线数据
        """
        pass
    
    async def on_order_update(self, order: Dict) -> None:
        """
        订单更新回调
        
        Args:
            order: 订单信息
        """
        pass
    
    async def on_trade(self, trade: Dict) -> None:
        """
        成交回调
        
        Args:
            trade: 成交信息
        """
        pass
    
    async def on_position_change(self, position_data: Dict) -> None:
        """
        持仓变化回调
        
        Args:
            position_data: 持仓信息
        """
        pass
    
    async def on_account_change(self, account_data: Dict) -> None:
        """
        账户变化回调
        
        Args:
            account_data: 账户信息
        """
        pass
    
    async def on_timer(self) -> None:
        """定时器回调，由策略执行器定期调用"""
        pass
    
    async def run(self) -> None:
        """
        策略主逻辑，由策略执行器调用
        """
        # 由子类实现具体交易逻辑
        pass

class StrategyExecutor:
    """
    策略执行器，负责管理和执行交易策略
    """
    
    def __init__(self, account_manager: AccountManager,
                 order_manager: OrderManager,
                 position_manager: PositionManager,
                 data_provider: DataProvider,
                 strategy_dir: str = "strategies",
                 config_dir: str = "configs"):
        """
        初始化策略执行器
        
        Args:
            account_manager: 账户管理器
            order_manager: 订单管理器
            position_manager: 仓位管理器
            data_provider: 市场数据提供者
            strategy_dir: 策略目录
            config_dir: 配置目录
        """
        self.logger = logging.getLogger("fst.core.strategy.executor")
        
        # 核心组件
        self.account_manager = account_manager
        self.order_manager = order_manager
        self.position_manager = position_manager
        self.data_provider = data_provider
        
        # 目录配置
        self.strategy_dir = strategy_dir
        self.config_dir = config_dir
        
        # 策略管理
        self.strategies = {}  # 当前加载的策略
        self.strategy_tasks = {}  # 策略运行任务
        self.strategy_configs = {}  # 策略配置
        
        # 运行控制
        self.running = False
        self.last_strategy_scan = 0
        self.strategy_scan_interval = 60  # 扫描间隔(秒)
        
        # 策略定时器
        self.timer_interval = 1.0  # 定时器间隔(秒)
        self.timer_task = None
        
        # 市场数据回调
        self.data_provider.add_market_data_listener(self._on_market_data)
        self.data_provider.add_bar_listener(self._on_bar)
        
        # 交易回调
        self.order_manager.add_order_listener(self._on_order_update)
        self.order_manager.add_trade_listener(self._on_trade)
        self.position_manager.add_position_listener(self._on_position_change)
        self.account_manager.add_status_listener(self._on_account_status_change)
        
        # 性能监控
        self.performance_stats = {
            "strategies": 0,
            "running_strategies": 0,
            "avg_execution_time": 0,
            "max_execution_time": 0,
            "executions": 0,
            "errors": 0,
            "last_scan_time": 0,
            "memory_usage": 0
        }
        
        # 安全控制
        self.global_strategy_lock = asyncio.Lock()
        self.strategy_locks = {}  # 每个策略一个锁
        
        self.logger.info("策略执行器初始化完成")
    
    async def start(self) -> bool:
        """
        启动策略执行器
        
        Returns:
            bool: 启动是否成功
        """
        self.logger.info("启动策略执行器")
        
        try:
            # 扫描策略配置
            await self._scan_strategy_configs()
            
            # 加载策略
            await self._load_strategies()
            
            # 启动策略
            for strategy_id, strategy in self.strategies.items():
                if self.strategy_configs[strategy_id].get("auto_start", False):
                    await self.start_strategy(strategy_id)
            
            # 启动定时器
            self.running = True
            self.timer_task = asyncio.create_task(self._timer_loop())
            
            self.logger.info(f"策略执行器启动成功，加载 {len(self.strategies)} 个策略")
            return True
            
        except Exception as e:
            self.logger.error(f"启动策略执行器失败: {str(e)}")
            traceback.print_exc()
            return False
    
    async def stop(self) -> None:
        """停止策略执行器"""
        self.logger.info("停止策略执行器")
        
        self.running = False
        
        # 停止定时器
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
            try:
                await self.timer_task
            except asyncio.CancelledError:
                pass
        
        # 停止所有策略
        for strategy_id in list(self.strategies.keys()):
            await self.stop_strategy(strategy_id)
        
        self.logger.info("策略执行器已停止")
    
    async def _timer_loop(self) -> None:
        """定时器循环"""
        self.logger.info(f"启动定时器，间隔 {self.timer_interval} 秒")
        
        while self.running:
            try:
                # 扫描策略
                current_time = time.time()
                if current_time - self.last_strategy_scan > self.strategy_scan_interval:
                    await self._scan_strategy_configs()
                    await self._check_strategy_changes()
                    self.last_strategy_scan = current_time
                
                # 触发策略定时器
                await self._trigger_strategy_timers()
                
                # 更新性能统计
                self._update_performance_stats()
                
                # 等待下一次触发
                await asyncio.sleep(self.timer_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"定时器循环出错: {str(e)}")
                self.performance_stats["errors"] += 1
                await asyncio.sleep(self.timer_interval)
        
        self.logger.info("定时器循环已停止")
    
    async def _scan_strategy_configs(self) -> None:
        """扫描策略配置文件"""
        self.logger.debug("扫描策略配置")
        
        config_path = os.path.join(self.config_dir, "strategies")
        if not os.path.exists(config_path):
            self.logger.warning(f"策略配置目录不存在: {config_path}")
            return
        
        # 扫描配置文件
        configs = {}
        for filename in os.listdir(config_path):
            if not filename.endswith(".json"):
                continue
                
            file_path = os.path.join(config_path, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    
                    # 检查必要字段
                    if "strategy_id" not in config or "class" not in config:
                        self.logger.warning(f"策略配置缺少必要字段: {file_path}")
                        continue
                    
                    strategy_id = config["strategy_id"]
                    configs[strategy_id] = config
                    
            except Exception as e:
                self.logger.error(f"加载策略配置出错: {file_path}, 错误: {str(e)}")
        
        # 更新策略配置
        self.strategy_configs = configs
        self.performance_stats["last_scan_time"] = time.time()
    
    async def _check_strategy_changes(self) -> None:
        """检查策略变化"""
        # 检查新增或更新的策略
        for strategy_id, config in self.strategy_configs.items():
            if strategy_id not in self.strategies:
                # 新策略
                self.logger.info(f"发现新策略: {strategy_id}")
                await self._load_strategy(strategy_id, config)
                
                # 自动启动
                if config.get("auto_start", False):
                    await self.start_strategy(strategy_id)
                    
            else:
                # 更新现有策略
                existing_strategy = self.strategies[strategy_id]
                
                # 检查配置是否变化
                if config.get("version", 0) > existing_strategy.params.get("version", 0):
                    self.logger.info(f"策略配置已更新: {strategy_id}")
                    
                    # 热更新
                    if config.get("hot_reload", False) and existing_strategy.is_running:
                        await self._reload_strategy(strategy_id, config)
        
        # 检查删除的策略
        for strategy_id in list(self.strategies.keys()):
            if strategy_id not in self.strategy_configs:
                self.logger.info(f"策略已移除: {strategy_id}")
                await self.stop_strategy(strategy_id)
                await self._unload_strategy(strategy_id)
    
    async def _load_strategies(self) -> None:
        """加载所有策略"""
        self.logger.info("加载所有策略")
        
        for strategy_id, config in self.strategy_configs.items():
            await self._load_strategy(strategy_id, config)
    
    async def _load_strategy(self, strategy_id: str, config: Dict) -> bool:
        """
        加载单个策略
        
        Args:
            strategy_id: 策略ID
            config: 策略配置
            
        Returns:
            bool: 加载是否成功
        """
        self.logger.info(f"加载策略: {strategy_id}")
        
        # 检查是否已加载
        if strategy_id in self.strategies:
            self.logger.warning(f"策略已存在: {strategy_id}")
            return False
        
        try:
            # 获取策略类信息
            class_path = config["class"]
            module_path, class_name = class_path.rsplit(".", 1)
            
            # 动态导入模块
            if self.strategy_dir not in sys.path:
                sys.path.append(self.strategy_dir)
                
            module = importlib.import_module(module_path)
            strategy_class = getattr(module, class_name)
            
            # 检查是否为有效策略类
            if not issubclass(strategy_class, Strategy):
                self.logger.error(f"无效的策略类: {class_path} 不是 Strategy 的子类")
                return False
            
            # 创建策略实例
            strategy = strategy_class(
                strategy_id=strategy_id,
                name=config.get("name", class_name),
                params=config.get("params", {})
            )
            
            # 设置组件引用
            strategy.executor = self
            strategy.account_manager = self.account_manager
            strategy.order_manager = self.order_manager
            strategy.position_manager = self.position_manager
            strategy.data_provider = self.data_provider
            
            # 创建策略锁
            self.strategy_locks[strategy_id] = asyncio.Lock()
            
            # 添加到策略字典
            self.strategies[strategy_id] = strategy
            
            # 初始化策略
            await strategy.initialize()
            
            # 订阅合约
            symbols = config.get("symbols", [])
            if symbols:
                await strategy.subscribe_symbols(symbols)
            
            self.logger.info(f"策略 {strategy_id} 加载成功")
            return True
            
        except Exception as e:
            self.logger.error(f"加载策略 {strategy_id} 失败: {str(e)}")
            traceback.print_exc()
            self.performance_stats["errors"] += 1
            return False
    
    async def _reload_strategy(self, strategy_id: str, config: Dict) -> bool:
        """
        热重载策略
        
        Args:
            strategy_id: 策略ID
            config: 新配置
            
        Returns:
            bool: 重载是否成功
        """
        self.logger.info(f"热重载策略: {strategy_id}")
        
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            self.logger.error(f"策略不存在: {strategy_id}")
            return False
        
        # 获取当前策略实例
        strategy = self.strategies[strategy_id]
        running = strategy.is_running
        
        try:
            # 停止策略
            if running:
                await self.stop_strategy(strategy_id)
            
            # 卸载策略
            await self._unload_strategy(strategy_id)
            
            # 重新加载策略
            success = await self._load_strategy(strategy_id, config)
            if not success:
                self.logger.error(f"重载策略 {strategy_id} 失败")
                return False
            
            # 重新启动策略
            if running:
                await self.start_strategy(strategy_id)
            
            self.logger.info(f"策略 {strategy_id} 热重载成功")
            return True
            
        except Exception as e:
            self.logger.error(f"热重载策略 {strategy_id} 失败: {str(e)}")
            traceback.print_exc()
            self.performance_stats["errors"] += 1
            return False
    
    async def _unload_strategy(self, strategy_id: str) -> bool:
        """
        卸载策略
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            bool: 卸载是否成功
        """
        self.logger.info(f"卸载策略: {strategy_id}")
        
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            self.logger.warning(f"策略不存在: {strategy_id}")
            return False
        
        try:
            # 获取策略实例
            strategy = self.strategies[strategy_id]
            
            # 确保策略已停止
            if strategy.is_running:
                await self.stop_strategy(strategy_id)
            
            # 取消订阅合约
            if strategy.subscribed_symbols:
                await strategy.unsubscribe_symbols(list(strategy.subscribed_symbols))
            
            # 清理资源
            # TODO: 实现其他清理逻辑，如关闭文件、数据库连接等
            
            # 移除策略
            del self.strategies[strategy_id]
            
            # 移除策略锁
            if strategy_id in self.strategy_locks:
                del self.strategy_locks[strategy_id]
            
            self.logger.info(f"策略 {strategy_id} 卸载成功")
            return True
            
        except Exception as e:
            self.logger.error(f"卸载策略 {strategy_id} 失败: {str(e)}")
            traceback.print_exc()
            return False
    
    async def start_strategy(self, strategy_id: str) -> bool:
        """
        启动策略
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            bool: 启动是否成功
        """
        self.logger.info(f"启动策略: {strategy_id}")
        
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            self.logger.error(f"策略不存在: {strategy_id}")
            return False
        
        # 获取策略实例
        strategy = self.strategies[strategy_id]
        
        # 检查是否已运行
        if strategy.is_running:
            self.logger.warning(f"策略 {strategy_id} 已在运行")
            return True
        
        try:
            # 启动策略
            async with self.strategy_locks[strategy_id]:
                success = await strategy.start()
                
                if success:
                    self.logger.info(f"策略 {strategy_id} 启动成功")
                    self.performance_stats["running_strategies"] += 1
                    return True
                else:
                    self.logger.error(f"策略 {strategy_id} 启动失败")
                    return False
                    
        except Exception as e:
            self.logger.error(f"启动策略 {strategy_id} 失败: {str(e)}")
            traceback.print_exc()
            self.performance_stats["errors"] += 1
            return False
    
    async def stop_strategy(self, strategy_id: str) -> bool:
        """
        停止策略
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            bool: 停止是否成功
        """
        self.logger.info(f"停止策略: {strategy_id}")
        
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            self.logger.error(f"策略不存在: {strategy_id}")
            return False
        
        # 获取策略实例
        strategy = self.strategies[strategy_id]
        
        # 检查是否已停止
        if not strategy.is_running:
            self.logger.warning(f"策略 {strategy_id} 已停止")
            return True
        
        try:
            # 停止策略
            async with self.strategy_locks[strategy_id]:
                success = await strategy.stop()
                
                if success:
                    self.logger.info(f"策略 {strategy_id} 停止成功")
                    self.performance_stats["running_strategies"] -= 1
                    
                    # 取消正在运行的任务
                    if strategy_id in self.strategy_tasks:
                        task = self.strategy_tasks[strategy_id]
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                        del self.strategy_tasks[strategy_id]
                    
                    return True
                else:
                    self.logger.error(f"策略 {strategy_id} 停止失败")
                    return False
                    
        except Exception as e:
            self.logger.error(f"停止策略 {strategy_id} 失败: {str(e)}")
            traceback.print_exc()
            self.performance_stats["errors"] += 1
            return False
    
    async def get_strategy_status(self, strategy_id: str) -> Optional[Dict]:
        """
        获取策略状态
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            Optional[Dict]: 策略状态信息
        """
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            self.logger.error(f"策略不存在: {strategy_id}")
            return None
        
        # 获取策略实例
        strategy = self.strategies[strategy_id]
        
        # 构建状态信息
        return {
            "strategy_id": strategy_id,
            "name": strategy.name,
            "status": strategy.status,
            "running": strategy.is_running,
            "initialized": strategy.is_initialized,
            "last_run_time": strategy.last_run_time,
            "metrics": copy.deepcopy(strategy.metrics),
            "subscribed_symbols": list(strategy.subscribed_symbols),
            "config": self.strategy_configs.get(strategy_id, {})
        }
    
    async def get_all_strategies(self) -> List[Dict]:
        """
        获取所有策略状态
        
        Returns:
            List[Dict]: 策略状态列表
        """
        result = []
        
        for strategy_id in self.strategies:
            status = await self.get_strategy_status(strategy_id)
            if status:
                result.append(status)
        
        return result
    
    async def update_strategy_params(self, strategy_id: str, params: Dict) -> bool:
        """
        更新策略参数
        
        Args:
            strategy_id: 策略ID
            params: 新参数
            
        Returns:
            bool: 更新是否成功
        """
        self.logger.info(f"更新策略参数: {strategy_id}")
        
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            self.logger.error(f"策略不存在: {strategy_id}")
            return False
        
        # 获取策略实例
        strategy = self.strategies[strategy_id]
        
        try:
            # 更新策略参数
            async with self.strategy_locks[strategy_id]:
                # 更新内存中的参数
                strategy.params.update(params)
                
                # 更新配置文件
                if strategy_id in self.strategy_configs:
                    config = self.strategy_configs[strategy_id]
                    if "params" not in config:
                        config["params"] = {}
                    config["params"].update(params)
                    
                    # 增加版本号
                    config["version"] = config.get("version", 0) + 1
                    
                    # 保存配置
                    config_path = os.path.join(self.config_dir, "strategies", f"{strategy_id}.json")
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=4)
                
                self.logger.info(f"策略 {strategy_id} 参数更新成功")
                return True
                
        except Exception as e:
            self.logger.error(f"更新策略参数失败: {str(e)}")
            traceback.print_exc()
            return False
    
    async def _execute_strategy(self, strategy_id: str) -> None:
        """
        执行策略的run方法
        
        Args:
            strategy_id: 策略ID
        """
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            return
        
        # 获取策略实例
        strategy = self.strategies[strategy_id]
        
        # 检查是否正在运行
        if not strategy.is_running:
            return
        
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 执行策略
            async with self.strategy_locks[strategy_id]:
                await strategy.run()
            
            # 计算执行时间
            execution_time = (time.time() - start_time) * 1000  # 毫秒
            
            # 更新策略统计
            strategy.last_run_time = datetime.now().isoformat()
            strategy.metrics["runs"] += 1
            strategy.metrics["last_run_time"] = execution_time
            strategy.metrics["avg_run_time"] = (
                (strategy.metrics["avg_run_time"] * (strategy.metrics["runs"] - 1) + execution_time) /
                strategy.metrics["runs"]
            )
            strategy.metrics["max_run_time"] = max(strategy.metrics["max_run_time"], execution_time)
            
            # 更新执行器统计
            self.performance_stats["executions"] += 1
            self.performance_stats["avg_execution_time"] = (
                (self.performance_stats["avg_execution_time"] * (self.performance_stats["executions"] - 1) + execution_time) /
                self.performance_stats["executions"]
            )
            self.performance_stats["max_execution_time"] = max(self.performance_stats["max_execution_time"], execution_time)
            
        except asyncio.CancelledError:
            # 策略被取消，正常情况
            pass
        except Exception as e:
            # 策略执行出错
            self.logger.error(f"策略 {strategy_id} 执行出错: {str(e)}")
            traceback.print_exc()
            
            # 更新统计
            strategy.metrics["errors"] += 1
            self.performance_stats["errors"] += 1
    
    async def _trigger_strategy_timers(self) -> None:
        """触发所有策略的定时器回调"""
        for strategy_id, strategy in self.strategies.items():
            if not strategy.is_running:
                continue
                
            try:
                # 创建定时器任务
                task = asyncio.create_task(self._execute_strategy_timer(strategy_id))
                
            except Exception as e:
                self.logger.error(f"创建策略 {strategy_id} 定时器任务失败: {str(e)}")
                self.performance_stats["errors"] += 1
    
    async def _execute_strategy_timer(self, strategy_id: str) -> None:
        """
        执行策略的定时器回调
        
        Args:
            strategy_id: 策略ID
        """
        # 检查策略是否存在
        if strategy_id not in self.strategies:
            return
        
        # 获取策略实例
        strategy = self.strategies[strategy_id]
        
        # 检查是否正在运行
        if not strategy.is_running:
            return
        
        try:
            # 执行策略定时器回调
            async with self.strategy_locks[strategy_id]:
                await strategy.on_timer()
                
                # 执行策略主逻辑
                self.strategy_tasks[strategy_id] = asyncio.create_task(
                    self._execute_strategy(strategy_id)
                )
                
        except Exception as e:
            self.logger.error(f"策略 {strategy_id} 定时器回调出错: {str(e)}")
            strategy.metrics["errors"] += 1
            self.performance_stats["errors"] += 1
    
    def _update_performance_stats(self) -> None:
        """更新性能统计信息"""
        # 更新策略数量
        self.performance_stats["strategies"] = len(self.strategies)
        
        # 更新内存使用
        try:
            import psutil
            process = psutil.Process(os.getpid())
            self.performance_stats["memory_usage"] = process.memory_info().rss / 1024 / 1024  # MB
        except:
            pass
    
    async def get_performance_stats(self) -> Dict:
        """
        获取性能统计信息
        
        Returns:
            Dict: 性能统计信息
        """
        self._update_performance_stats()
        return copy.deepcopy(self.performance_stats)
    
    # 事件回调方法
    
    async def _on_market_data(self, data: Dict) -> None:
        """
        市场数据回调
        
        Args:
            data: 市场数据
        """
        symbol = data.get("symbol", "")
        if not symbol:
            return
            
        # 遍历所有策略
        for strategy_id, strategy in self.strategies.items():
            if not strategy.is_running:
                continue
                
            # 检查是否订阅了该合约
            if symbol in strategy.subscribed_symbols:
                try:
                    asyncio.create_task(strategy.on_market_data(data))
                except Exception as e:
                    self.logger.error(f"策略 {strategy_id} 处理市场数据出错: {str(e)}")
                    strategy.metrics["errors"] += 1
    
    async def _on_bar(self, symbol: str, bar: Dict) -> None:
        """
        K线数据回调
        
        Args:
            symbol: 合约代码
            bar: K线数据
        """
        # 遍历所有策略
        for strategy_id, strategy in self.strategies.items():
            if not strategy.is_running:
                continue
                
            # 检查是否订阅了该合约
            if symbol in strategy.subscribed_symbols:
                try:
                    asyncio.create_task(strategy.on_bar(symbol, bar))
                except Exception as e:
                    self.logger.error(f"策略 {strategy_id} 处理K线数据出错: {str(e)}")
                    strategy.metrics["errors"] += 1
    
    async def _on_order_update(self, order: Dict) -> None:
        """
        订单更新回调
        
        Args:
            order: 订单信息
        """
        strategy_id = order.get("strategy_id", "")
        if not strategy_id:
            return
            
        # 检查策略是否存在
        if strategy_id in self.strategies:
            strategy = self.strategies[strategy_id]
            
            if strategy.is_running:
                try:
                    asyncio.create_task(strategy.on_order_update(order))
                except Exception as e:
                    self.logger.error(f"策略 {strategy_id} 处理订单更新出错: {str(e)}")
                    strategy.metrics["errors"] += 1
    
    async def _on_trade(self, trade: Dict) -> None:
        """
                成交回调
        
        Args:
            trade: 成交信息
        """
        order_id = trade.get("order_id", "")
        
        # 尝试获取订单信息
        if self.order_manager:
            order = await self.order_manager.get_order(order_id)
            if order:
                strategy_id = order.get("strategy_id", "")
                
                # 检查策略是否存在
                if strategy_id in self.strategies:
                    strategy = self.strategies[strategy_id]
                    
                    if strategy.is_running:
                        try:
                            asyncio.create_task(strategy.on_trade(trade))
                        except Exception as e:
                            self.logger.error(f"策略 {strategy_id} 处理成交回调出错: {str(e)}")
                            strategy.metrics["errors"] += 1
    
    async def _on_position_change(self, position_data: Dict) -> None:
        """
        持仓变化回调
        
        Args:
            position_data: 持仓信息
        """
        # 提取所有持仓
        positions = position_data.get("positions", [])
        
        # 按策略ID分组持仓
        positions_by_strategy = defaultdict(list)
        for position in positions:
            strategy_id = position.get("strategy_id", "")
            if strategy_id:
                positions_by_strategy[strategy_id].append(position)
        
        # 向相应策略发送持仓变化通知
        for strategy_id, strategy_positions in positions_by_strategy.items():
            if strategy_id in self.strategies:
                strategy = self.strategies[strategy_id]
                
                if strategy.is_running:
                    try:
                        # 创建策略专属的持仓数据
                        strategy_position_data = {
                            "positions": strategy_positions,
                            "statistics": position_data.get("statistics", {}),
                            "timestamp": position_data.get("timestamp", time.time())
                        }
                        
                        asyncio.create_task(strategy.on_position_change(strategy_position_data))
                    except Exception as e:
                        self.logger.error(f"策略 {strategy_id} 处理持仓变化出错: {str(e)}")
                        strategy.metrics["errors"] += 1
    
    async def _on_account_change(self, account_data: Dict) -> None:
        """
        账户变化回调
        
        Args:
            account_data: 账户信息
        """
        # 向所有运行中的策略发送账户变化通知
        for strategy_id, strategy in self.strategies.items():
            if strategy.is_running:
                try:
                    asyncio.create_task(strategy.on_account_change(account_data))
                except Exception as e:
                    self.logger.error(f"策略 {strategy_id} 处理账户变化出错: {str(e)}")
                    strategy.metrics["errors"] += 1
    
    async def _timer_task(self) -> None:
        """定时器任务，定期触发策略执行"""
        self.logger.info(f"启动策略定时器任务，间隔 {self.timer_interval} 秒")
        
        while self._running:
            try:
                # 触发策略定时器
                await self._trigger_strategy_timers()
                
                # 等待下一个时间间隔
                await asyncio.sleep(self.timer_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"定时器任务出错: {str(e)}")
                self.performance_stats["errors"] += 1
                await asyncio.sleep(self.timer_interval)
        
        self.logger.info("策略定时器任务已停止")
    
    async def _resource_monitor_task(self) -> None:
        """资源监控任务，监控系统资源使用情况"""
        self.logger.info("启动资源监控任务")
        
        try:
            import psutil
            has_psutil = True
        except ImportError:
            self.logger.warning("未安装psutil库，无法监控系统资源")
            has_psutil = False
            return
        
        while self._running:
            try:
                if has_psutil:
                    # 获取进程信息
                    process = psutil.Process(os.getpid())
                    
                    # 更新内存使用情况
                    mem_info = process.memory_info()
                    self.performance_stats["memory_usage"] = mem_info.rss / 1024 / 1024  # MB
                    
                    # 更新CPU使用情况
                    self.performance_stats["cpu_percent"] = process.cpu_percent(interval=0.1)
                    
                    # 检查是否超过资源限制
                    if (self.resource_limits["max_memory"] > 0 and 
                            self.performance_stats["memory_usage"] > self.resource_limits["max_memory"]):
                        self.logger.warning(f"内存使用超过限制: {self.performance_stats['memory_usage']:.2f}MB > {self.resource_limits['max_memory']}MB")
                        
                        # 触发资源警告
                        await self._handle_resource_warning("memory")
                    
                    if (self.resource_limits["max_cpu_percent"] > 0 and 
                            self.performance_stats["cpu_percent"] > self.resource_limits["max_cpu_percent"]):
                        self.logger.warning(f"CPU使用超过限制: {self.performance_stats['cpu_percent']:.2f}% > {self.resource_limits['max_cpu_percent']}%")
                        
                        # 触发资源警告
                        await self._handle_resource_warning("cpu")
                
                # 等待监控间隔
                await asyncio.sleep(self.resource_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"资源监控任务出错: {str(e)}")
                await asyncio.sleep(self.resource_check_interval)
        
        self.logger.info("资源监控任务已停止")
    
    async def _handle_resource_warning(self, resource_type: str) -> None:
        """
        处理资源警告
        
        Args:
            resource_type: 资源类型（memory/cpu）
        """
        # 根据配置决定如何处理资源警告
        if self.resource_limits["action_on_limit"] == "warn":
            # 只记录警告，不采取行动
            pass
            
        elif self.resource_limits["action_on_limit"] == "stop_new":
            # 停止添加新策略
            self.allow_new_strategies = False
            self.logger.warning(f"由于{resource_type}资源限制，已禁止添加新策略")
            
        elif self.resource_limits["action_on_limit"] == "stop_some":
            # 停止一些策略以释放资源
            await self._stop_strategies_to_free_resources()
            
        elif self.resource_limits["action_on_limit"] == "stop_all":
            # 停止所有策略
            self.logger.warning(f"由于{resource_type}资源限制，正在停止所有策略")
            await self.stop_all_strategies()
    
    async def _stop_strategies_to_free_resources(self) -> None:
        """停止一些策略以释放资源"""
        self.logger.info("尝试停止一些策略以释放资源")
        
        # 获取所有运行中的策略
        running_strategies = []
        for strategy_id, strategy in self.strategies.items():
            if strategy.is_running:
                # 计算策略优先级
                priority = strategy.params.get("resource_priority", 5)  # 默认中等优先级
                running_strategies.append((strategy_id, priority))
        
        if not running_strategies:
            self.logger.info("没有运行中的策略可以停止")
            return
        
        # 按优先级排序（低优先级先停止）
        running_strategies.sort(key=lambda x: x[1])
        
        # 停止最多三个低优先级策略
        count = 0
        for strategy_id, _ in running_strategies:
            if count >= 3:
                break
                
            self.logger.info(f"停止低优先级策略以释放资源: {strategy_id}")
            await self.stop_strategy(strategy_id)
            count += 1
        
        self.logger.info(f"已停止 {count} 个策略以释放资源")
    
    async def get_health_status(self) -> Dict:
        """
        获取健康状态
        
        Returns:
            Dict: 健康状态信息
        """
        # 更新性能统计
        self._update_performance_stats()
        
        # 计算运行中的策略数量
        running_count = 0
        error_count = 0
        for strategy in self.strategies.values():
            if strategy.is_running:
                running_count += 1
            error_count += strategy.metrics["errors"]
        
        return {
            'status': 'running' if self._running else 'stopped',
            'strategies_total': len(self.strategies),
            'strategies_running': running_count,
            'memory_usage': self.performance_stats.get("memory_usage", 0),
            'cpu_percent': self.performance_stats.get("cpu_percent", 0),
            'executions': self.performance_stats["executions"],
            'errors': self.performance_stats["errors"],
            'avg_execution_time': self.performance_stats["avg_execution_time"],
            'max_execution_time': self.performance_stats["max_execution_time"],
            'uptime': int(time.time() - self.start_time) if self.start_time else 0,
            'allow_new_strategies': self.allow_new_strategies
        }