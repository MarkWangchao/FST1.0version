#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 订单管理器

此模块负责订单创建、跟踪和状态管理，提供完整的订单生命周期支持。
特性包括：
- 异步订单处理
- 订单状态自动追踪
- 智能订单重试
- 高级订单管理功能
- 订单事件监听机制
- 完整性能监控
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

from infrastructure.api.broker_adapter import BrokerAdapter, ConnectionState, OrderStatus

class OrderType:
    """订单类型枚举"""
    LIMIT = "LIMIT"         # 限价单
    MARKET = "MARKET"       # 市价单
    STOP = "STOP"           # 止损单
    STOP_LIMIT = "STOP_LIMIT" # 止损限价单
    FAK = "FAK"             # 部成即撤 (Fill And Kill)
    FOK = "FOK"             # 全成或撤 (Fill Or Kill)

class OrderDirection:
    """订单方向枚举"""
    BUY = "BUY"       # 买入
    SELL = "SELL"     # 卖出

class OrderOffset:
    """开平标志枚举"""
    OPEN = "OPEN"     # 开仓
    CLOSE = "CLOSE"   # 平仓
    CLOSETODAY = "CLOSETODAY"  # 平今
    CLOSEYESTERDAY = "CLOSEYESTERDAY"  # 平昨

class OrderState:
    """订单状态枚举"""
    SUBMITTING = "SUBMITTING"   # 提交中
    SUBMITTED = "SUBMITTED"     # 已提交
    PARTIAL_FILLED = "PARTIAL_FILLED"  # 部分成交
    FILLED = "FILLED"           # 全部成交
    CANCELLING = "CANCELLING"   # 撤单中
    CANCELLED = "CANCELLED"     # 已撤单
    REJECTED = "REJECTED"       # 已拒绝
    FAILED = "FAILED"           # 下单失败
    UNKNOWN = "UNKNOWN"         # 未知状态

