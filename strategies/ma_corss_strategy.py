#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 均线交叉策略

经典的双均线交叉策略，当快速均线上穿慢速均线时做多，
当快速均线下穿慢速均线时做空。

具有以下优化特性：
- 解决了未来函数问题
- 添加滑点和手续费处理
- 改进订单类型和价格设置
- 加强仓位管理和风险控制
- 增强信号过滤条件
- 性能优化与监控
"""

import asyncio
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union, Tuple, Any
from datetime import datetime, timedelta, time
from functools import lru_cache
import traceback
import uuid
import copy

# 尝试导入TA-Lib
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False

from strategies.base_strategy import BaseStrategy

# 策略版本号
__version__ = 1.1

class MACrossStrategy(BaseStrategy):
    """
    均线交叉策略
    
    策略逻辑：
    1. 当短期均线上穿长期均线时，产生买入信号
    2. 当短期均线下穿长期均线时，产生卖出信号
    3. 支持额外的过滤条件，如交易量确认、趋势确认、波动率过滤等
    4. 支持ATR动态止损和资金管理
    """
    
    # 策略元数据
    AUTHOR = "FST开发团队"
    CREATED_AT = "2023-01-01"
    UPDATED_AT = "2023-08-15"
    CATEGORY = "趋势跟踪"
    RISK_LEVEL = "中等"
    SUPPORT_BACKTEST = True
    REQUIRED_MODULES = ["pandas", "numpy"]
    
    # 参数模式定义
    param_schema = {
        "properties": {
            "fast_period": {
                "type": "integer", 
                "minimum": 2, 
                "maximum": 100,
                "default": 5,
                "description": "快速均线周期"
            },
            "slow_period": {
                "type": "integer", 
                "minimum": 5, 
                "maximum": 200,
                "default": 20,
                "description": "慢速均线周期"
            },
            "trend_period": {
                "type": "integer", 
                "minimum": 10, 
                "maximum": 300,
                "default": 50,
                "description": "趋势判断周期"
            },
            "volume_factor": {
                "type": "number", 
                "minimum": 1.0, 
                "maximum": 5.0,
                "default": 1.5,
                "description": "交易量确认因子"
            },
            "atr_period": {
                "type": "integer", 
                "minimum": 5, 
                "maximum": 50,
                "default": 14,
                "description": "ATR计算周期"
            },
            "atr_multiple": {
                "type": "number", 
                "minimum": 1.0, 
                "maximum": 5.0,
                "default": 2.0,
                "description": "ATR止损倍数"
            },
            "risk_per_trade": {
                "type": "number", 
                "minimum": 0.001, 
                "maximum": 0.1,
                "default": 0.02,
                "description": "单笔风险比例"
            },
            "max_positions": {
                "type": "integer", 
                "minimum": 1, 
                "maximum": 10,
                "default": 1,
                "description": "最大持仓数"
            }
        },
        "required": ["fast_period", "slow_period"]
    }
    
    # 默认参数
    default_params = {
        "fast_period": 5,          # 快速均线周期
        "slow_period": 20,         # 慢速均线周期
        "trend_period": 50,        # 趋势判断均线周期
        "volume_factor": 1.5,      # 交易量确认因子
        "atr_period": 14,          # ATR计算周期
        "atr_multiple": 2.0,       # ATR止损倍数
        "slippage_pct": 0.1,       # 滑点百分比(0.1%)
        "commission_rate": 0.0003, # 手续费率(0.03%)
        "risk_per_trade": 0.02,    # 单笔风险比例(2%)
        "max_positions": 1,        # 最大持仓数量
        "use_trend_filter": True,  # 是否使用趋势过滤
        "use_volume_filter": True, # 是否使用交易量过滤
        "use_volatility_filter": True, # 是否使用波动率过滤
        "max_volatility": 0.05,    # 最大波动率阈值(5%)
        "trade_on_close": True,    # 是否在K线收盘时交易
        "enable_stop_loss": True,  # 启用止损
        "enable_take_profit": True, # 启用止盈
        "fixed_stop_loss_pct": 2.0, # 固定止损百分比
        "fixed_take_profit_pct": 4.0, # 固定止盈百分比
        "enable_trailing_stop": False, # 启用追踪止损
        "trailing_stop_activation_pct": 1.0, # 追踪止损激活百分比
        "trailing_stop_distance_pct": 1.5, # 追踪止损距离百分比
        "time_filter_start": "09:30", # 交易时间过滤-开始
        "time_filter_end": "14:55",   # 交易时间过滤-结束
        "filter_consolidation": True, # 过滤盘整区间
        "min_adr_pct": 1.0,          # 最小日内波动率百分比
        "entry_delay_bars": 1,        # 入场延迟K线数
        "exit_delay_bars": 0,         # 出场延迟K线数
        "require_confirmation": True, # 是否需要确认K线
        "max_consecutive_losses": 3,  # 最大连续亏损次数
        "daily_loss_limit_pct": 5.0   # 日内最大亏损限制百分比
    }
    
    def __init__(self, strategy_id: str = None, name: str = None, params: Dict = None, tq_account: Any = None):
        """初始化策略"""
        # 生成策略ID (如果未提供)
        strategy_id = strategy_id or f"mac_{uuid.uuid4().hex[:8]}"
        name = name or "均线交叉策略"
        
        # 调用父类初始化
        super().__init__(strategy_id, name, params)
        
        # 保存天勤账户
        self.tq_account = tq_account
        
        # 策略参数
        params_dict = params.get("params", {}) if params else {}
        
        # 初始化参数(使用默认值作为基础)
        self.strategy_params = copy.deepcopy(self.default_params)
        
        # 更新用户参数
        for key, value in params_dict.items():
            if key in self.strategy_params:
                self.strategy_params[key] = value
        
        # 为了简化代码，将关键参数单独提取出来
        self.fast_period = self.strategy_params["fast_period"]
        self.slow_period = self.strategy_params["slow_period"]
        self.trend_period = self.strategy_params["trend_period"]
        self.volume_factor = self.strategy_params["volume_factor"]
        self.atr_period = self.strategy_params["atr_period"]
        self.atr_multiple = self.strategy_params["atr_multiple"]
        self.slippage_pct = self.strategy_params["slippage_pct"]
        self.commission_rate = self.strategy_params["commission_rate"]
        self.risk_per_trade = self.strategy_params["risk_per_trade"]
        
        # 更新策略配置
        # 更新策略配置
        self.config["trade_period"] = params_dict.get("trade_period", "15m")  # 默认15分钟K线
        self.config["run_interval"] = params_dict.get("run_interval", 60)     # 默认60秒运行一次
        
        # 解析时间过滤器
        try:
            self.time_filter_start = datetime.strptime(self.strategy_params["time_filter_start"], "%H:%M").time()
            self.time_filter_end = datetime.strptime(self.strategy_params["time_filter_end"], "%H:%M").time()
        except ValueError:
            self.logger.warning("时间过滤器格式错误，使用默认值")
            self.time_filter_start = time(9, 30)
            self.time_filter_end = time(14, 55)
        
        # 初始化交易状态
        self._init_trading_state()
        
        # 初始化性能指标
        self.performance_metrics = {
            "wins": 0,
            "losses": 0,
            "total_profit": 0.0,
            "total_loss": 0.0,
            "max_drawdown": 0.0,
            "consecutive_losses": 0,
            "daily_pnl": 0.0,
            "last_update_date": None
        }
        
        # 初始化监控指标
        self.monitor_metrics = {
            "Sharpe Ratio": 0.0,
            "Win Rate": 0.0,
            "Profit Factor": 0.0,
            "Max Drawdown": 0.0,
            "Daily PnL": 0.0
        }
        
        # 日志
        self.logger.info(f"均线交叉策略初始化: ID={strategy_id}, 快速均线={self.fast_period}, 慢速均线={self.slow_period}")
    
    def _init_trading_state(self):
        """
        初始化交易状态
        """
        self.trading_state = {}
        self.indicators = {}
        self.trade_history = []
        self.signal_history = {}
        self.last_bar_processed = {}
        
        # 设置缓存
        self.data_cache = {}
        
        # 当日风控统计
        self._reset_daily_stats()
    
    def _reset_daily_stats(self):
        """重置每日统计数据"""
        today = datetime.now().date()
        
        # 如果日期变更，重置统计
        if self.performance_metrics["last_update_date"] != today:
            self.performance_metrics["daily_pnl"] = 0.0
            self.performance_metrics["last_update_date"] = today
    
    async def on_start(self):
        """
        策略启动时执行
        """
        self.logger.info(f"均线交叉策略 {self.name} (ID: {self.strategy_id}) 开始运行")
        
        # 初始化每个交易品种的状态
        for symbol in self.config.get("trade_symbols", []):
            if symbol not in self.trading_state:
                self.trading_state[symbol] = {
                    "position": 0,        # 1=多头, -1=空头, 0=无仓位
                    "entry_price": 0.0,   # 入场价格
                    "entry_time": None,   # 入场时间
                    "stop_loss": 0.0,     # 止损价格
                    "take_profit": 0.0,   # 止盈价格
                    "trailing_stop": 0.0, # 追踪止损价格
                    "is_trailing_active": False, # 追踪止损是否激活
                    "trade_count": 0,     # 交易次数
                    "consecutive_losses": 0, # 连续亏损次数
                    "last_signal": None,  # 最后一次信号
                    "last_signal_time": None, # 最后一次信号时间
                    "entry_bar_index": 0, # 入场K线索引
                    "delayed_signal": None, # 延迟信号
                    "delayed_bar_count": 0  # 延迟K线计数
                }
        
        # 加载初始数据
        await self._load_initial_data()
    
    async def _load_initial_data(self):
        """加载初始历史数据"""
        for symbol in self.config.get("trade_symbols", []):
            try:
                period = self.config["trade_period"]
                # 获取足够计算指标的历史数据
                bars_needed = max(self.fast_period, self.slow_period, self.trend_period, self.atr_period) * 3
                klines = await self.get_klines(symbol, period, bars_needed)
                
                if klines is not None and not klines.empty:
                    # 计算指标
                    self._calculate_indicators_for_symbol(symbol, klines)
                    self.logger.info(f"已加载 {symbol} 的历史数据: {len(klines)} 根K线")
                else:
                    self.logger.warning(f"无法加载 {symbol} 的历史数据")
            except Exception as e:
                self.logger.error(f"加载 {symbol} 历史数据异常: {str(e)}\n{traceback.format_exc()}")
    
    async def on_stop(self):
        """
        策略停止时执行
        """
        self.logger.info(f"均线交叉策略 {self.name} (ID: {self.strategy_id}) 停止运行")
        
        # 关闭所有持仓
        for symbol, state in self.trading_state.items():
            if state["position"] != 0:
                try:
                    current_price = await self.get_latest_price(symbol)
                    if current_price > 0:
                        position = state["position"]
                        volume = abs(position)  # 持仓数量
                        
                        if position > 0:
                            # 平多仓
                            await self._execute_trade(symbol, "SELL", current_price, "策略停止平仓")
                        elif position < 0:
                            # 平空仓
                            await self._execute_trade(symbol, "BUY", current_price, "策略停止平仓")
                except Exception as e:
                    self.logger.error(f"策略停止平仓异常 {symbol}: {str(e)}")
        
        # 显示策略统计
        self._log_strategy_summary()
    
    def _log_strategy_summary(self):
        """记录策略运行摘要"""
        metrics = self.performance_metrics
        wins = metrics["wins"]
        losses = metrics["losses"]
        total_trades = wins + losses
        
        if total_trades > 0:
            win_rate = wins / total_trades * 100
            
            if metrics["total_loss"] != 0:
                profit_factor = abs(metrics["total_profit"] / metrics["total_loss"]) if metrics["total_loss"] else float('inf')
            else:
                profit_factor = float('inf')
                
            self.logger.info(f"===== 策略运行摘要 =====")
            self.logger.info(f"总交易次数: {total_trades}")
            self.logger.info(f"盈利次数: {wins} ({win_rate:.2f}%)")
            self.logger.info(f"亏损次数: {losses}")
            self.logger.info(f"总盈利: {metrics['total_profit']:.2f}")
            self.logger.info(f"总亏损: {metrics['total_loss']:.2f}")
            self.logger.info(f"盈亏比: {profit_factor:.2f}")
            self.logger.info(f"最大回撤: {metrics['max_drawdown']:.2f}%")
    
    @lru_cache(maxsize=128)
    async def get_klines(self, symbol: str, period: str, length: int) -> pd.DataFrame:
        """
        带缓存的K线数据获取
        
        Args:
            symbol: 交易品种
            period: K线周期
            length: 需要的K线数量
            
        Returns:
            pandas.DataFrame: K线数据
        """
        try:
            return await super().get_klines(symbol, period, length)
        except Exception as e:
            self.logger.error(f"获取K线数据异常: {str(e)}")
            return pd.DataFrame()
    
    async def on_tick(self) -> None:
        """
        每个tick的处理逻辑 - 策略主循环
        """
        # 重置每日统计
        self._reset_daily_stats()
        
        # 并行处理所有交易品种
        tasks = []
        for symbol in self.config.get("trade_symbols", []):
            tasks.append(self._process_symbol(symbol))
        
        if tasks:
            await asyncio.gather(*tasks)
        
        # 更新监控指标
        self._update_monitoring_metrics()
    
    def _update_monitoring_metrics(self):
        """更新监控指标"""
        metrics = self.performance_metrics
        total_trades = metrics["wins"] + metrics["losses"]
        
        # 计算胜率
        if total_trades > 0:
            win_rate = metrics["wins"] / total_trades
            self.monitor_metrics["Win Rate"] = round(win_rate * 100, 2)
        
        # 计算盈亏比
        if metrics["total_loss"] != 0:
            profit_factor = abs(metrics["total_profit"] / metrics["total_loss"]) if metrics["total_loss"] else float('inf')
            self.monitor_metrics["Profit Factor"] = round(profit_factor, 2)
        
        # 更新最大回撤
        self.monitor_metrics["Max Drawdown"] = round(metrics["max_drawdown"], 2)
        
        # 更新日内盈亏
        self.monitor_metrics["Daily PnL"] = round(metrics["daily_pnl"], 2)
        
        # 待计算 Sharpe Ratio (需要历史数据)
        # self.monitor_metrics["Sharpe Ratio"] = ...
    
    async def _process_symbol(self, symbol: str):
        """处理单个交易品种"""
        try:
            # 1. 时间过滤
            if not self._time_filter():
                return
            
            # 2. 获取最新价格
            current_price = await self.get_latest_price(symbol)
            if current_price <= 0:
                self.logger.warning(f"{symbol} 无法获取有效价格")
                return
            
            # 3. 获取K线数据
            period = self.config["trade_period"]
            
            # 计算所需K线数量(至少是最长指标周期的3倍)
            bars_needed = max(self.fast_period, self.slow_period, self.trend_period, self.atr_period) * 3
            klines = await self.get_klines(symbol, period, bars_needed)
            
            if klines is None or klines.empty or len(klines) < bars_needed // 2:
                self.logger.warning(f"{symbol} K线数据不足")
                return
            
            # 4. 计算指标
            self._calculate_indicators_for_symbol(symbol, klines)
            
            # 5. 交易风控检查
            if not await self._pre_trade_check(symbol):
                return
            
            # 6. 获取当前持仓状态
            state = self.trading_state.get(symbol, {"position": 0})
            position = state.get("position", 0)
            
            # 7. 检查止损止盈
            if position != 0:
                await self._check_exit_signals(symbol, klines, current_price)
            
            # 8. 检查入场信号
            if position == 0 or (self.strategy_params["max_positions"] > 1):
                await self._check_entry_signals(symbol, klines, current_price)
            
        except Exception as e:
            self.logger.error(f"处理 {symbol} 异常: {str(e)}\n{traceback.format_exc()}")
    
    def _time_filter(self) -> bool:
        """
        时间过滤器
        
        Returns:
            bool: 是否通过时间过滤
        """
        current_time = datetime.now().time()
        
        # 检查是否在交易时间范围内
        if current_time < self.time_filter_start or current_time > self.time_filter_end:
            return False
        
        return True
    
    async def _pre_trade_check(self, symbol: str) -> bool:
        """
        交易前风控检查
        
        Args:
            symbol: 交易品种
            
        Returns:
            bool: 是否通过检查
        """
        # 检查账户状态
        try:
            account = await self.get_account()
            if not account or account.get("net_value", 0) <= 0:
                self.logger.warning("账户信息无效，跳过交易")
                return False
        except Exception as e:
            self.logger.error(f"获取账户信息异常: {str(e)}")
            return False
        
        # 检查日内亏损限制
        daily_loss_limit = self.strategy_params["daily_loss_limit_pct"] / 100
        if self.performance_metrics["daily_pnl"] < -account.get("net_value", 0) * daily_loss_limit:
            self.logger.warning(f"达到日内亏损限制 ({self.strategy_params['daily_loss_limit_pct']}%)，停止交易")
            return False
        
        # 检查连续亏损次数
        state = self.trading_state.get(symbol, {})
        consecutive_losses = state.get("consecutive_losses", 0)
        if consecutive_losses >= self.strategy_params["max_consecutive_losses"]:
            self.logger.warning(f"{symbol} 连续亏损 {consecutive_losses} 次，暂停交易")
            return False
        
        return True
    
    def _calculate_indicators_for_symbol(self, symbol: str, df: pd.DataFrame) -> None:
        """
        为指定品种计算指标
        
        Args:
            symbol: 交易品种
            df: K线数据
        """
        indicators = {}
        
        # 解决未来函数问题 - 使用前移数据
        close_shift = df["close"].shift(1)
        high_shift = df["high"].shift(1)
        low_shift = df["low"].shift(1)
        
        # 计算均线指标 (使用TA-Lib或者Pandas)
        if HAS_TALIB:
            # 使用TA-Lib计算 (更高效)
            for period in [self.fast_period, self.slow_period, self.trend_period]:
                indicators[f"MA{period}"] = talib.SMA(close_shift, timeperiod=period)
            
            # 计算ATR
            indicators["ATR"] = talib.ATR(high_shift, low_shift, close_shift, timeperiod=self.atr_period)
            
            # 计算波动率
            indicators["Volatility"] = indicators["ATR"] / close_shift * 100
            
            # 额外增加其他指标
            indicators["RSI"] = talib.RSI(close_shift, timeperiod=14)
            
            # 计算布林带
            upper, middle, lower = talib.BBANDS(close_shift, timeperiod=20, nbdevup=2, nbdevdn=2)
            indicators["BB_upper"] = upper
            indicators["BB_middle"] = middle
            indicators["BB_lower"] = lower
            
            # MACD
            macd, macd_signal, macd_hist = talib.MACD(close_shift, fastperiod=12, slowperiod=26, signalperiod=9)
            indicators["MACD"] = macd
            indicators["MACD_signal"] = macd_signal
            indicators["MACD_hist"] = macd_hist
            
        else:
            # 使用Pandas计算 (备选方案)
            for period in [self.fast_period, self.slow_period, self.trend_period]:
                indicators[f"MA{period}"] = close_shift.rolling(period).mean()
            
            # 简单ATR计算
            high_low = high_shift - low_shift
            high_close = abs(high_shift - close_shift.shift(1))
            low_close = abs(low_shift - close_shift.shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            indicators["ATR"] = tr.rolling(self.atr_period).mean()
            
            # 计算波动率
            indicators["Volatility"] = indicators["ATR"] / close_shift * 100
        
        # 计算交易量均线
        indicators["Volume_MA"] = df["volume"].rolling(20).mean()
        
        # 保存指标
        self.indicators[symbol] = indicators
        
        # 更新数据缓存
        for key, value in indicators.items():
            df[key] = value
            
        period = self.config["trade_period"]
        self.data_cache[f"{symbol}_{period}"] = df
    
    async def _check_entry_signals(self, symbol: str, klines: pd.DataFrame, current_price: float) -> None:
        """
        检查入场信号
        
        Args:
            symbol: 交易品种
            klines: K线数据
            current_price: 当前价格
        """
        # 获取已计算的指标
        indicators = self.indicators.get(symbol, {})
        if not indicators:
            return
        
        # 获取交易状态
        state = self.trading_state.get(symbol, {"position": 0})
        position = state.get("position", 0)
        
        # 检查是否已达到最大持仓限制
        position_count = sum(1 for s in self.trading_state.values() if s.get("position", 0) != 0)
        if position_count >= self.strategy_params["max_positions"] and position == 0:
            return
        
        # 获取指标数据
        fast_ma = indicators.get(f"MA{self.fast_period}")
        slow_ma = indicators.get(f"MA{self.slow_period}")
        trend_ma = indicators.get(f"MA{self.trend_period}")
        volume = klines["volume"]
        volume_ma = indicators.get("Volume_MA")
        volatility = indicators.get("Volatility")
        
        if fast_ma is None or slow_ma is None or len(fast_ma) < 2 or len(slow_ma) < 2:
            return
        
        # 计算金叉死叉
        golden_cross = fast_ma.iloc[-2] <= slow_ma.iloc[-2] and fast_ma.iloc[-1] > slow_ma.iloc[-1]
        death_cross = fast_ma.iloc[-2] >= slow_ma.iloc[-2] and fast_ma.iloc[-1] < slow_ma.iloc[-1]
        
        # 信号过滤
        signal = None
        
        # 检查金叉信号 (多头)
        if golden_cross and position <= 0:
            # 趋势过滤
            trend_filter_passed = True
            if self.strategy_params["use_trend_filter"] and trend_ma is not None:
                trend_filter_passed = klines["close"].iloc[-1] > trend_ma.iloc[-1]
            
            # 交易量过滤
            volume_filter_passed = True
            if self.strategy_params["use_volume_filter"] and volume_ma is not None:
                volume_filter_passed = volume.iloc[-1] > volume_ma.iloc[-1] * self.volume_factor
            
            # 波动率过滤
            volatility_filter_passed = True
            if self.strategy_params["use_volatility_filter"] and volatility is not None:
                volatility_filter_passed = volatility.iloc[-1] < self.strategy_params["max_volatility"]
            
            # K线形态确认
            pattern_confirmed = True
            if self.strategy_params["require_confirmation"] and HAS_TALIB:
                engulfing = talib.CDLENGULFING(
                    klines["open"].values, 
                    klines["high"].values, 
                    klines["low"].values, 
                    klines["close"].values
                )
                pattern_confirmed = engulfing[-1] > 0
            
            # 综合过滤条件
            if trend_filter_passed and volume_filter_passed and volatility_filter_passed and pattern_confirmed:
                signal = "BUY"
        
        # 检查死叉信号 (空头)
        elif death_cross and position >= 0:
            # 趋势过滤
            trend_filter_passed = True
            if self.strategy_params["use_trend_filter"] and trend_ma is not None:
                trend_filter_passed = klines["close"].iloc[-1] < trend_ma.iloc[-1]
            
            # 交易量过滤
            volume_filter_passed = True
            if self.strategy_params["use_volume_filter"] and volume_ma is not None:
                volume_filter_passed = volume.iloc[-1] > volume_ma.iloc[-1] * self.volume_factor
            
            # 波动率过滤
            volatility_filter_passed = True
            if self.strategy_params["use_volatility_filter"] and volatility is not None:
                volatility_filter_passed = volatility.iloc[-1] < self.strategy_params["max_volatility"]
            
            # K线形态确认
            pattern_confirmed = True
            if self.strategy_params["require_confirmation"] and HAS_TALIB:
                engulfing = talib.CDLENGULFING(
                    klines["open"].values, 
                    klines["high"].values, 
                    klines["low"].values, 
                    klines["close"].values
                )
                pattern_confirmed = engulfing[-1] < 0
            
            # 综合过滤条件
            if trend_filter_passed and volume_filter_passed and volatility_filter_passed and pattern_confirmed:
                signal = "SELL"
        
        # 处理入场延迟
        if signal:
            entry_delay_bars = self.strategy_params["entry_delay_bars"]
            if entry_delay_bars <= 0:
                # 无延迟，直接执行交易
                await self._execute_trade(symbol, signal, current_price, f"{signal}信号触发")
            else:
                # 设置延迟信号
                state["delayed_signal"] = signal
                state["delayed_bar_count"] = 0
                self.logger.info(f"{symbol} 设置延迟{signal}信号, 等待 {entry_delay_bars} 根K线确认")
                
                # 更新交易状态
                self.trading_state[symbol] = state
        
        # 处理已有的延迟信号
        elif state.get("delayed_signal"):
            delayed_signal = state["delayed_signal"]
            delayed_bar_count = state.get("delayed_bar_count", 0) + 1
            entry_delay_bars = self.strategy_params["entry_delay_bars"]
            
            if delayed_bar_count >= entry_delay_bars:
                # 延迟确认完成，执行交易
                await self._execute_trade(symbol, delayed_signal, current_price, f"延迟{delayed_signal}信号确认")
                
                # 清除延迟信号
                state["delayed_signal"] = None
                state["delayed_bar_count"] = 0
            else:
                # 更新延迟计数
                state["delayed_bar_count"] = delayed_bar_count
                
            # 更新交易状态
            self.trading_state[symbol] = state
    
    async def _check_exit_signals(self, symbol: str, klines: pd.DataFrame, current_price: float) -> None:
        """
        检查出场信号
        
        Args:
            symbol: 交易品种
            klines: K线数据
            current_price: 当前价格
        """
        # 获取交易状态
        state = self.trading_state.get(symbol, {"position": 0})
        position = state.get("position", 0)
        
        # 如果没有持仓，不需要检查出场
        if position == 0:
            return
        
        # 获取止损止盈价格
        entry_price = state.get("entry_price", 0)
        stop_loss = state.get("stop_loss", 0)
        take_profit = state.get("take_profit", 0)
        trailing_stop = state.get("trailing_stop", 0)
        is_trailing_active = state.get("is_trailing_active", False)
        
        # 获取指标
        indicators = self.indicators.get(symbol, {})
        fast_ma = indicators.get(f"MA{self.fast_period}")
        slow_ma = indicators.get(f"MA{self.slow_period}")
        
        # 初始化信号
        exit_signal = None
        exit_reason = ""
        
        # 检查交叉反转信号
        if fast_ma is not None and slow_ma is not None and len(fast_ma) > 1 and len(slow_ma) > 1:
            if position > 0 and fast_ma.iloc[-2] >= slow_ma.iloc[-2] and fast_ma.iloc[-1] < slow_ma.iloc[-1]:
                # 多头持仓，快线下穿慢线，死叉
                exit_signal = "SELL"
                exit_reason = "均线死叉"
            elif position < 0 and fast_ma.iloc[-2] <= slow_ma.iloc[-2] and fast_ma.iloc[-1] > slow_ma.iloc[-1]:
                # 空头持仓，快线上穿慢线，金叉
                exit_signal = "BUY"
                exit_reason = "均线金叉"
        
        # 检查止损信号
        if self.strategy_params["enable_stop_loss"] and stop_loss > 0:
            if position > 0 and current_price <= stop_loss:
                # 多头止损
                exit_signal = "SELL"
                exit_reason = "止损出场"
            elif position < 0 and current_price >= stop_loss:
                # 空头止损
                exit_signal = "BUY"
                exit_reason = "止损出场"
        
        # 检查止盈信号
        if self.strategy_params["enable_take_profit"] and take_profit > 0:
            if position > 0 and current_price >= take_profit:
                # 多头止盈
                exit_signal = "SELL"
                exit_reason = "止盈出场"
            elif position < 0 and current_price <= take_profit:
                # 空头止盈
                exit_signal = "BUY"
                exit_reason = "止盈出场"
        
        # 检查追踪止损
        if self.strategy_params["enable_trailing_stop"]:
            # 检查追踪止损是否激活
            if not is_trailing_active:
                activation_pct = self.strategy_params["trailing_stop_activation_pct"] / 100
                
                if position > 0 and current_price >= entry_price * (1 + activation_pct):
                    # 激活多头追踪止损
                    distance_pct = self.strategy_params["trailing_stop_distance_pct"] / 100
                    trailing_stop = current_price * (1 - distance_pct)
                    state["trailing_stop"] = trailing_stop
                    state["is_trailing_active"] = True
                    self.logger.info(f"{symbol} 激活多头追踪止损: {trailing_stop:.2f}")
                
                elif position < 0 and current_price <= entry_price * (1 - activation_pct):
                    # 激活空头追踪止损
                    distance_pct = self.strategy_params["trailing_stop_distance_pct"] / 100
                    trailing_stop = current_price * (1 + distance_pct)
                    state["trailing_stop"] = trailing_stop
                    state["is_trailing_active"] = True
                    self.logger.info(f"{symbol} 激活空头追踪止损: {trailing_stop:.2f}")
            
            # 检查是否触发追踪止损
            elif trailing_stop > 0:
                if position > 0 and current_price <= trailing_stop:
                    # 多头追踪止损触发
                    exit_signal = "SELL"
                    exit_reason = "追踪止损"
                elif position < 0 and current_price >= trailing_stop:
                    # 空头追踪止损触发
                    exit_signal = "BUY"
                    exit_reason = "追踪止损"
                else:
                    # 更新追踪止损价格
                    distance_pct = self.strategy_params["trailing_stop_distance_pct"] / 100
                    if position > 0:
                        new_trailing_stop = current_price * (1 - distance_pct)
                        if new_trailing_stop > trailing_stop:
                            state["trailing_stop"] = new_trailing_stop
                            self.logger.info(f"{symbol} 更新多头追踪止损: {new_trailing_stop:.2f}")
                    elif position < 0:
                        new_trailing_stop = current_price * (1 + distance_pct)
                        if new_trailing_stop < trailing_stop:
                            state["trailing_stop"] = new_trailing_stop
                            self.logger.info(f"{symbol} 更新空头追踪止损: {new_trailing_stop:.2f}")
        
        # 执行出场交易
        if exit_signal:
            await self._execute_trade(symbol, exit_signal, current_price, exit_reason)
        
        # 更新交易状态
        self.trading_state[symbol] = state
    
    async def _execute_trade(self, symbol: str, signal: str, price: float, reason: str) -> None:
        """
        执行交易
        
        Args:
            symbol: 交易品种
            signal: 信号类型 ("BUY" 或 "SELL")
            price: 交易价格
            reason: 交易原因
        """
        if price <= 0:
            self.logger.error(f"{symbol} 无效交易价格: {price}")
            return
        
        # 获取交易状态
        state = self.trading_state.get(symbol, {"position": 0})
        position = state.get("position", 0)
        
        # 滑点调整
        slippage = price * (self.slippage_pct / 100)
        adjusted_price = price * (1 + slippage) if signal == "BUY" else price * (1 - slippage)
        
        # 计算交易量
        volume = await self.calc_position_size(symbol, adjusted_price)
        if volume <= 0:
            self.logger.warning(f"{symbol} 计算的持仓量为0，取消交易")
            return
        
        # 确定订单类型和价格
        if self.strategy_params["trade_on_close"]:
            order_type = "MARKET"
        else:
            order_type = "LIMIT"
            # 限价单设置价格偏移
            adjusted_price = adjusted_price * 0.998 if signal == "BUY" else adjusted_price * 1.002
        
        # 计算手续费
        commission = volume * adjusted_price * self.commission_rate
        
        success = False
        order_id = ""
        msg = ""
        
        try:
            if signal == "BUY":
                if position < 0:
                    # 平空仓
                    success, order_id, msg = await self.buy(
                        symbol=symbol,
                        price=adjusted_price,
                        volume=volume,
                        order_type=order_type,
                        offset="CLOSE"
                    )
                    if success:
                        # 计算盈亏
                        pnl = (state.get("entry_price", 0) - adjusted_price) * volume - commission
                        
                        # 更新性能指标
                        if pnl > 0:
                            self.performance_metrics["wins"] += 1
                            self.performance_metrics["total_profit"] += pnl
                            state["consecutive_losses"] = 0
                        else:
                            self.performance_metrics["losses"] += 1
                            self.performance_metrics["total_loss"] += abs(pnl)
                            state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
                        
                        # 更新日内盈亏
                        self.performance_metrics["daily_pnl"] += pnl
                        
                        # 重置持仓状态
                        state["position"] = 0
                        state["entry_price"] = 0
                        state["entry_time"] = None
                        state["stop_loss"] = 0
                        state["take_profit"] = 0
                        state["trailing_stop"] = 0
                        state["is_trailing_active"] = False
                        
                        # 记录交易
                        self.trade_history.append({
                            "symbol": symbol,
                            "signal": signal,
                            "price": adjusted_price,
                            "volume": volume,
                            "pnl": pnl,
                            "time": datetime.now(),
                            "reason": reason
                        })
                        
                        self.logger.info(f"{symbol} 平空仓成功，价格={adjusted_price}，数量={volume}，盈亏={pnl:.2f}，原因={reason}")
                else:
                    # 开多仓
                    if position > 0:
                        self.logger.warning(f"{symbol} 已有多头持仓，不重复开仓")
                        return
                        
                    success, order_id, msg = await self.buy(
                        symbol=symbol,
                        price=adjusted_price,
                        volume=volume,
                        order_type=order_type,
                        offset="OPEN"
                    )
                    if success:
                        # 计算止损止盈价格
                        atr = self.indicators.get(symbol, {}).get("ATR", pd.Series([0])).iloc[-1]
                        
                        if self.strategy_params["enable_stop_loss"]:
                            if atr > 0 and HAS_TALIB:
                                # 使用ATR计算止损
                                stop_loss = adjusted_price - self.atr_multiple * atr
                            else:
                                # 使用固定百分比止损
                                stop_loss_pct = self.strategy_params["fixed_stop_loss_pct"] / 100
                                stop_loss = adjusted_price * (1 - stop_loss_pct)
                        else:
                            stop_loss = 0
                        
                        if self.strategy_params["enable_take_profit"]:
                            # 使用固定百分比止盈
                            take_profit_pct = self.strategy_params["fixed_take_profit_pct"] / 100
                            take_profit = adjusted_price * (1 + take_profit_pct)
                        else:
                            take_profit = 0
                        
                        # 更新持仓状态
                        # 更新持仓状态
                        state["position"] = 1
                        state["entry_price"] = adjusted_price
                        state["entry_time"] = datetime.now()
                        state["stop_loss"] = stop_loss
                        state["take_profit"] = take_profit
                        state["trailing_stop"] = stop_loss
                        state["is_trailing_active"] = False
                        state["trade_count"] += 1
                        state["entry_bar_index"] = len(self.data_cache.get(f"{symbol}_{self.config['trade_period']}", pd.DataFrame())) - 1
                        
                        self.logger.info(f"{symbol} 开多仓成功，价格={adjusted_price}，数量={volume}，止损={stop_loss:.2f}，止盈={take_profit:.2f}，原因={reason}")
            elif signal == "SELL":
                if position > 0:
                    # 平多仓
                    success, order_id, msg = await self.sell(
                        symbol=symbol,
                        price=adjusted_price,
                        volume=volume,
                        order_type=order_type,
                        offset="CLOSE"
                    )
                    if success:
                        # 计算盈亏
                        pnl = (adjusted_price - state.get("entry_price", 0)) * volume - commission
                        
                        # 更新性能指标
                        if pnl > 0:
                            self.performance_metrics["wins"] += 1
                            self.performance_metrics["total_profit"] += pnl
                            state["consecutive_losses"] = 0
                        else:
                            self.performance_metrics["losses"] += 1
                            self.performance_metrics["total_loss"] += abs(pnl)
                            state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
                        
                        # 更新日内盈亏
                        self.performance_metrics["daily_pnl"] += pnl
                        
                        # 重置持仓状态
                        state["position"] = 0
                        state["entry_price"] = 0
                        state["entry_time"] = None
                        state["stop_loss"] = 0
                        state["take_profit"] = 0
                        state["trailing_stop"] = 0
                        state["is_trailing_active"] = False
                        
                        # 记录交易
                        self.trade_history.append({
                            "symbol": symbol,
                            "signal": signal,
                            "price": adjusted_price,
                            "volume": volume,
                            "pnl": pnl,
                            "time": datetime.now(),
                            "reason": reason
                        })
                        
                        self.logger.info(f"{symbol} 平多仓成功，价格={adjusted_price}，数量={volume}，盈亏={pnl:.2f}，原因={reason}")
                else:
                    # 开空仓
                    if position < 0:
                        self.logger.warning(f"{symbol} 已有空头持仓，不重复开仓")
                        return
                        
                    success, order_id, msg = await self.sell(
                        symbol=symbol,
                        price=adjusted_price,
                        volume=volume,
                        order_type=order_type,
                        offset="OPEN"
                    )
                    if success:
                        # 计算止损止盈价格
                        atr = self.indicators.get(symbol, {}).get("ATR", pd.Series([0])).iloc[-1]
                        
                        if self.strategy_params["enable_stop_loss"]:
                            if atr > 0 and HAS_TALIB:
                                # 使用ATR计算止损
                                stop_loss = adjusted_price + self.atr_multiple * atr
                            else:
                                # 使用固定百分比止损
                                stop_loss_pct = self.strategy_params["fixed_stop_loss_pct"] / 100
                                stop_loss = adjusted_price * (1 + stop_loss_pct)
                        else:
                            stop_loss = 0
                        
                        if self.strategy_params["enable_take_profit"]:
                            # 使用固定百分比止盈
                            take_profit_pct = self.strategy_params["fixed_take_profit_pct"] / 100
                            take_profit = adjusted_price * (1 - take_profit_pct)
                        else:
                            take_profit = 0
                        
                        # 更新持仓状态
                        state["position"] = -1
                        state["entry_price"] = adjusted_price
                        state["entry_time"] = datetime.now()
                        state["stop_loss"] = stop_loss
                        state["take_profit"] = take_profit
                        state["trailing_stop"] = stop_loss
                        state["is_trailing_active"] = False
                        state["trade_count"] += 1
                        state["entry_bar_index"] = len(self.data_cache.get(f"{symbol}_{self.config['trade_period']}", pd.DataFrame())) - 1
                        
                        self.logger.info(f"{symbol} 开空仓成功，价格={adjusted_price}，数量={volume}，止损={stop_loss:.2f}，止盈={take_profit:.2f}，原因={reason}")
        except Exception as e:
            success = False
            msg = f"执行交易异常: {str(e)}"
            self.logger.error(f"{symbol} {msg}\n{traceback.format_exc()}")
        
        # 更新交易状态
        self.trading_state[symbol] = state
        
        # 更新监控指标
        self._update_monitor_metrics()
        
        return success, order_id, msg
    
    def _update_trailing_stop(self, symbol: str, current_price: float) -> bool:
        """
        更新追踪止损
        
        Args:
            symbol: 交易品种
            current_price: 当前价格
            
        Returns:
            bool: 是否触发止损
        """
        if symbol not in self.trading_state:
            return False
            
        state = self.trading_state[symbol]
        position = state.get("position", 0)
        if position == 0:
            return False
            
        if not self.strategy_params["enable_trailing_stop"]:
            return False
            
        # 获取参数
        activation_pct = self.strategy_params["trailing_stop_activation_pct"] / 100
        distance_pct = self.strategy_params["trailing_stop_distance_pct"] / 100
        
        # 多头追踪止损逻辑
        if position > 0:
            entry_price = state.get("entry_price", 0)
            
            # 检查是否达到激活条件
            if not state.get("is_trailing_active", False):
                if current_price >= entry_price * (1 + activation_pct):
                    state["is_trailing_active"] = True
                    state["trailing_stop"] = current_price * (1 - distance_pct)
                    self.logger.info(f"{symbol} 多头追踪止损已激活，触发价格={current_price:.2f}，追踪止损={state['trailing_stop']:.2f}")
            else:
                # 更新追踪止损价格
                new_stop = current_price * (1 - distance_pct)
                if new_stop > state.get("trailing_stop", 0):
                    state["trailing_stop"] = new_stop
                    self.logger.info(f"{symbol} 多头追踪止损更新: {state['trailing_stop']:.2f}")
                    
                # 检查是否触发追踪止损
                if current_price <= state.get("trailing_stop", 0):
                    self.logger.info(f"{symbol} 多头触发追踪止损: 当前价格={current_price:.2f}, 止损价格={state['trailing_stop']:.2f}")
                    return True
        
        # 空头追踪止损逻辑
        elif position < 0:
            entry_price = state.get("entry_price", 0)
            
            # 检查是否达到激活条件
            if not state.get("is_trailing_active", False):
                if current_price <= entry_price * (1 - activation_pct):
                    state["is_trailing_active"] = True
                    state["trailing_stop"] = current_price * (1 + distance_pct)
                    self.logger.info(f"{symbol} 空头追踪止损已激活，触发价格={current_price:.2f}，追踪止损={state['trailing_stop']:.2f}")
            else:
                # 更新追踪止损价格
                new_stop = current_price * (1 + distance_pct)
                if new_stop < state.get("trailing_stop", float('inf')):
                    state["trailing_stop"] = new_stop
                    self.logger.info(f"{symbol} 空头追踪止损更新: {state['trailing_stop']:.2f}")
                    
                # 检查是否触发追踪止损
                if current_price >= state.get("trailing_stop", float('inf')):
                    self.logger.info(f"{symbol} 空头触发追踪止损: 当前价格={current_price:.2f}, 止损价格={state['trailing_stop']:.2f}")
                    return True
        
        self.trading_state[symbol] = state
        return False
    
    def _check_stop_take_profit(self, symbol: str, current_price: float) -> Tuple[bool, str]:
        """
        检查止损止盈
        
        Args:
            symbol: 交易品种
            current_price: 当前价格
            
        Returns:
            Tuple[bool, str]: (是否触发, 触发原因)
        """
        if symbol not in self.trading_state:
            return False, ""
            
        state = self.trading_state[symbol]
        position = state.get("position", 0)
        if position == 0:
            return False, ""
            
        # 多头止损止盈检查
        if position > 0:
            # 止损检查
            if self.strategy_params["enable_stop_loss"]:
                stop_loss = state.get("stop_loss", 0)
                if stop_loss > 0 and current_price <= stop_loss:
                    return True, "止损"
            
            # 止盈检查
            if self.strategy_params["enable_take_profit"]:
                take_profit = state.get("take_profit", 0)
                if take_profit > 0 and current_price >= take_profit:
                    return True, "止盈"
        
        # 空头止损止盈检查
        elif position < 0:
            # 止损检查
            if self.strategy_params["enable_stop_loss"]:
                stop_loss = state.get("stop_loss", 0)
                if stop_loss > 0 and current_price >= stop_loss:
                    return True, "止损"
            
            # 止盈检查
            if self.strategy_params["enable_take_profit"]:
                take_profit = state.get("take_profit", 0)
                if take_profit > 0 and current_price <= take_profit:
                    return True, "止盈"
        
        # 追踪止损检查
        if self.strategy_params["enable_trailing_stop"]:
            if self._update_trailing_stop(symbol, current_price):
                return True, "追踪止损"
                
        return False, ""
    
    def _calculate_indicators_for_symbol(self, symbol: str, df: pd.DataFrame) -> None:
        """
        为指定品种计算指标
        
        Args:
            symbol: 交易品种
            df: K线数据
        """
        if df.empty:
            self.logger.warning(f"{symbol} 计算指标失败: 数据为空")
            return
            
        indicators = {}
        
        # 使用shift(1)避免未来函数问题
        close_shift = df["close"].shift(1)
        
        # 计算三个均线
        if HAS_TALIB:
            # 使用TA-Lib计算
            for period in [self.fast_period, self.slow_period, self.trend_period]:
                indicators[f"MA{period}"] = talib.SMA(close_shift, timeperiod=period)
                
            # 计算ATR
            indicators["ATR"] = talib.ATR(df["high"], df["low"], close_shift, timeperiod=self.atr_period)
            
            # 添加波动率指标
            indicators["Volatility"] = talib.STDDEV(close_shift, timeperiod=20) / close_shift
        else:
            # 使用pandas计算
            for period in [self.fast_period, self.slow_period, self.trend_period]:
                indicators[f"MA{period}"] = close_shift.rolling(period).mean()
            
            # 简单波动率计算
            indicators["Volatility"] = close_shift.rolling(20).std() / close_shift
            
            # 简易ATR计算
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - close_shift).abs()
            low_close = (df["low"] - close_shift).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            indicators["ATR"] = tr.rolling(self.atr_period).mean()
        
        # 计算交易量相关指标
        if "volume" in df.columns:
            # 交易量均线
            indicators["Volume_MA20"] = df["volume"].rolling(20).mean()
            # 相对交易量
            indicators["Relative_Volume"] = df["volume"] / indicators["Volume_MA20"]
        
        # 检测均线交叉信号
        if f"MA{self.fast_period}" in indicators and f"MA{self.slow_period}" in indicators:
            # 金叉：快线从下方穿过慢线
            golden_cross = (indicators[f"MA{self.fast_period}"].shift(1) < indicators[f"MA{self.slow_period}"].shift(1)) & \
                           (indicators[f"MA{self.fast_period}"] > indicators[f"MA{self.slow_period}"])
            
            # 死叉：快线从上方穿过慢线
            death_cross = (indicators[f"MA{self.fast_period}"].shift(1) > indicators[f"MA{self.slow_period}"].shift(1)) & \
                          (indicators[f"MA{self.fast_period}"] < indicators[f"MA{self.slow_period}"])
            
            indicators["Golden_Cross"] = golden_cross.astype(int)
            indicators["Death_Cross"] = death_cross.astype(int)
        
        # 保存指标
        self.indicators[symbol] = indicators
        
        # 更新数据缓存
        for key, value in indicators.items():
            df[key] = value
            
        period = self.config["trade_period"]
        self.data_cache[f"{symbol}_{period}"] = df
        
        self.logger.debug(f"{symbol} 计算指标完成，可用指标: {list(indicators.keys())}")
    
    def _update_monitor_metrics(self):
        """更新监控指标"""
        total_trades = self.performance_metrics["wins"] + self.performance_metrics["losses"]
        
        # 防止除零错误
        if total_trades > 0:
            win_rate = self.performance_metrics["wins"] / total_trades
            self.monitor_metrics["Win Rate"] = win_rate
        
        if self.performance_metrics["total_loss"] > 0:
            profit_factor = self.performance_metrics["total_profit"] / self.performance_metrics["total_loss"]
            self.monitor_metrics["Profit Factor"] = profit_factor
        
        # 更新日内盈亏
        self.monitor_metrics["Daily PnL"] = self.performance_metrics["daily_pnl"]
    
    async def on_stop(self):
        """策略停止时执行"""
        self.logger.info(f"均线交叉策略 {self.name} (ID: {self.strategy_id}) 停止运行")
        
        # 平掉所有持仓
        for symbol, state in self.trading_state.items():
            position = state.get("position", 0)
            if position != 0:
                try:
                    # 获取当前价格
                    current_price = await self.get_latest_price(symbol)
                    
                    # 根据持仓方向平仓
                    if position > 0:
                        await self._execute_trade(symbol, "SELL", current_price, "策略停止平仓")
                    elif position < 0:
                        await self._execute_trade(symbol, "BUY", current_price, "策略停止平仓")
                except Exception as e:
                    self.logger.error(f"策略停止平仓异常: {str(e)}")
        
        # 输出性能总结
        self._print_performance_summary()
    
    def _print_performance_summary(self):
        """输出性能总结"""
        total_trades = self.performance_metrics["wins"] + self.performance_metrics["losses"]
        if total_trades == 0:
            self.logger.info("策略未产生任何交易")
            return
            
        win_rate = self.performance_metrics["wins"] / total_trades
        net_profit = self.performance_metrics["total_profit"] - self.performance_metrics["total_loss"]
        
        summary = f"""
        ======== 策略性能总结 =========
        策略名称: {self.name} (ID: {self.strategy_id})
        总交易次数: {total_trades}
        胜率: {win_rate:.2%}
        盈利总额: {self.performance_metrics["total_profit"]:.2f}
        亏损总额: {self.performance_metrics["total_loss"]:.2f}
        净利润: {net_profit:.2f}
        利润因子: {self.monitor_metrics.get("Profit Factor", 0):.2f}
        最大回撤: {self.monitor_metrics.get("Max Drawdown", 0):.2%}
        ==============================
        """
        self.logger.info(summary)
    
    def get_indicator(self, symbol: str, indicator_name: str) -> Optional[pd.Series]:
        """
        获取特定指标数据
        
        Args:
            symbol: 交易品种
            indicator_name: 指标名称
            
        Returns:
            pd.Series: 指标数据，如果不存在则返回None
        """
        if symbol not in self.indicators:
            return None
            
        return self.indicators[symbol].get(indicator_name, None)
    
    @lru_cache(maxsize=32)
    def get_contract_size(self, symbol: str) -> float:
        """
        获取合约乘数
        
        Args:
            symbol: 交易品种
            
        Returns:
            float: 合约乘数
        """
        # 默认合约乘数，实际应从交易所或broker获取
        return 1.0
    
    def get_daily_pnl(self) -> float:
        """
        获取当日盈亏
        
        Returns:
            float: 当日盈亏
        """
        return self.performance_metrics.get("daily_pnl", 0.0)