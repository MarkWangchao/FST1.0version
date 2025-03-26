#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 基础策略类

此模块提供了交易策略的基类，所有自定义策略都应继承此类。
主要功能包括：
- 提供策略标准接口
- 处理基本的生命周期事件
- 提供常用的交易和分析工具
- 管理策略状态和统计数据
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Set, Tuple, Callable, Any
import copy
import uuid
import numpy as np
import pandas as pd

class BaseStrategy:
    """
    策略基类，所有用户策略应继承此类
    """
    
    def __init__(self, strategy_id: str = None, name: str = None, params: Dict = None):
        """
        初始化策略
        
        Args:
            strategy_id: 策略唯一ID，如果为None则自动生成
            name: 策略名称
            params: 策略参数
        """
        # 生成策略ID (如果未提供)
        self.strategy_id = strategy_id or f"strategy_{uuid.uuid4().hex[:8]}"
        self.name = name or self.__class__.__name__
        self.params = params or {}
        
        # 初始化日志记录器
        self.logger = logging.getLogger(f"fst.strategy.{self.strategy_id}")
        
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
        
        # 策略数据
        self.strategy_data = {}
        
        # 上次运行时间
        self.last_run_time = None
        
        # 策略状态和统计
        self.status = "stopped"
        self.metrics = {
            "runs": 0,
            "signals": 0,
            "orders": 0,
            "trades": 0,
            "errors": 0,
            "avg_run_time": 0,
            "max_run_time": 0,
            "last_run_time": 0,
            "total_pnl": 0,
            "win_count": 0,
            "loss_count": 0
        }
        
        # 策略配置
        self.config = {
            "auto_subscribe": True,       # 自动订阅合约
            "auto_reconnect": True,       # 自动重连
            "persist_state": True,        # 持久化状态
            "max_retries": 3,             # 最大重试次数
            "position_size_limit": 0,     # 最大持仓限制(0表示无限制)
            "trade_symbols": [],          # 交易的合约
            "trade_period": "1m",         # 交易周期
            "run_interval": 60,           # 运行间隔(秒)
            "trading_hours": {},          # 交易时段
            "custom_indicators": {}       # 自定义指标
        }
        
        # 更新配置
        if "config" in self.params:
            self.config.update(self.params["config"])
        
        # 初始化数据缓存
        self.data_cache = {}
        
        # 信号和指标
        self.signals = {}
        self.indicators = {}
        
        # 实时行情数据
        self.quotes = {}
        
        # 初始化自定义数据结构
        self._init_custom_data()
    
    def _init_custom_data(self):
        """初始化策略自定义数据结构，子类可重写"""
        pass
    
    async def initialize(self) -> bool:
        """
        初始化策略，在策略启动前调用
        
        Returns:
            bool: 初始化是否成功
        """
        self.logger.info(f"初始化策略 {self.name} (ID: {self.strategy_id})")
        
        # 检查必要组件
        if not self.executor or not self.data_provider:
            self.logger.error("策略初始化失败: 缺少必要组件")
            return False
        
        # 订阅合约
        if self.config["auto_subscribe"] and self.config["trade_symbols"]:
            for symbol in self.config["trade_symbols"]:
                await self.subscribe_symbol(symbol)
        
        # 加载历史数据
        await self._load_historical_data()
        
        # 初始化指标
        self._init_indicators()
        
        # 策略已初始化
        self.is_initialized = True
        self.status = "initialized"
        
        return True
    
    async def start(self) -> bool:
        """
        启动策略
        
        Returns:
            bool: 启动是否成功
        """
        # 确保策略已初始化
        if not self.is_initialized:
            success = await self.initialize()
            if not success:
                self.logger.error("策略启动失败: 初始化失败")
                return False
        
        self.logger.info(f"启动策略 {self.name} (ID: {self.strategy_id})")
        
        # 更新状态
        self.is_running = True
        self.status = "running"
        
        # 恢复状态(如果启用)
        if self.config["persist_state"]:
            await self._load_state()
        
        # 运行策略逻辑
        try:
            await self.on_start()
        except Exception as e:
            self.logger.error(f"策略启动时发生错误: {str(e)}")
            self.metrics["errors"] += 1
        
        return True
    
    async def stop(self) -> bool:
        """
        停止策略
        
        Returns:
            bool: 停止是否成功
        """
        self.logger.info(f"停止策略 {self.name} (ID: {self.strategy_id})")
        
        # 更新状态
        previous_status = self.status
        self.status = "stopping"
        
        # 运行策略停止逻辑
        try:
            await self.on_stop()
        except Exception as e:
            self.logger.error(f"策略停止时发生错误: {str(e)}")
            self.metrics["errors"] += 1
        
        # 保存状态(如果启用)
        if self.config["persist_state"]:
            await self._save_state()
        
        # 更新状态
        self.is_running = False
        self.status = "stopped"
        
        return True
    
    async def pause(self) -> bool:
        """
        暂停策略
        
        Returns:
            bool: 暂停是否成功
        """
        self.logger.info(f"暂停策略 {self.name} (ID: {self.strategy_id})")
        
        # 更新状态
        self.status = "paused"
        self.is_running = False
        
        # 运行策略暂停逻辑
        try:
            await self.on_pause()
        except Exception as e:
            self.logger.error(f"策略暂停时发生错误: {str(e)}")
            self.metrics["errors"] += 1
        
        return True
    
    async def resume(self) -> bool:
        """
        恢复策略
        
        Returns:
            bool: 恢复是否成功
        """
        self.logger.info(f"恢复策略 {self.name} (ID: {self.strategy_id})")
        
        # 更新状态
        self.status = "running"
        self.is_running = True
        
        # 运行策略恢复逻辑
        try:
            await self.on_resume()
        except Exception as e:
            self.logger.error(f"策略恢复时发生错误: {str(e)}")
            self.metrics["errors"] += 1
        
        return True
    
    async def run(self) -> None:
        """
        运行策略主逻辑，由执行器定期调用
        """
        if not self.is_running:
            return
            
        # 记录运行时间
        start_time = time.time()
        self.last_run_time = datetime.now()
        
        try:
            # 检查交易时段
            if not self._is_trading_hours():
                return
                
            # 更新行情数据
            await self._update_market_data()
            
            # 更新指标
            self._update_indicators()
            
            # 执行策略主逻辑
            await self.on_tick()
            
            # 更新统计
            self.metrics["runs"] += 1
            execution_time = (time.time() - start_time) * 1000  # 毫秒
            self.metrics["last_run_time"] = execution_time
            
            # 更新平均执行时间
            if self.metrics["runs"] > 1:
                self.metrics["avg_run_time"] = (
                    (self.metrics["avg_run_time"] * (self.metrics["runs"] - 1) + execution_time) / 
                    self.metrics["runs"]
                )
            else:
                self.metrics["avg_run_time"] = execution_time
                
            # 更新最大执行时间
            self.metrics["max_run_time"] = max(self.metrics["max_run_time"], execution_time)
            
        except Exception as e:
            self.logger.error(f"策略运行时发生错误: {str(e)}")
            self.metrics["errors"] += 1
    
    # 事件处理方法 (子类可重写)
    
    async def on_start(self) -> None:
        """策略启动时调用"""
        pass
    
    async def on_stop(self) -> None:
        """策略停止时调用"""
        pass
    
    async def on_pause(self) -> None:
        """策略暂停时调用"""
        pass
    
    async def on_resume(self) -> None:
        """策略恢复时调用"""
        pass
    
    async def on_tick(self) -> None:
        """
        策略主逻辑，每个周期调用
        子类必须实现此方法
        """
        raise NotImplementedError("策略必须实现on_tick方法")
    
    async def on_bar(self, symbol: str, bar: Dict) -> None:
        """
        K线数据回调
        
        Args:
            symbol: 合约代码
            bar: K线数据
        """
        pass
    
    async def on_market_data(self, data: Dict) -> None:
        """
        市场数据回调
        
        Args:
            data: 市场数据
        """
        symbol = data.get("symbol", "")
        if not symbol:
            return
            
        # 更新行情数据
        self.quotes[symbol] = data
    
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
        # 更新统计
        self.metrics["trades"] += 1
        
        # 计算盈亏
        if "profit" in trade:
            self.metrics["total_pnl"] += trade["profit"]
            
            if trade["profit"] > 0:
                self.metrics["win_count"] += 1
            elif trade["profit"] < 0:
                self.metrics["loss_count"] += 1
    
    async def on_position_change(self, positions: Dict) -> None:
        """
        持仓变化回调
        
        Args:
            positions: 持仓信息
        """
        pass
    
    async def on_account_change(self, account: Dict) -> None:
        """
        账户变化回调
        
        Args:
            account: 账户信息
        """
        pass
    
    async def on_timer(self) -> None:
        """定时器回调，由执行器调用"""
        pass
    
    # 交易操作方法
    
    async def buy(self, symbol: str, price: float, volume: float, 
                order_type: str = "LIMIT", offset: str = "OPEN") -> Tuple[bool, str, str]:
        """
        买入
        
        Args:
            symbol: 合约代码
            price: 价格 (0表示市价)
            volume: 数量
            order_type: 订单类型 (LIMIT/MARKET/STOP等)
            offset: 开平标志 (OPEN/CLOSE等)
            
        Returns:
            Tuple[bool, str, str]: (是否成功, 订单ID, 错误信息)
        """
        if not self.is_running:
            return False, "", "策略未运行"
            
        # 检查持仓限制
        if self.config["position_size_limit"] > 0:
            current_positions = await self.position_manager.get_positions(self.strategy_id)
            total_size = sum(pos["volume"] for pos in current_positions)
            
            if total_size + volume > self.config["position_size_limit"]:
                self.logger.warning(f"超过持仓限制: {total_size + volume} > {self.config['position_size_limit']}")
                return False, "", "超过持仓限制"
        
        # 创建订单
        if order_type == "MARKET":
            price = 0
            
        success, order_id, msg = await self.order_manager.create_order(
            symbol=symbol,
            direction="BUY",
            offset=offset,
            price=price,
            volume=volume,
            order_type=order_type,
            strategy_id=self.strategy_id
        )
        
        if success:
            self.logger.info(f"买入订单已提交: {symbol} 价格={price} 数量={volume} 订单ID={order_id}")
            self.metrics["orders"] += 1
        else:
            self.logger.error(f"买入订单失败: {symbol} 价格={price} 数量={volume} 错误={msg}")
        
        return success, order_id, msg
    
    async def sell(self, symbol: str, price: float, volume: float, 
                 order_type: str = "LIMIT", offset: str = "CLOSE") -> Tuple[bool, str, str]:
        """
        卖出
        
        Args:
            symbol: 合约代码
            price: 价格 (0表示市价)
            volume: 数量
            order_type: 订单类型 (LIMIT/MARKET/STOP等)
            offset: 开平标志 (OPEN/CLOSE等)
            
        Returns:
            Tuple[bool, str, str]: (是否成功, 订单ID, 错误信息)
        """
        if not self.is_running:
            return False, "", "策略未运行"
        
        # 创建订单
        if order_type == "MARKET":
            price = 0
            
        success, order_id, msg = await self.order_manager.create_order(
            symbol=symbol,
            direction="SELL",
            offset=offset,
            price=price,
            volume=volume,
            order_type=order_type,
            strategy_id=self.strategy_id
        )
        
        if success:
            self.logger.info(f"卖出订单已提交: {symbol} 价格={price} 数量={volume} 订单ID={order_id}")
            self.metrics["orders"] += 1
        else:
            self.logger.error(f"卖出订单失败: {symbol} 价格={price} 数量={volume} 错误={msg}")
        
        return success, order_id, msg
    
    async def close_all_positions(self) -> Tuple[int, int]:
        """
        平所有仓
        
        Returns:
            Tuple[int, int]: (成功数量, 失败数量)
        """
        if not self.is_running:
            return 0, 0
            
        # 通过持仓管理器平仓
        return await self.position_manager.close_all_positions(self.strategy_id)
    
    async def cancel_all_orders(self) -> Tuple[int, int]:
        """
        撤销所有订单
        
        Returns:
            Tuple[int, int]: (成功数量, 失败数量)
        """
        if not self.is_running:
            return 0, 0
            
        # 通过订单管理器撤单
        return await self.order_manager.cancel_all_orders(self.strategy_id)
    
    # 订阅和数据获取方法
    
    async def subscribe_symbol(self, symbol: str) -> bool:
        """
        订阅合约
        
        Args:
            symbol: 合约代码
            
        Returns:
            bool: 是否成功
        """
        if not self.data_provider:
            self.logger.error(f"订阅失败: 数据提供者未设置")
            return False
            
        success = await self.data_provider.subscribe_symbol(symbol)
        
        if success:
            self.subscribed_symbols.add(symbol)
            self.logger.info(f"订阅合约成功: {symbol}")
            
            # 更新交易合约列表
            if symbol not in self.config["trade_symbols"]:
                self.config["trade_symbols"].append(symbol)
        else:
            self.logger.error(f"订阅合约失败: {symbol}")
            
        return success
    
    async def get_klines(self, symbol: str, period: str, count: int = 100) -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            period: K线周期
            count: K线数量
            
        Returns:
            pd.DataFrame: K线数据
        """
        if not self.data_provider:
            self.logger.error("获取K线失败: 数据提供者未设置")
            return pd.DataFrame()
            
        try:
            klines = await self.data_provider.get_klines(symbol, period, count)
            return klines
        except Exception as e:
            self.logger.error(f"获取K线异常: {str(e)}")
            return pd.DataFrame()
    
    async def get_latest_price(self, symbol: str) -> float:
        """
        获取最新价格
        
        Args:
            symbol: 合约代码
            
        Returns:
            float: 最新价格
        """
        # 优先从缓存中获取
        if symbol in self.quotes:
            return self.quotes[symbol].get("last_price", 0)
            
        try:
            # 从数据提供者获取
            price = await self.data_provider.get_latest_price(symbol)
            return price
        except Exception as e:
            self.logger.error(f"获取最新价格异常: {str(e)}")
            return 0
    
    # 内部帮助方法
    
    def _is_trading_hours(self) -> bool:
        """检查当前是否在交易时段内"""
        if not self.config["trading_hours"]:
            return True  # 未设置交易时段，默认一直可交易
            
        now = datetime.now().time()
        
        for start_str, end_str in self.config["trading_hours"].items():
            start_time = datetime.strptime(start_str, "%H:%M:%S").time()
            end_time = datetime.strptime(end_str, "%H:%M:%S").time()
            
            if start_time <= now <= end_time:
                return True
                
        return False
    
    async def _load_historical_data(self) -> None:
        """加载历史数据"""
        if not self.data_provider:
            return
            
        for symbol in self.config["trade_symbols"]:
            try:
                # 获取交易周期的K线数据
                period = self.config["trade_period"]
                klines = await self.data_provider.get_klines(symbol, period, 100)
                
                if not klines.empty:
                    self.data_cache[f"{symbol}_{period}"] = klines
                    self.logger.info(f"加载历史数据成功: {symbol} {period} {len(klines)}条")
                    
            except Exception as e:
                self.logger.error(f"加载历史数据失败: {symbol} {str(e)}")
    
    async def _update_market_data(self) -> None:
        """更新市场数据"""
        if not self.data_provider:
            return
            
        for symbol in self.config["trade_symbols"]:
            try:
                # 获取最新行情
                quote = await self.data_provider.get_quote(symbol)
                
                if quote:
                    self.quotes[symbol] = quote
                    
                # 更新K线缓存
                period = self.config["trade_period"]
                klines = await self.data_provider.get_klines(symbol, period, 100)
                
                if not klines.empty:
                    self.data_cache[f"{symbol}_{period}"] = klines
                    
            except Exception as e:
                self.logger.error(f"更新市场数据失败: {symbol} {str(e)}")
    
    def _init_indicators(self) -> None:
        """初始化技术指标"""
        # 基础指标配置
        self.indicators["default"] = {
            "MA": [5, 10, 20, 60],
            "EMA": [5, 10, 20, 60],
            "MACD": {"fast": 12, "slow": 26, "signal": 9},
            "RSI": [14],
            "BOLL": {"period": 20, "std_dev": 2},
            "KDJ": {"period": 9},
            "Supertrend": {"period": 10, "multiplier": 3},
            "ATR": [14]
        }
        
        # 添加自定义指标
        if self.config["custom_indicators"]:
            self.indicators.update(self.config["custom_indicators"])
    
    def _update_indicators(self) -> None:
        """更新技术指标"""
        # 遍历所有合约
        for symbol in self.config["trade_symbols"]:
            period = self.config["trade_period"]
            cache_key = f"{symbol}_{period}"
            
            if cache_key not in self.data_cache:
                continue
                
            df = self.data_cache[cache_key]
            
            if df.empty:
                continue
                
            # 计算基本指标
            self._calculate_indicators(symbol, df)
    
    def _calculate_indicators(self, symbol: str, df: pd.DataFrame) -> None:
        """
        计算技术指标
        
        Args:
            symbol: 合约代码
            df: K线数据
        """
        # 确保有收盘价
        if "close" not in df.columns:
            return
            
        indicators = {}
        
        # 计算移动平均线
        for ma_period in self.indicators["default"]["MA"]:
            indicators[f"MA{ma_period}"] = df["close"].rolling(ma_period).mean()
            
        # 计算指数移动平均线
        for ema_period in self.indicators["default"]["EMA"]:
            indicators[f"EMA{ema_period}"] = df["close"].ewm(span=ema_period, adjust=False).mean()
            
        # 计算MACD
        macd_config = self.indicators["default"]["MACD"]
        fast = df["close"].ewm(span=macd_config["fast"], adjust=False).mean()
        slow = df["close"].ewm(span=macd_config["slow"], adjust=False).mean()
        indicators["MACD"] = fast - slow
        indicators["MACD_signal"] = indicators["MACD"].ewm(span=macd_config["signal"], adjust=False).mean()
        indicators["MACD_hist"] = indicators["MACD"] - indicators["MACD_signal"]
        
        # 计算RSI
        for rsi_period in self.indicators["default"]["RSI"]:
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(rsi_period).mean()
            avg_loss = loss.rolling(rsi_period).mean()
            
            rs = avg_gain / avg_loss
            indicators[f"RSI{rsi_period}"] = 100 - (100 / (1 + rs))
            
        # 计算布林带
        boll_config = self.indicators["default"]["BOLL"]
        mid = df["close"].rolling(boll_config["period"]).mean()
        std = df["close"].rolling(boll_config["period"]).std()
        
        indicators["BOLL_mid"] = mid
        indicators["BOLL_upper"] = mid + std * boll_config["std_dev"]
        indicators["BOLL_lower"] = mid - std * boll_config["std_dev"]
        
        # 计算ATR
        for atr_period in self.indicators["default"]["ATR"]:
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - df["close"].shift()).abs()
            low_close = (df["low"] - df["close"].shift()).abs()
            
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            indicators[f"ATR{atr_period}"] = tr.rolling(atr_period).mean()
            
        # 计算KDJ
        kdj_config = self.indicators["default"]["KDJ"]
        period = kdj_config["period"]
        
        low_min = df["low"].rolling(window=period).min()
        high_max = df["high"].rolling(window=period).max()
        
        rsv = 100 * ((df["close"] - low_min) / (high_max - low_min))
        indicators["KDJ_K"] = rsv.ewm(alpha=1/3, adjust=False).mean()
        indicators["KDJ_D"] = indicators["KDJ_K"].ewm(alpha=1/3, adjust=False).mean()
        indicators["KDJ_J"] = 3 * indicators["KDJ_K"] - 2 * indicators["KDJ_D"]
        
        # 计算Supertrend (简化版)
        st_config = self.indicators["default"]["Supertrend"]
        period = st_config["period"]
        multiplier = st_config["multiplier"]
        
        atr = indicators[f"ATR{period}"]
        
        # 计算上轨和下轨
        hl2 = (df["high"] + df["low"]) / 2
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)
        
        # 初始化Supertrend
        supertrend = pd.Series(0, index=df.index)
        trend = pd.Series(1, index=df.index)  # 1: 上涨, -1: 下跌
        
        # 计算Supertrend值
        for i in range(period, len(df)):
            if df["close"].iloc[i] > upper_band.iloc[i-1]:
                trend.iloc[i] = 1
            elif df["close"].iloc[i] < lower_band.iloc[i-1]:
                trend.iloc[i] = -1
            else:
                trend.iloc[i] = trend.iloc[i-1]
                
                if trend.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i-1]:
                    lower_band.iloc[i] = lower_band.iloc[i-1]
                if trend.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i-1]:
                    upper_band.iloc[i] = upper_band.iloc[i-1]
            
            if trend.iloc[i] == 1:
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
        
        indicators["Supertrend"] = supertrend
        indicators["Supertrend_trend"] = trend
            
        # 保存指标
        self.indicators[symbol] = indicators
        
        # 更新数据缓存
        for key, value in indicators.items():
            df[key] = value
            
        period = self.config["trade_period"]
        self.data_cache[f"{symbol}_{period}"] = df
    
    async def _save_state(self) -> bool:
        """
        保存策略状态
        
        Returns:
            bool: 是否成功
        """
        try:
            # 构建要保存的状态
            state = {
                "strategy_id": self.strategy_id,
                "name": self.name,
                "status": self.status,
                "metrics": self.metrics,
                "strategy_data": self.strategy_data,
                "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
                "signals": self.signals,
                "config": self.config,
                "subscribed_symbols": list(self.subscribed_symbols),
                "version": 1  # 状态版本
            }
            
            # 保存状态
            if self.executor and hasattr(self.executor, "save_strategy_state"):
                await self.executor.save_strategy_state(self.strategy_id, state)
                self.logger.info(f"保存策略状态成功")
                return True
            else:
                self.logger.warning("保存策略状态失败: 执行器未提供状态保存功能")
                return False
                
        except Exception as e:
            self.logger.error(f"保存策略状态出错: {str(e)}")
            return False
    
    async def _load_state(self) -> bool:
        """
        加载策略状态
        
        Returns:
            bool: 是否成功
        """
        try:
            # 从执行器加载状态
            if self.executor and hasattr(self.executor, "load_strategy_state"):
                state = await self.executor.load_strategy_state(self.strategy_id)
                
                if not state:
                    self.logger.info("没有找到保存的策略状态")
                    return False
                    
                # 恢复状态
                self.metrics = state.get("metrics", self.metrics)
                self.strategy_data = state.get("strategy_data", {})
                self.signals = state.get("signals", {})
                self.subscribed_symbols = set(state.get("subscribed_symbols", []))
                
                # 其他配置可选择性恢复
                
                self.logger.info(f"加载策略状态成功")
                return True
            else:
                self.logger.warning("加载策略状态失败: 执行器未提供状态加载功能")
                return False
                
        except Exception as e:
            self.logger.error(f"加载策略状态出错: {str(e)}")
            return False
    
    def calc_position_size(self, symbol: str, price: float, risk_amount: float = None) -> float:
        """
        计算头寸大小
        
        Args:
            symbol: 合约代码
            price: 入场价格
            risk_amount: 风险金额 (可选)
            
        Returns:
            float: 头寸大小
        """
        # 根据策略配置的头寸管理方式计算
        sizing_method = self.config.get("position_sizing", "fixed")
        
        if sizing_method == "fixed":
            # 固定头寸
            return self.config.get("position_size", 1)
            
        elif sizing_method == "risk_pct" and risk_amount is not None:
            # 基于风险百分比的头寸
            account_balance = 0
            if self.account_manager:
                account_info = await self.account_manager.get_account_info()
                account_balance = account_info.get("balance", 0)
            
            if account_balance <= 0:
                return self.config.get("position_size", 1)
                
            risk_pct = self.config.get("risk_per_trade", 2.0) / 100.0
            risk_amount = account_balance * risk_pct
            
            # 计算头寸大小
            if risk_amount <= 0 or price <= 0:
                return self.config.get("position_size", 1)
                
            # 简单计算 (假设一手价值为价格*单位)
            contract_value = price * 1  # 这里应该根据合约单位计算
            
            if contract_value <= 0:
                return self.config.get("position_size", 1)
                
            position_size = max(1, int(risk_amount / contract_value))
            return position_size
            
        else:
            # 默认固定头寸
            return self.config.get("position_size", 1)
            
    def get_statistics(self) -> Dict:
        """
        获取策略统计信息
        
        Returns:
            Dict: 统计信息
        """
        # 计算胜率
        win_rate = 0
        if (self.metrics["win_count"] + self.metrics["loss_count"]) > 0:
            win_rate = self.metrics["win_count"] / (self.metrics["win_count"] + self.metrics["loss_count"])
            
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "status": self.status,
            "is_running": self.is_running,
            "last_run": self.last_run_time.isoformat() if self.last_run_time else None,
            "runs": self.metrics["runs"],
            "orders": self.metrics["orders"],
            "trades": self.metrics["trades"],
            "errors": self.metrics["errors"],
            "avg_run_time": self.metrics["avg_run_time"],
            "max_run_time": self.metrics["max_run_time"],
            "subscribed_symbols": list(self.subscribed_symbols),
            "pnl": self.metrics["total_pnl"],
            "win_count": self.metrics["win_count"],
            "loss_count": self.metrics["loss_count"],
            "win_rate": win_rate
        }
    
    async def generate_signal(self, symbol: str, signal_type: str, 
                            price: float, volume: float, 
                            reason: str = "", data: Dict = None) -> Dict:
        """
        生成交易信号
        
        Args:
            symbol: 合约代码
            signal_type: 信号类型 (BUY/SELL/CLOSE)
            price: 信号价格
            volume: 信号数量
            reason: 信号原因
            data: 附加数据
            
        Returns:
            Dict: 信号信息
        """
        # 创建信号
        signal = {
            "id": str(uuid.uuid4()),
            "strategy_id": self.strategy_id,
            "symbol": symbol,
            "type": signal_type,
            "price": price,
            "volume": volume,
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "data": data or {}
        }
        
        # 保存信号
        if symbol not in self.signals:
            self.signals[symbol] = []
            
        self.signals[symbol].append(signal)
        
        # 只保留最近的100个信号
        if len(self.signals[symbol]) > 100:
            self.signals[symbol] = self.signals[symbol][-100:]
            
        # 更新统计信息
        self.metrics["signals"] += 1
        
        # 记录日志
        self.logger.info(f"生成信号: {signal_type} {symbol} 价格={price} 数量={volume} 原因={reason}")
        
        return signal
    
    async def execute_signal(self, signal: Dict) -> Tuple[bool, str, str]:
        """
        执行交易信号
        
        Args:
            signal: 信号信息
            
        Returns:
            Tuple[bool, str, str]: (是否成功, 订单ID, 错误信息)
        """
        if not self.is_running:
            return False, "", "策略未运行"
            
        symbol = signal.get("symbol", "")
        signal_type = signal.get("type", "")
        price = signal.get("price", 0)
        volume = signal.get("volume", 0)
        
        if not symbol or not signal_type or price <= 0 or volume <= 0:
            return False, "", "信号参数无效"
            
        result = (False, "", "未知信号类型")
        
        try:
            # 根据信号类型执行交易
            if signal_type == "BUY":
                result = await self.buy(symbol, price, volume)
            elif signal_type == "SELL":
                result = await self.sell(symbol, price, volume)
            elif signal_type == "CLOSE":
                # 关闭持仓
                position = await self.position_manager.get_position(symbol)
                if position and position.get("volume", 0) > 0:
                    direction = position.get("direction", "")
                    if direction == "LONG":
                        result = await self.sell(symbol, price, position.get("volume", 0), "MARKET", "CLOSE")
                    elif direction == "SHORT":
                        result = await self.buy(symbol, price, position.get("volume", 0), "MARKET", "CLOSE")
            else:
                self.logger.warning(f"未知信号类型: {signal_type}")
                
            return result
                
        except Exception as e:
            self.logger.error(f"执行信号出错: {str(e)}")
            return False, "", f"执行信号出错: {str(e)}"
    
    async def get_market_trend(self, symbol: str, period: str = None, ma_period: int = 20) -> str:
        """
        获取市场趋势
        
        Args:
            symbol: 合约代码
            period: K线周期 (可选，默认使用策略配置的周期)
            ma_period: 均线周期
            
        Returns:
            str: 趋势类型 ("up"/"down"/"sideways")
        """
        # 使用默认周期
        if not period:
            period = self.config["trade_period"]
            
        # 获取K线数据
        klines = await self.get_klines(symbol, period, ma_period * 2)
        
        if klines.empty:
            return "unknown"
            
        # 计算均线
        ma = klines["close"].rolling(ma_period).mean()
        
        if ma.iloc[-1] > ma.iloc[-5] * 1.01:
            return "up"
        elif ma.iloc[-1] < ma.iloc[-5] * 0.99:
            return "down"
        else:
            return "sideways"
    
    async def analyze_volatility(self, symbol: str, period: str = None, atr_period: int = 14) -> float:
        """
        分析市场波动率
        
        Args:
            symbol: 合约代码
            period: K线周期 (可选，默认使用策略配置的周期)
            atr_period: ATR周期
            
        Returns:
            float: 相对波动率 (ATR/价格)
        """
        # 使用默认周期
        if not period:
            period = self.config["trade_period"]
            
        # 获取K线数据
        klines = await self.get_klines(symbol, period, atr_period * 2)
        
        if klines.empty:
            return 0.0
            
        # 计算ATR
        high_low = klines["high"] - klines["low"]
        high_close = (klines["high"] - klines["close"].shift()).abs()
        low_close = (klines["low"] - klines["close"].shift()).abs()
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(atr_period).mean().iloc[-1]
        
        # 计算相对波动率
        current_price = klines["close"].iloc[-1]
        if current_price > 0:
            relative_volatility = atr / current_price
            return relative_volatility
        else:
            return 0.0
    
    def set_parameter(self, param_name: str, value: Any) -> bool:
        """
        设置策略参数
        
        Args:
            param_name: 参数名
            value: 参数值
            
        Returns:
            bool: 是否成功
        """
        if "params" not in self.params:
            self.params["params"] = {}
            
        self.params["params"][param_name] = value
        self.logger.info(f"设置参数: {param_name} = {value}")
        return True
    
    def set_config(self, config_name: str, value: Any) -> bool:
        """
        设置配置参数
        
        Args:
            config_name: 配置名
            value: 配置值
            
        Returns:
            bool: 是否成功
        """
        self.config[config_name] = value
        self.logger.info(f"设置配置: {config_name} = {value}")
        return True
    
    def get_parameter(self, param_name: str, default: Any = None) -> Any:
        """
        获取策略参数
        
        Args:
            param_name: 参数名
            default: 默认值
            
        Returns:
            Any: 参数值
        """
        params = self.params.get("params", {})
        return params.get(param_name, default)
    
    def get_config(self, config_name: str, default: Any = None) -> Any:
        """
        获取配置参数
        
        Args:
            config_name: 配置名
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        return self.config.get(config_name, default)
    
    def log_debug(self, message: str) -> None:
        """
        记录调试日志
        
        Args:
            message: 日志内容
        """
        self.logger.debug(message)
    
    def log_info(self, message: str) -> None:
        """
        记录信息日志
        
        Args:
            message: 日志内容
        """
        self.logger.info(message)
    
    def log_warning(self, message: str) -> None:
        """
        记录警告日志
        
        Args:
            message: 日志内容
        """
        self.logger.warning(message)
    
    def log_error(self, message: str) -> None:
        """
        记录错误日志
        
        Args:
            message: 日志内容
        """
        self.logger.error(message)
        self.metrics["errors"] += 1
    
    def get_current_time(self) -> datetime:
        """
        获取当前时间
        
        Returns:
            datetime: 当前时间
        """
        return datetime.now()
    
    def get_indicator(self, symbol: str, indicator_name: str, index: int = -1) -> float:
        """
        获取技术指标值
        
        Args:
            symbol: 合约代码
            indicator_name: 指标名称
            index: 数据索引，-1表示最新值
            
        Returns:
            float: 指标值
        """
        if symbol not in self.indicators:
            return 0.0
            
        indicators = self.indicators[symbol]
        if indicator_name not in indicators:
            return 0.0
            
        indicator_series = indicators[indicator_name]
        if len(indicator_series) <= 0:
            return 0.0
            
        try:
            return indicator_series.iloc[index]
        except:
            return 0.0
    
    def is_bullish(self, symbol: str) -> bool:
        """
        判断是否看涨
        
        Args:
            symbol: 合约代码
            
        Returns:
            bool: 是否看涨
        """
        # 使用均线判断趋势
        fast_ma = self.get_indicator(symbol, "MA5")
        slow_ma = self.get_indicator(symbol, "MA20")
        
        if fast_ma <= 0 or slow_ma <= 0:
            return False
            
        return fast_ma > slow_ma
    
    def is_bearish(self, symbol: str) -> bool:
        """
        判断是否看跌
        
        Args:
            symbol: 合约代码
            
        Returns:
            bool: 是否看跌
        """
        # 使用均线判断趋势
        fast_ma = self.get_indicator(symbol, "MA5")
        slow_ma = self.get_indicator(symbol, "MA20")
        
        if fast_ma <= 0 or slow_ma <= 0:
            return False
            
        return fast_ma < slow_ma