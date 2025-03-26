"""
市场数据服务实现 - 负责市场数据的获取、处理和分发

该服务提供以下功能:
- 多数据源集成和数据一致性处理
- 实时和历史数据提供
- 支持REST API和WebSocket流式数据
- 数据缓存和压缩
- 服务健康监控
"""

import json
import logging
import asyncio
import threading
import time
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime, timedelta
import uuid
import os
import sys

# 假设这些模块已经存在
from core.market.data_provider import DataProvider
from core.market.market_data import MarketData
from data.cache.memory_cache import MemoryCache
from data.time_series.time_series_manager import TimeSeriesManager
from infrastructure.event_bus.event_manager import EventManager

logger = logging.getLogger(__name__)

class MarketDataService:
    """
    市场数据服务 - 提供市场数据的微服务实现
    
    该服务可以作为独立微服务运行，也可以作为库嵌入到主应用中。
    提供市场数据的统一访问接口，负责数据获取、处理和分发。
    """
    
    # 服务状态常量
    STATUS_STOPPED = "stopped"
    STATUS_STARTING = "starting"
    STATUS_RUNNING = "running"
    STATUS_STOPPING = "stopping"
    STATUS_ERROR = "error"
    
    # 数据频率常量
    FREQUENCY_TICK = "tick"
    FREQUENCY_1S = "1s"
    FREQUENCY_1M = "1m"
    FREQUENCY_5M = "5m"
    FREQUENCY_15M = "15m"
    FREQUENCY_30M = "30m"
    FREQUENCY_1H = "1h"
    FREQUENCY_4H = "4h"
    FREQUENCY_1D = "1d"
    
    def __init__(self, 
                config: Optional[Dict[str, Any]] = None,
                data_providers: Optional[List[DataProvider]] = None,
                event_manager: Optional[EventManager] = None,
                cache_size: int = 10000,
                api_port: int = 8001,
                ws_port: int = 8002):
        """
        初始化市场数据服务
        
        Args:
            config: 服务配置
            data_providers: 数据提供者列表
            event_manager: 事件管理器
            cache_size: 缓存大小
            api_port: REST API端口
            ws_port: WebSocket端口
        """
        self.config = config or {}
        self.status = self.STATUS_STOPPED
        self.service_id = str(uuid.uuid4())
        self.start_time = None
        
        # 数据提供者
        self.data_providers = data_providers or []
        self._default_provider = None
        
        # 事件管理器
        self.event_manager = event_manager or EventManager()
        
        # 数据缓存
        self.cache = MemoryCache(name="market_data", max_size=cache_size)
        
        # 时序数据管理
        self.ts_manager = TimeSeriesManager()
        
        # API服务器
        self.api_port = api_port
        self.api_server = None
        
        # WebSocket服务器
        self.ws_port = ws_port
        self.ws_server = None
        self.ws_clients = {}
        
        # 订阅管理
        self.subscriptions = {}
        
        # 运行状态
        self._running = False
        self._main_loop = None
        self._lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_error": 0,
            "data_points_processed": 0,
            "ws_messages_sent": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        logger.info(f"Market Data Service initialized with ID: {self.service_id}")
        
    def start(self) -> bool:
        """
        启动市场数据服务
        
        Returns:
            bool: 是否成功启动
        """
        with self._lock:
            if self.status != self.STATUS_STOPPED:
                logger.warning(f"Cannot start service: current status is {self.status}")
                return False
            
            self.status = self.STATUS_STARTING
            
        try:
            # 初始化数据提供者
            self._init_data_providers()
            
            # 启动API服务器
            self._start_api_server()
            
            # 启动WebSocket服务器
            self._start_ws_server()
            
            # 启动主循环
            self._running = True
            self._main_loop = threading.Thread(target=self._run_main_loop)
            self._main_loop.daemon = True
            self._main_loop.start()
            
            self.start_time = datetime.now()
            self.status = self.STATUS_RUNNING
            logger.info(f"Market Data Service started: {self.service_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Market Data Service: {str(e)}")
            self.status = self.STATUS_ERROR
            return False
    
    def stop(self) -> bool:
        """
        停止市场数据服务
        
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
            
            # 停止WebSocket服务器
            self._stop_ws_server()
            
            # 停止API服务器
            self._stop_api_server()
            
            # 关闭数据提供者
            for provider in self.data_providers:
                try:
                    provider.close()
                except:
                    pass
            
            # 关闭缓存
            self.cache.close()
            
            self.status = self.STATUS_STOPPED
            logger.info(f"Market Data Service stopped: {self.service_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping Market Data Service: {str(e)}")
            self.status = self.STATUS_ERROR
            return False
    
    def get_market_data(self, 
                      symbol: str, 
                      data_type: str = "quote",
                      frequency: str = "1m",
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      count: Optional[int] = None,
                      provider_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取市场数据
        
        Args:
            symbol: 交易品种代码
            data_type: 数据类型 (quote, trade, bar, etc)
            frequency: 数据频率
            start_time: 开始时间
            end_time: 结束时间
            count: 数据点数量
            provider_id: 数据提供者ID，如果为None则使用默认提供者
            
        Returns:
            Dict[str, Any]: 市场数据
        """
        self.stats["requests_total"] += 1
        
        try:
            # 检查缓存
            cache_key = f"{symbol}:{data_type}:{frequency}:{start_time}:{end_time}:{count}"
            cached_data = self.cache.get(cache_key)
            
            if cached_data:
                self.stats["cache_hits"] += 1
                return cached_data
                
            self.stats["cache_misses"] += 1
            
            # 选择数据提供者
            provider = self._get_provider(provider_id)
            if not provider:
                logger.error(f"No data provider available for {provider_id}")
                self.stats["requests_error"] += 1
                return {"error": "No data provider available"}
            
            # 获取数据
            data = provider.get_market_data(
                symbol=symbol,
                data_type=data_type,
                frequency=frequency,
                start_time=start_time,
                end_time=end_time,
                count=count
            )
            
            # 缓存数据
            if data and "error" not in data:
                self.cache.put(cache_key, data, ttl=300)  # 缓存5分钟
                self.stats["requests_success"] += 1
                self.stats["data_points_processed"] += len(data.get("data", []))
            else:
                self.stats["requests_error"] += 1
            
            return data
            
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {str(e)}")
            self.stats["requests_error"] += 1
            return {"error": str(e)}
    
    def subscribe(self, 
                symbol: str, 
                data_type: str = "quote",
                frequency: str = "1m",
                callback: Optional[Callable] = None,
                client_id: Optional[str] = None) -> str:
        """
        订阅市场数据
        
        Args:
            symbol: 交易品种代码
            data_type: 数据类型
            frequency: 数据频率
            callback: 回调函数
            client_id: 客户端ID
            
        Returns:
            str: 订阅ID
        """
        subscription_id = str(uuid.uuid4())
        
        subscription = {
            "id": subscription_id,
            "symbol": symbol,
            "data_type": data_type,
            "frequency": frequency,
            "callback": callback,
            "client_id": client_id,
            "created_at": datetime.now()
        }
        
        self.subscriptions[subscription_id] = subscription
        
        # 如果提供了客户端ID，添加到WebSocket客户端订阅列表
        if client_id and client_id in self.ws_clients:
            if "subscriptions" not in self.ws_clients[client_id]:
                self.ws_clients[client_id]["subscriptions"] = []
            
            self.ws_clients[client_id]["subscriptions"].append(subscription_id)
        
        logger.info(f"New subscription: {subscription_id} for {symbol} {data_type} {frequency}")
        return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        取消订阅
        
        Args:
            subscription_id: 订阅ID
            
        Returns:
            bool: 是否成功取消
        """
        if subscription_id not in self.subscriptions:
            return False
            
        subscription = self.subscriptions[subscription_id]
        client_id = subscription.get("client_id")
        
        # 如果关联了WebSocket客户端，从客户端订阅列表中移除
        if client_id and client_id in self.ws_clients:
            if "subscriptions" in self.ws_clients[client_id]:
                if subscription_id in self.ws_clients[client_id]["subscriptions"]:
                    self.ws_clients[client_id]["subscriptions"].remove(subscription_id)
        
        # 从订阅字典中移除
        del self.subscriptions[subscription_id]
        
        logger.info(f"Subscription removed: {subscription_id}")
        return True
    
    def get_available_symbols(self, provider_id: Optional[str] = None) -> List[str]:
        """
        获取可用的交易品种列表
        
        Args:
            provider_id: 数据提供者ID
            
        Returns:
            List[str]: 可用的交易品种列表
        """
        provider = self._get_provider(provider_id)
        if not provider:
            return []
            
        return provider.get_available_symbols()
    
    def get_trading_hours(self, symbol: str, provider_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取交易时间
        
        Args:
            symbol: 交易品种代码
            provider_id: 数据提供者ID
            
        Returns:
            Dict[str, Any]: 交易时间信息
        """
        provider = self._get_provider(provider_id)
        if not provider:
            return {}
            
        return provider.get_trading_hours(symbol)
    
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
            "providers": [p.provider_id for p in self.data_providers],
            "default_provider": self._default_provider.provider_id if self._default_provider else None,
            "subscriptions_count": len(self.subscriptions),
            "ws_clients_count": len(self.ws_clients),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": uptime,
            "api_port": self.api_port,
            "ws_port": self.ws_port,
            "stats": self.stats
        }
    
    def _init_data_providers(self):
        """初始化数据提供者"""
        if not self.data_providers:
            logger.warning("No data providers specified")
            return
            
        # 设置默认提供者
        self._default_provider = self.data_providers[0]
        
        for provider in self.data_providers:
            try:
                # 初始化数据提供者
                if not provider.is_initialized():
                    provider.initialize()
                    
                logger.info(f"Initialized data provider: {provider.provider_id}")
                
            except Exception as e:
                logger.error(f"Failed to initialize data provider {provider.provider_id}: {str(e)}")
    
    def _get_provider(self, provider_id: Optional[str] = None) -> Optional[DataProvider]:
        """获取数据提供者"""
        if not provider_id:
            return self._default_provider
            
        for provider in self.data_providers:
            if provider.provider_id == provider_id:
                return provider
                
        return self._default_provider
    
    def _start_api_server(self):
        """启动REST API服务器"""
        logger.info(f"REST API server would start on port {self.api_port}")
        # 实际实现会启动一个Web服务器，这里简化处理
        self.api_server = {"status": "running", "port": self.api_port}
    
    def _stop_api_server(self):
        """停止REST API服务器"""
        logger.info("Stopping REST API server")
        self.api_server = None
    
    def _start_ws_server(self):
        """启动WebSocket服务器"""
        logger.info(f"WebSocket server would start on port {self.ws_port}")
        # 实际实现会启动一个WebSocket服务器，这里简化处理
        self.ws_server = {"status": "running", "port": self.ws_port}
    
    def _stop_ws_server(self):
        """停止WebSocket服务器"""
        logger.info("Stopping WebSocket server")
        self.ws_clients = {}
        self.ws_server = None
    
    def _run_main_loop(self):
        """运行主循环，处理数据更新和分发"""
        logger.info("Market data service main loop started")
        
        while self._running:
            try:
                # 获取和处理最新数据
                self._process_data_updates()
                
                # 处理订阅和分发
                self._process_subscriptions()
                
                # 维护缓存
                self._maintain_cache()
                
                # 简化实现，实际应使用异步事件循环
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in market data service main loop: {str(e)}")
                time.sleep(5.0)  # 错误后等待时间长一些
        
        logger.info("Market data service main loop stopped")
    
    def _process_data_updates(self):
        """处理数据更新"""
        # 实际实现会从各数据源获取最新数据并处理
        pass
    
    def _process_subscriptions(self):
        """处理订阅和数据分发"""
        # 实际实现会根据订阅信息分发数据
        pass
    
    def _maintain_cache(self):
        """维护数据缓存"""
        # 自动清理过期数据
        pass
    
    def _send_ws_message(self, client_id: str, message: Dict[str, Any]):
        """发送WebSocket消息"""
        if client_id not in self.ws_clients:
            return
            
        # 实际实现会通过WebSocket发送消息
        logger.debug(f"Would send WS message to {client_id}: {message}")
        self.stats["ws_messages_sent"] += 1
    
    def add_data_provider(self, provider: DataProvider) -> bool:
        """
        添加数据提供者
        
        Args:
            provider: 数据提供者
            
        Returns:
            bool: 是否成功添加
        """
        # 检查是否已存在
        for p in self.data_providers:
            if p.provider_id == provider.provider_id:
                logger.warning(f"Provider {provider.provider_id} already exists")
                return False
        
        # 初始化提供者
        try:
            if not provider.is_initialized():
                provider.initialize()
                
            # 添加到列表
            self.data_providers.append(provider)
            
            # 如果是第一个提供者，设为默认
            if len(self.data_providers) == 1:
                self._default_provider = provider
                
            logger.info(f"Added data provider: {provider.provider_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add data provider {provider.provider_id}: {str(e)}")
            return False
    
    def remove_data_provider(self, provider_id: str) -> bool:
        """
        移除数据提供者
        
        Args:
            provider_id: 数据提供者ID
            
        Returns:
            bool: 是否成功移除
        """
        for i, provider in enumerate(self.data_providers):
            if provider.provider_id == provider_id:
                try:
                    provider.close()
                except:
                    pass
                    
                # 从列表中移除
                self.data_providers.pop(i)
                
                # 如果移除的是默认提供者，重新设置默认提供者
                if self._default_provider and self._default_provider.provider_id == provider_id:
                    self._default_provider = self.data_providers[0] if self.data_providers else None
                
                logger.info(f"Removed data provider: {provider_id}")
                return True
        
        logger.warning(f"Data provider {provider_id} not found")
        return False