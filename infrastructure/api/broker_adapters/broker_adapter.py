#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 券商适配器基类

定义了统一的券商API适配接口，所有具体适配器实现必须继承此类。
支持异步操作和状态管理。
"""

import abc
import asyncio
import enum
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union, Any, Tuple, Callable

class ConnectionState(enum.Enum):
    """连接状态枚举"""
    DISCONNECTED = 0   # 未连接
    CONNECTING = 1     # 连接中
    CONNECTED = 2      # 已连接
    RECONNECTING = 3   # 重连中
    ERROR = 4          # 错误状态

class OrderStatus(enum.Enum):
    """订单状态枚举"""
    PENDING = 0        # 待处理
    SUBMITTED = 1      # 已提交
    ACCEPTED = 2       # 已接受
    PARTIALLY_FILLED = 3  # 部分成交
    FILLED = 4         # 全部成交
    CANCELLED = 5      # 已撤销
    REJECTED = 6       # 已拒绝
    ERROR = 7          # 错误

class BrokerAdapter(abc.ABC):
    """券商适配器抽象基类"""
    
    def __init__(self):
        """初始化适配器"""
        self.logger = logging.getLogger(f"fst.infrastructure.api.{self.__class__.__name__.lower()}")
        self._connection_state = ConnectionState.DISCONNECTED
        self._connection_listeners = []
        self._order_status_listeners = []
        self._state_change_event = asyncio.Event()
        self._reconnect_task = None
        self._last_error = None
        self._event_loop = None
    
    @property
    def connection_state(self) -> ConnectionState:
        """获取当前连接状态"""
        return self._connection_state
    
    @connection_state.setter
    def connection_state(self, state: ConnectionState):
        """设置连接状态并触发回调"""
        if state != self._connection_state:
            old_state = self._connection_state
            self._connection_state = state
            self._state_change_event.set()
            
            # 通知所有监听器
            for listener in self._connection_listeners:
                try:
                    listener(old_state, state)
                except Exception as e:
                    self.logger.error(f"连接状态监听器执行出错: {e}")
    
    @property
    def last_error(self) -> Optional[Exception]:
        """获取最近的错误信息"""
        return self._last_error
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connection_state == ConnectionState.CONNECTED
    
    def add_connection_listener(self, listener: Callable[[ConnectionState, ConnectionState], None]) -> None:
        """
        添加连接状态变化监听器
        
        Args:
            listener: 状态变化回调函数，接收(old_state, new_state)参数
        """
        if listener not in self._connection_listeners:
            self._connection_listeners.append(listener)
    
    def remove_connection_listener(self, listener: Callable) -> None:
        """移除连接状态监听器"""
        if listener in self._connection_listeners:
            self._connection_listeners.remove(listener)
    
    def add_order_status_listener(self, listener: Callable[[Dict], None]) -> None:
        """
        添加订单状态变化监听器
        
        Args:
            listener: 订单状态回调函数，接收订单信息字典
        """
        if listener not in self._order_status_listeners:
            self._order_status_listeners.append(listener)
    
    def remove_order_status_listener(self, listener: Callable) -> None:
        """移除订单状态监听器"""
        if listener in self._order_status_listeners:
            self._order_status_listeners.remove(listener)
    
    async def wait_for_state(self, state: ConnectionState, timeout: Optional[float] = None) -> bool:
        """
        等待特定连接状态
        
        Args:
            state: 目标连接状态
            timeout: 超时时间(秒)，None表示无限等待
            
        Returns:
            bool: 是否到达目标状态
        """
        if self._connection_state == state:
            return True
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            # 检查当前状态
            if self._connection_state == state:
                return True
            
            # 检查超时
            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    return False
                wait_timeout = timeout - elapsed
            else:
                wait_timeout = None
            
            # 清除状态变化事件
            self._state_change_event.clear()
            
            # 等待状态变化
            try:
                await asyncio.wait_for(self._state_change_event.wait(), wait_timeout)
            except asyncio.TimeoutError:
                return False
    
    @abc.abstractmethod
    async def connect(self) -> bool:
        """
        连接到券商API
        
        Returns:
            bool: 连接是否成功
        """
        pass
    
    @abc.abstractmethod
    async def disconnect(self) -> None:
        """断开与券商API的连接"""
        pass
    
    @abc.abstractmethod
    async def subscribe_market_data(self, symbols: List[str]) -> bool:
        """
        订阅市场行情数据
        
        Args:
            symbols: 合约代码列表
            
        Returns:
            bool: 订阅是否成功
        """
        pass
    
    @abc.abstractmethod
    async def get_account_info(self) -> Dict:
        """
        获取账户信息
        
        Returns:
            Dict: 账户信息字典
        """
        pass
    
    @abc.abstractmethod
    async def get_positions(self) -> List[Dict]:
        """
        获取持仓信息
        
        Returns:
            List[Dict]: 持仓信息列表
        """
        pass
    
    @abc.abstractmethod
    async def get_orders(self, status: Optional[OrderStatus] = None) -> List[Dict]:
        """
        获取订单信息
        
        Args:
            status: 可选，过滤特定状态的订单
            
        Returns:
            List[Dict]: 订单信息列表
        """
        pass
    
    @abc.abstractmethod
    async def place_order(self, symbol: str, direction: str, offset: str, 
                         volume: float, price: Optional[float] = None,
                         order_type: str = "LIMIT") -> Dict:
        """
        下单
        
        Args:
            symbol: 合约代码
            direction: 方向 ("BUY"/"SELL")
            offset: 开平 ("OPEN"/"CLOSE")
            volume: 数量
            price: 价格，None表示市价单
            order_type: 订单类型
            
        Returns:
            Dict: 订单信息
        """
        pass
    
    @abc.abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        撤单
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 撤单是否成功
        """
        pass
    
    @abc.abstractmethod
    async def get_market_data(self, symbol: str) -> Dict:
        """
        获取市场数据快照
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 市场数据字典
        """
        pass
    
    @abc.abstractmethod
    async def get_klines(self, symbol: str, 
                        interval: str,
                        count: int = 200,
                        start_time: Optional[datetime] = None,
                        end_time: Optional[datetime] = None) -> List[Dict]:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            interval: K线周期 ("1m", "5m", "1h", "1d"等)
            count: 数量限制
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[Dict]: K线数据列表
        """
        pass
    
    async def start_auto_reconnect(self, max_retries: int = -1, 
                                 retry_interval: float = 5.0) -> None:
        """
        启动自动重连任务
        
        Args:
            max_retries: 最大重试次数，-1表示无限重试
            retry_interval: 重试间隔(秒)
        """
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        async def reconnect_loop():
            retry_count = 0
            
            while max_retries == -1 or retry_count < max_retries:
                # 如果已连接，不需要重连
                if self.is_connected:
                    await asyncio.sleep(1)
                    continue
                
                # 如果正在连接/重连中，等待完成
                if self._connection_state in [ConnectionState.CONNECTING, ConnectionState.RECONNECTING]:
                    await asyncio.sleep(1)
                    continue
                
                # 尝试重连
                try:
                    self.logger.info(f"尝试自动重连 (第{retry_count+1}次)")
                    self.connection_state = ConnectionState.RECONNECTING
                    
                    success = await self.connect()
                    
                    if success:
                        self.logger.info("自动重连成功")
                        retry_count = 0  # 重置重试计数
                    else:
                        self.logger.warning(f"自动重连失败，{retry_interval}秒后重试")
                        retry_count += 1
                        await asyncio.sleep(retry_interval)
                except Exception as e:
                    self._last_error = e
                    self.logger.error(f"自动重连出错: {e}")
                    retry_count += 1
                    self.connection_state = ConnectionState.ERROR
                    await asyncio.sleep(retry_interval)
        
        # 获取事件循环
        if self._event_loop is None:
            self._event_loop = asyncio.get_event_loop()
        
        # 启动重连任务
        self._reconnect_task = self._event_loop.create_task(reconnect_loop())
        self.logger.info("自动重连任务已启动")
    
    async def stop_auto_reconnect(self) -> None:
        """停止自动重连任务"""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
            self.logger.info("自动重连任务已停止")