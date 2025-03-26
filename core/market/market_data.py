#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 市场数据管理模块

统一管理多数据源的市场数据，提供数据访问、转换和处理功能：
- 多数据源管理与动态切换
- 数据一致性与质量保证
- 历史行情加载与回放
- 技术指标计算与自定义数据处理
- 事件驱动的市场数据更新广播
- 高效缓存与数据分发
"""

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Union, Set, Tuple, Callable, Any
import copy
import json
import threading
from functools import lru_cache
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from tqsdk import TqApi, TqAuth, TqAccount
    HAS_TQSDK = True
except ImportError:
    HAS_TQSDK = False

# 导入数据提供者
from core.market.data_provider import DataProvider
from infrastructure.api.broker_adapter import BrokerAdapter

# 导入事件总线
from core.event.event_bus import EventBus, Event, EventType

# 设置日志记录器
logger = logging.getLogger("fst.core.market.market_data")

class DataSourceType(str, Enum):
    """数据源类型枚举"""
    BROKER = "BROKER"         # 券商接口
    TQSDK = "TQSDK"           # 天勤SDK
    CTP = "CTP"               # CTP接口
    PLAYBACK = "PLAYBACK"     # 回放数据
    CSV = "CSV"               # CSV文件
    CUSTOM = "CUSTOM"         # 自定义数据源


class DataSourceConfig:
    """数据源配置"""
    
    def __init__(self, 
                 source_id: str = None,
                 source_type: DataSourceType = DataSourceType.BROKER,
                 name: str = "",
                 description: str = "",
                 priority: int = 0,
                 config: Dict[str, Any] = None):
        """
        初始化数据源配置
        
        Args:
            source_id: 数据源ID
            source_type: 数据源类型
            name: 数据源名称
            description: 数据源描述
            priority: 优先级（数字越小优先级越高）
            config: 数据源配置参数
        """
        self.source_id = source_id or f"ds_{uuid.uuid4().hex[:8]}"
        self.source_type = source_type
        self.name = name or f"{source_type} Source"
        self.description = description
        self.priority = priority
        self.config = config or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "config": self.config
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DataSourceConfig':
        """从字典创建数据源配置"""
        return cls(
            source_id=data.get("source_id"),
            source_type=data.get("source_type", DataSourceType.BROKER),
            name=data.get("name", ""),
            description=data.get("description", ""),
            priority=data.get("priority", 0),
            config=data.get("config", {})
        )


class DataSource:
    """数据源基类"""
    
    def __init__(self, config: DataSourceConfig):
        """
        初始化数据源
        
        Args:
            config: 数据源配置
        """
        self.config = config
        self.logger = logging.getLogger(f"fst.core.market.source.{config.source_id}")
        self.connected = False
        self.last_heartbeat = time.time()
        self.subscriptions = set()
        self.stats = {
            "requests": 0,
            "errors": 0,
            "data_updates": 0,
            "connect_attempts": 0,
            "subscription_count": 0,
        }
    
    async def connect(self) -> bool:
        """
        连接数据源
        
        Returns:
            bool: 是否成功连接
        """
        # 基类方法，由子类实现
        return False
    
    async def disconnect(self) -> bool:
        """
        断开数据源连接
        
        Returns:
            bool: 是否成功断开
        """
        # 基类方法，由子类实现
        return False
    
    async def subscribe(self, symbols: Union[str, List[str]]) -> bool:
        """
        订阅合约
        
        Args:
            symbols: 合约代码或列表
            
        Returns:
            bool: 是否成功订阅
        """
        # 基类方法，由子类实现
        return False
    
    async def unsubscribe(self, symbols: Union[str, List[str]]) -> bool:
        """
        取消订阅合约
        
        Args:
            symbols: 合约代码或列表
            
        Returns:
            bool: 是否成功取消订阅
        """
        # 基类方法，由子类实现
        return False
    
    async def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取市场行情数据
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 市场数据
        """
        # 基类方法，由子类实现
        self.stats["requests"] += 1
        return {}
    
    async def get_klines(self, symbol: str, 
                         interval: str, 
                         count: int = 200,
                         start_time: Optional[datetime] = None, 
                         end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            interval: K线周期 (1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 1M)
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[Dict]: K线数据列表
        """
        # 基类方法，由子类实现
        self.stats["requests"] += 1
        return []
    
    async def get_ticks(self, symbol: str, 
                       count: int = 100,
                       start_time: Optional[datetime] = None, 
                       end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        获取Tick数据
        
        Args:
            symbol: 合约代码
            count: 获取数量 
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[Dict]: Tick数据列表
        """
        # 基类方法，由子类实现
        self.stats["requests"] += 1
        return []
    
    async def get_instrument_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取合约信息
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 合约信息
        """
        # 基类方法，由子类实现
        self.stats["requests"] += 1
        return {}
    
    async def is_alive(self) -> bool:
        """
        检查数据源是否活跃
        
        Returns:
            bool: 是否活跃
        """
        return self.connected and time.time() - self.last_heartbeat < 30
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取数据源统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            "source_id": self.config.source_id,
            "name": self.config.name,
            "type": self.config.source_type,
            "connected": self.connected,
            "last_heartbeat": self.last_heartbeat,
            "subscription_count": len(self.subscriptions),
            "stats": copy.deepcopy(self.stats)
        }

class BrokerDataSource(DataSource):
    """券商数据源实现，基于DataProvider"""
    
    def __init__(self, config: DataSourceConfig, broker_adapter: BrokerAdapter):
        """
        初始化券商数据源
        
        Args:
            config: 数据源配置
            broker_adapter: 券商适配器
        """
        super().__init__(config)
        self.broker_adapter = broker_adapter
        self.data_provider = None
        self.logger.info(f"创建券商数据源: {config.name}")
    
    async def connect(self) -> bool:
        """
        连接数据源
        
        Returns:
            bool: 是否成功连接
        """
        self.stats["connect_attempts"] += 1
        
        try:
            # 创建数据提供者
            self.data_provider = DataProvider(
                self.broker_adapter,
                cache_size=self.config.config.get("cache_size", 10000),
                enable_redis=self.config.config.get("enable_redis", False),
                redis_url=self.config.config.get("redis_url")
            )
            
            # 启动数据提供者
            await self.data_provider.start()
            
            self.connected = True
            self.last_heartbeat = time.time()
            self.logger.info(f"已连接到券商数据源: {self.config.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"连接券商数据源失败: {e}")
            self.stats["errors"] += 1
            return False
    
    async def disconnect(self) -> bool:
        """
        断开数据源连接
        
        Returns:
            bool: 是否成功断开
        """
        try:
            if self.data_provider:
                await self.data_provider.stop()
                self.data_provider = None
            
            self.connected = False
            self.logger.info(f"已断开券商数据源连接: {self.config.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"断开券商数据源连接失败: {e}")
            self.stats["errors"] += 1
            return False
    
    async def subscribe(self, symbols: Union[str, List[str]]) -> bool:
        """
        订阅合约
        
        Args:
            symbols: 合约代码或列表
            
        Returns:
            bool: 是否成功订阅
        """
        if not self.connected or not self.data_provider:
            self.logger.warning("数据源未连接，无法订阅")
            return False
        
        if isinstance(symbols, str):
            symbols = [symbols]
            
        success = True
        for symbol in symbols:
            try:
                if symbol in self.subscriptions:
                    continue
                
                result = await self.data_provider.subscribe_symbol(symbol)
                if result:
                    self.subscriptions.add(symbol)
                    self.stats["subscription_count"] = len(self.subscriptions)
                    self.logger.info(f"订阅合约成功: {symbol}")
                else:
                    self.logger.warning(f"订阅合约失败: {symbol}")
                    success = False
                    
            except Exception as e:
                self.logger.error(f"订阅合约出错: {symbol}, {e}")
                self.stats["errors"] += 1
                success = False
                
        return success
    
    async def unsubscribe(self, symbols: Union[str, List[str]]) -> bool:
        """
        取消订阅合约
        
        Args:
            symbols: 合约代码或列表
            
        Returns:
            bool: 是否成功取消订阅
        """
        if not self.connected or not self.data_provider:
            return True
        
        if isinstance(symbols, str):
            symbols = [symbols]
            
        success = True
        for symbol in symbols:
            try:
                if symbol not in self.subscriptions:
                    continue
                
                result = await self.data_provider.unsubscribe_symbol(symbol)
                if result:
                    self.subscriptions.discard(symbol)
                    self.stats["subscription_count"] = len(self.subscriptions)
                    self.logger.info(f"取消订阅合约成功: {symbol}")
                else:
                    self.logger.warning(f"取消订阅合约失败: {symbol}")
                    success = False
                    
            except Exception as e:
                self.logger.error(f"取消订阅合约出错: {symbol}, {e}")
                self.stats["errors"] += 1
                success = False
                
        return success
    
    async def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取市场行情数据
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 市场数据
        """
        if not self.connected or not self.data_provider:
            self.logger.warning("数据源未连接，无法获取市场数据")
            return {}
        
        self.stats["requests"] += 1
        self.last_heartbeat = time.time()
        
        try:
            data = await self.data_provider.get_market_data(symbol)
            self.stats["data_updates"] += 1
            return data
            
        except Exception as e:
            self.logger.error(f"获取市场数据出错: {symbol}, {e}")
            self.stats["errors"] += 1
            return {}
    
    async def get_klines(self, symbol: str, 
                       interval: str, 
                       count: int = 200,
                       start_time: Optional[datetime] = None, 
                       end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            interval: K线周期
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[Dict]: K线数据列表
        """
        if not self.connected or not self.data_provider:
            self.logger.warning("数据源未连接，无法获取K线数据")
            return []
        
        self.stats["requests"] += 1
        self.last_heartbeat = time.time()
        
        try:
            klines_df = await self.data_provider.get_klines(
                symbol=symbol,
                interval=interval,
                count=count,
                start_time=start_time,
                end_time=end_time
            )
            
            # 将DataFrame转换为列表
            klines_list = []
            for idx, row in klines_df.iterrows():
                kline = row.to_dict()
                kline["datetime"] = idx.isoformat()
                klines_list.append(kline)
                
            self.stats["data_updates"] += 1
            return klines_list
            
        except Exception as e:
            self.logger.error(f"获取K线数据出错: {symbol}, {interval}, {e}")
            self.stats["errors"] += 1
            return []


class TqsdkDataSource(DataSource):
    """天勤SDK数据源实现"""
    
    def __init__(self, config: DataSourceConfig):
        """
        初始化天勤SDK数据源
        
        Args:
            config: 数据源配置
        """
        super().__init__(config)
        self.api = None
        self.api_task = None
        self.tick_callbacks = {}
        self.kline_serials = {}
        self.subscribe_tasks = {}
        self.logger.info(f"创建天勤SDK数据源: {config.name}")
    
    async def connect(self) -> bool:
        """
        连接天勤SDK
        
        Returns:
            bool: 是否成功连接
        """
        if not HAS_TQSDK:
            self.logger.error("未安装天勤SDK，无法创建天勤数据源")
            return False
        
        self.stats["connect_attempts"] += 1
        
        try:
            from tqsdk import TqApi, TqAuth, TqAccount, TqSim
            
            # 创建API配置
            auth_config = self.config.config.get("auth", {})
            account_config = self.config.config.get("account", {})
            
            auth = None
            if auth_config.get("username") and auth_config.get("password"):
                auth = TqAuth(auth_config["username"], auth_config["password"])
            
            # 创建账户
            account = None
            if account_config.get("type") == "sim":
                # 模拟账户
                init_balance = account_config.get("init_balance", 1000000)
                account = TqSim(init_balance=init_balance)
            elif account_config.get("type") == "account":
                # 实盘账户
                broker_id = account_config.get("broker_id", "")
                account_id = account_config.get("account_id", "")
                password = account_config.get("password", "")
                
                if broker_id and account_id and password:
                    account = TqAccount(broker_id, account_id, password)
                else:
                    self.logger.warning("实盘账户配置不完整，使用模拟账户")
                    account = TqSim()
            else:
                # 默认使用模拟账户
                account = TqSim()
            
            # 创建API
            self.api = TqApi(account, auth=auth)
            
            # 创建API任务
            loop = asyncio.get_event_loop()
            self.api_task = loop.create_task(self._api_background_task())
            
            self.connected = True
            self.last_heartbeat = time.time()
            self.logger.info(f"已连接到天勤SDK: {self.config.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"连接天勤SDK失败: {e}")
            self.stats["errors"] += 1
            return False
    
    async def _api_background_task(self):
        """天勤API后台任务，保持API连接"""
        try:
            await self.api.wait_update()
            while True:
                self.last_heartbeat = time.time()
                await self.api.wait_update()
                self.stats["data_updates"] += 1
                
                # 处理更新的数据
                await self._process_api_updates()
                
        except asyncio.CancelledError:
            self.logger.info("天勤API任务被取消")
            if self.api:
                await self.api.close()
            
        except Exception as e:
            self.logger.error(f"天勤API任务出错: {e}")
            self.stats["errors"] += 1
            if self.api:
                try:
                    await self.api.close()
                except:
                    pass
            
            self.connected = False
    
    async def _process_api_updates(self):
        """处理API数据更新"""
        # 处理更新的合约
        for symbol in list(self.subscriptions):
            # 处理Tick回调
            if symbol in self.tick_callbacks:
                try:
                    tick = self.api.get_tick(symbol)
                    for callback in self.tick_callbacks.get(symbol, []):
                        if asyncio.iscoroutinefunction(callback):
                            asyncio.create_task(callback(tick))
                        else:
                            callback(tick)
                except Exception as e:
                    self.logger.error(f"处理Tick回调出错: {symbol}, {e}")
    
    async def disconnect(self) -> bool:
        """
        断开天勤SDK连接
        
        Returns:
            bool: 是否成功断开
        """
        try:
            # 取消所有订阅任务
            for symbol, task in self.subscribe_tasks.items():
                if not task.done():
                    task.cancel()
                    
            # 关闭API
            if self.api_task and not self.api_task.done():
                self.api_task.cancel()
                try:
                    await self.api_task
                except (asyncio.CancelledError, Exception):
                    pass
                
            if self.api:
                await self.api.close()
                self.api = None
                
            self.connected = False
            self.logger.info(f"已断开天勤SDK连接: {self.config.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"断开天勤SDK连接失败: {e}")
            self.stats["errors"] += 1
            return False
    
    async def subscribe(self, symbols: Union[str, List[str]]) -> bool:
        """
        订阅合约
        
        Args:
            symbols: 合约代码或列表
            
        Returns:
            bool: 是否成功订阅
        """
        if not self.connected or not self.api:
            self.logger.warning("天勤SDK未连接，无法订阅")
            return False
            
        if isinstance(symbols, str):
            symbols = [symbols]
            
        success = True
        
        for symbol in symbols:
            try:
                if symbol in self.subscriptions:
                    continue
                    
                # 订阅Tick数据
                self.api.get_tick_serial(symbol)
                
                # 创建数据处理任务
                task = asyncio.create_task(self._process_symbol_data(symbol))
                self.subscribe_tasks[symbol] = task
                
                self.subscriptions.add(symbol)
                self.stats["subscription_count"] = len(self.subscriptions)
                self.logger.info(f"订阅合约成功: {symbol}")
                
            except Exception as e:
                self.logger.error(f"订阅合约失败: {symbol}, {e}")
                self.stats["errors"] += 1
                success = False
                
        return success
    
    async def _process_symbol_data(self, symbol: str):
        """
        处理合约数据
        
        Args:
            symbol: 合约代码
        """
        try:
            while self.connected and symbol in self.subscriptions:
                await self.api.wait_update()
                # 处理更新的数据
                try:
                    tick = self.api.get_tick(symbol)
                    # 回调处理
                    for callback in self.tick_callbacks.get(symbol, []):
                        if asyncio.iscoroutinefunction(callback):
                            asyncio.create_task(callback(tick))
                        else:
                            callback(tick)
                except Exception as e:
                    self.logger.error(f"处理合约数据出错: {symbol}, {e}")
                
                # 防止过快循环
                await asyncio.sleep(0.001)
                
        except asyncio.CancelledError:
            self.logger.info(f"合约数据处理任务取消: {symbol}")
        except Exception as e:
            self.logger.error(f"合约数据处理任务出错: {symbol}, {e}")
    
    async def unsubscribe(self, symbols: Union[str, List[str]]) -> bool:
        """
        取消订阅合约
        
        Args:
            symbols: 合约代码或列表
            
        Returns:
            bool: 是否成功取消订阅
        """
        if isinstance(symbols, str):
            symbols = [symbols]
            
        success = True
        
        for symbol in symbols:
            try:
                if symbol not in self.subscriptions:
                    continue
                
                # 取消订阅任务
                if symbol in self.subscribe_tasks:
                    task = self.subscribe_tasks.pop(symbol)
                    if not task.done():
                        task.cancel()
                        
                # 移除回调
                if symbol in self.tick_callbacks:
                    del self.tick_callbacks[symbol]
                
                # 移除订阅记录
                self.subscriptions.discard(symbol)
                self.stats["subscription_count"] = len(self.subscriptions)
                self.logger.info(f"取消订阅合约成功: {symbol}")
                
            except Exception as e:
                self.logger.error(f"取消订阅合约失败: {symbol}, {e}")
                self.stats["errors"] += 1
                success = False
                
        return success
    
    async def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取市场行情数据
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict: 市场数据
        """
        if not self.connected or not self.api:
            self.logger.warning("天勤SDK未连接，无法获取市场数据")
            return {}
        
        self.stats["requests"] += 1
        self.last_heartbeat = time.time()
        
        try:
            # 获取行情数据
            quote = self.api.get_quote(symbol)
            
            # 转换为标准格式
            market_data = {
                "symbol": symbol,
                "datetime": datetime.fromtimestamp(quote.datetime / 1e9).isoformat(),
                "last_price": quote.last_price,
                "volume": quote.volume,
                "open_interest": quote.open_interest,
                "open": quote.open,
                "high": quote.high,
                "low": quote.low,
                "close": quote.close,
                "limit_up": quote.upper_limit,
                "limit_down": quote.lower_limit,
                "ask_price1": quote.ask_price1,
                "ask_volume1": quote.ask_volume1,
                "bid_price1": quote.bid_price1,
                "bid_volume1": quote.bid_volume1,
                "updated_time": time.time()
            }
            
            self.stats["data_updates"] += 1
            return market_data
            
        except Exception as e:
            self.logger.error(f"获取市场数据出错: {symbol}, {e}")
            self.stats["errors"] += 1
            return {}
    
    async def get_klines(self, symbol: str, 
                       interval: str, 
                       count: int = 200,
                       start_time: Optional[datetime] = None, 
                       end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            interval: K线周期
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            List[Dict]: K线数据列表
        """
        if not self.connected or not self.api:
            self.logger.warning("天勤SDK未连接，无法获取K线数据")
            return []
        
        self.stats["requests"] += 1
        self.last_heartbeat = time.time()
        
        try:
            # 转换K线周期格式
            duration = self._convert_interval_to_seconds(interval)
            
            # 获取K线数据
            kline_serial_key = f"{symbol}_{interval}"
            
            if kline_serial_key not in self.kline_serials:
                self.kline_serials[kline_serial_key] = self.api.get_kline_serial(symbol, duration, count * 2)
            
            klines = self.kline_serials[kline_serial_key]
            
            # 转换为标准格式
            kline_list = []
            for i in range(min(len(klines), count)):
                k = klines.iloc[-(i+1)]
                kline = {
                    "datetime": datetime.fromtimestamp(k["datetime"] / 1e9).isoformat(),
                    "open": k["open"],
                    "high": k["high"],
                    "low": k["low"],
                    "close": k["close"],
                    "volume": k["volume"],
                    "open_interest": k["open_interest"]
                }
                kline_list.append(kline)
            
            # 过滤时间范围
            if start_time or end_time:
                filtered_klines = []
                for k in kline_list:
                    ktime = datetime.fromisoformat(k["datetime"])
                    if start_time and ktime < start_time:
                        continue
                    if end_time and ktime > end_time:
                        continue
                    filtered_klines.append(k)
                kline_list = filtered_klines
            
            # 反转列表使其按时间正序排列
            kline_list.reverse()
            
            self.stats["data_updates"] += 1
            return kline_list
            
        except Exception as e:
            self.logger.error(f"获取K线数据出错: {symbol}, {interval}, {e}")
            self.stats["errors"] += 1
            return []
    
    def _convert_interval_to_seconds(self, interval: str) -> int:
        """
        转换K线周期为秒数
        
        Args:
            interval: K线周期字符串 ('1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w', '1M')
            
        Returns:
            int: 周期秒数
        """
        # 定义转换表
        mapping = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '30m': 1800,
            '1h': 3600,
            '2h': 7200,
            '4h': 14400,
            '1d': 86400,
            '1w': 604800,
            '1M': 2592000  # 30天
        }
        
        if interval in mapping:
            return mapping[interval]
        
        # 解析自定义格式
        import re
        match = re.match(r'(\d+)([mhdwM])', interval)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            
            if unit == 'm':
                return value * 60
            elif unit == 'h':
                return value * 3600
            elif unit == 'd':
                return value * 86400
            elif unit == 'w':
                return value * 604800
            elif unit == 'M':
                return value * 2592000
        
        # 默认返回1分钟
        self.logger.warning(f"未知的K线周期格式: {interval}，使用默认值60秒")
        return 60


class MarketDataManager:
    """市场数据管理器，统一管理和提供市场数据"""
    
    def __init__(self, broker_adapter: Optional[BrokerAdapter] = None, event_bus: Optional[EventBus] = None):
        """
        初始化市场数据管理器
        
        Args:
            broker_adapter: 券商适配器
            event_bus: 事件总线
        """
        self.logger = logging.getLogger("fst.core.market.manager")
        self.broker_adapter = broker_adapter
        self.event_bus = event_bus
        
        # 数据源管理
        self.data_sources = {}  # source_id -> DataSource
        self.source_configs = {}  # source_id -> DataSourceConfig
        self.primary_source_map = {}  # symbol -> source_id
        
        # 合约订阅状态
        self.subscribed_symbols = set()
        
        # 合约信息缓存
        self.instrument_cache = {}
        
        # 任务管理
        self.tasks = []
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # 性能统计
        self.stats = {
            "requests": 0,
            "errors": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        # 合约信息配置路径
        self.instruments_dir = Path("data/instruments")
        self.instruments_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("市场数据管理器初始化完成")
    
    async def start(self) -> bool:
        """
        启动市场数据管理器
        
        Returns:
            bool: 是否成功启动
        """
        if self.running:
            return True
        
        self.logger.info("启动市场数据管理器")
        
        # 加载合约信息缓存
        await self._load_instrument_cache()
        
        # 启动数据源
        for source_id, source in self.data_sources.items():
            try:
                success = await source.connect()
                if not success:
                    self.logger.warning(f"数据源连接失败: {source_id}")
                    
            except Exception as e:
                self.logger.error(f"启动数据源出错: {source_id}, {e}")
                self.stats["errors"] += 1
        
        # 启动心跳检测任务
        heartbeat_task = asyncio.create_task(self._heartbeat_task())
        self.tasks.append(heartbeat_task)
        
        self.running = True
        self.logger.info("市场数据管理器启动完成")
        return True
    
    async def stop(self) -> bool:
        """
        停止市场数据管理器
        
        Returns:
            bool: 是否成功停止
        """
        if not self.running:
            return True
        
        self.logger.info("停止市场数据管理器")
        
        # 设置关闭事件
        self.shutdown_event.set()
        
        # 取消所有任务
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # 等待任务取消
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.tasks.clear()
        
        # 断开所有数据源
        for source_id, source in self.data_sources.items():
            try:
                await source.disconnect()
            except Exception as e:
                self.logger.error(f"断开数据源出错: {source_id}, {e}")
        
        self.running = False
        self.logger.info("市场数据管理器已停止")
        return True
    
    async def add_data_source(self, config: DataSourceConfig) -> bool:
        
        """
        添加数据源
        
        Args:
            config: 数据源配置
            
        Returns:
            bool: 是否成功添加
        """
        source_id = config.source_id or str(uuid.uuid4())
        
        # 检查是否已存在
        if source_id in self.data_sources:
            self.logger.warning(f"数据源已存在: {source_id}")
            return False
        
        self.logger.info(f"添加数据源: {source_id}, 类型: {config.source_type}")
        
        try:
            # 创建数据源
            if config.source_type == DataSourceType.BROKER:
                # 使用券商适配器
                broker_adapter = self.broker_adapter
                if not broker_adapter:
                    self.logger.error("添加券商数据源失败: 券商适配器未设置")
                    return False
                
                data_source = BrokerDataSource(
                    source_id=source_id,
                    name=config.name,
                    broker_adapter=broker_adapter,
                    config=config.config
                )
                
            elif config.source_type == DataSourceType.TQSDK:
                if not HAS_TQSDK:
                    self.logger.error("添加天勤数据源失败: 缺少tqsdk依赖")
                    return False
                
                # 创建天勤数据源
                data_source = TqsdkDataSource(
                    source_id=source_id,
                    name=config.name,
                    config=config.config
                )
                
            elif config.source_type == DataSourceType.PLAYBACK:
                # 创建回放数据源
                data_source = PlaybackDataSource(
                    source_id=source_id,
                    name=config.name,
                    config=config.config
                )
                
            else:
                self.logger.error(f"不支持的数据源类型: {config.source_type}")
                return False
            
            # 保存数据源
            self.data_sources[source_id] = data_source
            self.source_priorities[source_id] = config.priority
            
            # 如果管理器已启动，则连接数据源
            if self.running:
                success = await data_source.connect()
                if not success:
                    self.logger.warning(f"数据源连接失败: {source_id}")
            
            # 发布数据源添加事件
            await self.event_bus.publish(Event(
                event_type=EventType.MARKET_DATA_SOURCE_ADDED,
                data={
                    "source_id": source_id,
                    "source_type": config.source_type,
                    "name": config.name
                }
            ))
            
            return True
            
        except Exception as e:
            self.logger.error(f"添加数据源出错: {e}")
            self.stats["errors"] += 1
            return False
    
    async def remove_data_source(self, source_id: str) -> bool:
        """
        移除数据源
        
        Args:
            source_id: 数据源ID
            
        Returns:
            bool: 是否成功移除
        """
        if source_id not in self.data_sources:
            self.logger.warning(f"数据源不存在: {source_id}")
            return False
        
        self.logger.info(f"移除数据源: {source_id}")
        
        try:
            # 断开数据源连接
            await self.data_sources[source_id].disconnect()
            
            # 移除数据源
            data_source = self.data_sources.pop(source_id)
            self.source_priorities.pop(source_id, None)
            
            # 发布数据源移除事件
            await self.event_bus.publish(Event(
                event_type=EventType.MARKET_DATA_SOURCE_REMOVED,
                data={
                    "source_id": source_id,
                    "name": data_source.name
                }
            ))
            
            return True
            
        except Exception as e:
            self.logger.error(f"移除数据源出错: {e}")
            self.stats["errors"] += 1
            return False
    
    async def get_market_data(self, symbol: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取市场数据
        
        Args:
            symbol: 合约代码
            use_cache: 是否使用缓存
            
        Returns:
            Dict[str, Any]: 市场数据
        """
        self.stats["requests"] += 1
        
        # 检查缓存
        if use_cache:
            cached_data = self.market_data_cache.get(symbol)
            if cached_data and (time.time() - cached_data.get("_update_time", 0) < self.cache_ttl):
                self.stats["cache_hits"] += 1
                return copy.deepcopy(cached_data)
        
        # 按优先级排序的数据源ID列表
        sorted_sources = sorted(
            self.data_sources.keys(),
            key=lambda source_id: self.source_priorities.get(source_id, 0),
            reverse=True  # 优先级高的排在前面
        )
        
        # 尝试从各数据源获取
        errors = []
        for source_id in sorted_sources:
            data_source = self.data_sources[source_id]
            
            try:
                market_data = await data_source.get_market_data(symbol)
                if market_data:
                    # 添加数据源信息
                    market_data["_source"] = source_id
                    market_data["_update_time"] = time.time()
                    
                    # 更新缓存
                    self.market_data_cache[symbol] = copy.deepcopy(market_data)
                    
                    # 更新最后活跃时间
                    self.last_active_time[source_id] = time.time()
                    
                    return market_data
                    
            except Exception as e:
                error_msg = f"从数据源 {source_id} 获取 {symbol} 行情失败: {e}"
                self.logger.warning(error_msg)
                errors.append(error_msg)
                self.stats["errors"] += 1
        
        # 所有数据源都失败
        if errors:
            self.logger.error(f"获取 {symbol} 行情失败: {errors}")
            
        # 返回缓存中的旧数据，即使已过期
        if symbol in self.market_data_cache:
            self.logger.warning(f"返回过期缓存数据: {symbol}")
            return copy.deepcopy(self.market_data_cache[symbol])
            
        return {}
    
    async def get_klines(self, symbol: str, interval: str, count: int = 200,
                         start_time: Optional[datetime] = None, 
                         end_time: Optional[datetime] = None,
                         use_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        获取K线数据
        
        Args:
            symbol: 合约代码
            interval: K线周期 ('1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w', '1M')
            count: 获取数量
            start_time: 开始时间
            end_time: 结束时间
            use_cache: 是否使用缓存
            
        Returns:
            pd.DataFrame: K线数据DataFrame
        """
        if not HAS_PANDAS:
            self.logger.error("获取K线数据失败: 缺少pandas依赖")
            return None
            
        self.stats["kline_requests"] += 1
        
        # 检查缓存
        cache_key = f"{symbol}:{interval}"
        if use_cache and cache_key in self.kline_cache:
            cached_klines, update_time = self.kline_cache[cache_key]
            
            if time.time() - update_time < self.cache_ttl:
                # 过滤时间范围
                filtered_klines = cached_klines
                if start_time:
                    filtered_klines = filtered_klines[filtered_klines.index >= pd.Timestamp(start_time)]
                if end_time:
                    filtered_klines = filtered_klines[filtered_klines.index <= pd.Timestamp(end_time)]
                
                # 如果缓存数据足够，直接返回
                if len(filtered_klines) >= count:
                    self.stats["kline_cache_hits"] += 1
                    return filtered_klines.tail(count).copy()
        
        # 按优先级排序的数据源ID列表
        sorted_sources = sorted(
            self.data_sources.keys(),
            key=lambda source_id: self.source_priorities.get(source_id, 0),
            reverse=True
        )
        
        # 尝试从各数据源获取
        errors = []
        for source_id in sorted_sources:
            data_source = self.data_sources[source_id]
            
            try:
                klines_df = await data_source.get_klines(
                    symbol=symbol,
                    interval=interval,
                    count=count,
                    start_time=start_time,
                    end_time=end_time
                )
                
                if klines_df is not None and not klines_df.empty:
                    # 更新缓存
                    self.kline_cache[cache_key] = (klines_df, time.time())
                    
                    # 更新最后活跃时间
                    self.last_active_time[source_id] = time.time()
                    
                    return klines_df
                    
            except Exception as e:
                error_msg = f"从数据源 {source_id} 获取 {symbol} K线失败: {e}"
                self.logger.warning(error_msg)
                errors.append(error_msg)
                self.stats["errors"] += 1
        
        # 所有数据源都失败
        if errors:
            self.logger.error(f"获取 {symbol} K线失败: {errors}")
            
        # 返回缓存中的旧数据，即使已过期
        if cache_key in self.kline_cache:
            self.logger.warning(f"返回过期缓存K线数据: {cache_key}")
            klines_df, _ = self.kline_cache[cache_key]
            
            # 过滤时间范围
            if start_time:
                klines_df = klines_df[klines_df.index >= pd.Timestamp(start_time)]
            if end_time:
                klines_df = klines_df[klines_df.index <= pd.Timestamp(end_time)]
                
            return klines_df.tail(count).copy()
            
        return None
    
    async def subscribe_symbol(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        """
        订阅合约行情
        
        Args:
            symbol: 合约代码
            callback: 行情更新回调函数
            
        Returns:
            bool: 是否成功订阅
        """
        if symbol in self.subscribed_symbols:
            # 如果提供了回调，添加到回调列表
            if callback and callback not in self.callbacks.get(symbol, []):
                if symbol not in self.callbacks:
                    self.callbacks[symbol] = []
                self.callbacks[symbol].append(callback)
            
            return True
        
        self.logger.info(f"订阅合约: {symbol}")
        
        # 添加到订阅列表
        self.subscribed_symbols.add(symbol)
        
        # 添加回调
        if callback:
            if symbol not in self.callbacks:
                self.callbacks[symbol] = []
            self.callbacks[symbol].append(callback)
        
        # 在所有数据源上订阅
        success = False
        for source_id, data_source in self.data_sources.items():
            try:
                source_success = await data_source.subscribe(symbol)
                if source_success:
                    success = True
                    self.logger.debug(f"在数据源 {source_id} 上订阅 {symbol} 成功")
                    
                    # 设置数据更新处理
                    await data_source.set_update_callback(symbol, 
                        lambda data: self._on_market_data_update(symbol, data, source_id))
                    
            except Exception as e:
                self.logger.error(f"在数据源 {source_id} 上订阅 {symbol} 失败: {e}")
                self.stats["errors"] += 1
        
        if not success:
            self.logger.warning(f"所有数据源都无法订阅 {symbol}")
            self.subscribed_symbols.remove(symbol)
            if symbol in self.callbacks:
                del self.callbacks[symbol]
            return False
        
        # 订阅成功，立即获取一次数据
        try:
            market_data = await self.get_market_data(symbol, use_cache=False)
            if market_data:
                # 通知回调
                await self._notify_callbacks(symbol, market_data)
        except Exception as e:
            self.logger.error(f"获取 {symbol} 初始市场数据失败: {e}")
        
        return success
    
    async def unsubscribe_symbol(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        """
        取消订阅合约行情
        
        Args:
            symbol: 合约代码
            callback: 要移除的回调函数，None表示移除所有回调
            
        Returns:
            bool: 是否成功取消订阅
        """
        if symbol not in self.subscribed_symbols:
            return True
        
        # 处理回调
        if callback is not None and symbol in self.callbacks:
            # 移除特定回调
            if callback in self.callbacks[symbol]:
                self.callbacks[symbol].remove(callback)
            
            # 如果还有其他回调，不取消订阅
            if self.callbacks[symbol]:
                return True
        
        self.logger.info(f"取消订阅合约: {symbol}")
        
        # 在所有数据源上取消订阅
        for source_id, data_source in self.data_sources.items():
            try:
                await data_source.unsubscribe(symbol)
            except Exception as e:
                self.logger.error(f"在数据源 {source_id} 上取消订阅 {symbol} 失败: {e}")
                self.stats["errors"] += 1
        
        # 移除订阅记录
        self.subscribed_symbols.discard(symbol)
        if symbol in self.callbacks:
            del self.callbacks[symbol]
        
        return True
    
    async def get_instrument_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取合约信息
        
        Args:
            symbol: 合约代码
            
        Returns:
            Dict[str, Any]: 合约信息
        """
        # 先检查缓存
        if symbol in self.instrument_cache:
            return copy.deepcopy(self.instrument_cache[symbol])
        
        # 按优先级排序的数据源
        sorted_sources = sorted(
            self.data_sources.keys(),
            key=lambda source_id: self.source_priorities.get(source_id, 0),
            reverse=True
        )
        
        # 尝试从各数据源获取
        for source_id in sorted_sources:
            data_source = self.data_sources[source_id]
            
            try:
                info = await data_source.get_instrument_info(symbol)
                if info:
                    # 更新缓存
                    self.instrument_cache[symbol] = copy.deepcopy(info)
                    return info
                    
            except Exception as e:
                self.logger.warning(f"从数据源 {source_id} 获取 {symbol} 合约信息失败: {e}")
        
        return {}
    
    async def get_all_instruments(self, instrument_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取所有合约信息
        
        Args:
            instrument_type: 合约类型，如 "FUTURES", "SPOT" 等，None表示所有类型
            
        Returns:
            List[Dict[str, Any]]: 合约信息列表
        """
        # 按优先级排序的数据源
        sorted_sources = sorted(
            self.data_sources.keys(),
            key=lambda source_id: self.source_priorities.get(source_id, 0),
            reverse=True
        )
        
        # 尝试从各数据源获取
        for source_id in sorted_sources:
            data_source = self.data_sources[source_id]
            
            try:
                instruments = await data_source.get_all_instruments(instrument_type)
                if instruments:
                    # 更新缓存
                    for instrument in instruments:
                        symbol = instrument.get("symbol")
                        if symbol:
                            self.instrument_cache[symbol] = copy.deepcopy(instrument)
                    
                    return instruments
                    
            except Exception as e:
                self.logger.warning(f"从数据源 {source_id} 获取全部合约信息失败: {e}")
        
        # 如果所有数据源都失败，返回缓存中的合约信息
        if instrument_type:
            return [
                info for info in self.instrument_cache.values()
                if info.get("type") == instrument_type
            ]
        else:
            return list(self.instrument_cache.values())
    
    async def _on_market_data_update(self, symbol: str, data: Dict[str, Any], source_id: str) -> None:
        """
        市场数据更新处理
        
        Args:
            symbol: 合约代码
            data: 市场数据
            source_id: 数据源ID
        """
        # 更新缓存
        data["_source"] = source_id
        data["_update_time"] = time.time()
        self.market_data_cache[symbol] = copy.deepcopy(data)
        
        # 更新数据源最后活跃时间
        self.last_active_time[source_id] = time.time()
        
        # 通知回调
        await self._notify_callbacks(symbol, data)
        
        # 发布事件
        await self.event_bus.publish(Event(
            event_type=EventType.MARKET_DATA_UPDATE,
            data={
                "symbol": symbol,
                "data": data
            }
        ))
    
    async def _notify_callbacks(self, symbol: str, data: Dict[str, Any]) -> None:
        """
        通知回调函数
        
        Args:
            symbol: 合约代码
            data: 市场数据
        """
        if symbol not in self.callbacks:
            return
        
        callbacks = self.callbacks[symbol]
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"执行 {symbol} 回调函数出错: {e}")
                self.stats["callback_errors"] += 1
    
    async def _heartbeat_task(self) -> None:
        """心跳检测任务"""
        while not self.shutdown_event.is_set():
            try:
                now = time.time()
                
                # 检查数据源健康状态
                for source_id, data_source in list(self.data_sources.items()):
                    # 跳过回放数据源
                    if isinstance(data_source, PlaybackDataSource):
                        continue
                    
                    last_active = self.last_active_time.get(source_id, 0)
                    
                    # 如果长时间未收到数据更新，则尝试重新连接
                    if now - last_active > self.heartbeat_interval * 3:
                        self.logger.warning(f"数据源 {source_id} 长时间未活动，尝试重新连接")
                        
                        try:
                            # 断开连接
                            await data_source.disconnect()
                            
                            # 重新连接
                            success = await data_source.connect()
                            if success:
                                self.logger.info(f"数据源 {source_id} 重新连接成功")
                                
                                # 重新订阅
                                for symbol in self.subscribed_symbols:
                                    await data_source.subscribe(symbol)
                                    
                                    # 设置数据更新处理
                                    await data_source.set_update_callback(symbol, 
                                        lambda data: self._on_market_data_update(symbol, data, source_id))
                            else:
                                self.logger.error(f"数据源 {source_id} 重新连接失败")
                        
                        except Exception as e:
                            self.logger.error(f"数据源 {source_id} 重连过程中出错: {e}")
                            self.stats["errors"] += 1
                
                # 保存合约信息缓存
                await self._save_instrument_cache()
                
                # 等待下一个检测周期
                await asyncio.sleep(self.heartbeat_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳检测任务出错: {e}")
                await asyncio.sleep(5)  # 发生错误时稍等片刻再继续
    
    async def _load_instrument_cache(self) -> None:
        """加载合约信息缓存"""
        cache_file = Path(self.cache_dir) / "instrument_cache.json"
        
        if not cache_file.exists():
            return
        
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            
            self.instrument_cache = cache_data
            self.logger.info(f"从 {cache_file} 加载了 {len(cache_data)} 个合约信息")
            
        except Exception as e:
            self.logger.error(f"加载合约信息缓存失败: {e}")
    
    async def _save_instrument_cache(self) -> None:
        """保存合约信息缓存"""
        if not self.instrument_cache:
            return
        
        cache_file = Path(self.cache_dir) / "instrument_cache.json"
        
        try:
            # 确保缓存目录存在
            os.makedirs(Path(self.cache_dir), exist_ok=True)
            
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(self.instrument_cache, f, ensure_ascii=False, indent=2)
                
            self.logger.debug(f"已将 {len(self.instrument_cache)} 个合约信息保存到 {cache_file}")
            
        except Exception as e:
            self.logger.error(f"保存合约信息缓存失败: {e}")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = copy.deepcopy(self.stats)
        stats.update({
            "subscribed_symbols": len(self.subscribed_symbols),
            "market_data_cache": len(self.market_data_cache),
            "kline_cache": len(self.kline_cache),
            "instrument_cache": len(self.instrument_cache),
            "data_sources": len(self.data_sources),
            "running": self.running,
            "sources": {}
        })
        
        # 添加各数据源统计信息
        for source_id, data_source in self.data_sources.items():
            source_stats = await data_source.get_statistics()
            stats["sources"][source_id] = {
                "name": data_source.name,
                "type": data_source.__class__.__name__,
                "priority": self.source_priorities.get(source_id, 0),
                "connected": data_source.connected,
                "stats": source_stats
            }
        
        return stats