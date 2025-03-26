#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 仓位管理器

此模块负责管理交易持仓，提供持仓跟踪、风险控制和统计功能。
特性包括：
- 实时持仓跟踪
- 多维度风险计算
- 智能仓位管理
- 持仓历史记录
- 灵活的风控规则
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

from infrastructure.api.broker_adapter import BrokerAdapter, ConnectionState

class PositionSide:
    """持仓方向枚举"""
    LONG = "LONG"    # 多头
    SHORT = "SHORT"  # 空头
    BOTH = "BOTH"    # 双向持仓

class PositionManager:
    """
    仓位管理器，负责管理交易持仓、风险控制和统计功能
    """
    
    def __init__(self, broker_adapter: BrokerAdapter, 
                 account_manager: Any,
                 order_manager: Any,
                 risk_limits: Optional[Dict] = None,
                 auto_update_interval: float = 5.0):
        """
        初始化仓位管理器
        
        Args:
            broker_adapter: 券商适配器
            account_manager: 账户管理器
            order_manager: 订单管理器
            risk_limits: 风险控制参数，包括:
                - max_position_size: 最大单一持仓量
                - max_total_position: 最大总持仓量
                - max_position_value: 最大持仓价值
                - max_concentration: 最大集中度 (占比)
                - max_leverage: 最大杠杆率
            auto_update_interval: 自动更新持仓信息的间隔(秒)
        """
        self.logger = logging.getLogger("fst.core.trading.position_manager")
        self.broker_adapter = broker_adapter
        self.account_manager = account_manager
        self.order_manager = order_manager
        
        # 设置默认风险控制参数
        self.risk_limits = {
            "max_position_size": {},    # 按合约设置最大持仓量
            "max_total_position": 0,    # 最大总持仓量 (0表示无限制)
            "max_position_value": 0,    # 最大持仓价值 (0表示无限制)
            "max_concentration": 0.3,   # 最大集中度 (30%)
            "max_leverage": 5.0,        # 最大杠杆率 (5倍)
            "stop_loss_threshold": 0.1, # 止损阈值 (10%)
            "value_at_risk_limit": 0.05 # 风险价值限制 (5%)
        }
        
        # 更新用户提供的风险参数
        if risk_limits:
            self.risk_limits.update(risk_limits)
        
        # 持仓数据
        self._positions = {}  # 所有持仓
        self._positions_by_symbol = defaultdict(dict)  # 按合约分组的持仓
        self._positions_by_strategy = defaultdict(dict)  # 按策略分组的持仓
        
        # 持仓历史
        self._position_history = defaultdict(lambda: deque(maxlen=100))
        self._closed_positions = deque(maxlen=500)  # 已平仓的持仓
        
        # 统计数据
        self._position_stats = {
            "total_long_value": 0,    # 多头总价值
            "total_short_value": 0,   # 空头总价值
            "total_net_value": 0,     # 净头寸价值
            "total_absolute_value": 0, # 总头寸价值(绝对值)
            "max_single_value": 0,    # 最大单一持仓价值
            "max_concentration": 0,   # 最大集中度
            "leverage_ratio": 0,      # 杠杆率
            "value_at_risk": 0        # 风险价值(VaR)
        }
        
        # 锁
        self._position_lock = asyncio.Lock()
        
        # 监听器
        self._position_listeners = []  # 持仓变动监听器
        self._risk_listeners = []      # 风险监听器
        
        # 自动更新任务
        self._auto_update_interval = auto_update_interval
        self._auto_update_task = None
        self._running = False
        
        # 风险控制状态
        self._risk_breaches = {}
        
        # 添加订单成交监听
        self.order_manager.add_trade_listener(self._on_trade)
        
        # 添加连接状态监听
        self.broker_adapter.add_connection_listener(self._on_connection_state_change)
        
        self.logger.info("仓位管理器初始化完成")
    
    async def start(self) -> bool:
        """
        启动仓位管理器
        
        Returns:
            bool: 启动是否成功
        """
        self.logger.info("启动仓位管理器")
        
        # 检查适配器连接状态
        if not self.broker_adapter.is_connected:
            self.logger.error("券商适配器未连接，仓位管理器无法启动")
            return False
        
        # 加载现有持仓
        try:
            await self._load_positions()
            
            # 启动自动更新任务
            self._running = True
            self._auto_update_task = asyncio.create_task(self._auto_update())
            
            return True
            
        except Exception as e:
            self.logger.error(f"启动仓位管理器失败: {str(e)}")
            return False
    
    async def stop(self) -> None:
        """停止仓位管理器"""
        self.logger.info("停止仓位管理器")
        
        self._running = False
        
        # 取消自动更新任务
        if self._auto_update_task and not self._auto_update_task.done():
            self._auto_update_task.cancel()
            try:
                await self._auto_update_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("仓位管理器已停止")
    
    async def _on_connection_state_change(self, old_state: str, new_state: str) -> None:
        """
        连接状态变化处理
        
        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        self.logger.info(f"检测到券商适配器连接状态变化: {old_state} -> {new_state}")
        
        if new_state == ConnectionState.CONNECTED.name and old_state != ConnectionState.CONNECTED.name:
            # 连接恢复，重新加载持仓
            if self._running:
                self.logger.info("连接恢复，重新加载持仓")
                asyncio.create_task(self._load_positions())
    
    async def _on_trade(self, trade: Dict) -> None:
        """
        处理成交回调
        
        Args:
            trade: 成交信息
        """
        self.logger.info(f"收到成交回调: {trade}")
        
        # 提取成交信息
        order_id = trade.get('order_id', '')
        symbol = trade.get('symbol', '')
        direction = trade.get('direction', '')
        offset = trade.get('offset', '')
        price = trade.get('price', 0)
        volume = trade.get('volume', 0)
        
        if not symbol or not direction or not offset or price <= 0 or volume <= 0:
            self.logger.warning(f"成交信息不完整: {trade}")
            return
        
        # 获取订单信息以提取策略ID
        order = await self.order_manager.get_order(order_id)
        strategy_id = order.get('strategy_id', '') if order else ''
        
        # 更新持仓
        try:
            await self._update_position_on_trade(
                symbol=symbol,
                strategy_id=strategy_id,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume
            )
        except Exception as e:
            self.logger.error(f"处理成交更新持仓失败: {str(e)}")
    
    async def _update_position_on_trade(self, symbol: str, strategy_id: str,
                                      direction: str, offset: str,
                                      price: float, volume: float) -> None:
        """
        基于成交更新持仓
        
        Args:
            symbol: 合约代码
            strategy_id: 策略ID
            direction: 方向 (BUY/SELL)
            offset: 开平标志 (OPEN/CLOSE)
            price: 成交价格
            volume: 成交数量
        """
        # 确定持仓方向
        position_side = PositionSide.LONG if direction == "BUY" else PositionSide.SHORT
        
        async with self._position_lock:
            # 获取合约持仓
            if symbol not in self._positions_by_symbol:
                self._positions_by_symbol[symbol] = {
                    PositionSide.LONG: None,
                    PositionSide.SHORT: None
                }
            
            # 获取策略持仓
            if strategy_id and strategy_id not in self._positions_by_strategy:
                self._positions_by_strategy[strategy_id] = {}
            
            # 处理开仓
            if offset == "OPEN":
                # 获取现有持仓
                current_position = self._positions_by_symbol[symbol][position_side]
                
                if current_position:
                    # 更新现有持仓
                    new_volume = current_position['volume'] + volume
                    new_cost = (current_position['cost'] * current_position['volume'] + price * volume) / new_volume
                    
                    current_position['volume'] = new_volume
                    current_position['cost'] = new_cost
                    current_position['last_price'] = price
                    current_position['update_time'] = time.time()
                    
                    # 记录交易
                    current_position['trades'].append({
                        'time': time.time(),
                        'price': price,
                        'volume': volume,
                        'direction': direction,
                        'offset': offset
                    })
                    
                    self.logger.info(f"更新{position_side}持仓: {symbol}, 数量={new_volume}, 成本={new_cost:.2f}")
                    
                else:
                    # 创建新持仓
                    position_id = str(uuid.uuid4())
                    
                    new_position = {
                        'id': position_id,
                        'symbol': symbol,
                        'strategy_id': strategy_id,
                        'side': position_side,
                        'volume': volume,
                        'cost': price,
                        'open_price': price,
                        'last_price': price,
                        'floating_profit': 0,
                        'realized_profit': 0,
                        'open_time': time.time(),
                        'update_time': time.time(),
                        'trades': [{
                            'time': time.time(),
                            'price': price,
                            'volume': volume,
                            'direction': direction,
                            'offset': offset
                        }]
                    }
                    
                    # 添加到持仓集合
                    self._positions_by_symbol[symbol][position_side] = new_position
                    self._positions[position_id] = new_position
                    
                    # 如果有策略ID，添加到策略持仓
                    if strategy_id:
                        position_key = f"{symbol}_{position_side}"
                        self._positions_by_strategy[strategy_id][position_key] = new_position
                    
                    self.logger.info(f"新建{position_side}持仓: {symbol}, 数量={volume}, 价格={price:.2f}")
            
            # 处理平仓
            elif offset in ["CLOSE", "CLOSETODAY", "CLOSEYESTERDAY"]:
                # 对手方向
                counter_side = PositionSide.SHORT if direction == "BUY" else PositionSide.LONG
                
                # 获取要平仓的持仓
                position = self._positions_by_symbol[symbol][counter_side]
                
                if not position:
                    self.logger.warning(f"平仓失败: 没有{counter_side}持仓 {symbol}")
                    return
                
                # 检查持仓量
                if position['volume'] < volume:
                    self.logger.warning(f"平仓数量 {volume} 大于持仓数量 {position['volume']}")
                    # 仍然处理实际持仓量
                    actual_volume = position['volume']
                else:
                    actual_volume = volume
                
                # 计算已实现盈亏
                if counter_side == PositionSide.LONG:
                    # 平多仓 (卖出)
                    realized_profit = (price - position['cost']) * actual_volume
                else:
                    # 平空仓 (买入)
                    realized_profit = (position['cost'] - price) * actual_volume
                
                # 更新持仓
                position['realized_profit'] += realized_profit
                position['volume'] -= actual_volume
                position['last_price'] = price
                position['update_time'] = time.time()
                
                # 记录交易
                position['trades'].append({
                    'time': time.time(),
                    'price': price,
                    'volume': actual_volume,
                    'direction': direction,
                    'offset': offset,
                    'profit': realized_profit
                })
                
                self.logger.info(
                    f"平仓{counter_side}持仓: {symbol}, 数量={actual_volume}, "
                    f"价格={price:.2f}, 盈亏={realized_profit:.2f}"
                )
                
                # 如果持仓量为0，关闭持仓
                if position['volume'] <= 0:
                    # 计算总盈亏
                    total_profit = position['realized_profit']
                    holding_time = time.time() - position['open_time']
                    
                    # 添加到已关闭持仓集合
                    closed_position = copy.deepcopy(position)
                    closed_position['close_time'] = time.time()
                    closed_position['close_price'] = price
                    closed_position['holding_time'] = holding_time
                    closed_position['total_profit'] = total_profit
                    
                    self._closed_positions.append(closed_position)
                    
                    # 从持仓集合中删除
                    position_id = position['id']
                    self._positions_by_symbol[symbol][counter_side] = None
                    
                    if position_id in self._positions:
                        del self._positions[position_id]
                    
                    # 如果有策略ID，从策略持仓中删除
                    strategy_id = position.get('strategy_id')
                    if strategy_id and strategy_id in self._positions_by_strategy:
                        position_key = f"{symbol}_{counter_side}"
                        if position_key in self._positions_by_strategy[strategy_id]:
                            del self._positions_by_strategy[strategy_id][position_key]
                    
                    self.logger.info(
                        f"关闭{counter_side}持仓: {symbol}, 持仓时间={holding_time:.2f}秒, "
                        f"总盈亏={total_profit:.2f}"
                    )
        
        # 更新持仓统计
        await self._update_position_statistics()
        
        # 通知持仓监听器
        await self._notify_position_listeners()
        
        # 进行风险检查
        await self._check_risk_limits()
    
    async def _load_positions(self) -> None:
        """加载持仓数据"""
        self.logger.info("开始加载持仓数据")
        
        try:
            # 获取持仓信息
            positions = await self.broker_adapter.get_positions()
            
            if not positions:
                self.logger.info("没有查询到持仓数据")
                return
            
            # 清空现有持仓
            async with self._position_lock:
                self._positions.clear()
                self._positions_by_symbol.clear()
                self._positions_by_strategy.clear()
                
                # 处理持仓数据
                for position in positions:
                    symbol = position.get('symbol', '')
                    side_str = position.get('side', '')
                    
                    if not symbol or not side_str:
                        continue
                    
                    # 确定持仓方向
                    side = (
                        PositionSide.LONG 
                        if side_str in ['LONG', 'BUY'] 
                        else PositionSide.SHORT
                    )
                    
                    # 生成唯一ID
                    position_id = position.get('id', str(uuid.uuid4()))
                    
                    # 标准化持仓数据
                    std_position = {
                        'id': position_id,
                        'symbol': symbol,
                        'strategy_id': position.get('strategy_id', ''),
                        'side': side,
                        'volume': position.get('volume', 0),
                        'cost': position.get('cost', 0),
                        'open_price': position.get('open_price', 0),
                        'last_price': position.get('last_price', 0),
                        'floating_profit': position.get('floating_profit', 0),
                        'realized_profit': position.get('realized_profit', 0),
                        'open_time': position.get('open_time', time.time()),
                        'update_time': time.time(),
                        'trades': position.get('trades', [])
                    }
                    
                    # 添加到集合
                    self._positions[position_id] = std_position
                    
                    # 初始化合约持仓字典
                    if symbol not in self._positions_by_symbol:
                        self._positions_by_symbol[symbol] = {
                            PositionSide.LONG: None,
                            PositionSide.SHORT: None
                        }
                    
                    # 添加到合约持仓字典
                    self._positions_by_symbol[symbol][side] = std_position
                    
                    # 如果有策略ID，添加到策略持仓字典
                    strategy_id = std_position.get('strategy_id')
                    if strategy_id:
                        if strategy_id not in self._positions_by_strategy:
                            self._positions_by_strategy[strategy_id] = {}
                        
                        position_key = f"{symbol}_{side}"
                        self._positions_by_strategy[strategy_id][position_key] = std_position
            
            self.logger.info(f"加载了 {len(self._positions)} 个持仓")
            
            # 更新持仓统计
            await self._update_position_statistics()
            
            # 通知持仓监听器
            await self._notify_position_listeners()
            
        except Exception as e:
            self.logger.error(f"加载持仓数据失败: {str(e)}")
            raise
    
    async def _auto_update(self) -> None:
        """自动更新持仓的后台任务"""
        self.logger.info(f"启动持仓自动更新任务，间隔 {self._auto_update_interval} 秒")
        
        while self._running:
            try:
                # 更新持仓价格和浮动盈亏
                await self._update_position_prices()
                
                # 更新持仓统计
                await self._update_position_statistics()
                
                # 进行风险检查
                await self._check_risk_limits()
                
                # 等待下一次更新
                await asyncio.sleep(self._auto_update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"持仓自动更新出错: {str(e)}")
                await asyncio.sleep(self._auto_update_interval)
        
        self.logger.info("持仓自动更新任务已停止")
    
    async def _update_position_prices(self) -> None:
        """更新持仓价格和浮动盈亏"""
        # 获取所有有持仓的合约
        symbols = list(self._positions_by_symbol.keys())
        if not symbols:
            return
        
        # 批量获取行情
        try:
            market_data = {}
            for symbol in symbols:
                # 获取行情
                quote = await self.broker_adapter.get_market_data(symbol)
                if quote and 'last_price' in quote:
                    market_data[symbol] = quote
            
            # 更新持仓
            async with self._position_lock:
                for symbol, quote in market_data.items():
                    last_price = quote.get('last_price', 0)
                    if last_price <= 0:
                        continue
                    
                    # 更新持仓价格
                    for side in [PositionSide.LONG, PositionSide.SHORT]:
                        position = self._positions_by_symbol[symbol].get(side)
                        if position and position['volume'] > 0:
                            old_price = position['last_price']
                            position['last_price'] = last_price
                            
                            # 计算浮动盈亏
                            if side == PositionSide.LONG:
                                position['floating_profit'] = (last_price - position['cost']) * position['volume']
                            else:
                                position['floating_profit'] = (position['cost'] - last_price) * position['volume']
                            
                            position['update_time'] = time.time()
                            
                            # 如果价格变化较大，记录到历史
                            if abs(last_price - old_price) / old_price > 0.001:  # 价格变化超过0.1%
                                self._position_history[position['id']].append({
                                    'time': time.time(),
                                    'price': last_price,
                                    'floating_profit': position['floating_profit']
                                })
            
            # 通知持仓监听器
            await self._notify_position_listeners()
            
        except Exception as e:
            self.logger.error(f"更新持仓价格失败: {str(e)}")
    
    async def _update_position_statistics(self) -> None:
        """更新持仓统计数据"""
        async with self._position_lock:
            # 重置统计数据
            stats = {
                "total_long_value": 0,  # 多头总价值
                "total_short_value": 0, # 空头总价值
                "total_net_value": 0,   # 净头寸价值
                "total_absolute_value": 0, # 总头寸价值(绝对值)
                "max_single_value": 0,  # 最大单一持仓价值
                "max_concentration": 0, # 最大集中度
                "leverage_ratio": 0,    # 杠杆率
                "value_at_risk": 0      # 风险价值(VaR)
            }
            
            # 计算持仓价值
            position_values = {}
            
            for position_id, position in self._positions.items():
                if position['volume'] <= 0:
                    continue
                
                # 计算持仓价值
                position_value = position['last_price'] * position['volume']
                position_values[position_id] = position_value
                
                # 累计总价值
                if position['side'] == PositionSide.LONG:
                    stats["total_long_value"] += position_value
                else:
                    stats["total_short_value"] += position_value
                
                # 更新最大单一持仓价值
                stats["max_single_value"] = max(stats["max_single_value"], position_value)
            
            # 计算总价值
            stats["total_absolute_value"] = stats["total_long_value"] + stats["total_short_value"]
            stats["total_net_value"] = stats["total_long_value"] - stats["total_short_value"]
            
            # 计算最大集中度
            if stats["total_absolute_value"] > 0:
                stats["max_concentration"] = stats["max_single_value"] / stats["total_absolute_value"]
            
            # 计算杠杆率
            account_info = await self.account_manager.get_account_info()
            account_balance = account_info.get('balance', 0)
            
            if account_balance > 0:
                stats["leverage_ratio"] = stats["total_absolute_value"] / account_balance
            
            # 简化的VaR计算 (假设正态分布，95%置信度)
            # 实际生产系统应使用更复杂的VaR模型
            if account_balance > 0:
                # 假设组合波动率为10% (实际应从市场数据计算)
                portfolio_volatility = 0.1
                stats["value_at_risk"] = 1.65 * portfolio_volatility * stats["total_net_value"]
                stats["value_at_risk_ratio"] = stats["value_at_risk"] / account_balance
            
            # 更新统计数据
            self._position_stats = stats
    
    async def _check_risk_limits(self) -> None:
        """检查风险限制"""
        # 获取持仓统计
        stats = self._position_stats
        risk_breaches = {}
        
        # 检查杠杆率
        max_leverage = self.risk_limits["max_leverage"]
        if max_leverage > 0 and stats["leverage_ratio"] > max_leverage:
            risk_breaches["leverage"] = {
                "limit": max_leverage,
                "current": stats["leverage_ratio"],
                "breach_ratio": stats["leverage_ratio"] / max_leverage
            }
        
        # 检查最大集中度
        max_concentration = self.risk_limits["max_concentration"]
        if max_concentration > 0 and stats["max_concentration"] > max_concentration:
            risk_breaches["concentration"] = {
                "limit": max_concentration,
                "current": stats["max_concentration"],
                "breach_ratio": stats["max_concentration"] / max_concentration
            }
        
        # 检查最大持仓价值
        max_position_value = self.risk_limits["max_position_value"]
        if max_position_value > 0 and stats["total_absolute_value"] > max_position_value:
            risk_breaches["position_value"] = {
                "limit": max_position_value,
                "current": stats["total_absolute_value"],
                "breach_ratio": stats["total_absolute_value"] / max_position_value
            }
        
        # 检查风险价值比率
        var_limit = self.risk_limits["value_at_risk_limit"]
        if var_limit > 0 and stats.get("value_at_risk_ratio", 0) > var_limit:
            risk_breaches["var"] = {
                "limit": var_limit,
                "current": stats["value_at_risk_ratio"],
                "breach_ratio": stats["value_at_risk_ratio"] / var_limit
            }
        
        # 检查单一合约持仓限制
        for symbol, positions in self._positions_by_symbol.items():
            for side, position in positions.items():
                if not position or position['volume'] <= 0:
                    continue
                
                # 检查最大持仓量限制
                max_size = self.risk_limits["max_position_size"].get(symbol, 0)
                if max_size > 0 and position['volume'] > max_size:
                    key = f"size_{symbol}_{side}"
                    risk_breaches[key] = {
                        "symbol": symbol,
                        "side": side,
                        "limit": max_size,
                        "current": position['volume'],
                        "breach_ratio": position['volume'] / max_size
                    }
        
        # 如果有新的风险违规，通知监听器
        if risk_breaches and risk_breaches != self._risk_breaches:
            self.logger.warning(f"检测到风险限制违规: {risk_breaches}")
            
            # 更新风险违规
            old_breaches = self._risk_breaches
            self._risk_breaches = risk_breaches
            
            # 通知风险监听器
            for listener in self._risk_listeners:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        asyncio.create_task(listener(old_breaches, risk_breaches))
                    else:
                        listener(old_breaches, risk_breaches)
                except Exception as e:
                    self.logger.error(f"执行风险监听器出错: {str(e)}")
    
    async def _notify_position_listeners(self) -> None:
        """通知持仓监听器"""
        # 创建持仓列表副本
        positions_copy = []
        async with self._position_lock:
            for position in self._positions.values():
                if position['volume'] > 0:
                    positions_copy.append(copy.deepcopy(position))
        
        # 添加统计数据
        data = {
            'positions': positions_copy,
            'statistics': copy.deepcopy(self._position_stats),
            'timestamp': time.time()
        }
        
        # 通知监听器
        for listener in self._position_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(data))
                else:
                    listener(data)
            except Exception as e:
                self.logger.error(f"执行持仓监听器出错: {str(e)}")
    
    # 公开方法
    
    async def get_position(self, symbol: str, side: str = PositionSide.BOTH) -> Union[Dict, List[Dict]]:
        """
        获取持仓信息
        
        Args:
            symbol: 合约代码
            side: 持仓方向，LONG/SHORT/BOTH
            
        Returns:
            Union[Dict, List[Dict]]: 持仓信息或持仓列表
        """
        async with self._position_lock:
            if symbol not in self._positions_by_symbol:
                return [] if side == PositionSide.BOTH else None
            
            if side == PositionSide.BOTH:
                # 返回双向持仓
                result = []
                for s in [PositionSide.LONG, PositionSide.SHORT]:
                    position = self._positions_by_symbol[symbol].get(s)
                    if position and position['volume'] > 0:
                        result.append(copy.deepcopy(position))
                return result
            else:
                # 返回单向持仓
                position = self._positions_by_symbol[symbol].get(side)
                return copy.deepcopy(position) if position and position['volume'] > 0 else None
    
    async def get_positions(self, strategy_id: str = "") -> List[Dict]:
        """
        获取持仓列表
        
        Args:
            strategy_id: 策略ID(可选)
            
        Returns:
            List[Dict]: 持仓列表
        """
        result = []
        
        async with self._position_lock:
            if strategy_id:
                # 获取策略持仓
                if strategy_id in self._positions_by_strategy:
                    for position in self._positions_by_strategy[strategy_id].values():
                        if position and position['volume'] > 0:
                            result.append(copy.deepcopy(position))
            else:
                # 获取所有持仓
                for position in self._positions.values():
                    if position['volume'] > 0:
                        result.append(copy.deepcopy(position))
        
        return result
    
    async def get_position_value(self, symbol: str = "", strategy_id: str = "") -> Dict:
        """
        获取持仓价值
        
        Args:
            symbol: 合约代码(可选)
            strategy_id: 策略ID(可选)
            
        Returns:
            Dict: 持仓价值信息
        """
        result = {
            "long_value": 0,
            "short_value": 0,
            "net_value": 0,
            "total_value": 0
        }
        
        positions = await self.get_positions(strategy_id)
        
        for position in positions:
            if symbol and position['symbol'] != symbol:
                continue
            
            # 计算持仓价值
            position_value = position['last_price'] * position['volume']
            
            if position['side'] == PositionSide.LONG:
                result["long_value"] += position_value
            else:
                result["short_value"] += position_value
        
        result["total_value"] = result["long_value"] + result["short_value"]
        result["net_value"] = result["long_value"] - result["short_value"]
        
        return result
    
    async def close_position(self, symbol: str, side: str, 
                       volume: float = 0, 
                       price: float = 0,
                       strategy_id: str = "") -> bool:
        """
        平仓
    
        Args:
            symbol: 合约代码
            side: 持仓方向 LONG/SHORT
            volume: 平仓数量，0表示全部平仓
            price: 平仓价格，0表示市价
            strategy_id: 策略ID(可选)
        
        Returns:
            bool: 是否成功
        """
        try:
            # 检查持仓是否存在
            position = await self.get_position(symbol, side)
            if not position or position.get('volume', 0) <= 0:
                self.logger.warning(f"平仓失败: 没有{side}持仓 {symbol}")
                return False
        
            # 检查策略ID
            if strategy_id and position.get('strategy_id') != strategy_id:
                self.logger.warning(f"平仓失败: 持仓策略ID不匹配 {position.get('strategy_id')} != {strategy_id}")
                return False
        
            # 确定平仓数量（增加浮点数精度处理）
            close_volume = min(
                round(position['volume'], 8), 
                round(volume, 8) if volume > 0 else float('inf')
            )
        
            # 确定下单方向（增加枚举值校验）
            if side == PositionSide.LONG:
                direction = "SELL"
            elif side == PositionSide.SHORT:
                direction = "BUY"
            else:
                raise ValueError(f"无效的持仓方向: {side}")
        
            # 创建平仓订单（增加市价单/限价单校验）
            order_type = "MARKET" if price <= 1e-8 else "LIMIT"  # 处理浮点精度误差
            success, order_id, _ = await self.order_manager.create_order(
                symbol=symbol,
                direction=direction,
                offset="CLOSE",
                price=round(price, 8),
                volume=close_volume,
                order_type=order_type,
                strategy_id=strategy_id
            )
        
            if success:
                self.logger.info(f"平仓订单已提交: {symbol} {side} 数量={close_volume} 订单ID={order_id}")
                return True
            else:
                self.logger.error(f"平仓订单创建失败: {symbol} {side} 数量={close_volume}")
                return False
            
        except ValueError as ve:
            self.logger.error(f"参数错误: {str(ve)}")
            return False
        except Exception as e:
            self.logger.error(f"平仓失败: {str(e)}", exc_info=True)
            return False
    
    async def close_all_positions(self, strategy_id: str = "") -> Tuple[int, int]:
        """
        平所有仓
        
        Args:
            strategy_id: 策略ID(可选)，指定时只平该策略的仓位
            
        Returns:
            Tuple[int, int]: (成功数量, 失败数量)
        """
        self.logger.info(f"准备平所有仓位{' 策略: ' + strategy_id if strategy_id else ''}")
        
        # 获取持仓列表
        positions = await self.get_positions(strategy_id)
        
        if not positions:
            self.logger.info("没有需要平仓的持仓")
            return 0, 0
        
        success_count = 0
        fail_count = 0
        
        # 并发执行平仓
        tasks = []
        for position in positions:
            symbol = position['symbol']
            side = position['side']
            position_strategy_id = position.get('strategy_id', '')
            
            # 只平指定策略的仓位
            if strategy_id and position_strategy_id != strategy_id:
                continue
                
            tasks.append(self.close_position(
                symbol=symbol,
                side=side,
                volume=0,  # 全部平仓
                price=0,   # 市价
                strategy_id=position_strategy_id
            ))
        
        if not tasks:
            self.logger.info("没有符合条件的持仓需要平仓")
            return 0, 0
            
        # 等待所有平仓任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"平仓时发生异常: {str(result)}")
                fail_count += 1
            elif result:
                success_count += 1
            else:
                fail_count += 1
        
        self.logger.info(f"平所有仓位完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count
    
    async def reduce_position(self, symbol: str, side: str, 
                            ratio: float, 
                            price: float = 0,
                            strategy_id: str = "") -> bool:
        """
        减仓
        
        Args:
            symbol: 合约代码
            side: 持仓方向 LONG/SHORT
            ratio: 减仓比例 (0.0-1.0)
            price: 平仓价格，0表示市价
            strategy_id: 策略ID(可选)
            
        Returns:
            bool: 是否成功
        """
        if not 0 < ratio <= 1:
            self.logger.error(f"减仓比例必须在0-1之间: {ratio}")
            return False
            
        # 检查持仓是否存在
        position = await self.get_position(symbol, side)
        if not position:
            self.logger.warning(f"减仓失败: 没有{side}持仓 {symbol}")
            return False
        
        # 检查策略ID
        if strategy_id and position.get('strategy_id') != strategy_id:
            self.logger.warning(f"减仓失败: 持仓策略ID不匹配 {position.get('strategy_id')} != {strategy_id}")
            return False
        
        # 计算减仓数量
        volume = position['volume'] * ratio
        
        # 确保最小减仓数量
        if volume < 1:
            volume = 1
        
        # 确保不超过持仓
        if volume > position['volume']:
            volume = position['volume']
        
        # 执行平仓
        return await self.close_position(
            symbol=symbol,
            side=side,
            volume=volume,
            price=price,
            strategy_id=strategy_id
        )
    
    async def reduce_all_positions(self, ratio: float, strategy_id: str = "") -> Tuple[int, int]:
        """
        减少所有仓位
        
        Args:
            ratio: 减仓比例 (0.0-1.0)
            strategy_id: 策略ID(可选)
            
        Returns:
            Tuple[int, int]: (成功数量, 失败数量)
        """
        if not 0 < ratio <= 1:
            self.logger.error(f"减仓比例必须在0-1之间: {ratio}")
            return 0, 0
            
        self.logger.info(f"准备减仓 {ratio*100}%{' 策略: ' + strategy_id if strategy_id else ''}")
        
        # 获取持仓列表
        positions = await self.get_positions(strategy_id)
        
        if not positions:
            self.logger.info("没有需要减仓的持仓")
            return 0, 0
        
        success_count = 0
        fail_count = 0
        
        # 并发执行减仓
        tasks = []
        for position in positions:
            symbol = position['symbol']
            side = position['side']
            position_strategy_id = position.get('strategy_id', '')
            
            # 只减指定策略的仓位
            if strategy_id and position_strategy_id != strategy_id:
                continue
                
            tasks.append(self.reduce_position(
                symbol=symbol,
                side=side,
                ratio=ratio,
                price=0,   # 市价
                strategy_id=position_strategy_id
            ))
        
        if not tasks:
            self.logger.info("没有符合条件的持仓需要减仓")
            return 0, 0
            
        # 等待所有减仓任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"减仓时发生异常: {str(result)}")
                fail_count += 1
            elif result:
                success_count += 1
            else:
                fail_count += 1
        
        self.logger.info(f"减仓完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count
    
    async def calculate_statistics(self) -> Dict:
        """
        计算持仓统计数据
        
        Returns:
            Dict: 统计数据
        """
        # 获取账户信息
        account_info = await self.account_manager.get_account_info()
        balance = account_info.get('balance', 0)
        
        # 初始化统计数据
        stats = {
            "total_long_value": 0,    # 多头总价值
            "total_short_value": 0,   # 空头总价值
            "total_net_value": 0,     # 净头寸价值
            "total_absolute_value": 0, # 总头寸价值(绝对值)
            "max_single_value": 0,    # 最大单一持仓价值
            "max_concentration": 0,   # 最大集中度
            "leverage_ratio": 0,      # 杠杆率
            "value_at_risk": 0,       # 风险价值(VaR)
            "value_at_risk_ratio": 0, # 风险价值比率
            "total_unrealized_pnl": 0, # 总未实现盈亏
            "total_positions": 0,     # 持仓总数
            "symbols": set(),         # 持仓合约集合
            "position_count_by_side": {
                PositionSide.LONG: 0, 
                PositionSide.SHORT: 0
            }, # 按方向统计持仓数量
            "unrealized_pnl_by_side": {
                PositionSide.LONG: 0, 
                PositionSide.SHORT: 0
            }  # 按方向统计未实现盈亏
        }
        
        # 遍历所有持仓
        async with self._position_lock:
            for position in self._positions.values():
                if position['volume'] <= 0:
                    continue
                    
                # 计算持仓价值
                position_value = position['last_price'] * position['volume']
                
                # 计算未实现盈亏
                unrealized_pnl = position['unrealized_pnl']
                
                # 更新统计数据
                if position['side'] == PositionSide.LONG:
                    stats["total_long_value"] += position_value
                    stats["position_count_by_side"][PositionSide.LONG] += 1
                    stats["unrealized_pnl_by_side"][PositionSide.LONG] += unrealized_pnl
                else:
                    stats["total_short_value"] += position_value
                    stats["position_count_by_side"][PositionSide.SHORT] += 1
                    stats["unrealized_pnl_by_side"][PositionSide.SHORT] += unrealized_pnl
                
                # 更新最大单一持仓价值
                if position_value > stats["max_single_value"]:
                    stats["max_single_value"] = position_value
                
                # 添加合约
                stats["symbols"].add(position['symbol'])
                
                # 累加未实现盈亏
                stats["total_unrealized_pnl"] += unrealized_pnl
                
                # 累加持仓总数
                stats["total_positions"] += 1
        
        # 计算净头寸价值
        stats["total_net_value"] = stats["total_long_value"] - stats["total_short_value"]
        
        # 计算总头寸价值
        stats["total_absolute_value"] = stats["total_long_value"] + stats["total_short_value"]
        
        # 计算最大集中度
        if stats["total_absolute_value"] > 0:
            stats["max_concentration"] = stats["max_single_value"] / stats["total_absolute_value"]
        
        # 计算杠杆率
        if balance > 0:
            stats["leverage_ratio"] = stats["total_absolute_value"] / balance
        
        # 简化的VaR计算 (实际应用中应使用更复杂的模型)
        # 这里使用一个简单的假设：VaR = 总持仓价值 * 波动率假设 * 置信度系数
        volatility = 0.02  # 假设的日波动率
        confidence = 1.65  # 90%置信水平的系数
        stats["value_at_risk"] = stats["total_absolute_value"] * volatility * confidence
        
        # 计算VaR比率
        if balance > 0:
            stats["value_at_risk_ratio"] = stats["value_at_risk"] / balance
        
        # 将合约集合转换为列表
        stats["symbols"] = list(stats["symbols"])
        
        return stats
    
    async def add_position_listener(self, listener: Callable[[Dict], None]) -> None:
        """
        添加持仓监听器
        
        Args:
            listener: 回调函数 (positions_data) -> None
        """
        if listener not in self._position_listeners:
            self._position_listeners.append(listener)
    
    async def add_risk_listener(self, listener: Callable[[Dict, Dict], None]) -> None:
        """
        添加风险监听器
        
        Args:
            listener: 回调函数 (old_breaches, new_breaches) -> None
        """
        if listener not in self._risk_listeners:
            self._risk_listeners.append(listener)
    
    async def set_risk_limit(self, limit_name: str, value: Any) -> bool:
        """
        设置风险限制
        
        Args:
            limit_name: 限制名称
            value: 限制值
            
        Returns:
            bool: 是否成功
        """
        if limit_name not in self.risk_limits:
            self.logger.error(f"未知的风险限制: {limit_name}")
            return False
        
        # 更新风险限制
        self.risk_limits[limit_name] = value
        self.logger.info(f"风险限制已更新: {limit_name} = {value}")
        
        # 清空风险违规记录，以便重新检查
        self._risk_breaches = {}
        
        # 触发风险检查
        asyncio.create_task(self._check_risk_limits())
        
        return True
    
    async def set_position_limit(self, symbol: str, max_size: int) -> bool:
        """
        设置单一合约持仓限制
        
        Args:
            symbol: 合约代码
            max_size: 最大持仓量
            
        Returns:
            bool: 是否成功
        """
        self.risk_limits["max_position_size"][symbol] = max_size
        self.logger.info(f"合约持仓限制已更新: {symbol} = {max_size}")
        
        # 触发风险检查
        asyncio.create_task(self._check_risk_limits())
        
        return True
    
    async def get_risk_breaches(self) -> Dict:
        """
        获取风险违规信息
        
        Returns:
            Dict: 风险违规信息
        """
        return copy.deepcopy(self._risk_breaches)
    
    async def get_statistics(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        # 计算最新统计
        stats = await self.calculate_statistics()
        
        # 获取持仓数据
        positions = []
        async with self._position_lock:
            for position in self._positions.values():
                if position['volume'] > 0:
                    positions.append(copy.deepcopy(position))
        
        # 按合约分组
        positions_by_symbol = defaultdict(list)
        for position in positions:
            positions_by_symbol[position['symbol']].append(position)
        
        # 按策略分组
        positions_by_strategy = defaultdict(list)
        for position in positions:
            strategy_id = position.get('strategy_id', '')
            if strategy_id:
                positions_by_strategy[strategy_id].append(position)
        
        return {
            'statistics': stats,
            'total_positions': len(positions),
            'position_symbols': list(positions_by_symbol.keys()),
            'positions_by_symbol': {k: len(v) for k, v in positions_by_symbol.items()},
            'positions_by_strategy': {k: len(v) for k, v in positions_by_strategy.items()},
            'risk_breaches': copy.deepcopy(self._risk_breaches),
            'risk_limits': copy.deepcopy(self.risk_limits)
        }
    
    async def get_health_status(self) -> Dict:
        """
        获取健康状态
        
        Returns:
            Dict: 健康状态信息
        """
        stats = await self.calculate_statistics()
        
        return {
            'status': 'normal' if not self._risk_breaches else 'risk_breach',
            'total_positions': stats['total_positions'],
            'total_value': stats['total_absolute_value'],
            'leverage': stats['leverage_ratio'],
            'unrealized_pnl': stats['total_unrealized_pnl'],
            'risk_breaches': len(self._risk_breaches),
            'major_risks': list(self._risk_breaches.keys()) if self._risk_breaches else []
        }
    
    async def _auto_update(self) -> None:
        """自动更新持仓信息的后台任务"""
        self.logger.info(f"启动持仓自动更新任务，间隔 {self._auto_update_interval} 秒")
        
        while self._running:
            try:
                # 更新持仓信息
                await self._load_positions()
                
                # 检查风险限制
                await self._check_risk_limits()
                
                # 通知监听器
                await self._notify_position_listeners()
                
                # 等待下一次更新
                await asyncio.sleep(self._auto_update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"持仓自动更新出错: {str(e)}")
                await asyncio.sleep(self._auto_update_interval)
        
        self.logger.info("持仓自动更新任务已停止")