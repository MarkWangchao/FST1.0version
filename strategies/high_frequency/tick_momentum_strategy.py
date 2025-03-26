#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - Tick动量高频策略

此策略基于Tick数据的短期价格动量进行高频交易。
主要特点：
- 使用Tick级别数据
- 基于短期价格动量和成交量变化
- 使用自适应阈值
- 实现快速进出场
- 包含流动性分析
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import time

from strategies.base_strategy import BaseStrategy

class TickMomentumStrategy(BaseStrategy):
    """
    Tick级别动量策略
    
    基于短期价格变动和成交量突变进行高频交易，
    适用于流动性好、波动性适中的期货品种。
    """
    
    # 策略元数据
    version = 1.0
    author = "FST Team"
    description = "基于Tick数据的高频动量交易策略"
    risk_level = "高"
    required_modules = ["numpy", "pandas"]
    
    def __init__(self, strategy_id: str = None, name: str = None, params: Dict = None):
        """
        初始化策略
        
        Args:
            strategy_id: 策略唯一ID
            name: 策略名称
            params: 策略参数
        """
        # 默认参数
        default_params = {
            "symbols": ["IF2403"],  # 交易的合约
            "tick_window": 20,      # Tick窗口大小
            "momentum_threshold": 0.6,  # 动量阈值
            "volume_threshold": 2.0,    # 成交量阈值(倍数)
            "profit_ticks": 3,      # 止盈跳数
            "loss_ticks": 5,        # 止损跳数
            "max_holding_time": 30, # 最大持仓时间(秒)
            "max_positions": 1,     # 最大持仓数量
            "min_tick_interval": 0.2, # 最小Tick间隔(秒)
            "cooldown_period": 5,   # 交易冷却期(秒)
            "adaptive_threshold": True, # 是否使用自适应阈值
            "use_order_book": True, # 是否使用订单簿数据
            "config": {
                "auto_subscribe": True,
                "run_interval": 0.1,  # 0.1秒运行一次
                "trade_period": "tick"
            }
        }
        
        # 合并默认参数和用户参数
        if params:
            for key, value in default_params.items():
                if key not in params:
                    params[key] = value
                elif key == "config" and "config" in params:
                    for config_key, config_value in default_params["config"].items():
                        if config_key not in params["config"]:
                            params["config"][config_key] = config_value
        else:
            params = default_params
            
        # 调用父类初始化
        super().__init__(strategy_id, name, params)
        
        # 设置交易合约
        self.config["trade_symbols"] = self.params["symbols"]
        
    def _init_custom_data(self):
        """初始化策略自定义数据结构"""
        # Tick数据缓存
        self.tick_cache = {symbol: [] for symbol in self.params["symbols"]}
        
        # 订单簿数据
        self.order_book = {}
        
        # 交易状态
        self.trade_status = {
            "last_trade_time": 0,
            "cooling_down": False,
            "cooling_down_until": 0,
            "positions": {},
            "open_orders": {},
            "position_entry_time": {},
            "adaptive_thresholds": {
                symbol: {
                    "momentum": self.params["momentum_threshold"],
                    "volume": self.params["volume_threshold"]
                } for symbol in self.params["symbols"]
            }
        }
        
        # 性能统计
        self.performance_stats = {
            "tick_processing_time": [],
            "signal_generation_time": [],
            "order_execution_time": []
        }
        
    async def on_start(self):
        """策略启动时执行"""
        self.logger.info(f"Tick动量策略启动: {self.params['symbols']}")
        
        # 初始化订单簿
        for symbol in self.params["symbols"]:
            self.order_book[symbol] = {
                "asks": [],  # [(price, volume), ...]
                "bids": [],  # [(price, volume), ...]
                "last_update": 0
            }
            
        # 初始化自适应阈值
        if self.params["adaptive_threshold"]:
            await self._initialize_adaptive_thresholds()
    
    async def _initialize_adaptive_thresholds(self):
        """初始化自适应阈值"""
        for symbol in self.params["symbols"]:
            try:
                # 获取历史Tick数据
                ticks = await self.data_provider.get_ticks(symbol, 1000)
                if ticks is None or len(ticks) < 100:
                    continue
                    
                # 计算价格变化
                price_changes = np.abs(np.diff(ticks["last_price"]))
                volume_changes = np.abs(np.diff(ticks["volume"]))
                
                # 计算自适应阈值
                momentum_threshold = np.percentile(price_changes, 80)
                volume_threshold = np.percentile(volume_changes, 80) / np.mean(volume_changes)
                
                # 更新阈值
                self.trade_status["adaptive_thresholds"][symbol] = {
                    "momentum": max(momentum_threshold, self.params["momentum_threshold"] * 0.5),
                    "volume": max(volume_threshold, self.params["volume_threshold"] * 0.5)
                }
                
                self.logger.info(f"初始化自适应阈值 - {symbol}: 动量={momentum_threshold:.4f}, 成交量={volume_threshold:.2f}")
                
            except Exception as e:
                self.logger.error(f"初始化自适应阈值失败 - {symbol}: {str(e)}")
    
    async def on_tick(self):
        """每个Tick执行"""
        if not self.is_running:
            return
            
        # 检查是否在冷却期
        if self.trade_status["cooling_down"] and time.time() < self.trade_status["cooling_down_until"]:
            return
        else:
            self.trade_status["cooling_down"] = False
        
        # 处理每个交易合约
        for symbol in self.params["symbols"]:
            await self._process_symbol_tick(symbol)
            
        # 检查持仓时间
        await self._check_holding_time()
    
    async def _process_symbol_tick(self, symbol: str):
        """处理单个合约的Tick数据"""
        start_time = time.time()
        
        try:
            # 获取最新Tick数据
            tick_data = await self.data_provider.get_latest_tick(symbol)
            if tick_data is None:
                return
                
            # 检查Tick间隔
            if self.tick_cache[symbol] and time.time() - self.tick_cache[symbol][-1]["timestamp"] < self.params["min_tick_interval"]:
                return
                
            # 添加时间戳
            tick_data["timestamp"] = time.time()
            
            # 更新Tick缓存
            self.tick_cache[symbol].append(tick_data)
            
            # 保持缓存大小
            if len(self.tick_cache[symbol]) > self.params["tick_window"]:
                self.tick_cache[symbol] = self.tick_cache[symbol][-self.params["tick_window"]:]
            
            # 如果缓存不足，则返回
            if len(self.tick_cache[symbol]) < self.params["tick_window"]:
                return
                
            # 更新订单簿(如果启用)
            if self.params["use_order_book"]:
                await self._update_order_book(symbol)
                
            # 生成交易信号
            signal_start = time.time()
            signal = await self._generate_tick_signal(symbol)
            self.performance_stats["signal_generation_time"].append(time.time() - signal_start)
            
            # 执行信号
            if signal:
                order_start = time.time()
                await self._execute_tick_signal(symbol, signal)
                self.performance_stats["order_execution_time"].append(time.time() - order_start)
                
        except Exception as e:
            self.logger.error(f"处理Tick数据失败 - {symbol}: {str(e)}")
            self.metrics["errors"] += 1
            
        finally:
            # 记录处理时间
            self.performance_stats["tick_processing_time"].append(time.time() - start_time)
    
    async def _update_order_book(self, symbol: str):
        """更新订单簿数据"""
        try:
            # 获取最新订单簿
            order_book = await self.data_provider.get_order_book(symbol)
            if order_book is None:
                return
                
            # 更新订单簿
            self.order_book[symbol] = {
                "asks": order_book.get("asks", [])[:5],  # 只保留前5档
                "bids": order_book.get("bids", [])[:5],  # 只保留前5档
                "last_update": time.time()
            }
            
        except Exception as e:
            self.logger.error(f"更新订单簿失败 - {symbol}: {str(e)}")
    
    async def _generate_tick_signal(self, symbol: str) -> Optional[Dict]:
        """
        基于Tick数据生成交易信号
        
        Args:
            symbol: 合约代码
            
        Returns:
            Optional[Dict]: 交易信号，如果没有信号则返回None
        """
        # 检查是否已有持仓
        if symbol in self.trade_status["positions"] and self.trade_status["positions"][symbol] != 0:
            return None
            
        # 检查是否已达到最大持仓数量
        if len([p for p in self.trade_status["positions"].values() if p != 0]) >= self.params["max_positions"]:
            return None
            
        # 获取Tick缓存
        ticks = self.tick_cache[symbol]
        if not ticks or len(ticks) < self.params["tick_window"]:
            return None
            
        # 提取价格和成交量
        prices = np.array([tick["last_price"] for tick in ticks])
        volumes = np.array([tick["volume"] for tick in ticks])
        
        # 计算价格动量
        price_diff = prices[-1] - prices[0]
        price_std = np.std(prices)
        if price_std == 0:
            return None
            
        momentum = price_diff / price_std
        
        # 计算成交量变化
        volume_ratio = volumes[-1] / np.mean(volumes[:-1]) if np.mean(volumes[:-1]) > 0 else 1.0
        
        # 获取当前阈值
        thresholds = self.trade_status["adaptive_thresholds"][symbol]
        
        # 分析订单簿(如果启用)
        order_book_signal = 0
        if self.params["use_order_book"] and symbol in self.order_book:
            order_book_signal = self._analyze_order_book(symbol)
        
        # 生成信号
        signal = None
        
        # 多头信号
        if (momentum > thresholds["momentum"] and 
            volume_ratio > thresholds["volume"] and
            order_book_signal >= 0):
            
            signal = {
                "type": "buy",
                "symbol": symbol,
                "price": prices[-1],
                "volume": 1,  # 固定为1手
                "reason": f"动量={momentum:.2f}, 成交量比={volume_ratio:.2f}, 订单簿={order_book_signal:.2f}",
                "timestamp": time.time()
            }
            
        # 空头信号
        elif (momentum < -thresholds["momentum"] and 
              volume_ratio > thresholds["volume"] and
              order_book_signal <= 0):
              
            signal = {
                "type": "sell",
                "symbol": symbol,
                "price": prices[-1],
                "volume": 1,  # 固定为1手
                "reason": f"动量={momentum:.2f}, 成交量比={volume_ratio:.2f}, 订单簿={order_book_signal:.2f}",
                "timestamp": time.time()
            }
        
        # 更新自适应阈值
        if self.params["adaptive_threshold"] and len(self.performance_stats["tick_processing_time"]) % 100 == 0:
            await self._update_adaptive_thresholds(symbol)
            
        return signal
    
    def _analyze_order_book(self, symbol: str) -> float:
        """
        分析订单簿数据
        
        Args:
            symbol: 合约代码
            
        Returns:
            float: 订单簿信号，正值表示多头压力，负值表示空头压力
        """
        order_book = self.order_book.get(symbol)
        if not order_book or not order_book["asks"] or not order_book["bids"]:
            return 0
            
        # 计算买卖压力
        ask_volume = sum(volume for _, volume in order_book["asks"])
        bid_volume = sum(volume for _, volume in order_book["bids"])
        
        if ask_volume == 0 or bid_volume == 0:
            return 0
            
        # 计算买卖比率
        volume_ratio = bid_volume / ask_volume
        
        # 计算买卖价差
        spread = order_book["asks"][0][0] - order_book["bids"][0][0]
        
        # 归一化信号
        signal = np.log(volume_ratio) * (1.0 / (1.0 + spread))
        
        return signal
    
    async def _execute_tick_signal(self, symbol: str, signal: Dict) -> bool:
        """
        执行Tick信号
        
        Args:
            symbol: 合约代码
            signal: 交易信号
            
        Returns:
            bool: 是否成功执行
        """
        # 检查冷却期
        if time.time() - self.trade_status["last_trade_time"] < self.params["cooldown_period"]:
            return False
            
        # 获取最新价格
        latest_price = await self.get_latest_price(symbol)
        if latest_price is None:
            return False
            
        # 计算止盈止损价格
        tick_size = 0.2  # 假设最小变动价位为0.2点
        
        if signal["type"] == "buy":
            stop_profit = latest_price + tick_size * self.params["profit_ticks"]
            stop_loss = latest_price - tick_size * self.params["loss_ticks"]
            
            # 执行买入
            success, order_id, msg = await self.buy(
                symbol=symbol,
                price=latest_price,
                volume=signal["volume"],
                order_type="LIMIT"
            )
            
        else:  # sell
            stop_profit = latest_price - tick_size * self.params["profit_ticks"]
            stop_loss = latest_price + tick_size * self.params["loss_ticks"]
            
            # 执行卖出
            success, order_id, msg = await self.sell(
                symbol=symbol,
                price=latest_price,
                volume=signal["volume"],
                order_type="LIMIT"
            )
        
        if success:
            # 记录交易
            self.trade_status["last_trade_time"] = time.time()
            self.trade_status["positions"][symbol] = signal["volume"] if signal["type"] == "buy" else -signal["volume"]
            self.trade_status["open_orders"][order_id] = {
                "symbol": symbol,
                "type": signal["type"],
                "price": latest_price,
                "volume": signal["volume"],
                "stop_profit": stop_profit,
                "stop_loss": stop_loss,
                "timestamp": time.time()
            }
            self.trade_status["position_entry_time"][symbol] = time.time()
            
            # 设置冷却期
            self.trade_status["cooling_down"] = True
            self.trade_status["cooling_down_until"] = time.time() + self.params["cooldown_period"]
            
            self.logger.info(f"执行{signal['type']}信号 - {symbol}: 价格={latest_price}, 数量={signal['volume']}, 原因={signal['reason']}")
            return True
            
        else:
            self.logger.warning(f"执行{signal['type']}信号失败 - {symbol}: {msg}")
            return False
    
    async def _check_holding_time(self):
        """检查持仓时间，超过最大持仓时间则平仓"""
        current_time = time.time()
        
        for symbol, entry_time in list(self.trade_status["position_entry_time"].items()):
            # 检查是否超过最大持仓时间
            if current_time - entry_time > self.params["max_holding_time"]:
                # 平仓
                if symbol in self.trade_status["positions"] and self.trade_status["positions"][symbol] != 0:
                    position = self.trade_status["positions"][symbol]
                    
                    if position > 0:
                        # 平多
                        await self.sell(
                            symbol=symbol,
                            price=await self.get_latest_price(symbol),
                            volume=abs(position),
                            order_type="MARKET",
                            offset="CLOSE"
                        )
                    else:
                        # 平空
                        await self.buy(
                            symbol=symbol,
                            price=await self.get_latest_price(symbol),
                            volume=abs(position),
                            order_type="MARKET",
                            offset="CLOSE"
                        )
                    
                    self.logger.info(f"超过最大持仓时间，平仓 - {symbol}: 持仓时间={current_time - entry_time:.2f}秒")
                    
                    # 清除持仓记录
                    self.trade_status["positions"][symbol] = 0
                    del self.trade_status["position_entry_time"][symbol]
    
    async def on_order_update(self, order: Dict) -> None:
        """
        订单更新回调
        
        Args:
            order: 订单信息
        """
        order_id = order.get("order_id")
        if not order_id or order_id not in self.trade_status["open_orders"]:
            return
            
        status = order.get("status")
        
        # 订单已完成
        if status in ["FINISHED", "FILLED"]:
            self.logger.info(f"订单已完成: {order_id}, 状态: {status}")
            
            # 移除订单记录
            if order_id in self.trade_status["open_orders"]:
                del self.trade_status["open_orders"][order_id]
                
        # 订单已取消或拒绝
        elif status in ["CANCELLED", "REJECTED"]:
            self.logger.warning(f"订单已取消或拒绝: {order_id}, 状态: {status}")
            
            # 清除持仓记录
            order_info = self.trade_status["open_orders"].get(order_id)
            if order_info:
                symbol = order_info["symbol"]
                self.trade_status["positions"][symbol] = 0
                if symbol in self.trade_status["position_entry_time"]:
                    del self.trade_status["position_entry_time"][symbol]
                
            # 移除订单记录
            if order_id in self.trade_status["open_orders"]:
                del self.trade_status["open_orders"][order_id]
    
    async def on_trade(self, trade: Dict) -> None:
        """
        成交回调
        
        Args:
            trade: 成交信息
        """
        symbol = trade.get("symbol")
        if not symbol or symbol not in self.params["symbols"]:
            return
            
        direction = trade.get("direction")
        offset = trade.get("offset")
        price = trade.get("price")
        volume = trade.get("volume")
        
        self.logger.info(f"成交: {symbol}, 方向: {direction}, 开平: {offset}, 价格: {price}, 数量: {volume}")
        
        # 检查止盈止损
        await self._check_stop_conditions(symbol, price)
    
    async def _check_stop_conditions(self, symbol: str, current_price: float):
        """
        检查止盈止损条件
        
        Args:
            symbol: 合约代码
            current_price: 当前价格
        """
        if symbol not in self.trade_status["positions"] or self.trade_status["positions"][symbol] == 0:
            return
            
        position = self.trade_status["positions"][symbol]
        
        # 查找对应的订单
        for order_id, order_info in list(self.trade_status["open_orders"].items()):
            if order_info["symbol"] != symbol:
                continue
                
            stop_profit = order_info["stop_profit"]
            stop_loss = order_info["stop_loss"]
            
            # 检查止盈条件
            if (position > 0 and current_price >= stop_profit) or (position < 0 and current_price <= stop_profit):
                # 平仓
                await self._close_position(symbol, current_price, "止盈")
                return
                
            # 检查止损条件
            if (position > 0 and current_price <= stop_loss) or (position < 0 and current_price >= stop_loss):
                # 平仓
                await self._close_position(symbol, current_price, "止损")
                return
    
    async def _close_position(self, symbol: str, price: float, reason: str):
        """
        平仓
        
        Args:
            symbol: 合约代码
            price: 平仓价格
            reason: 平仓原因
        """
        position = self.trade_status["positions"].get(symbol, 0)
        if position == 0:
            return
            
        if position > 0:
            # 平多
            success, order_id, msg = await self.sell(
                symbol=symbol,
                price=price,
                volume=abs(position),
                order_type="MARKET",
                offset="CLOSE"
            )
        else:
            # 平空
            success, order_id, msg = await self.buy(
                symbol=symbol,
                price=price,
                volume=abs(position),
                order_type="MARKET",
                offset="CLOSE"
            )
            
        if success:
            self.logger.info(f"{reason}平仓 - {symbol}: 价格={price}, 数量={abs(position)}")
            
            # 清除持仓记录
            self.trade_status["positions"][symbol] = 0
            if symbol in self.trade_status["position_entry_time"]:
                del self.trade_status["position_entry_time"][symbol]
                
            # 清除相关订单
            for order_id, order_info in list(self.trade_status["open_orders"].items()):
                if order_info["symbol"] == symbol:
                    del self.trade_status["open_orders"][order_id]
        else:
            self.logger.warning(f"{reason}平仓失败 - {symbol}: {msg}")
    
    async def _update_adaptive_thresholds(self, symbol: str):
        """更新自适应阈值"""
        try:
            # 获取最近的Tick数据
            ticks = self.tick_cache[symbol]
            if not ticks or len(ticks) < self.params["tick_window"]:
                return
                
            # 提取价格和成交量
            prices = np.array([tick["last_price"] for tick in ticks])
            volumes = np.array([tick["volume"] for tick in ticks])
            
            # 计算价格变化
            price_changes = np.abs(np.diff(prices))
            volume_changes = np.abs(np.diff(volumes))
            
            if len(price_changes) < 5 or len(volume_changes) < 5:
                return
                
            # 计算自适应阈值
            momentum_threshold = np.percentile(price_changes, 80)
            volume_threshold = np.percentile(volume_changes, 80) / np.mean(volume_changes) if np.mean(volume_changes) > 0 else 1.0
            
            # 平滑更新阈值
            current_thresholds = self.trade_status["adaptive_thresholds"][symbol]
            current_thresholds["momentum"] = 0.8 * current_thresholds["momentum"] + 0.2 * momentum_threshold
            current_thresholds["volume"] = 0.8 * current_thresholds["volume"] + 0.2 * volume_threshold
            
            # 确保阈值不低于最小值
            current_thresholds["momentum"] = max(current_thresholds["momentum"], self.params["momentum_threshold"] * 0.5)
            current_thresholds["volume"] = max(current_thresholds["volume"], self.params["volume_threshold"] * 0.5)
            
        except Exception as e:
            self.logger.error(f"更新自适应阈值失败 - {symbol}: {str(e)}")
    
    def get_statistics(self) -> Dict:
        """
        获取策略统计信息
        
        Returns:
            Dict: 统计信息
        """
        stats = super().get_statistics()
        
        # 添加高频策略特有的统计信息
        if self.performance_stats["tick_processing_time"]:
            stats["avg_tick_processing_time"] = np.mean(self.performance_stats["tick_processing_time"]) * 1000  # 毫秒
            stats["max_tick_processing_time"] = np.max(self.performance_stats["tick_processing_time"]) * 1000  # 毫秒
            
        if self.performance_stats["signal_generation_time"]:
            stats["avg_signal_generation_time"] = np.mean(self.performance_stats["signal_generation_time"]) * 1000  # 毫秒
            
        if self.performance_stats["order_execution_time"]:
            stats["avg_order_execution_time"] = np.mean(self.performance_stats["order_execution_time"]) * 1000  # 毫秒
        
        # 添加自适应阈值信息
        stats["adaptive_thresholds"] = self.trade_status["adaptive_thresholds"]
        
        return stats