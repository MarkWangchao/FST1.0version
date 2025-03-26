#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 天勤SDK适配器

此模块提供天勤量化交易平台(TQSDK)的接口适配，处理连接、认证、
行情获取和交易执行等功能。
实现了异步IO、连接状态管理、行情订阅去重和订单追踪功能。
"""

import asyncio
import logging
import time
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Tuple, Set, Any, Callable
import copy
import traceback

from infrastructure.api.broker_adapter import BrokerAdapter, ConnectionState, OrderStatus

# 导入天勤SDK
try:
    from tqsdk import TqApi, TqAuth, TqAccount, TqBacktest, TqSim
    from tqsdk.objs import Account, Position, Order, Quote
    from tqsdk.exceptions import TqTimeoutError, TqAuthFailError
    TQSDK_AVAILABLE = True
except ImportError:
    # 定义类型别名，仅用于类型注解
    Account = Any
    Position = Any
    Order = Any
    Quote = Any
    TqTimeoutError = Exception
    TqAuthFailError = Exception
    TQSDK_AVAILABLE = False

class TqsdkAdapter(BrokerAdapter):
    """天勤SDK适配器类，实现券商适配器接口"""
    
    def __init__(self, 
                 account: str = "",
                 password: str = "",
                 auth_id: Optional[str] = None,
                 auth_code: Optional[str] = None,
                 backtest_mode: bool = False,
                 start_dt: Optional[str] = None,
                 end_dt: Optional[str] = None):
        """
        初始化天勤SDK适配器
        
        Args:
            account: 账户ID
            password: 账户密码
            auth_id: 天勤认证ID (可选)
            auth_code: 天勤认证码 (可选)
            backtest_mode: 是否使用回测模式
            start_dt: 回测开始日期 (YYYY-MM-DD)
            end_dt: 回测结束日期 (YYYY-MM-DD)
        """
        super().__init__()
        
        if not TQSDK_AVAILABLE:
            self.logger.error("无法导入天勤SDK (tqsdk)，请确保已正确安装")
            raise ImportError("无法导入天勤SDK (tqsdk)")
        
        self.account_id = account
        self.password = password
        self.auth_id = auth_id
        self.auth_code = auth_code
        
        self.backtest_mode = backtest_mode
        self.start_dt = start_dt
        self.end_dt = end_dt
        
        self.api = None
        self.account_instance = None
        
        # 行情订阅管理
        self._subscribed_symbols = set()
        self._subscription_lock = threading.Lock()
        
        # 订单状态追踪
        self._orders = {}
        self._order_updates = queue.Queue()
        
        # API运行线程
        self._api_thread = None
        self._api_running = False
        
        # 异常订单自动恢复
        self._pending_orders = {}
        self._order_timeout = 10  # 秒
        self._order_recovery_task = None
        
        # 市场数据缓存
        self._market_data_cache = {}
        self._market_data_lock = threading.Lock()
        self._market_data_ttl = 1  # 秒
        
        # 异步事件循环和队列
        self._task_queue = asyncio.Queue()
        self._result_dict = {}
        self._next_task_id = 1
        self._task_lock = threading.Lock()
        
        self.logger.info("天勤SDK适配器初始化完成")
    
    async def connect(self) -> bool:
        """
        连接到天勤交易平台
        
        Returns:
            bool: 连接是否成功
        """
        # 更新连接状态
        self.connection_state = ConnectionState.CONNECTING
        
        try:
            # 创建任务并等待结果
            task_id = await self._create_api_instance()
            if not task_id:
                self.connection_state = ConnectionState.ERROR
                return False
            
            # 等待10秒获取结果
            result = await self._wait_for_result(task_id, timeout=10)
            
            if result.get('success', False):
                # 连接成功
                self.connection_state = ConnectionState.CONNECTED
                
                # 启动订单恢复任务
                await self._start_order_recovery()
                
                return True
            else:
                # 连接失败
                error = result.get('error', '未知错误')
                self.logger.error(f"连接天勤交易平台失败: {error}")
                self._last_error = Exception(error)
                self.connection_state = ConnectionState.ERROR
                return False
                
        except Exception as e:
            self.logger.error(f"连接天勤交易平台时出错: {str(e)}")
            self.logger.debug(traceback.format_exc())
            self._last_error = e
            self.connection_state = ConnectionState.ERROR
            return False
    
    async def disconnect(self) -> None:
        """断开与天勤交易平台的连接"""
        if self.api is not None:
            try:
                self.logger.info("断开天勤交易平台连接")
                
                # 停止订单恢复任务
                await self._stop_order_recovery()
                
                # 创建关闭API的任务
                await self._create_task('close_api')
                
                # 等待API线程结束
                if self._api_thread and self._api_thread.is_alive():
                    self._api_running = False
                    self._api_thread.join(timeout=5)
                
                self.api = None
                self.connection_state = ConnectionState.DISCONNECTED
                
            except Exception as e:
                self.logger.error(f"断开连接时出错: {str(e)}")
                self._last_error = e
    
    async def subscribe_market_data(self, symbols: List[str]) -> bool:
        """
        订阅市场行情数据，支持去重
        
        Args:
            symbols: 合约代码列表
            
        Returns:
            bool: 订阅是否成功
        """
        if not self.is_connected:
            self.logger.error("无法订阅行情: 未连接到交易平台")
            return False
        
        try:
            # 过滤已订阅的合约
            new_symbols = []
            with self._subscription_lock:
                for symbol in symbols:
                    if symbol not in self._subscribed_symbols:
                        new_symbols.append(symbol)
                        self._subscribed_symbols.add(symbol)
            
            if not new_symbols:
                self.logger.info("所有合约已订阅，无需重复订阅")
                return True
            
            self.logger.info(f"订阅行情: {new_symbols}")
            
            # 创建订阅任务
            task_id = await self._create_task('subscribe', symbols=new_symbols)
            result = await self._wait_for_result(task_id, timeout=10)
            
            if result.get('success', False):
                self.logger.info(f"行情订阅成功: {new_symbols}")
                return True
            else:
                # 订阅失败，从已订阅集合中移除
                with self._subscription_lock:
                    for symbol in new_symbols:
                        self._subscribed_symbols.discard(symbol)
                
                error = result.get('error', '未知错误')
                self.logger.error(f"行情订阅失败: {error}")
                return False
                
        except Exception as e:
            self.logger.error(f"订阅行情时出错: {str(e)}")
            return False
    
    async def get_account_info(self) -> Dict:
        """
        获取账户信息
        
        Returns:
            Dict: 账户信息字典
        """
        if not self.is_connected:
            raise ConnectionError("未连接到交易平台")
            
        # 创建获取账户信息的任务
        task_id = await self._create_task('get_account')
        result = await self._wait_for_result(task_id)
        
        if not result.get('success', False):
            error = result.get('error', '未知错误')
            raise Exception(f"获取账户信息失败: {error}")
        
        return result.get('data', {})
    
    async def get_positions(self) -> List[Dict]:
        """
        获取持仓信息
        
        Returns:
            List[Dict]: 持仓信息列表
        """
        if not self.is_connected:
            raise ConnectionError("未连接到交易平台")
            
        # 创建获取持仓信息的任务
        task_id = await self._create_task('get_positions')
        result = await self._wait_for_result(task_id)
        
        if not result.get('success', False):
            error = result.get('error', '未知错误')
            raise Exception(f"获取持仓信息失败: {error}")
        
        return result.get('data', [])
    
    async def get_orders(self, status: Optional[OrderStatus] = None) -> List[Dict]:
        """
        获取订单信息
        
        Args:
            status: 可选，过滤特定状态的订单
            
        Returns:
            List[Dict]: 订单信息列表
        """
        if not self.is_connected:
            raise ConnectionError("未连接到交易平台")
            
        # 创建获取订单信息的任务
        task_id = await self._create_task('get_orders', status=status)
        result = await self._wait_for_result(task_id)
        
        if not result.get('success', False):
            error = result.get('error', '未知错误')
            raise Exception(f"获取订单信息失败: {error}")
        
        return result.get('data', [])
    
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
        if not self.is_connected:
            raise ConnectionError("未连接到交易平台")
        
        # 订阅行情（如果未订阅）
        if symbol not in self._subscribed_symbols:
            await self.subscribe_market_data([symbol])
        
        # 市价单处理
        if order_type == "MARKET" or price is None:
            price_type = "MARKET"
            if price is None:
                # 获取最新行情来确定价格
                market_data = await self.get_market_data(symbol)
                if direction == "BUY":
                    # 买入用卖一价
                    price = market_data.get('ask_price1', 0)
                else:
                    # 卖出用买一价
                    price = market_data.get('bid_price1', 0)
        else:
            price_type = "LIMIT"
        
        # 创建下单任务
        task_id = await self._create_task(
            'place_order',
            symbol=symbol,
            direction=direction,
            offset=offset,
            volume=volume,
            price=price,
            price_type=price_type
        )
        
        result = await self._wait_for_result(task_id)
        
        if not result.get('success', False):
            error = result.get('error', '未知错误')
            raise Exception(f"下单失败: {error}")
        
        order_info = result.get('data', {})
        
        # 记录挂单信息，用于异常恢复
        if price_type == "LIMIT":
            order_id = order_info.get('order_id')
            if order_id:
                self._pending_orders[order_id] = {
                    'timestamp': time.time(),
                    'symbol': symbol,
                    'direction': direction,
                    'offset': offset,
                    'volume': volume,
                    'price': price,
                    'price_type': price_type
                }
        
        return order_info
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        撤单
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 撤单是否成功
        """
        if not self.is_connected:
            raise ConnectionError("未连接到交易平台")
        
        # 创建撤单任务
        task_id = await self._create_task('cancel_order', order_id=order_id)
        result = await self._wait_for_result(task_id)
        
        # 从挂单记录中移除
        if order_id in self._pending_orders:
            del self._pending_orders[order_id]
        
        if not result.get('success', False):
            error = result.get('error', '未知错误')
            if "找不到委托单" in error:
                # 订单可能已经成交或已撤销
                self.logger.warning(f"撤单失败，找不到委托单: {order_id}")
                return False
            raise Exception(f"撤单失败: {error}")
        
        return True
    
    async def get_market_data(self, symbol: str) -> Dict:
        """
        获取市场数据快照
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 市场数据字典
        """
        if not self.is_connected:
            raise ConnectionError("未连接到交易平台")
        
        # 检查缓存
        with self._market_data_lock:
            cache_entry = self._market_data_cache.get(symbol)
            if cache_entry:
                timestamp = cache_entry.get('timestamp', 0)
                if time.time() - timestamp < self._market_data_ttl:
                    return cache_entry.get('data', {})
        
        # 检查行情是否已订阅
        if symbol not in self._subscribed_symbols:
            self.logger.info(f"自动订阅行情: {symbol}")
            await self.subscribe_market_data([symbol])
        
        # 获取最新行情
        task_id = await self._create_task('get_quote', symbol=symbol)
        result = await self._wait_for_result(task_id)
        
        if not result.get('success', False):
            error = result.get('error', '未知错误')
            raise Exception(f"获取行情失败: {error}")
        
        market_data = result.get('data', {})
        
        # 更新缓存
        with self._market_data_lock:
            self._market_data_cache[symbol] = {
                'data': market_data,
                'timestamp': time.time()
            }
        
        return market_data
    
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
        if not self.is_connected:
            raise ConnectionError("未连接到交易平台")
        
        # 检查行情是否已订阅
        if symbol not in self._subscribed_symbols:
            self.logger.info(f"自动订阅行情: {symbol}")
            await self.subscribe_market_data([symbol])
        
        # 获取K线数据
        task_id = await self._create_task(
            'get_klines', 
            symbol=symbol,
            interval=interval,
            count=count,
            start_time=start_time,
            end_time=end_time
        )
        
        result = await self._wait_for_result(task_id)
        
        if not result.get('success', False):
            error = result.get('error', '未知错误')
            raise Exception(f"获取K线数据失败: {error}")
        
        return result.get('data', [])
    
    # 内部方法: API实例创建与管理
    
    async def _create_api_instance(self) -> int:
        """
        创建天勤API实例任务
        
        Returns:
            int: 任务ID
        """
        if self._api_thread and self._api_thread.is_alive():
            self.logger.warning("API线程已存在，先关闭旧实例")
            self._api_running = False
            self._api_thread.join(timeout=5)
        
        # 创建新的API任务
        return await self._create_task('create_api')
    
    def _api_worker(self):
        """API工作线程"""
        self.logger.info("启动API工作线程")
        self._api_running = True
        
        try:
            # 创建认证对象
            auth = None
            if self.auth_id and self.auth_code:
                self.logger.info("使用天勤认证信息")
                auth = TqAuth(self.auth_id, self.auth_code)
            
            # 准备交易账户
            if self.backtest_mode:
                self.logger.info(f"初始化回测模式: {self.start_dt} 至 {self.end_dt}")
                
                # 初始化回测环境
                backtest = TqBacktest(start_dt=self.start_dt, end_dt=self.end_dt)
                account = TqSim(init_balance=1000000)  # 初始资金100万
                
                # 创建API实例 (回测模式)
                self.api = TqApi(account=account, backtest=backtest, auth=auth)
            else:
                # 实盘模式
                if self.account_id and self.password:
                    self.logger.info(f"使用实盘账户: {self.account_id}")
                    account = TqAccount(self.account_id, self.password)
                else:
                    self.logger.info("使用模拟账户")
                    account = TqSim(init_balance=1000000)  # 初始资金100万
                
                # 创建API实例 (实盘/模拟)
                self.api = TqApi(account=account, auth=auth)
            
            self.account_instance = account
            
            # 设置连接成功的结果
            with self._task_lock:
                if 'create_api' in self._result_dict:
                    self._result_dict['create_api'] = {
                        'success': True,
                        'data': 'API创建成功'
                    }
            
            # 启动订单状态监控
            self._start_order_monitor()
            
            # 启动API事件循环
            while self._api_running:
                # 使用较短的超时时间，以便及时响应关闭请求
                try:
                    self.api.wait_update(timeout=1)
                    
                    # 处理任务队列
                    self._process_api_tasks()
                    
                except TqTimeoutError:
                    # 忽略超时错误，继续循环
                    pass
                except Exception as e:
                    self.logger.error(f"API事件循环出错: {str(e)}")
                    traceback.print_exc()
                    
                    # 设置错误结果，通知主线程
                    with self._task_lock:
                        if 'api_error' not in self._result_dict:
                            self._result_dict['api_error'] = {
                                'success': False,
                                'error': str(e)
                            }
                    
                    # 在异常情况下，添加短暂休眠，防止CPU占用过高
                    time.sleep(0.1)
            
            # 关闭API
            if self.api:
                self.logger.info("关闭天勤API")
                self.api.close()
                self.api = None
            
        except Exception as e:
            self.logger.error(f"API线程出错: {str(e)}")
            traceback.print_exc()
            
            # 设置错误结果
            with self._task_lock:
                if 'create_api' in self._result_dict:
                    self._result_dict['create_api'] = {
                        'success': False,
                        'error': str(e)
                    }
        
        finally:
            self._api_running = False
            self.logger.info("API工作线程结束")
    
    def _process_api_tasks(self):
        """处理API任务队列"""
        # 处理最多10个任务，防止阻塞太久
        for _ in range(10):
            try:
                # 非阻塞获取任务
                task = self._task_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            
            task_id = task.get('id')
            task_type = task.get('type')
            task_args = task.get('args', {})
            
            result = {'success': False, 'error': '未知任务类型'}
            
            try:
                if task_type == 'create_api':
                    # API创建已在线程启动时处理
                    continue
                
                elif task_type == 'close_api':
                    self._api_running = False
                    result = {'success': True}
                
                elif task_type == 'subscribe':
                    symbols = task_args.get('symbols', [])
                    for symbol in symbols:
                        self.api.get_quote(symbol)
                    result = {'success': True}
                
                elif task_type == 'get_account':
                    account_info = self._convert_account(self.api.get_account())
                    result = {'success': True, 'data': account_info}
                
                elif task_type == 'get_positions':
                    positions = self._get_positions_info()
                    result = {'success': True, 'data': positions}
                
                elif task_type == 'get_orders':
                    status = task_args.get('status')
                    orders = self._get_orders_info(status)
                    result = {'success': True, 'data': orders}
                
                elif task_type == 'place_order':
                    order_result = self._place_order(task_args)
                    result = {'success': True, 'data': order_result}
                
                elif task_type == 'cancel_order':
                    order_id = task_args.get('order_id')
                    success = self._cancel_order(order_id)
                    result = {'success': success}
                    if not success:
                        result['error'] = f"找不到委托单: {order_id}"
                
                elif task_type == 'get_quote':
                    symbol = task_args.get('symbol')
                    quote = self._convert_quote(self.api.get_quote(symbol))
                    result = {'success': True, 'data': quote}
                
                elif task_type == 'get_klines':
                    klines = self._get_klines(task_args)
                    result = {'success': True, 'data': klines}
                
                else:
                    result = {'success': False, 'error': f"未知任务类型: {task_type}"}
            
            except Exception as e:
                self.logger.error(f"处理任务 {task_type} 出错: {str(e)}")
                result = {'success': False, 'error': str(e)}
            
            # 存储任务结果
            with self._task_lock:
                self._result_dict[task_id] = result
    
    async def _create_task(self, task_type: str, **kwargs) -> int:
        """
        创建任务并放入队列
        
        Args:
            task_type: 任务类型
            **kwargs: 任务参数
            
        Returns:
            int: 任务ID
        """
        with self._task_lock:
            task_id = self._next_task_id
            self._next_task_id += 1
            # 将任务ID存入结果字典，表示任务已创建但未完成
            self._result_dict[task_id] = None
        
        # 创建任务对象
        task = {
            'id': task_id,
            'type': task_type,
            'args': kwargs,
            'create_time': time.time()
        }
        
        # 如果是API创建任务，启动API线程
        if task_type == 'create_api':
            # 启动API线程
            self._api_thread = threading.Thread(target=self._api_worker)
            self._api_thread.daemon = True
            self._api_thread.start()
        
        # 放入任务队列
        await self._task_queue.put(task)
        
        return task_id
    
    async def _wait_for_result(self, task_id: int, timeout: float = 30.0) -> Dict:
        """
        等待任务结果
        
        Args:
            task_id: 任务ID
            timeout: 超时时间(秒)
            
        Returns:
            Dict: 任务结果
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._task_lock:
                result = self._result_dict.get(task_id)
                if result is not None:
                    # 任务已完成，删除结果并返回
                    del self._result_dict[task_id]
                    return result
            
            # 等待一段时间再检查
            await asyncio.sleep(0.1)
        
        # 超时处理
        with self._task_lock:
            if task_id in self._result_dict:
                del self._result_dict[task_id]
        
        return {'success': False, 'error': '任务超时'}
    
    # 订单状态监控与订单恢复相关方法
    
    def _start_order_monitor(self):
        """启动订单状态监控"""
        if not self.api:
            return
        
        # 获取账户中的未完成订单
        for order_id, order in self.api.get_order().items():
            if order_id not in self._orders:
                self._orders[order_id] = order
                self._notify_order_update(self._convert_order(order))
        
        self.logger.info(f"订单监控已启动，当前订单数: {len(self._orders)}")
    
    def _notify_order_update(self, order_info: Dict):
        """
        通知订单状态变化
        
        Args:
            order_info: 订单信息
        """
        # 将订单更新放入队列
        self._order_updates.put(order_info)
        
        # 通知订单状态监听器
        for listener in self._order_status_listeners:
            try:
                listener(order_info)
            except Exception as e:
                self.logger.error(f"订单状态监听器执行出错: {e}")
        
        # 从挂单记录中移除已完成的订单
        order_id = order_info.get('order_id')
        status = order_info.get('status')
        if order_id and status in [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value, OrderStatus.REJECTED.value]:
            if order_id in self._pending_orders:
                del self._pending_orders[order_id]
    
    async def _start_order_recovery(self):
        """启动异常订单恢复任务"""
        if self._order_recovery_task is not None and not self._order_recovery_task.done():
            return
        
        self._order_recovery_task = asyncio.create_task(self._order_recovery_loop())
        self.logger.info("订单恢复任务已启动")
    
    async def _stop_order_recovery(self):
        """停止异常订单恢复任务"""
        if self._order_recovery_task is not None and not self._order_recovery_task.done():
            self._order_recovery_task.cancel()
            try:
                await self._order_recovery_task
            except asyncio.CancelledError:
                pass
            self._order_recovery_task = None
            self.logger.info("订单恢复任务已停止")
    
    async def _order_recovery_loop(self):
        """订单恢复循环"""
        while True:
            try:
                # 每5秒检查一次
                await asyncio.sleep(5)
                
                # 检查挂单状态
                now = time.time()
                pending_order_ids = list(self._pending_orders.keys())
                
                for order_id in pending_order_ids:
                    # 获取挂单信息
                    order_info = self._pending_orders.get(order_id)
                    if not order_info:
                        continue
                    
                    # 检查是否超时
                    timestamp = order_info.get('timestamp', 0)
                    if now - timestamp > self._order_timeout:
                        # 检查订单状态
                        try:
                            task_id = await self._create_task('check_order', order_id=order_id)
                            result = await self._wait_for_result(task_id, timeout=5)
                            
                            if result.get('success', False):
                                order_status = result.get('data', {}).get('status')
                                
                                # 如果订单状态正常，更新时间戳
                                if order_status in ['ALIVE', 'PENDING']:
                                    self._pending_orders[order_id]['timestamp'] = now
                                else:
                                    # 订单已处理，从挂单列表移除
                                    del self._pending_orders[order_id]
                                    
                            else:
                                # 查询失败，可能是订单不存在，尝试恢复
                                self.logger.warning(f"订单 {order_id} 查询失败，尝试恢复")
                                
                                # 重新下单
                                symbol = order_info.get('symbol')
                                direction = order_info.get('direction')
                                offset = order_info.get('offset')
                                volume = order_info.get('volume')
                                price = order_info.get('price')
                                price_type = order_info.get('price_type')
                                
                                # 从挂单列表移除
                                del self._pending_orders[order_id]
                                
                                # 只恢复限价单
                                if price_type == "LIMIT":
                                    self.logger.info(f"重新下单: {symbol} {direction} {offset} {volume}@{price}")
                                    await self.place_order(
                                        symbol=symbol,
                                        direction=direction,
                                        offset=offset,
                                        volume=volume,
                                        price=price,
                                        order_type="LIMIT"
                                    )
                        
                        except Exception as e:
                            self.logger.error(f"订单恢复出错: {str(e)}")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"订单恢复任务出错: {str(e)}")
                await asyncio.sleep(10)  # 发生错误后等待较长时间
    
    # 数据转换方法
    
    def _convert_account(self, account: Account) -> Dict:
        """
        将天勤账户对象转换为标准字典
        
        Args:
            account: 天勤账户对象
            
        Returns:
            Dict: 账户信息字典
        """
        if not account:
            return {}
        
        return {
            'account_id': self.account_id,
            'balance': account.balance,
            'available': account.available,
            'margin': account.margin,
            'frozen_margin': account.frozen_margin,
            'frozen_commission': account.frozen_commission,
            'commission': account.commission,
            'float_profit': account.float_profit,
            'close_profit': account.close_profit,
            'risk_ratio': account.risk_ratio if hasattr(account, 'risk_ratio') else 0,
            'updated_time': datetime.now().isoformat()
        }
    
    def _convert_position(self, position: Position, symbol: str) -> Dict:
        """
        将天勤持仓对象转换为标准字典
        
        Args:
            position: 天勤持仓对象
            symbol: 合约代码
            
        Returns:
            Dict: 持仓信息字典
        """
        if not position:
            return {}
        
        return {
            'symbol': symbol,
            'exchange': position.exchange_id,
            'long_volume': position.long_volume,
            'long_open_price': position.long_open_price,
            'long_float_profit': position.long_float_profit,
            'short_volume': position.short_volume,
            'short_open_price': position.short_open_price,
            'short_float_profit': position.short_float_profit,
            'margin': position.margin,
            'frozen_margin': position.frozen_margin,
            'updated_time': datetime.now().isoformat()
        }
    
    def _convert_order(self, order: Order) -> Dict:
        """
        将天勤订单对象转换为标准字典
        
        Args:
            order: 天勤订单对象
            
        Returns:
            Dict: 订单信息字典
        """
        if not order:
            return {}
        
        # 转换订单状态
        status_map = {
            "ALIVE": OrderStatus.ACCEPTED.value,
            "FINISHED": OrderStatus.FILLED.value,
            "CANCELED": OrderStatus.CANCELLED.value,
            "EXPIRED": OrderStatus.CANCELLED.value,
            "ERROR": OrderStatus.ERROR.value,
            "REJECTED": OrderStatus.REJECTED.value,
        }
        
        status = status_map.get(order.status, OrderStatus.PENDING.value)
        
        # 如果部分成交，状态为部分成交
        if status == OrderStatus.ACCEPTED.value and order.volume_left < order.volume:
            status = OrderStatus.PARTIALLY_FILLED.value
        
        return {
            'order_id': order.order_id,
            'symbol': order.exchange_id + "." + order.instrument_id,
            'direction': "BUY" if order.direction == "BUY" else "SELL",
            'offset': "OPEN" if order.offset == "OPEN" else "CLOSE",
            'volume': order.volume,
            'volume_left': order.volume_left,
            'volume_filled': order.volume - order.volume_left,
            'price': order.limit_price,
            'status': status,
            'order_type': "LIMIT" if order.limit_price != 0 else "MARKET",
            'insert_time': datetime.fromtimestamp(order.insert_date_time / 1e9).isoformat() if order.insert_date_time else None,
            'trade_time': datetime.fromtimestamp(order.last_msg_date_time / 1e9).isoformat() if order.last_msg_date_time else None,
            'updated_time': datetime.now().isoformat(),
            'error_msg': order.last_msg if order.status == "ERROR" or order.status == "REJECTED" else None
        }
    
    def _convert_market_data(self, quote: Quote) -> Dict:
        """
        将天勤行情对象转换为标准字典
        
        Args:
            quote: 天勤行情对象
            
        Returns:
            Dict: 市场数据字典
        """
        if not quote:
            return {}
        
        # 构建统一格式的市场数据字典
        market_data = {
            'symbol': quote.instrument_id,
            'exchange': quote.exchange_id,
            'last_price': quote.last_price,
            'open': quote.open,
            'high': quote.high,
            'low': quote.low,
            'close': quote.close,
            'volume': quote.volume,
            'open_interest': quote.open_interest,
            'upper_limit': quote.upper_limit,
            'lower_limit': quote.lower_limit,
            'pre_close': quote.pre_close,
            'pre_settlement': quote.pre_settlement,
            'pre_open_interest': quote.pre_open_interest,
            
            # 盘口数据
            'ask_price1': quote.ask_price1,
            'ask_volume1': quote.ask_volume1,
            'bid_price1': quote.bid_price1,
            'bid_volume1': quote.bid_volume1,
            
            # 时间信息
            'datetime': datetime.fromtimestamp(quote.datetime / 1e9).isoformat() if quote.datetime else None,
            'updated_time': datetime.now().isoformat()
        }
        
        # 添加扩展的盘口数据（如果有）
        for i in range(2, 6):
            ask_price_key = f'ask_price{i}'
            ask_volume_key = f'ask_volume{i}'
            bid_price_key = f'bid_price{i}'
            bid_volume_key = f'bid_volume{i}'
            
            if hasattr(quote, ask_price_key):
                market_data[ask_price_key] = getattr(quote, ask_price_key)
                market_data[ask_volume_key] = getattr(quote, ask_volume_key)
                market_data[bid_price_key] = getattr(quote, bid_price_key)
                market_data[bid_volume_key] = getattr(quote, bid_volume_key)
        
        return market_data
    
    def _convert_kline(self, kline: Dict) -> Dict:
        """
        转换K线数据
        
        Args:
            kline: 天勤K线数据
            
        Returns:
            Dict: 标准格式K线数据
        """
        # 天勤的K线数据本身就是字典，只需要进行字段名转换
        return {
            'datetime': datetime.fromtimestamp(kline['datetime'] / 1e9).isoformat() if 'datetime' in kline else None,
            'open': kline.get('open', 0),
            'high': kline.get('high', 0),
            'low': kline.get('low', 0),
            'close': kline.get('close', 0),
            'volume': kline.get('volume', 0),
            'open_interest': kline.get('open_oi', 0)
        }
    
    # 异步任务处理系统
    
    async def _create_task(self, task_type: str, **kwargs) -> int:
        """
        创建异步任务
        
        Args:
            task_type: 任务类型
            **kwargs: 任务参数
            
        Returns:
            int: 任务ID
        """
        with self._task_lock:
            task_id = self._next_task_id
            self._next_task_id += 1
            
            # 初始化结果字典
            self._result_dict[task_id] = None
        
        # 创建任务并加入队列
        task = {
            'id': task_id,
            'type': task_type,
            'args': kwargs,
            'timestamp': time.time()
        }
        
        await self._task_queue.put(task)
        
        # 如果是create_api任务，需要启动API线程
        if task_type == 'create_api' and (not self._api_thread or not self._api_thread.is_alive()):
            self._api_thread = threading.Thread(target=self._api_worker, daemon=True)
            self._api_thread.start()
        
        return task_id
    
    async def _wait_for_result(self, task_id: int, timeout: Optional[float] = None) -> Dict:
        """
        等待任务结果
        
        Args:
            task_id: 任务ID
            timeout: 超时时间(秒)
            
        Returns:
            Dict: 任务结果
            
        Raises:
            asyncio.TimeoutError: 如果等待超时
            ValueError: 如果任务ID无效
        """
        if task_id not in self._result_dict:
            raise ValueError(f"无效的任务ID: {task_id}")
        
        start_time = time.time()
        
        while True:
            # 检查结果是否已准备好
            with self._task_lock:
                result = self._result_dict.get(task_id)
                if result is not None:
                    # 清理结果字典
                    del self._result_dict[task_id]
                    return result
            
            # 检查超时
            if timeout is not None and time.time() - start_time > timeout:
                raise asyncio.TimeoutError(f"等待任务 {task_id} 结果超时")
            
            # 短暂休眠
            await asyncio.sleep(0.05)
    
    def _process_api_tasks(self):
        """处理API任务队列"""
        # 处理最多10个任务，防止阻塞太久
        for _ in range(10):
            try:
                # 非阻塞获取任务
                task = self._task_queue.get_nowait()
            except:
                break
            
            task_id = task.get('id')
            task_type = task.get('type')
            task_args = task.get('args', {})
            
            result = {'success': False, 'error': '未知任务类型'}
            
            try:
                if task_type == 'create_api':
                    # API创建已在线程启动时处理
                    continue
                
                elif task_type == 'close_api':
                    self._api_running = False
                    result = {'success': True}
                
                elif task_type == 'subscribe':
                    symbols = task_args.get('symbols', [])
                    for symbol in symbols:
                        self.api.get_quote(symbol)
                    result = {'success': True}
                
                elif task_type == 'get_account':
                    account_info = self._convert_account(self.api.get_account())
                    result = {'success': True, 'data': account_info}
                
                elif task_type == 'get_positions':
                    positions = self._get_positions_info()
                    result = {'success': True, 'data': positions}
                
                elif task_type == 'get_orders':
                    status = task_args.get('status')
                    orders = self._get_orders_info(status)
                    result = {'success': True, 'data': orders}
                
                elif task_type == 'place_order':
                    order_result = self._place_order_impl(
                        symbol=task_args.get('symbol'),
                        direction=task_args.get('direction'),
                        offset=task_args.get('offset'),
                        volume=task_args.get('volume'),
                        price=task_args.get('price'),
                        order_type=task_args.get('order_type')
                    )
                    result = {'success': True, 'data': order_result}
                
                elif task_type == 'cancel_order':
                    order_id = task_args.get('order_id')
                    success = self._cancel_order_impl(order_id)
                    result = {'success': success, 'data': {'order_id': order_id}}
                
                elif task_type == 'get_market_data':
                    symbol = task_args.get('symbol')
                    market_data = self._get_market_data_impl(symbol)
                    result = {'success': True, 'data': market_data}
                
                elif task_type == 'get_klines':
                    klines = self._get_klines_impl(
                        symbol=task_args.get('symbol'),
                        interval=task_args.get('interval'),
                        count=task_args.get('count'),
                        start_time=task_args.get('start_time'),
                        end_time=task_args.get('end_time')
                    )
                    result = {'success': True, 'data': klines}
                
                elif task_type == 'check_order':
                    order_id = task_args.get('order_id')
                    order_info = self._check_order_impl(order_id)
                    result = {'success': True, 'data': order_info}
                
                else:
                    result = {'success': False, 'error': f'未知任务类型: {task_type}'}
            
            except Exception as e:
                error_msg = str(e)
                self.logger.error(f"执行任务 {task_type} 时出错: {error_msg}")
                traceback.print_exc()
                result = {'success': False, 'error': error_msg}
            
            # 保存任务结果
            with self._task_lock:
                if task_id in self._result_dict:
                    self._result_dict[task_id] = result
    
    # 具体任务实现
    
    def _get_positions_info(self) -> List[Dict]:
        """
        获取持仓信息
        
        Returns:
            List[Dict]: 持仓信息列表
        """
        positions = []
        
        # 遍历所有持仓
        for pos_key, pos in self.api.get_position().items():
            # 过滤掉空持仓
            if pos.long_volume == 0 and pos.short_volume == 0:
                continue
            
            # 构建合约代码
            symbol = f"{pos.exchange_id}.{pos.instrument_id}"
            
            # 转换持仓
            pos_info = self._convert_position(pos, symbol)
            positions.append(pos_info)
        
        return positions
    
    def _get_orders_info(self, status: Optional[OrderStatus] = None) -> List[Dict]:
        """
        获取订单信息
        
        Args:
            status: 订单状态过滤
            
        Returns:
            List[Dict]: 订单信息列表
        """
        orders = []
        
        # 转换天勤订单对象
        for order_id, order in self.api.get_order().items():
            order_info = self._convert_order(order)
            
            # 按状态过滤
            if status is None or order_info.get('status') == status.value:
                orders.append(order_info)
        
        return orders
    
    def _place_order_impl(self, symbol: str, direction: str, offset: str, 
                         volume: float, price: Optional[float], 
                         order_type: str) -> Dict:
        """
        下单实现
        
        Args:
            symbol: 合约代码
            direction: 方向
            offset: 开平
            volume: 数量
            price: 价格
            order_type: 订单类型
            
        Returns:
            Dict: 订单信息
        """
        # 解析合约代码
        if "." in symbol:
            exchange_id, instrument_id = symbol.split(".", 1)
        else:
            # 默认为上期所合约
            exchange_id, instrument_id = "SHFE", symbol
        
        # 下单
        if order_type == "MARKET":
            # 市价单，价格设为0
            order = self.api.insert_order(
                instrument_id=instrument_id,
                exchange_id=exchange_id,
                direction=direction,
                offset=offset,
                volume=volume,
                limit_price=0
            )
        else:
            # 限价单
            if price is None:
                raise ValueError("限价单必须指定价格")
            
            order = self.api.insert_order(
                instrument_id=instrument_id,
                exchange_id=exchange_id,
                direction=direction,
                offset=offset,
                volume=volume,
                limit_price=price
            )
        
        # 转换订单信息
        order_info = self._convert_order(order)
        
        # 添加到挂单追踪
        self._pending_orders[order.order_id] = {
            'order_id': order.order_id,
            'symbol': symbol,
            'direction': direction,
            'offset': offset,
            'volume': volume,
            'price': price,
            'price_type': order_type,
            'timestamp': time.time()
        }
        
        return order_info
    
    def _cancel_order_impl(self, order_id: str) -> bool:
        """
        撤单实现
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 撤单是否成功
        """
        # 查找订单
        orders = self.api.get_order()
        if order_id not in orders:
            self.logger.warning(f"撤单失败: 未找到订单 {order_id}")
            return False
        
        # 获取订单对象
        order = orders[order_id]
        
        # 只有活跃订单才能撤销
        if order.status != "ALIVE":
            self.logger.warning(f"撤单失败: 订单 {order_id} 状态为 {order.status}，无法撤销")
            return False
        
        # 撤单
        self.api.cancel_order(order)
        
        # 从挂单追踪中移除
        if order_id in self._pending_orders:
            del self._pending_orders[order_id]
        
        return True
    
    def _get_market_data_impl(self, symbol: str) -> Dict:
        """
        获取市场数据实现
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 市场数据
        """
        # 解析合约代码
        if "." in symbol:
            exchange_id, instrument_id = symbol.split(".", 1)
        else:
            # 尝试从已订阅的合约中找到对应的完整合约代码
            for full_symbol in self._subscribed_symbols:
                if full_symbol.endswith(f".{symbol}"):
                    symbol = full_symbol
                    exchange_id, instrument_id = symbol.split(".", 1)
                    break
            else:
                # 默认为上期所合约
                exchange_id, instrument_id = "SHFE", symbol
        
        # 先检查缓存
        with self._market_data_lock:
            cache_item = self._market_data_cache.get(symbol)
            if cache_item:
                cache_time, cache_data = cache_item
                if time.time() - cache_time < self._market_data_ttl:
                    return cache_data
        
        # 获取行情数据
        quote = self.api.get_quote(instrument_id, exchange_id)
        
        # 转换为标准格式
        market_data = self._convert_market_data(quote)
        
        # 更新缓存
        with self._market_data_lock:
            self._market_data_cache[symbol] = (time.time(), market_data)
        
        return market_data
    
    def _get_klines_impl(self, symbol: str, interval: str, count: int,
                        start_time: Optional[datetime], end_time: Optional[datetime]) -> List[Dict]:
        """
        获取K线数据实现
        
        Args:
            symbol: 合约代码
            interval: K线周期
            count: 数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[Dict]: K线数据列表
        """
        # 解析合约代码
        if "." in symbol:
            exchange_id, instrument_id = symbol.split(".", 1)
        else:
            # 默认为上期所合约
            exchange_id, instrument_id = "SHFE", symbol
        
        # 转换K线周期到天勤格式
        duration_map = {
            "1m": 60,     # 1分钟
            "5m": 300,    # 5分钟
            "15m": 900,   # 15分钟
            "30m": 1800,  # 30分钟
            "1h": 3600,   # 1小时
            "2h": 7200,   # 2小时
            "4h": 14400,  # 4小时
            "1d": "D",    # 日线
            "1w": "W",    # 周线
            "1M": "M",    # 月线
        }
        
        duration = duration_map.get(interval)
        if not duration:
            raise ValueError(f"不支持的K线周期: {interval}")
        
        # 获取K线数据
        klines = self.api.get_kline_serial(
            instrument_id=instrument_id,
            exchange_id=exchange_id,
            duration_seconds=duration if isinstance(duration, int) else None,
            duration_str=duration if isinstance(duration, str) else None,
            data_length=count
        )
        
        # 转换为标准格式
        result = []
        for i in range(len(klines)):
            kline = {
                'datetime': klines['datetime'][i],
                'open': klines['open'][i],
                'high': klines['high'][i],
                'low': klines['low'][i],
                'close': klines['close'][i],
                'volume': klines['volume'][i],
                'open_oi': klines['open_oi'][i] if 'open_oi' in klines else 0
            }
            result.append(self._convert_kline(kline))
        
        # 按时间过滤
        if start_time:
            start_ts = start_time.timestamp()
            result = [k for k in result if datetime.fromisoformat(k['datetime']).timestamp() >= start_ts]
        
        if end_time:
            end_ts = end_time.timestamp()
            result = [k for k in result if datetime.fromisoformat(k['datetime']).timestamp() <= end_ts]
        
        return result
    
    def _check_order_impl(self, order_id: str) -> Dict:
        """
        检查订单状态实现
        
        Args:
            order_id: 订单ID
            
        Returns:
            Dict: 订单信息
        """
        # 查找订单
        orders = self.api.get_order()
        if order_id not in orders:
            raise ValueError(f"未找到订单: {order_id}")
        
        # 获取订单对象
        order = orders[order_id]
        
        # 转换订单信息
        return self._convert_order(order)
                                                