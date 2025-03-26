#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 多周期趋势跟踪策略

此策略基于多个时间周期的趋势分析和动量确认进行交易。
主要特点：
- 多周期趋势判断
- 趋势强度评估
- 动量确认
- 自适应止损
- 仓位管理
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import talib
import time

from strategies.base_strategy import BaseStrategy

class TrendFollowingStrategy(BaseStrategy):
    """
    多周期趋势跟踪策略
    
    使用多个时间周期的趋势分析和动量确认来捕捉市场趋势。
    适用于具有明显趋势特征的期货品种。
    """
    
    # 策略元数据
    version = 1.0
    author = "FST Team"
    description = "基于多周期趋势分析的趋势跟踪策略"
    risk_level = "中等"
    required_modules = ["numpy", "pandas", "talib"]
    
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
            "timeframes": {         # 多周期设置
                "fast": "15m",      # 快周期
                "medium": "1h",     # 中周期
                "slow": "4h"        # 慢周期
            },
            "ma_periods": {         # 移动平均周期
                "fast": 20,
                "medium": 40,
                "slow": 60
            },
            "atr_period": 14,      # ATR周期
            "rsi_period": 14,      # RSI周期
            "macd_params": {       # MACD参数
                "fast": 12,
                "slow": 26,
                "signal": 9
            },
            "trend_threshold": 25,  # 趋势确认阈值
            "momentum_threshold": 55, # 动量确认阈值
            "position_sizing": {    # 仓位管理参数
                "max_positions": 3,  # 最大持仓数
                "risk_per_trade": 0.02,  # 每笔交易风险
                "max_risk_multiplier": 2.0  # 最大风险倍数
            },
            "stop_loss": {         # 止损设置
                "atr_multiplier": 2.0,  # ATR倍数
                "max_loss": 0.03    # 最大止损比例
            },
            "take_profit": {       # 止盈设置
                "target_multiplier": 1.5,  # 目标收益倍数
                "trailing_stop": True  # 是否启用追踪止损
            },
            "filters": {           # 过滤器
                "min_volatility": 0.01,  # 最小波动率
                "max_spread": 0.002,   # 最大价差
                "min_volume": 1000     # 最小成交量
            },
            "config": {
                "auto_subscribe": True,
                "run_interval": 60,  # 60秒运行一次
                "trade_period": "tick"
            }
        }
        
        # 合并默认参数和用户参数
        if params:
            for key, value in default_params.items():
                if key not in params:
                    params[key] = value
                elif isinstance(value, dict) and key in params:
                    for sub_key, sub_value in value.items():
                        if sub_key not in params[key]:
                            params[key][sub_key] = sub_value
        else:
            params = default_params
            
        # 调用父类初始化
        super().__init__(strategy_id, name, params)
        
        # 设置交易合约
        self.config["trade_symbols"] = self.params["symbols"]
        
    def _init_custom_data(self):
        """初始化策略自定义数据结构"""
        # 行情数据缓存
        self.market_data = {
            symbol: {
                tf: pd.DataFrame() for tf in self.params["timeframes"].values()
            } for symbol in self.params["symbols"]
        }
        
        # 技术指标数据
        self.indicators = {
            symbol: {
                tf: {} for tf in self.params["timeframes"].values()
            } for symbol in self.params["symbols"]
        }
        
        # 趋势状态
        self.trend_status = {
            symbol: {
                "direction": 0,  # 1: 上涨, -1: 下跌, 0: 震荡
                "strength": 0,   # 趋势强度 0-100
                "duration": 0,   # 趋势持续时间
                "last_update": 0 # 最后更新时间
            } for symbol in self.params["symbols"]
        }
        
        # 交易状态
        self.trade_status = {
            "positions": {},      # 当前持仓
            "open_orders": {},    # 未完成订单
            "stop_loss_prices": {},  # 止损价格
            "take_profit_prices": {}, # 止盈价格
            "risk_metrics": {}    # 风险指标
        }
        
    async def on_start(self):
        """策略启动时执行"""
        self.logger.info(f"趋势跟踪策略启动: {self.params['symbols']}")
        
        # 初始化数据
        for symbol in self.params["symbols"]:
            await self._initialize_market_data(symbol)
            
    async def _initialize_market_data(self, symbol: str):
        """初始化市场数据"""
        try:
            # 获取各个周期的历史数据
            for tf_name, tf in self.params["timeframes"].items():
                # 获取K线数据
                klines = await self.data_provider.get_klines(
                    symbol=symbol,
                    interval=tf,
                    limit=100  # 获取足够多的历史数据用于指标计算
                )
                
                if klines is not None and len(klines) > 0:
                    # 转换为DataFrame
                    df = pd.DataFrame(klines)
                    self.market_data[symbol][tf] = df
                    
                    # 计算技术指标
                    await self._calculate_indicators(symbol, tf)
                    
            # 初始化趋势状态
            await self._update_trend_status(symbol)
                    
        except Exception as e:
            self.logger.error(f"初始化市场数据失败 - {symbol}: {str(e)}")
            
    async def _calculate_indicators(self, symbol: str, timeframe: str):
        """计算技术指标"""
        try:
            df = self.market_data[symbol][timeframe]
            if len(df) < 60:  # 确保有足够的数据
                return
                
            # 计算移动平均线
            ma_period = self.params["ma_periods"][timeframe]
            df["ma"] = talib.MA(df["close"].values, timeperiod=ma_period)
            
            # 计算MACD
            macd, signal, hist = talib.MACD(
                df["close"].values,
                fastperiod=self.params["macd_params"]["fast"],
                slowperiod=self.params["macd_params"]["slow"],
                signalperiod=self.params["macd_params"]["signal"]
            )
            df["macd"] = macd
            df["macd_signal"] = signal
            df["macd_hist"] = hist
            
            # 计算RSI
            df["rsi"] = talib.RSI(df["close"].values, timeperiod=self.params["rsi_period"])
            
            # 计算ATR
            df["atr"] = talib.ATR(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                timeperiod=self.params["atr_period"]
            )
            
            # 更新指标数据
            self.indicators[symbol][timeframe] = {
                "ma": df["ma"].values[-1],
                "macd": df["macd"].values[-1],
                "macd_signal": df["macd_signal"].values[-1],
                "macd_hist": df["macd_hist"].values[-1],
                "rsi": df["rsi"].values[-1],
                "atr": df["atr"].values[-1]
            }
            
        except Exception as e:
            self.logger.error(f"计算技术指标失败 - {symbol} {timeframe}: {str(e)}")
            
    async def _update_trend_status(self, symbol: str):
        """更新趋势状态"""
        try:
            # 获取各周期的指标数据
            fast_indicators = self.indicators[symbol][self.params["timeframes"]["fast"]]
            medium_indicators = self.indicators[symbol][self.params["timeframes"]["medium"]]
            slow_indicators = self.indicators[symbol][self.params["timeframes"]["slow"]]
            
            if not all([fast_indicators, medium_indicators, slow_indicators]):
                return
                
            # 计算趋势方向
            trend_scores = []
            
            # 快周期趋势
            if fast_indicators["ma"] > 0:
                fast_trend = 1 if fast_indicators["close"] > fast_indicators["ma"] else -1
                trend_scores.append(fast_trend)
            
            # 中周期趋势
            if medium_indicators["ma"] > 0:
                medium_trend = 1 if medium_indicators["close"] > medium_indicators["ma"] else -1
                trend_scores.append(medium_trend * 1.5)  # 中周期权重更大
            
            # 慢周期趋势
            if slow_indicators["ma"] > 0:
                slow_trend = 1 if slow_indicators["close"] > slow_indicators["ma"] else -1
                trend_scores.append(slow_trend * 2)  # 慢周期权重最大
            
            # 计算综合趋势方向
            trend_direction = np.sign(np.mean(trend_scores)) if trend_scores else 0
            
            # 计算趋势强度
            strength_factors = []
            
            # RSI趋势强度
            rsi_strength = (fast_indicators["rsi"] - 50) / 50
            strength_factors.append(abs(rsi_strength))
            
            # MACD趋势强度
            macd_strength = fast_indicators["macd_hist"] / fast_indicators["atr"]
            strength_factors.append(abs(macd_strength))
            
            # 计算综合趋势强度 (0-100)
            trend_strength = min(100, np.mean(strength_factors) * 100)
            
            # 更新趋势状态
            current_time = time.time()
            if self.trend_status[symbol]["direction"] == trend_direction:
                self.trend_status[symbol]["duration"] += current_time - self.trend_status[symbol]["last_update"]
            else:
                self.trend_status[symbol]["duration"] = 0
            
            self.trend_status[symbol].update({
                "direction": trend_direction,
                "strength": trend_strength,
                "last_update": current_time
            })
            
        except Exception as e:
            self.logger.error(f"更新趋势状态失败 - {symbol}: {str(e)}")
            
    async def on_bar(self, bar: Dict):
        """
        K线更新回调
        
        Args:
            bar: K线数据
        """
        symbol = bar.get("symbol")
        if not symbol or symbol not in self.params["symbols"]:
            return
            
        timeframe = bar.get("interval")
        if not timeframe or timeframe not in self.params["timeframes"].values():
            return
            
        try:
            # 更新市场数据
            df = self.market_data[symbol][timeframe]
            df = df.append(bar, ignore_index=True)
            
            # 保持固定长度
            if len(df) > 100:
                df = df.iloc[-100:]
            
            self.market_data[symbol][timeframe] = df
            
            # 更新技术指标
            await self._calculate_indicators(symbol, timeframe)
            
            # 更新趋势状态
            await self._update_trend_status(symbol)
            
            # 生成交易信号
            await self._generate_trading_signals(symbol)
            
            # 更新止损止盈
            await self._update_stop_levels(symbol)
            
        except Exception as e:
            self.logger.error(f"处理K线数据失败 - {symbol} {timeframe}: {str(e)}")
            
    async def _generate_trading_signals(self, symbol: str):
        """生成交易信号"""
        try:
            # 检查趋势状态
            trend = self.trend_status[symbol]
            if abs(trend["strength"]) < self.params["trend_threshold"]:
                return
                
            # 获取快周期指标
            fast_indicators = self.indicators[symbol][self.params["timeframes"]["fast"]]
            
            # 检查动量确认
            rsi = fast_indicators["rsi"]
            if trend["direction"] > 0 and rsi < self.params["momentum_threshold"]:
                return
            if trend["direction"] < 0 and rsi > (100 - self.params["momentum_threshold"]):
                return
                
            # 检查过滤条件
            if not self._check_filters(symbol):
                return
                
            # 检查是否已有持仓
            current_position = self.trade_status["positions"].get(symbol, 0)
            
            # 计算目标仓位
            target_position = self._calculate_position_size(symbol)
            
            if target_position == 0:
                return
                
            # 生成交易信号
            if trend["direction"] > 0 and current_position <= 0:
                # 做多信号
                await self._open_long_position(symbol, target_position)
                
            elif trend["direction"] < 0 and current_position >= 0:
                # 做空信号
                await self._open_short_position(symbol, target_position)
                
        except Exception as e:
            self.logger.error(f"生成交易信号失败 - {symbol}: {str(e)}")
            
    def _check_filters(self, symbol: str) -> bool:
        """检查过滤条件"""
        try:
            # 获取快周期数据
            df = self.market_data[symbol][self.params["timeframes"]["fast"]]
            if len(df) < 20:
                return False
                
            # 计算波动率
            volatility = df["close"].pct_change().std()
            if volatility < self.params["filters"]["min_volatility"]:
                return False
                
            # 检查价差
            spread = (df["high"].iloc[-1] - df["low"].iloc[-1]) / df["close"].iloc[-1]
            if spread > self.params["filters"]["max_spread"]:
                return False
                
            # 检查成交量
            if df["volume"].iloc[-1] < self.params["filters"]["min_volume"]:
                return False
                
            return True
            
        except Exception:
            return False
            
    def _calculate_position_size(self, symbol: str) -> int:
        """计算仓位大小"""
        try:
            # 检查是否达到最大持仓数
            current_positions = len([p for p in self.trade_status["positions"].values() if p != 0])
            if current_positions >= self.params["position_sizing"]["max_positions"]:
                return 0
                
            # 获取账户信息
            account_info = self.get_account_info()
            if not account_info:
                return 0
                
            equity = account_info.get("equity", 0)
            
            # 获取合约信息
            contract_info = self.get_contract_info(symbol)
            if not contract_info:
                return 0
                
            # 计算每手保证金
            margin_per_lot = contract_info.get("margin_per_lot", 0)
            if margin_per_lot <= 0:
                return 0
                
            # 计算风险金额
            risk_amount = equity * self.params["position_sizing"]["risk_per_trade"]
            
            # 获取ATR
            atr = self.indicators[symbol][self.params["timeframes"]["fast"]]["atr"]
            
            # 计算每手风险
            risk_per_lot = atr * self.params["stop_loss"]["atr_multiplier"]
            
            # 计算目标仓位
            target_position = int(risk_amount / risk_per_lot)
            
            # 限制最大仓位
            max_position = int(equity * self.params["position_sizing"]["max_risk_multiplier"] / margin_per_lot)
            target_position = min(target_position, max_position)
            
            return max(1, target_position)  # 至少开仓1手
            
        except Exception as e:
            self.logger.error(f"计算仓位大小失败 - {symbol}: {str(e)}")
            return 0
            
    async def _open_long_position(self, symbol: str, volume: int):
        """开多仓"""
        try:
            # 获取最新价格
            latest_price = await self.get_latest_price(symbol)
            if not latest_price:
                return
                
            # 计算止损价格
            atr = self.indicators[symbol][self.params["timeframes"]["fast"]]["atr"]
            stop_loss = latest_price - atr * self.params["stop_loss"]["atr_multiplier"]
            
            # 计算止盈价格
            take_profit = latest_price + atr * self.params["stop_loss"]["atr_multiplier"] * self.params["take_profit"]["target_multiplier"]
            
            # 执行买入
            success, order_id, msg = await self.buy(
                symbol=symbol,
                price=latest_price,
                volume=volume,
                order_type="LIMIT"
            )
            
            if success:
                # 记录交易状态
                self.trade_status["positions"][symbol] = volume
                self.trade_status["stop_loss_prices"][symbol] = stop_loss
                self.trade_status["take_profit_prices"][symbol] = take_profit
                self.trade_status["open_orders"][order_id] = {
                    "symbol": symbol,
                    "type": "buy",
                    "price": latest_price,
                    "volume": volume,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit
                }
                
                self.logger.info(f"开多仓 - {symbol}: 价格={latest_price}, 数量={volume}, 止损={stop_loss}, 止盈={take_profit}")
            else:
                self.logger.warning(f"开多仓失败 - {symbol}: {msg}")
                
        except Exception as e:
            self.logger.error(f"开多仓失败 - {symbol}: {str(e)}")
            
    async def _open_short_position(self, symbol: str, volume: int):
        """开空仓"""
        try:
            # 获取最新价格
            latest_price = await self.get_latest_price(symbol)
            if not latest_price:
                return
                
            # 计算止损价格
            atr = self.indicators[symbol][self.params["timeframes"]["fast"]]["atr"]
            stop_loss = latest_price + atr * self.params["stop_loss"]["atr_multiplier"]
            
            # 计算止盈价格
            take_profit = latest_price - atr * self.params["stop_loss"]["atr_multiplier"] * self.params["take_profit"]["target_multiplier"]
            
            # 执行卖出
            success, order_id, msg = await self.sell(
                symbol=symbol,
                price=latest_price,
                volume=volume,
                order_type="LIMIT"
            )
            
            if success:
                # 记录交易状态
                self.trade_status["positions"][symbol] = -volume
                self.trade_status["stop_loss_prices"][symbol] = stop_loss
                self.trade_status["take_profit_prices"][symbol] = take_profit
                self.trade_status["open_orders"][order_id] = {
                    "symbol": symbol,
                    "type": "sell",
                    "price": latest_price,
                    "volume": volume,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit
                }
                
                self.logger.info(f"开空仓 - {symbol}: 价格={latest_price}, 数量={volume}, 止损={stop_loss}, 止盈={take_profit}")
            else:
                self.logger.warning(f"开空仓失败 - {symbol}: {msg}")
                
        except Exception as e:
            self.logger.error(f"开空仓失败 - {symbol}: {str(e)}")
            
    async def _update_stop_levels(self, symbol: str):
        """更新止损止盈价格"""
        try:
            position = self.trade_status["positions"].get(symbol, 0)
            if position == 0:
                return
                
            latest_price = await self.get_latest_price(symbol)
            if not latest_price:
                return
                
            # 获取当前止损止盈价格
            current_stop = self.trade_status["stop_loss_prices"].get(symbol)
            current_take_profit = self.trade_status["take_profit_prices"].get(symbol)
            
            if not current_stop or not current_take_profit:
                return
                
            # 更新追踪止损
            if self.params["take_profit"]["trailing_stop"]:
                atr = self.indicators[symbol][self.params["timeframes"]["fast"]]["atr"]
                
                if position > 0:  # 多仓
                    new_stop = latest_price - atr * self.params["stop_loss"]["atr_multiplier"]
                    if new_stop > current_stop:
                        self.trade_status["stop_loss_prices"][symbol] = new_stop
                        self.logger.info(f"更新多仓追踪止损 - {symbol}: {new_stop}")
                        
                else:  # 空仓
                    new_stop = latest_price + atr * self.params["stop_loss"]["atr_multiplier"]
                    if new_stop < current_stop:
                        self.trade_status["stop_loss_prices"][symbol] = new_stop
                        self.logger.info(f"更新空仓追踪止损 - {symbol}: {new_stop}")
                        
        except Exception as e:
            self.logger.error(f"更新止损止盈失败 - {symbol}: {str(e)}")
            
    async def on_order_update(self, order: Dict):
        """订单更新回调"""
        order_id = order.get("order_id")
        if not order_id or order_id not in self.trade_status["open_orders"]:
            return
            
        status = order.get("status")
        
        # 订单完成
        if status in ["FINISHED", "FILLED"]:
            self.logger.info(f"订单完成: {order_id}")
            
            # 移除订单记录
            if order_id in self.trade_status["open_orders"]:
                del self.trade_status["open_orders"][order_id]
                
        # 订单取消或拒绝
        elif status in ["CANCELLED", "REJECTED"]:
            self.logger.warning(f"订单取消或拒绝: {order_id}")
            
            # 清除相关状态
            order_info = self.trade_status["open_orders"].get(order_id)
            if order_info:
                symbol = order_info["symbol"]
                self.trade_status["positions"][symbol] = 0
                if symbol in self.trade_status["stop_loss_prices"]:
                    del self.trade_status["stop_loss_prices"][symbol]
                if symbol in self.trade_status["take_profit_prices"]:
                    del self.trade_status["take_profit_prices"][symbol]
                
            # 移除订单记录
            if order_id in self.trade_status["open_orders"]:
                del self.trade_status["open_orders"][order_id]
                
    async def on_trade(self, trade: Dict):
        """成交回调"""
        symbol = trade.get("symbol")
        if not symbol or symbol not in self.params["symbols"]:
            return
            
        # 获取最新价格
        latest_price = await self.get_latest_price(symbol)
        if not latest_price:
            return
            
        # 检查止损止盈
        position = self.trade_status["positions"].get(symbol, 0)
        if position == 0:
            return
            
        stop_loss = self.trade_status["stop_loss_prices"].get(symbol)
        take_profit = self.trade_status["take_profit_prices"].get(symbol)
        
        if not stop_loss or not take_profit:
            return
            
        # 检查是否触发止损
        if (position > 0 and latest_price <= stop_loss) or (position < 0 and latest_price >= stop_loss):
            await self._close_position(symbol, "止损")
            return
            
        # 检查是否触发止盈
        if (position > 0 and latest_price >= take_profit) or (position < 0 and latest_price <= take_profit):
            await self._close_position(symbol, "止盈")
            return
            
    async def _close_position(self, symbol: str, reason: str):
        """平仓"""
        try:
            position = self.trade_status["positions"].get(symbol, 0)
            if position == 0:
                return
                
            # 获取最新价格
            latest_price = await self.get_latest_price(symbol)
            if not latest_price:
                return
                
            if position > 0:
                # 平多仓
                success, order_id, msg = await self.sell(
                    symbol=symbol,
                    price=latest_price,
                    volume=abs(position),
                    order_type="MARKET",
                    offset="CLOSE"
                )
            else:
                # 平空仓
                success, order_id, msg = await self.buy(
                    symbol=symbol,
                    price=latest_price,
                    volume=abs(position),
                    order_type="MARKET",
                    offset="CLOSE"
                )
                
            if success:
                self.logger.info(f"{reason}平仓 - {symbol}: 价格={latest_price}, 数量={abs(position)}")
                
                # 清除交易状态
                self.trade_status["positions"][symbol] = 0
                if symbol in self.trade_status["stop_loss_prices"]:
                    del self.trade_status["stop_loss_prices"][symbol]
                if symbol in self.trade_status["take_profit_prices"]:
                    del self.trade_status["take_profit_prices"][symbol]
            else:
                self.logger.warning(f"{reason}平仓失败 - {symbol}: {msg}")
                
        except Exception as e:
            self.logger.error(f"平仓失败 - {symbol}: {str(e)}")
            
    def get_statistics(self) -> Dict:
        """获取策略统计信息"""
        stats = super().get_statistics()
        
        # 添加趋势策略特有的统计信息
        stats.update({
            "trend_status": self.trend_status,
            "current_positions": self.trade_status["positions"],
            "stop_levels": {
                symbol: {
                    "stop_loss": self.trade_status["stop_loss_prices"].get(symbol),
                    "take_profit": self.trade_status["take_profit_prices"].get(symbol)
                } for symbol in self.params["symbols"]
            }
        })
        
        return stats