class OrderManager:
    """
    订单管理器，负责管理订单创建、跟踪和状态管理
    """
    
    def __init__(self, broker_adapter: BrokerAdapter, 
                 account_manager: Any,
                 max_retry_count: int = 3,
                 order_timeout: float = 60.0,
                 auto_track_interval: float = 2.0):
        """
        初始化订单管理器
        
        Args:
            broker_adapter: 券商适配器
            account_manager: 账户管理器
            max_retry_count: 最大重试次数
            order_timeout: 订单超时时间(秒)
            auto_track_interval: 自动跟踪间隔(秒)
        """
        self.logger = logging.getLogger("fst.core.trading.order_manager")
        self.broker_adapter = broker_adapter
        self.account_manager = account_manager
        
        # 订单设置
        self.max_retry_count = max_retry_count
        self.order_timeout = order_timeout
        self.auto_track_interval = auto_track_interval
        
        # 订单数据
        self._orders = {}  # 所有订单
        self._active_orders = {}  # 活动订单
        self._orders_by_symbol = defaultdict(set)  # 按合约分组的订单
        self._orders_by_strategy = defaultdict(set)  # 按策略分组的订单
        self._pending_orders = set()  # 等待中的订单
        
        # 锁
        self._order_lock = asyncio.Lock()
        
        # 订单限制
        self._order_restriction = False  # 订单限制标志
        self._trading_enabled = True  # 交易启用标志
        
        # 订单监听器
        self._order_listeners = []  # 订单状态变化监听器
        self._trade_listeners = []  # 成交事件监听器
        
        # 自动跟踪任务
        self._auto_track_task = None
        self._running = False
        
        # 统计指标
        self._metrics = {
            "orders_created": 0,
            "orders_submitted": 0,
            "orders_filled": 0,
            "orders_cancelled": 0,
            "orders_rejected": 0,
            "orders_failed": 0,
            "retry_count": 0,
            "timeout_count": 0,
            "latency_submit": 0.0,
            "latency_submit_avg": 0.0,
            "latency_cancel": 0.0,
            "latency_cancel_avg": 0.0,
            "errors": 0
        }
        
        # 添加连接状态监听
        self.broker_adapter.add_connection_listener(self._on_connection_state_change)
        
        self.logger.info("订单管理器初始化完成")
    
    async def start(self) -> bool:
        """
        启动订单管理器
        
        Returns:
            bool: 启动是否成功
        """
        self.logger.info("启动订单管理器")
        
        # 检查适配器连接状态
        if not self.broker_adapter.is_connected:
            self.logger.error("券商适配器未连接，订单管理器无法启动")
            return False
        
        # 加载现有订单
        try:
            await self._load_existing_orders()
            
            # 启动自动跟踪任务
            self._running = True
            self._auto_track_task = asyncio.create_task(self._auto_track_orders())
            
            return True
            
        except Exception as e:
            self.logger.error(f"启动订单管理器失败: {str(e)}")
            return False
    
    async def stop(self) -> None:
        """停止订单管理器"""
        self.logger.info("停止订单管理器")
        
        self._running = False
        
        # 取消自动跟踪任务
        if self._auto_track_task and not self._auto_track_task.done():
            self._auto_track_task.cancel()
            try:
                await self._auto_track_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("订单管理器已停止")
    
    async def _on_connection_state_change(self, old_state: str, new_state: str) -> None:
        """
        连接状态变化处理
        
        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        self.logger.info(f"检测到券商适配器连接状态变化: {old_state} -> {new_state}")
        
        if new_state == ConnectionState.CONNECTED.name:
            # 连接恢复，重新加载订单
            if self._running:
                self.logger.info("连接恢复，重新加载订单")
                asyncio.create_task(self._load_existing_orders())
        
        elif new_state in [ConnectionState.DISCONNECTED.name, ConnectionState.ERROR.name]:
            # 连接断开，标记所有活动订单为未知状态
            if self._active_orders:
                self.logger.warning(f"连接断开，将 {len(self._active_orders)} 个活动订单标记为未知状态")
                
                async with self._order_lock:
                    for order_id, order in list(self._active_orders.items()):
                        order['state'] = OrderState.UNKNOWN
                        order['error_message'] = "连接断开，订单状态未知"
                        
                        # 通知监听器
                        await self._notify_order_listeners(order)
    
    async def _load_existing_orders(self) -> None:
        """加载现有订单"""
        self.logger.info("加载现有订单")
        
        try:
            # 获取所有订单
            orders = await self.broker_adapter.get_orders()
            
            async with self._order_lock:
                # 清空现有订单
                self._orders.clear()
                self._active_orders.clear()
                self._orders_by_symbol.clear()
                self._orders_by_strategy.clear()
                self._pending_orders.clear()
                
                # 加载订单
                for order_data in orders:
                    order_id = order_data.get('order_id')
                    if not order_id:
                        continue
                    
                    # 转换为内部订单格式
                    order = self._convert_to_internal_order(order_data)
                    
                    # 添加到订单集合
                    self._orders[order_id] = order
                    
                    # 更新索引
                    symbol = order.get('symbol')
                    if symbol:
                        self._orders_by_symbol[symbol].add(order_id)
                    
                    strategy_id = order.get('strategy_id')
                    if strategy_id:
                        self._orders_by_strategy[strategy_id].add(order_id)
                    
                    # 检查是否活动订单
                    if order.get('state') in [
                        OrderState.SUBMITTING, 
                        OrderState.SUBMITTED, 
                        OrderState.PARTIAL_FILLED,
                        OrderState.CANCELLING
                    ]:
                        self._active_orders[order_id] = order
            
            self.logger.info(f"加载了 {len(self._orders)} 个订单，其中 {len(self._active_orders)} 个活动订单")
            
        except Exception as e:
            self.logger.error(f"加载现有订单失败: {str(e)}")
            raise
    
    async def _auto_track_orders(self) -> None:
        """自动跟踪订单状态的后台任务"""
        self.logger.info(f"启动订单自动跟踪任务，间隔 {self.auto_track_interval} 秒")
        
        while self._running:
            try:
                # 检查活动订单
                if self._active_orders:
                    await self._check_active_orders()
                
                # 检查超时订单
                await self._check_timeout_orders()
                
                # 等待下一次检查
                await asyncio.sleep(self.auto_track_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"订单自动跟踪出错: {str(e)}")
                self._metrics["errors"] += 1
                await asyncio.sleep(self.auto_track_interval)
        
        self.logger.info("订单自动跟踪任务已停止")
    
    async def _check_active_orders(self) -> None:
        """检查活动订单状态"""
        order_ids = list(self._active_orders.keys())
        
        if not order_ids:
            return
        
        self.logger.debug(f"检查 {len(order_ids)} 个活动订单状态")
        
        for order_id in order_ids:
            try:
                # 获取订单状态
                order_info = await self.broker_adapter.get_order(order_id)
                
                if not order_info:
                    self.logger.warning(f"获取订单 {order_id} 状态失败，可能已不存在")
                    continue
                
                # 更新订单状态
                await self._update_order_status(order_id, order_info)
                
            except Exception as e:
                self.logger.error(f"检查订单 {order_id} 状态出错: {str(e)}")
                self._metrics["errors"] += 1
    
    async def _check_timeout_orders(self) -> None:
        """检查超时订单"""
        now = time.time()
        
        async with self._order_lock:
            for order_id, order in list(self._active_orders.items()):
                # 检查提交中的订单是否超时
                if order['state'] == OrderState.SUBMITTING:
                    submit_time = order.get('create_time', 0)
                    elapsed = now - submit_time
                    
                    if elapsed > self.order_timeout:
                        self.logger.warning(f"订单 {order_id} 提交超时")
                        
                        # 标记为失败
                        order['state'] = OrderState.FAILED
                        order['error_message'] = "订单提交超时"
                        order['update_time'] = now
                        
                        # 从活动订单中移除
                        self._active_orders.pop(order_id, None)
                        
                        # 更新统计信息
                        self._metrics["timeout_count"] += 1
                        self._metrics["orders_failed"] += 1
                        
                        # 通知监听器
                        await self._notify_order_listeners(order)
                
                # 检查撤单中的订单是否超时
                elif order['state'] == OrderState.CANCELLING:
                    cancel_time = order.get('cancel_time', 0)
                    elapsed = now - cancel_time
                    
                    if elapsed > self.order_timeout:
                        self.logger.warning(f"订单 {order_id} 撤单超时")
                        
                        # 重新查询订单状态
                        try:
                            order_info = await self.broker_adapter.get_order(order_id)
                            
                            if order_info:
                                # 更新订单状态
                                await self._update_order_status(order_id, order_info)
                            else:
                                # 标记为未知状态
                                order['state'] = OrderState.UNKNOWN
                                order['error_message'] = "撤单超时，订单状态未知"
                                order['update_time'] = now
                                
                                # 通知监听器
                                await self._notify_order_listeners(order)
                                
                        except Exception as e:
                            self.logger.error(f"撤单超时检查订单 {order_id} 状态出错: {str(e)}")
                            self._metrics["errors"] += 1
    
    async def _update_order_status(self, order_id: str, order_info: Dict) -> None:
        """
        更新订单状态
        
        Args:
            order_id: 订单ID
            order_info: 订单信息
        """
        if order_id not in self._orders:
            self.logger.warning(f"更新不存在的订单状态: {order_id}")
            return
        
        async with self._order_lock:
            old_order = self._orders[order_id]
            old_state = old_order.get('state')
            
            # 获取新状态
            new_state = self._convert_broker_order_state(order_info.get('status'))
            
            # 状态未变，跳过
            if old_state == new_state:
                return
            
            # 更新订单状态
            self._orders[order_id]['state'] = new_state
            self._orders[order_id]['update_time'] = time.time()
            
            # 更新成交信息
            filled_volume = order_info.get('volume_filled', 0)
            if filled_volume > old_order.get('filled_volume', 0):
                self._orders[order_id]['filled_volume'] = filled_volume
                
                # 检查是否需要触发成交事件
                if filled_volume > 0:
                    trade_info = {
                        'order_id': order_id,
                        'symbol': old_order.get('symbol'),
                        'direction': old_order.get('direction'),
                        'offset': old_order.get('offset'),
                        'volume': filled_volume - old_order.get('filled_volume', 0),
                        'price': order_info.get('price', 0),
                        'trade_time': order_info.get('trade_time', datetime.now().isoformat())
                    }
                    
                    # 通知成交监听器
                    await self._notify_trade_listeners(trade_info)
            
            # 更新错误信息
            if 'error_msg' in order_info and order_info['error_msg']:
                self._orders[order_id]['error_message'] = order_info['error_msg']
            
            # 更新统计信息
            if new_state == OrderState.FILLED and old_state != OrderState.FILLED:
                self._metrics["orders_filled"] += 1
            elif new_state == OrderState.CANCELLED and old_state != OrderState.CANCELLED:
                self._metrics["orders_cancelled"] += 1
            elif new_state == OrderState.REJECTED and old_state != OrderState.REJECTED:
                self._metrics["orders_rejected"] += 1
            
            # 处理完成状态
            if new_state in [
                OrderState.FILLED, 
                OrderState.CANCELLED, 
                OrderState.REJECTED,
                OrderState.FAILED
            ]:
                # 从活动订单中移除
                self._active_orders.pop(order_id, None)
                
                # 从挂单集合中移除
                self._pending_orders.discard(order_id)
            
            # 通知监听器
            await self._notify_order_listeners(self._orders[order_id])
            
            self.logger.info(f"订单 {order_id} 状态更新: {old_state} -> {new_state}")
    
    async def _notify_order_listeners(self, order: Dict) -> None:
        """
        通知订单监听器
        
        Args:
            order: 订单信息
        """
        for listener in self._order_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(copy.deepcopy(order)))
                else:
                    listener(copy.deepcopy(order))
            except Exception as e:
                self.logger.error(f"执行订单监听器出错: {str(e)}")
    
    async def _notify_trade_listeners(self, trade: Dict) -> None:
        """
        通知成交监听器
        
        Args:
            trade: 成交信息
        """
        for listener in self._trade_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(copy.deepcopy(trade)))
                else:
                    listener(copy.deepcopy(trade))
            except Exception as e:
                self.logger.error(f"执行成交监听器出错: {str(e)}")
    
    def _convert_broker_order_state(self, broker_state: Any) -> str:
        """
        转换券商订单状态为内部状态
        
        Args:
            broker_state: 券商订单状态
            
        Returns:
            str: 内部订单状态
        """
        # 如果是已经用OrderStatus枚举
        if isinstance(broker_state, int):
            # 转换OrderStatus枚举值为OrderState字符串
            status_map = {
                OrderStatus.PENDING.value: OrderState.SUBMITTING,
                OrderStatus.ACCEPTED.value: OrderState.SUBMITTED,
                OrderStatus.PARTIALLY_FILLED.value: OrderState.PARTIAL_FILLED,
                OrderStatus.FILLED.value: OrderState.FILLED,
                OrderStatus.CANCELLED.value: OrderState.CANCELLED,
                OrderStatus.REJECTED.value: OrderState.REJECTED,
                OrderStatus.ERROR.value: OrderState.FAILED
            }
            return status_map.get(broker_state, OrderState.UNKNOWN)
            
        # 如果是字符串
        elif isinstance(broker_state, str):
            # 不同券商可能有不同的状态名称，这里提供一个常见映射
            if broker_state in ['PENDING', 'SUBMITTING', '报单中']:
                return OrderState.SUBMITTING
            elif broker_state in ['ACCEPTED', 'SUBMITTED', 'WORKING', '已报']:
                return OrderState.SUBMITTED
            elif broker_state in ['PARTIAL_FILLED', 'PART_FILLED', '部分成交']:
                return OrderState.PARTIAL_FILLED
            elif broker_state in ['FILLED', 'COMPLETED', 'ALL_TRADED', '全部成交']:
                return OrderState.FILLED
            elif broker_state in ['CANCELLING', 'PENDING_CANCEL', '撤单中']:
                return OrderState.CANCELLING
            elif broker_state in ['CANCELLED', 'CANCELED', 'ALL_CANCELED', '已撤单', '已撤销']:
                return OrderState.CANCELLED
            elif broker_state in ['REJECTED', 'EXPIRED', '已拒绝']:
                return OrderState.REJECTED
            elif broker_state in ['FAILED', 'ERROR', '错误']:
                return OrderState.FAILED
            else:
                self.logger.warning(f"未知的券商订单状态: {broker_state}")
                return OrderState.UNKNOWN
        else:
            self.logger.warning(f"无法识别的订单状态类型: {type(broker_state)}")
            return OrderState.UNKNOWN
    
    def _convert_to_internal_order(self, order_data: Dict) -> Dict:
        """
        转换为内部订单格式
        
        Args:
            order_data: 券商订单数据
            
        Returns:
            Dict: 内部订单格式
        """
        # 转换订单状态
        state = self._convert_broker_order_state(order_data.get('status'))
        
        # 解析时间戳
        create_time = time.time()
        if 'insert_time' in order_data and order_data['insert_time']:
            try:
                create_time = datetime.fromisoformat(order_data['insert_time']).timestamp()
            except (ValueError, TypeError):
                pass
        
        update_time = time.time()
        if 'trade_time' in order_data and order_data['trade_time']:
            try:
                update_time = datetime.fromisoformat(order_data['trade_time']).timestamp()
            except (ValueError, TypeError):
                pass
        
        # 构建内部订单对象
        return {
            'order_id': order_data.get('order_id', ''),
            'client_order_id': order_data.get('client_order_id', ''),
            'strategy_id': order_data.get('strategy_id', ''),
            'symbol': order_data.get('symbol', ''),
            'exchange': order_data.get('exchange', ''),
            'direction': order_data.get('direction', ''),
            'offset': order_data.get('offset', ''),
            'price': order_data.get('price', 0.0),
            'volume': order_data.get('volume', 0),
            'filled_volume': order_data.get('volume_filled', 0),
            'order_type': order_data.get('order_type', OrderType.LIMIT),
            'state': state,
            'create_time': create_time,
            'update_time': update_time,
            'cancel_time': 0,
            'error_message': order_data.get('error_msg', ''),
            'retry_count': 0,
            'broker_order_id': order_data.get('broker_order_id', '')
        }
    
    # 公开API方法
    
    async def create_order(self, 
                          symbol: str, 
                          direction: str, 
                          offset: str, 
                          price: float, 
                          volume: int,
                          order_type: str = OrderType.LIMIT,
                          strategy_id: str = '',
                          client_order_id: str = '') -> Tuple[bool, str, Dict]:
        """
        创建订单
        
        Args:
            symbol: 合约代码
            direction: 方向 (BUY/SELL)
            offset: 开平 (OPEN/CLOSE/CLOSETODAY/CLOSEYESTERDAY)
            price: 价格
            volume: 数量
            order_type: 订单类型
            strategy_id: 策略ID
            client_order_id: 客户端订单ID
            
        Returns:
            Tuple[bool, str, Dict]: (是否成功, 订单ID/错误信息, 订单信息)
        """
        # 检查是否允许交易
        if not self._trading_enabled:
            error_msg = "交易已禁用"
            self.logger.error(error_msg)
            return False, error_msg, {}
        
        # 检查是否有订单限制
        if self._order_restriction:
            # 如果有订单限制，检查是否是平仓订单
            if offset not in [OrderOffset.CLOSE, OrderOffset.CLOSETODAY, OrderOffset.CLOSEYESTERDAY]:
                error_msg = "当前有订单限制，只允许平仓操作"
                self.logger.error(error_msg)
                return False, error_msg, {}
        
        # 检查账户状态
        if self.account_manager:
            account_status = await self.account_manager.get_account_status()
            if account_status in ['SUSPENDED', 'LIQUIDATION', 'FROZEN']:
                error_msg = f"账户状态为 {account_status}，不允许下单"
                self.logger.error(error_msg)
                return False, error_msg, {}
            
            # 检查是否可以开仓
            if offset == OrderOffset.OPEN:
                can_open, reason = await self.account_manager.can_open_position(symbol, volume, price)
                if not can_open:
                    self.logger.error(f"无法开仓: {reason}")
                    return False, reason, {}
        
        # 生成客户端订单ID（如果未提供）
        if not client_order_id:
            client_order_id = f"FST_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        
        # 创建订单对象
        order = {
            'order_id': '',  # 将由券商填充
            'client_order_id': client_order_id,
            'strategy_id': strategy_id,
            'symbol': symbol,
            'direction': direction,
            'offset': offset,
            'price': price,
            'volume': volume,
            'filled_volume': 0,
            'order_type': order_type,
            'state': OrderState.SUBMITTING,
            'create_time': time.time(),
            'update_time': time.time(),
            'cancel_time': 0,
            'error_message': '',
            'retry_count': 0,
            'broker_order_id': ''
        }
        
        # 更新统计信息
        self._metrics["orders_created"] += 1
        
        # 提交订单
        start_time = time.time()
        
        try:
            # 准备订单参数
            order_params = {
                'symbol': symbol,
                'direction': direction,
                'offset': offset,
                'price': price,
                'volume': volume,
                'order_type': order_type,
                'client_order_id': client_order_id
            }
            
            # 发送订单
            result = await self.broker_adapter.send_order(**order_params)
            
            # 计算延迟
            latency = (time.time() - start_time) * 1000  # ms
            self._metrics["latency_submit"] = latency
            if self._metrics["orders_submitted"] > 0:
                self._metrics["latency_submit_avg"] = (
                    (self._metrics["latency_submit_avg"] * self._metrics["orders_submitted"] + latency) / 
                    (self._metrics["orders_submitted"] + 1)
                )
            
            # 检查结果
            if result.get('success'):
                order_id = result.get('order_id', '')
                
                if not order_id:
                    error_msg = "订单创建成功但未返回订单ID"
                    self.logger.error(error_msg)
                    return False, error_msg, order
                
                # 设置订单ID
                order['order_id'] = order_id
                order['state'] = OrderState.SUBMITTED
                
                # 更新统计信息
                self._metrics["orders_submitted"] += 1
                
                # 添加到订单管理
                async with self._order_lock:
                    self._orders[order_id] = order
                    self._active_orders[order_id] = order
                    
                    # 更新索引
                    self._orders_by_symbol[symbol].add(order_id)
                    if strategy_id:
                        self._orders_by_strategy[strategy_id].add(order_id)
                    
                    # 添加到挂单集合
                    self._pending_orders.add(order_id)
                
                # 通知监听器
                await self._notify_order_listeners(order)
                
                self.logger.info(f"订单创建成功: {symbol} {direction} {offset} {volume}@{price} ({order_id})")
                return True, order_id, order
                
            else:
                # 订单创建失败
                error_msg = result.get('error', '未知错误')
                
                # 设置订单状态
                order['state'] = OrderState.FAILED
                order['error_message'] = error_msg
                
                # 更新统计信息
                self._metrics["orders_failed"] += 1
                
                self.logger.error(f"订单创建失败: {symbol} {direction} {offset} {volume}@{price}, 错误: {error_msg}")
                return False, error_msg, order
                
        except Exception as e:
            # 异常情况
            error_msg = f"订单创建异常: {str(e)}"
            
            # 设置订单状态
            order['state'] = OrderState.FAILED
            order['error_message'] = error_msg
            
            # 更新统计信息
            self._metrics["errors"] += 1
            self._metrics["orders_failed"] += 1
            
            self.logger.error(f"{error_msg}, 订单: {symbol} {direction} {offset} {volume}@{price}")
            return False, error_msg, order
    
    async def cancel_order(self, order_id: str) -> Tuple[bool, str]:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            Tuple[bool, str]: (是否成功, 错误信息)
        """
        # 检查订单是否存在
        if order_id not in self._orders:
            error_msg = f"订单 {order_id} 不存在"
            self.logger.error(error_msg)
            return False, error_msg
        
        # 检查订单状态
        order = self._orders[order_id]
        if order['state'] not in [OrderState.SUBMITTING, OrderState.SUBMITTED, OrderState.PARTIAL_FILLED]:
            error_msg = f"无法取消订单 {order_id}，当前状态: {order['state']}"
            self.logger.warning(error_msg)
            return False, error_msg
        
        # 设置撤单状态
        async with self._order_lock:
            self._orders[order_id]['state'] = OrderState.CANCELLING
            self._orders[order_id]['cancel_time'] = time.time()
            self._orders[order_id]['update_time'] = time.time()
        
        # 通知监听器
        await self._notify_order_listeners(self._orders[order_id])
        
        # 发送撤单请求
        start_time = time.time()
        
        try:
            # 执行撤单
            result = await self.broker_adapter.cancel_order(order_id)
            
            # 计算延迟
            latency = (time.time() - start_time) * 1000  # ms
            self._metrics["latency_cancel"] = latency
            self._metrics["latency_cancel_avg"] = (
                (self._metrics["latency_cancel_avg"] * self._metrics["orders_cancelled"] + latency) / 
                (self._metrics["orders_cancelled"] + 1)
            ) if self._metrics["orders_cancelled"] > 0 else latency
            
            # 检查结果
            if result.get('success'):
                # 撤单成功，将在状态检查时更新状态
                self.logger.info(f"撤单请求成功: {order_id}")
                return True, ""
                
            else:
                # 撤单失败
                error_msg = result.get('error', '未知错误')
                
                # 重新获取订单状态，因为撤单失败可能订单已完成
                order_info = await self.broker_adapter.get_order(order_id)
                if order_info:
                    await self._update_order_status(order_id, order_info)
                else:
                    # 无法获取订单状态，恢复到之前状态
                    async with self._order_lock:
                        previous_state = self._orders[order_id]['state']
                        if previous_state == OrderState.CANCELLING:
                            # 如果还是撤单中，改为提交状态
                            self._orders[order_id]['state'] = OrderState.SUBMITTED
                            self._orders[order_id]['update_time'] = time.time()
                            self._orders[order_id]['error_message'] = error_msg
                
                self.logger.error(f"撤单请求失败: {order_id}, 错误: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            # 异常情况
            error_msg = f"撤单异常: {str(e)}"
            
            # 更新统计信息
            self._metrics["errors"] += 1
            
            self.logger.error(f"{error_msg}, 订单ID: {order_id}")
            return False, error_msg
    
    async def cancel_all_orders(self, strategy_id: str = "", symbol: str = "") -> Tuple[int, int]:
        """
        取消所有订单
        
        Args:
            strategy_id: 策略ID (可选)
            symbol: 合约代码 (可选)
            
        Returns:
            Tuple[int, int]: (成功数量,: 失败数量)
        """
        # 获取要取消的订单
        orders_to_cancel = []
        
        async with self._order_lock:
            if strategy_id:
                # 按策略取消
                order_ids = self._orders_by_strategy.get(strategy_id, set())
                for order_id in order_ids:
                    if order_id in self._active_orders:
                        orders_to_cancel.append(order_id)
            
            elif symbol:
                # 按合约取消
                order_ids = self._orders_by_symbol.get(symbol, set())
                for order_id in order_ids:
                    if order_id in self._active_orders:
                        orders_to_cancel.append(order_id)
            
            else:
                # 取消所有活动订单
                orders_to_cancel = list(self._active_orders.keys())
        
        if not orders_to_cancel:
            self.logger.info("没有需要取消的订单")
            return 0, 0
        
        # 开始批量取消
        self.logger.info(f"准备取消 {len(orders_to_cancel)} 个订单")
        
        success_count = 0
        fail_count = 0
        
        # 并发取消订单
        tasks = [self.cancel_order(order_id) for order_id in orders_to_cancel]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"取消订单 {orders_to_cancel[i]} 时发生异常: {str(result)}")
                fail_count += 1
            else:
                success, _ = result
                if success:
                    success_count += 1
                else:
                    fail_count += 1
        
        self.logger.info(f"批量取消完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count
    
    async def cancel_all_pending_orders(self) -> Tuple[int, int]:
        """
        取消所有挂单
        
        Returns:
            Tuple[int, int]: (成功数量, 失败数量)
        """
        # 获取当前所有挂单
        orders_to_cancel = []
        
        async with self._order_lock:
            for order_id in self._pending_orders:
                if order_id in self._active_orders:
                    orders_to_cancel.append(order_id)
        
        if not orders_to_cancel:
            self.logger.info("没有需要取消的挂单")
            return 0, 0
        
        # 开始批量取消
        self.logger.info(f"准备取消 {len(orders_to_cancel)} 个挂单")
        
        success_count = 0
        fail_count = 0
        
        # 并发取消订单
        tasks = [self.cancel_order(order_id) for order_id in orders_to_cancel]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"取消挂单 {orders_to_cancel[i]} 时发生异常: {str(result)}")
                fail_count += 1
            else:
                success, _ = result
                if success:
                    success_count += 1
                else:
                    fail_count += 1
        
        self.logger.info(f"批量取消挂单完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count
    
    async def get_order(self, order_id: str) -> Optional[Dict]:
        """
        获取订单信息
        
        Args:
            order_id: 订单ID
            
        Returns:
            Optional[Dict]: 订单信息
        """
        # 检查本地缓存
        if order_id in self._orders:
            # 返回深拷贝防止修改
            return copy.deepcopy(self._orders[order_id])
        
        # 查询订单
        try:
            order_info = await self.broker_adapter.get_order(order_id)
            
            if order_info:
                # 更新本地缓存
                await self._update_order_status(order_id, order_info)
                
                # 返回深拷贝
                return copy.deepcopy(self._orders.get(order_id))
            
        except Exception as e:
            self.logger.error(f"获取订单 {order_id} 信息失败: {str(e)}")
        
        return None
    
    async def get_orders(self, strategy_id: str = "", symbol: str = "", 
                        states: List[str] = None) -> List[Dict]:
        """
        获取订单列表
        
        Args:
            strategy_id: 策略ID (可选)
            symbol: 合约代码 (可选)
            states: 订单状态列表 (可选)
            
        Returns:
            List[Dict]: 订单列表
        """
        result = []
        
        async with self._order_lock:
            # 筛选订单
            order_ids = set()
            
            if strategy_id:
                # 按策略筛选
                order_ids.update(self._orders_by_strategy.get(strategy_id, set()))
            
            if symbol:
                # 按合约筛选
                order_ids.update(self._orders_by_symbol.get(symbol, set()))
            
            if not order_ids:
                # 未指定筛选条件，返回所有订单
                order_ids = set(self._orders.keys())
            
            # 按状态筛选
            for order_id in order_ids:
                if order_id in self._orders:
                    order = self._orders[order_id]
                    
                    # 状态过滤
                    if states and order['state'] not in states:
                        continue
                    
                    # 添加到结果
                    result.append(copy.deepcopy(order))
        
        # 按创建时间排序
        result.sort(key=lambda x: x.get('create_time', 0))
        
        return result
    
    async def get_active_orders(self, strategy_id: str = "", symbol: str = "") -> List[Dict]:
        """
        获取活动订单
        
        Args:
            strategy_id: 策略ID (可选)
            symbol: 合约代码 (可选)
            
        Returns:
            List[Dict]: 活动订单列表
        """
        active_states = [
            OrderState.SUBMITTING,
            OrderState.SUBMITTED,
            OrderState.PARTIAL_FILLED,
            OrderState.CANCELLING
        ]
        
        return await self.get_orders(
            strategy_id=strategy_id,
            symbol=symbol,
            states=active_states
        )
    
    async def get_completed_orders(self, strategy_id: str = "", symbol: str = "") -> List[Dict]:
        """
        获取已完成订单
        
        Args:
            strategy_id: 策略ID (可选)
            symbol: 合约代码 (可选)
            
        Returns:
            List[Dict]: 已完成订单列表
        """
        completed_states = [
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.FAILED
        ]
        
        return await self.get_orders(
            strategy_id=strategy_id,
            symbol=symbol,
            states=completed_states
        )
    
    async def get_order_count(self, strategy_id: str = "", symbol: str = "", 
                             state: str = "") -> int:
        """
        获取订单数量
        
        Args:
            strategy_id: 策略ID (可选)
            symbol: 合约代码 (可选)
            state: 订单状态 (可选)
            
        Returns:
            int: 订单数量
        """
        # 使用get_orders获取订单并计数
        orders = await self.get_orders(
            strategy_id=strategy_id,
            symbol=symbol,
            states=[state] if state else None
        )
        
        return len(orders)
    
    async def track_order(self, order_id: str) -> None:
        """
        跟踪单个订单状态
        
        Args:
            order_id: 订单ID
        """
        # 检查订单是否存在
        if order_id not in self._orders:
            self.logger.warning(f"跟踪未知订单: {order_id}")
            return
        
        # 获取当前订单状态
        order = self._orders[order_id]
        current_state = order['state']
        
        # 已完成订单不需要跟踪
        if current_state in [
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.FAILED
        ]:
            return
        
        # 获取订单最新状态
        try:
            order_info = await self.broker_adapter.get_order(order_id)
            
            if order_info:
                # 更新订单状态
                await self._update_order_status(order_id, order_info)
            else:
                # 找不到订单信息
                self.logger.warning(f"无法获取订单 {order_id} 的状态")
                
                # 检查是否超时
                current_time = time.time()
                create_time = order.get('create_time', 0)
                
                if current_state in [OrderState.SUBMITTING, OrderState.SUBMITTED] and \
                   current_time - create_time > self.order_timeout:
                    # 订单超时
                    self.logger.warning(f"订单 {order_id} 超时，自动取消")
                    
                    # 记录超时
                    self._metrics["timeout_count"] += 1
                    
                    # 自动取消
                    await self.cancel_order(order_id)
        
        except Exception as e:
            self.logger.error(f"跟踪订单 {order_id} 失败: {str(e)}")
            self._metrics["errors"] += 1
    
    async def _auto_track_orders(self) -> None:
        """自动跟踪所有活动订单的后台任务"""
        self.logger.info(f"启动订单自动跟踪任务，间隔 {self.auto_track_interval} 秒")
        
        while self._running:
            try:
                # 获取活动订单ID列表
                active_order_ids = list(self._active_orders.keys())
                
                if active_order_ids:
                    # 使用批量API获取多个订单状态
                    if hasattr(self.broker_adapter, 'get_orders_batch') and \
                       callable(getattr(self.broker_adapter, 'get_orders_batch')):
                        # 批量获取
                        orders_info = await self.broker_adapter.get_orders_batch(active_order_ids)
                        
                        # 更新订单状态
                        for order_id, order_info in orders_info.items():
                            if order_info:
                                await self._update_order_status(order_id, order_info)
                    else:
                        # 单独获取每个订单状态
                        for order_id in active_order_ids:
                            await self.track_order(order_id)
                
                # 等待下一次检查
                await asyncio.sleep(self.auto_track_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"订单自动跟踪出错: {str(e)}")
                self._metrics["errors"] += 1
                await asyncio.sleep(self.auto_track_interval)
        
        self.logger.info("订单自动跟踪任务已停止")
    
    async def _update_order_status(self, order_id: str, order_info: Dict) -> None:
        """
        更新订单状态
        
        Args:
            order_id: 订单ID
            order_info: 订单信息
        """
        # 检查订单是否存在
        if order_id not in self._orders:
            self.logger.warning(f"更新未知订单状态: {order_id}")
            
            # 添加到订单管理
            async with self._order_lock:
                self._orders[order_id] = order_info
                
                symbol = order_info.get('symbol', '')
                if symbol:
                    self._orders_by_symbol[symbol].add(order_id)
                
                strategy_id = order_info.get('strategy_id', '')
                if strategy_id:
                    self._orders_by_strategy[strategy_id].add(order_id)
            
            return
        
        # 获取当前订单
        current_order = self._orders[order_id]
        current_state = current_order['state']
        
        # 获取新状态
        new_state = order_info.get('state', '')
        new_filled = order_info.get('filled_volume', 0)
        current_filled = current_order.get('filled_volume', 0)
        
        # 检查是否有状态变化
        state_changed = (new_state and new_state != current_state)
        filled_changed = (new_filled > current_filled)
        
        if not (state_changed or filled_changed):
            # 没有变化，不需要更新
            return
        
        # 更新订单信息
        async with self._order_lock:
            # 更新订单字典
            for key, value in order_info.items():
                current_order[key] = value
            
            # 更新时间戳
            current_order['update_time'] = time.time()
            
            # 更新状态相关逻辑
            if state_changed:
                self.logger.info(f"订单 {order_id} 状态变化: {current_state} -> {new_state}")
                
                # 更新统计信息
                if new_state == OrderState.FILLED:
                    self._metrics["orders_filled"] += 1
                    
                elif new_state == OrderState.CANCELLED:
                    self._metrics["orders_cancelled"] += 1
                    
                    # 从挂单集合移除
                    self._pending_orders.discard(order_id)
                    
                elif new_state == OrderState.REJECTED:
                    self._metrics["orders_rejected"] += 1
                    
                    # 从挂单集合移除
                    self._pending_orders.discard(order_id)
                
                # 检查是否完成
                if new_state in [
                    OrderState.FILLED,
                    OrderState.CANCELLED,
                    OrderState.REJECTED,
                    OrderState.FAILED
                ]:
                    # 从活动订单移除
                    if order_id in self._active_orders:
                        del self._active_orders[order_id]
            
            # 检查成交量变化
            if filled_changed:
                # 计算新成交量
                new_trade_volume = new_filled - current_filled
                
                self.logger.info(f"订单 {order_id} 新增成交: {new_trade_volume}, 总成交: {new_filled}/{current_order['volume']}")
                
                # 创建成交记录
                trade = {
                    'order_id': order_id,
                    'symbol': current_order['symbol'],
                    'direction': current_order['direction'],
                    'offset': current_order['offset'],
                    'price': order_info.get('trade_price', current_order['price']),
                    'volume': new_trade_volume,
                    'trade_time': time.time(),
                    'commission': order_info.get('commission', 0)
                }
                
                # 通知成交监听器
                for listener in self._trade_listeners:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            asyncio.create_task(listener(trade))
                        else:
                            listener(trade)
                    except Exception as e:
                        self.logger.error(f"执行成交监听器出错: {str(e)}")
        
        # 通知订单监听器
        await self._notify_order_listeners(current_order)
    
    async def _notify_order_listeners(self, order: Dict) -> None:
        """
        通知订单监听器
        
        Args:
            order: 订单信息
        """
        # 创建副本防止修改
        order_copy = copy.deepcopy(order)
        
        # 通知所有监听器
        for listener in self._order_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(order_copy))
                else:
                    listener(order_copy)
            except Exception as e:
                self.logger.error(f"执行订单监听器出错: {str(e)}")
    
    async def add_order_listener(self, listener: Callable[[Dict], None]) -> None:
        """
        添加订单监听器
        
        Args:
            listener: 回调函数 (order) -> None
        """
        if listener not in self._order_listeners:
            self._order_listeners.append(listener)
    
    async def add_trade_listener(self, listener: Callable[[Dict], None]) -> None:
        """
        添加成交监听器
        
        Args:
            listener: 回调函数 (trade) -> None
        """
        if listener not in self._trade_listeners:
            self._trade_listeners.append(listener)
    
    async def set_order_restriction(self, restricted: bool) -> None:
        """
        设置订单限制
        
        Args:
            restricted: 是否限制新订单
        """
        self._order_restriction = restricted
        self.logger.info(f"{'启用' if restricted else '禁用'}订单限制")
    
    async def enable_trading(self) -> None:
        """启用交易"""
        self._trading_enabled = True
        self.logger.info("启用交易")
    
    async def disable_trading(self) -> None:
        """禁用交易"""
        self._trading_enabled = False
        self.logger.info("禁用交易")
    
    async def get_statistics(self) -> Dict:
        """
        获取订单统计信息
        
        Returns:
            Dict: 统计信息
        """
        async with self._order_lock:
            active_count = len(self._active_orders)
            total_count = len(self._orders)
            
            # 按状态统计
            state_counts = defaultdict(int)
            for order in self._orders.values():
                state = order.get('state', '')
                state_counts[state] += 1
            
            # 按合约统计
            symbol_counts = {symbol: len(orders) for symbol, orders in self._orders_by_symbol.items()}
            
            # 按策略统计
            strategy_counts = {strategy: len(orders) for strategy, orders in self._orders_by_strategy.items()}
        
        return {
            'active_count': active_count,
            'total_count': total_count,
            'state_counts': dict(state_counts),
            'symbol_counts': symbol_counts,
            'strategy_counts': strategy_counts,
            'trading_enabled': self._trading_enabled,
            'order_restriction': self._order_restriction,
            'metrics': copy.deepcopy(self._metrics)
        }
    
    async def get_health_status(self) -> Dict:
        """
        获取健康状态
        
        Returns:
            Dict: 健康状态信息
        """
        stats = await self.get_statistics()
        
        return {
            'status': 'normal' if self._running else 'stopped',
            'active_orders': stats['active_count'],
            'error_count': self._metrics['errors'],
            'latency_submit': self._metrics['latency_submit'],
            'latency_submit_avg': self._metrics['latency_submit_avg'],
            'latency_cancel': self._metrics['latency_cancel'],
            'latency_cancel_avg': self._metrics['latency_cancel_avg'],
            'trading_enabled': self._trading_enabled,
            'order_restriction': self._order_restriction
        }