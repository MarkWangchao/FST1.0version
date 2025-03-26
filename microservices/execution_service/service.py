"""
执行服务实现 - 负责订单执行和交易管理

该服务提供以下功能:
- 多经纪商/交易所连接和交易执行
- 智能订单路由和执行算法
- 订单生命周期管理
- 执行分析和性能统计
- 风险控制和预执行检查
"""

import json
import logging
import threading
import time
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime, timedelta
import uuid
import os
import sys

# 假设这些模块已经存在
from core.execution.broker import Broker
from core.execution.order import Order, OrderStatus, OrderType, TimeInForce
from core.execution.execution_report import ExecutionReport
from infrastructure.event_bus.event_manager import EventManager
from infrastructure.storage.document.order_store import OrderStore

logger = logging.getLogger(__name__)

class ExecutionService:
    """
    执行服务 - 提供订单执行和交易管理的微服务实现
    
    该服务可以作为独立微服务运行，也可以作为库嵌入到主应用中。
    提供统一的订单管理和执行接口，负责连接多个经纪商/交易所并执行交易指令。
    """
    
    # 服务状态常量
    STATUS_STOPPED = "stopped"
    STATUS_STARTING = "starting"
    STATUS_RUNNING = "running"
    STATUS_STOPPING = "stopping"
    STATUS_ERROR = "error"
    
    def __init__(self, 
                config: Optional[Dict[str, Any]] = None,
                brokers: Optional[List[Broker]] = None,
                event_manager: Optional[EventManager] = None,
                order_store: Optional[OrderStore] = None,
                api_port: int = 8005,
                risk_check_enabled: bool = True):
        """
        初始化执行服务
        
        Args:
            config: 服务配置
            brokers: 经纪商/交易所连接列表
            event_manager: 事件管理器
            order_store: 订单存储
            api_port: REST API端口
            risk_check_enabled: 是否启用风险检查
        """
        self.config = config or {}
        self.status = self.STATUS_STOPPED
        self.service_id = str(uuid.uuid4())
        self.start_time = None
        
        # 经纪商/交易所连接
        self.brokers = brokers or []
        self._default_broker = None
        
        # 事件管理器
        self.event_manager = event_manager or EventManager()
        
        # 订单存储
        self.order_store = order_store or OrderStore()
        
        # API服务器
        self.api_port = api_port
        self.api_server = None
        
        # 风险控制
        self.risk_check_enabled = risk_check_enabled
        
        # 活跃订单管理
        self.active_orders = {}  # order_id -> order
        
        # 执行算法
        self.execution_algos = {}
        
        # 运行状态
        self._running = False
        self._main_loop = None
        self._lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            "orders_total": 0,
            "orders_executed": 0,
            "orders_canceled": 0,
            "orders_rejected": 0,
            "avg_execution_time_ms": 0,
            "total_commissions": 0.0,
            "total_slippage": 0.0,
        }
        
        logger.info(f"Execution Service initialized with ID: {self.service_id}")
    
    def start(self) -> bool:
        """
        启动执行服务
        
        Returns:
            bool: 是否成功启动
        """
        with self._lock:
            if self.status != self.STATUS_STOPPED:
                logger.warning(f"Cannot start service: current status is {self.status}")
                return False
            
            self.status = self.STATUS_STARTING
            
        try:
            # 初始化经纪商连接
            self._init_brokers()
            
            # 启动API服务器
            self._start_api_server()
            
            # 加载执行算法
            self._load_execution_algos()
            
            # 启动主循环
            self._running = True
            self._main_loop = threading.Thread(target=self._run_main_loop)
            self._main_loop.daemon = True
            self._main_loop.start()
            
            self.start_time = datetime.now()
            self.status = self.STATUS_RUNNING
            logger.info(f"Execution Service started: {self.service_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Execution Service: {str(e)}")
            self.status = self.STATUS_ERROR
            return False
    
    def stop(self) -> bool:
        """
        停止执行服务
        
        Returns:
            bool: 是否成功停止
        """
        with self._lock:
            if self.status not in [self.STATUS_RUNNING, self.STATUS_ERROR]:
                logger.warning(f"Cannot stop service: current status is {self.status}")
                return False
                
            self.status = self.STATUS_STOPPING
            
        try:
            # 停止主循环
            self._running = False
            if self._main_loop and self._main_loop.is_alive():
                self._main_loop.join(timeout=5.0)
            
            # 停止API服务器
            self._stop_api_server()
            
            # 关闭经纪商连接
            for broker in self.brokers:
                try:
                    broker.disconnect()
                except:
                    pass
            
            self.status = self.STATUS_STOPPED
            logger.info(f"Execution Service stopped: {self.service_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping Execution Service: {str(e)}")
            self.status = self.STATUS_ERROR
            return False
    
    def place_order(self, order: Order) -> Dict[str, Any]:
        """
        下单
        
        Args:
            order: 订单对象
            
        Returns:
            Dict[str, Any]: 订单提交结果
        """
        self.stats["orders_total"] += 1
        
        try:
            # 为订单生成ID（如果没有）
            if not order.order_id:
                order.order_id = str(uuid.uuid4())
            
            # 设置订单状态为待处理
            order.status = OrderStatus.PENDING
            order.creation_time = datetime.now()
            
            # 执行风险检查
            if self.risk_check_enabled:
                risk_result = self._check_risk(order)
                if not risk_result["passed"]:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = risk_result.get("reason", "Risk check failed")
                    
                    logger.warning(f"Order rejected due to risk check: {order.order_id} - {order.reject_reason}")
                    self.stats["orders_rejected"] += 1
                    
                    # 保存订单
                    self._save_order(order)
                    
                    return {
                        "success": False,
                        "order_id": order.order_id,
                        "status": order.status,
                        "message": order.reject_reason
                    }
            
            # 选择经纪商
            broker = self._get_broker(order.broker_id)
            if not broker:
                order.status = OrderStatus.REJECTED
                order.reject_reason = f"Broker not found: {order.broker_id}"
                
                logger.error(f"Order rejected: {order.order_id} - {order.reject_reason}")
                self.stats["orders_rejected"] += 1
                
                # 保存订单
                self._save_order(order)
                
                return {
                    "success": False,
                    "order_id": order.order_id,
                    "status": order.status,
                    "message": order.reject_reason
                }
            
            # 检查是否使用执行算法
            if order.algo_id and order.algo_id in self.execution_algos:
                # 将订单交给执行算法
                algo = self.execution_algos[order.algo_id]
                result = algo.start(order)
                
                # 添加到活跃订单列表
                self.active_orders[order.order_id] = order
                
                # 保存订单
                self._save_order(order)
                
                return result
            
            # 标准订单执行
            start_time = time.time()
            
            # 将订单提交给经纪商
            broker_result = broker.place_order(order)
            
            end_time = time.time()
            execution_time_ms = (end_time - start_time) * 1000
            
            # 更新订单状态
            if broker_result["success"]:
                order.status = OrderStatus.SUBMITTED
                order.broker_order_id = broker_result.get("broker_order_id")
                
                # 添加到活跃订单列表
                self.active_orders[order.order_id] = order
                
                # 更新统计信息
                current_avg = self.stats["avg_execution_time_ms"]
                order_count = self.stats["orders_total"]
                self.stats["avg_execution_time_ms"] = (current_avg * (order_count - 1) + execution_time_ms) / order_count
                
                logger.info(f"Order submitted: {order.order_id} -> {order.broker_order_id}")
            else:
                order.status = OrderStatus.REJECTED
                order.reject_reason = broker_result.get("message", "Unknown error")
                self.stats["orders_rejected"] += 1
                
                logger.warning(f"Order rejected by broker: {order.order_id} - {order.reject_reason}")
            
            # 保存订单
            self._save_order(order)
            
            # 发布订单事件
            self._publish_order_event(order, "order_submitted" if broker_result["success"] else "order_rejected")
            
            return {
                "success": broker_result["success"],
                "order_id": order.order_id,
                "status": order.status,
                "broker_order_id": order.broker_order_id if broker_result["success"] else None,
                "message": broker_result.get("message")
            }
            
        except Exception as e:
            logger.error(f"Error placing order: {str(e)}")
            
            if order:
                order.status = OrderStatus.REJECTED
                order.reject_reason = f"System error: {str(e)}"
                self.stats["orders_rejected"] += 1
                
                # 保存订单
                self._save_order(order)
                
                # 发布订单事件
                self._publish_order_event(order, "order_rejected")
            
            return {
                "success": False,
                "order_id": order.order_id if order else None,
                "status": OrderStatus.REJECTED,
                "message": f"System error: {str(e)}"
            }
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            Dict[str, Any]: 取消结果
        """
        try:
            # 查找订单
            order = self.active_orders.get(order_id)
            if not order:
                # 尝试从订单存储中加载
                order = self.order_store.get_order(order_id)
                
            if not order:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": "Order not found"
                }
                
            # 检查订单状态
            if order.status not in [OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]:
                return {
                    "success": False,
                    "order_id": order_id,
                    "status": order.status,
                    "message": f"Cannot cancel order with status: {order.status}"
                }
                
            # 选择经纪商
            broker = self._get_broker(order.broker_id)
            if not broker:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": f"Broker not found: {order.broker_id}"
                }
                
            # 发送取消请求给经纪商
            result = broker.cancel_order(order)
            
            # 更新订单状态
            if result["success"]:
                order.status = OrderStatus.CANCELING
                logger.info(f"Cancel request sent for order: {order_id}")
            else:
                logger.warning(f"Failed to cancel order {order_id}: {result.get('message')}")
                
            # 保存订单
            self._save_order(order)
            
            # 发布订单事件
            self._publish_order_event(order, "order_cancel_requested")
            
            return {
                "success": result["success"],
                "order_id": order_id,
                "status": order.status,
                "message": result.get("message")
            }
            
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {str(e)}")
            return {
                "success": False,
                "order_id": order_id,
                "message": f"System error: {str(e)}"
            }
    
    def modify_order(self, order_id: str, modifications: Dict[str, Any]) -> Dict[str, Any]:
        """
        修改订单
        
        Args:
            order_id: 订单ID
            modifications: 要修改的订单属性
            
        Returns:
            Dict[str, Any]: 修改结果
        """
        try:
            # 查找订单
            order = self.active_orders.get(order_id)
            if not order:
                # 尝试从订单存储中加载
                order = self.order_store.get_order(order_id)
                
            if not order:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": "Order not found"
                }
                
            # 检查订单状态
            if order.status not in [OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]:
                return {
                    "success": False,
                    "order_id": order_id,
                    "status": order.status,
                    "message": f"Cannot modify order with status: {order.status}"
                }
                
            # 选择经纪商
            broker = self._get_broker(order.broker_id)
            if not broker:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": f"Broker not found: {order.broker_id}"
                }
                
            # 创建修改后的订单副本
            modified_order = order.copy()
            
            # 应用修改
            for key, value in modifications.items():
                if hasattr(modified_order, key):
                    setattr(modified_order, key, value)
            
            # 执行风险检查
            if self.risk_check_enabled:
                risk_result = self._check_risk(modified_order)
                if not risk_result["passed"]:
                    return {
                        "success": False,
                        "order_id": order_id,
                        "message": risk_result.get("reason", "Risk check failed")
                    }
            
            # 发送修改请求给经纪商
            result = broker.modify_order(order, modified_order)
            
            # 更新订单
            if result["success"]:
                # 应用修改
                for key, value in modifications.items():
                    if hasattr(order, key):
                        setattr(order, key, value)
                
                order.last_modified_time = datetime.now()
                logger.info(f"Order modified: {order_id}")
            else:
                logger.warning(f"Failed to modify order {order_id}: {result.get('message')}")
                
            # 保存订单
            self._save_order(order)
            
            # 发布订单事件
            self._publish_order_event(order, "order_modified")
            
            return {
                "success": result["success"],
                "order_id": order_id,
                "status": order.status,
                "message": result.get("message")
            }
            
        except Exception as e:
            logger.error(f"Error modifying order {order_id}: {str(e)}")
            return {
                "success": False,
                "order_id": order_id,
                "message": f"System error: {str(e)}"
            }
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单信息
        
        Args:
            order_id: 订单ID
            
        Returns:
            Optional[Order]: 订单对象，如果未找到则返回None
        """
        # 先检查活跃订单
        order = self.active_orders.get(order_id)
        if order:
            return order
            
        # 从订单存储中加载
        return self.order_store.get_order(order_id)
    
    def get_orders(self, 
                 account_id: Optional[str] = None,
                 status: Optional[Union[str, List[str]]] = None,
                 symbol: Optional[str] = None,
                 start_time: Optional[datetime] = None,
                 end_time: Optional[datetime] = None,
                 limit: int = 100) -> List[Order]:
        """
        查询订单列表
        
        Args:
            account_id: 账户ID
            status: 订单状态或状态列表
            symbol: 交易品种
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回条数限制
            
        Returns:
            List[Order]: 订单列表
        """
        # 转换状态为列表
        if status and isinstance(status, str):
            status = [status]
            
        # 从订单存储中查询
        return self.order_store.query_orders(
            account_id=account_id,
            status=status,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
    
    def get_positions(self, account_id: str) -> Dict[str, Any]:
        """
        获取账户持仓
        
        Args:
            account_id: 账户ID
            
        Returns:
            Dict[str, Any]: 持仓信息
        """
        # 找到关联的经纪商
        broker = None
        for b in self.brokers:
            if account_id in b.get_accounts():
                broker = b
                break
                
        if not broker:
            return {
                "success": False,
                "message": f"No broker found for account: {account_id}"
            }
            
        # 获取持仓信息
        return broker.get_positions(account_id)
    
    def get_account_info(self, account_id: str) -> Dict[str, Any]:
        """
        获取账户信息
        
        Args:
            account_id: 账户ID
            
        Returns:
            Dict[str, Any]: 账户信息
        """
        # 找到关联的经纪商
        broker = None
        for b in self.brokers:
            if account_id in b.get_accounts():
                broker = b
                break
                
        if not broker:
            return {
                "success": False,
                "message": f"No broker found for account: {account_id}"
            }
            
        # 获取账户信息
        return broker.get_account_info(account_id)
    
    def get_execution_report(self, order_id: str) -> Optional[ExecutionReport]:
        """
        获取执行报告
        
        Args:
            order_id: 订单ID
            
        Returns:
            Optional[ExecutionReport]: 执行报告，如果未找到则返回None
        """
        order = self.get_order(order_id)
        if not order:
            return None
            
        # 获取订单的执行报告
        return self.order_store.get_execution_report(order_id)
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        获取服务状态
        
        Returns:
            Dict[str, Any]: 服务状态信息
        """
        uptime = None
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
            
        return {
            "service_id": self.service_id,
            "status": self.status,
            "brokers": [b.broker_id for b in self.brokers],
            "active_orders_count": len(self.active_orders),
            "risk_check_enabled": self.risk_check_enabled,
            "execution_algos": list(self.execution_algos.keys()),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": uptime,
            "api_port": self.api_port,
            "stats": self.stats
        }
    
    def _init_brokers(self):
        """初始化经纪商连接"""
        if not self.brokers:
            logger.warning("No brokers specified")
            return
            
        # 设置默认经纪商
        self._default_broker = self.brokers[0]
        
        for broker in self.brokers:
            try:
                # 初始化连接
                if not broker.is_connected():
                    broker.connect()
                    
                logger.info(f"Connected to broker: {broker.broker_id}")
                
                # 注册回调
                broker.register_callbacks({
                    "order_status": self._on_order_status_update,
                    "execution": self._on_execution_update,
                    "position": self._on_position_update,
                    "account": self._on_account_update
                })
                
            except Exception as e:
                logger.error(f"Failed to initialize broker {broker.broker_id}: {str(e)}")
    
    def _get_broker(self, broker_id: Optional[str] = None) -> Optional[Broker]:
        """获取经纪商"""
        if not broker_id:
            return self._default_broker
            
        for broker in self.brokers:
            if broker.broker_id == broker_id:
                return broker
                
        return self._default_broker
    
    def _start_api_server(self):
        """启动REST API服务器"""
        logger.info(f"REST API server would start on port {self.api_port}")
        # 实际实现会启动一个Web服务器，这里简化处理
        self.api_server = {"status": "running", "port": self.api_port}
    
    def _stop_api_server(self):
        """停止REST API服务器"""
        logger.info("Stopping REST API server")
        self.api_server = None
    
    def _load_execution_algos(self):
        """加载执行算法"""
        # 实际实现会动态加载算法，这里简化处理
        logger.info("Loading execution algorithms")
        # self.execution_algos = {...}
    
    def _run_main_loop(self):
        """运行主循环，监控订单状态和更新"""
        logger.info("Execution service main loop started")
        
        while self._running:
            try:
                # 处理活跃订单的状态更新
                self._update_active_orders()
                
                # 处理执行算法
                self._update_execution_algos()
                
                # 简化实现，实际应使用异步事件循环
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in execution service main loop: {str(e)}")
                time.sleep(5.0)  # 错误后等待时间长一些
        
        logger.info("Execution service main loop stopped")
    
    def _update_active_orders(self):
        """更新活跃订单状态"""
        # 实际实现会请求最新的订单状态
        for order_id, order in list(self.active_orders.items()):
            if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                # 从活跃订单中移除已完成的订单
                del self.active_orders[order_id]
    
    def _update_execution_algos(self):
        """更新执行算法"""
        # 实际实现会更新各执行算法的状态
        pass
    
    def _check_risk(self, order: Order) -> Dict[str, Any]:
        """
        执行风险检查
        
        Args:
            order: 订单对象
            
        Returns:
            Dict[str, Any]: 风险检查结果
        """
        # 实际实现会执行多种风险检查
        return {"passed": True}
    
    def _save_order(self, order: Order):
        """保存订单到存储"""
        try:
            self.order_store.save_order(order)
        except Exception as e:
            logger.error(f"Error saving order {order.order_id}: {str(e)}")
    
    def _publish_order_event(self, order: Order, event_type: str):
        """发布订单事件"""
        try:
            self.event_manager.publish(event_type, {
                "order_id": order.order_id,
                "broker_order_id": order.broker_order_id,
                "status": order.status,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "filled_quantity": order.filled_quantity,
                "price": order.price,
                "order_type": order.order_type,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error publishing event {event_type} for order {order.order_id}: {str(e)}")
    
    def _on_order_status_update(self, data: Dict[str, Any]):
        """
        订单状态更新回调
        
        Args:
            data: 更新数据
        """
        try:
            broker_order_id = data.get("broker_order_id")
            if not broker_order_id:
                return
                
            # 查找对应的订单
            order = None
            for o in self.active_orders.values():
                if o.broker_order_id == broker_order_id:
                    order = o
                    break
                    
            if not order:
                # 可能是未跟踪的订单，忽略
                return
                
            # 更新订单状态
            old_status = order.status
            order.status = data.get("status", order.status)
            order.filled_quantity = data.get("filled_quantity", order.filled_quantity)
            order.average_price = data.get("average_price", order.average_price)
            order.last_update_time = datetime.now()
            
            # 如果订单已完成
            if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                # 统计信息更新
                if order.status == OrderStatus.FILLED:
                    self.stats["orders_executed"] += 1
                elif order.status == OrderStatus.CANCELED:
                    self.stats["orders_canceled"] += 1
                elif order.status == OrderStatus.REJECTED:
                    self.stats["orders_rejected"] += 1
                    
                # 计算手续费
                if "commission" in data:
                    self.stats["total_commissions"] += data["commission"]
                    
                # 计算滑点
                if "slippage" in data:
                    self.stats["total_slippage"] += data["slippage"]
                    
                # 从活跃订单中移除
                if order.order_id in self.active_orders:
                    del self.active_orders[order.order_id]
            
            # 保存订单
            self._save_order(order)
            
            # 发布事件
            event_type = "order_status_update"
            if old_status != order.status:
                if order.status == OrderStatus.FILLED:
                    event_type = "order_filled"
                elif order.status == OrderStatus.PARTIALLY_FILLED:
                    event_type = "order_partially_filled"
                elif order.status == OrderStatus.CANCELED:
                    event_type = "order_canceled"
                elif order.status == OrderStatus.REJECTED:
                    event_type = "order_rejected"
                    
            self._publish_order_event(order, event_type)
            
        except Exception as e:
            logger.error(f"Error processing order status update: {str(e)}")
    
    def _on_execution_update(self, data: Dict[str, Any]):
        """
        执行更新回调（单笔成交）
        
        Args:
            data: 更新数据
        """
        try:
            broker_order_id = data.get("broker_order_id")
            if not broker_order_id:
                return
                
            # 查找对应的订单
            order = None
            for o in self.active_orders.values():
                if o.broker_order_id == broker_order_id:
                    order = o
                    break
                    
            if not order:
                # 可能是未跟踪的订单，忽略
                return
                
            # 记录执行信息
            execution_id = data.get("execution_id")
            if execution_id:
                # 保存执行信息
                self.order_store.add_execution(order.order_id, data)
                
                # 发布事件
                self.event_manager.publish("order_execution", {
                    "order_id": order.order_id,
                    "broker_order_id": order.broker_order_id,
                    "execution_id": execution_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": data.get("quantity"),
                    "price": data.get("price"),
                    "timestamp": data.get("timestamp") or datetime.now().isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error processing execution update: {str(e)}")
    
    def _on_position_update(self, data: Dict[str, Any]):
        """
        持仓更新回调
        
        Args:
            data: 更新数据
        """
        try:
            # 发布持仓更新事件
            self.event_manager.publish("position_update", data)
        except Exception as e:
            logger.error(f"Error processing position update: {str(e)}")
    
    def _on_account_update(self, data: Dict[str, Any]):
        """
        账户更新回调
        
        Args:
            data: 更新数据
        """
        try:
            # 发布账户更新事件
            self.event_manager.publish("account_update", data)
        except Exception as e:
            logger.error(f"Error processing account update: {str(e)}")
    
    def add_broker(self, broker: Broker) -> bool:
        """
        添加经纪商
        
        Args:
            broker: 经纪商对象
            
        Returns:
            bool: 是否成功添加
        """
        # 检查是否已存在
        for b in self.brokers:
            if b.broker_id == broker.broker_id:
                logger.warning(f"Broker {broker.broker_id} already exists")
                return False
        
        # 初始化连接
        try:
            if not broker.is_connected():
                broker.connect()
                
            # 注册回调
            broker.register_callbacks({
                "order_status": self._on_order_status_update,
                "execution": self._on_execution_update,
                "position": self._on_position_update,
                "account": self._on_account_update
            })
                
            # 添加到列表
            self.brokers.append(broker)
            
            # 如果是第一个经纪商，设为默认
            if len(self.brokers) == 1:
                self._default_broker = broker
                
            logger.info(f"Added broker: {broker.broker_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add broker {broker.broker_id}: {str(e)}")
            return False
    
    def remove_broker(self, broker_id: str) -> bool:
        """
        移除经纪商
        
        Args:
            broker_id: 经纪商ID
            
        Returns:
            bool: 是否成功移除
        """
        for i, broker in enumerate(self.brokers):
            if broker.broker_id == broker_id:
                try:
                    broker.disconnect()
                except:
                    pass
                    
                # 从列表中移除
                self.brokers.pop(i)
                
                # 如果移除的是默认经纪商，重新设置默认经纪商
                if self._default_broker and self._default_broker.broker_id == broker_id:
                    self._default_broker = self.brokers[0] if self.brokers else None
                
                logger.info(f"Removed broker: {broker_id}")
                return True
        
        logger.warning(f"Broker {broker_id} not found")
        return False