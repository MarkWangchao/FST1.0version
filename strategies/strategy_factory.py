#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强版策略工厂

此模块负责策略的创建、注册和管理，支持动态加载和实例化策略。
主要功能包括：
- 策略类的注册和管理
- 从配置创建策略实例
- 支持动态导入策略类
- 提供策略元数据
- 策略版本管理与热更新
- 依赖检查和安全验证
- 分布式部署支持
- 性能监控与优化
- 自动化参数调优
- 智能策略推荐
"""

import importlib
import inspect
import logging
import os
import pkgutil
import sys
import asyncio
import traceback
import copy
import hashlib
import time
import json
import pickle
import uuid
import warnings
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Type, Any, Optional, Tuple, Generic, TypeVar, Set, Union, Callable
from functools import lru_cache, wraps
from collections import defaultdict, deque

# 尝试导入增强功能所需的库
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    
try:
    from numba import jit, njit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    # 创建空装饰器
    def jit(signature_or_function=None, **kwargs):
        if signature_or_function is None:
            return lambda x: x
        return signature_or_function
    njit = jit

try:
    import redis
    from redis.lock import Lock as RedLock
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    class RedLock:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            pass
        def __exit__(self, *args):
            pass

try:
    import optuna
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    from prometheus_client import Counter, Gauge, Histogram
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    
try:
    import tensorflow as tf
    import numpy as np
    HAS_TF = True
except ImportError:
    HAS_TF = False

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# 策略基类类型变量
T = TypeVar('T', bound='BaseStrategy')

# 导入基类(通过相对导入方式)
try:
    from strategies.base_strategy import BaseStrategy
except ImportError:
    from .base_strategy import BaseStrategy

# 尝试导入天勤相关组件
try:
    from tqsdk import TqAccount, TqKq, TqSim
    from tqsdk.sandbox import StrategySandbox
    from tqsdk.monitor import StrategyMonitor
    HAS_TQSDK = True
except ImportError:
    HAS_TQSDK = False
    # 创建替代类，避免类型错误
    class TqAccount: pass
    class TqKq: pass
    class TqSim: pass
    class StrategySandbox: pass
    class StrategyMonitor: pass

# 性能计时装饰器
def timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger = logging.getLogger("fst.performance")
        logger.debug(f"函数 {func.__name__} 执行时间: {end_time - start_time:.4f}秒")
        return result
    return wrapper

# 增强型沙箱环境
class EnhancedSandbox:
    """增强型策略沙箱环境，提供更严格的安全隔离"""
    
    def __init__(self, allowed_modules=None):
        """
        初始化沙箱环境
        
        Args:
            allowed_modules: 允许使用的模块列表
        """
        self.allowed_modules = allowed_modules or [
            'math', 'datetime', 'time', 'json', 
            'numpy', 'pandas', 'talib'
        ]
        self.original_modules = {}
        
    def __enter__(self):
        # 保存并限制模块访问
        for module_name in list(sys.modules.keys()):
            if module_name not in self.allowed_modules and not any(
                module_name.startswith(prefix) for prefix in self.allowed_modules
            ):
                if module_name in ['os', 'sys', 'subprocess', 'socket']:
                    self.original_modules[module_name] = sys.modules[module_name]
                    sys.modules[module_name] = None
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 恢复模块访问
        for module_name, module in self.original_modules.items():
            sys.modules[module_name] = module

# 策略依赖图管理
class DependencyGraph:
    """策略依赖关系图管理器"""
    
    def __init__(self):
        """初始化依赖图"""
        if not HAS_NETWORKX:
            self.enabled = False
            return
            
        self.graph = nx.DiGraph()
        self.enabled = True
        self.logger = logging.getLogger("fst.dependency_graph")
    
    def add_strategy(self, strategy_name: str, dependencies: List[str]) -> None:
        """
        添加策略及其依赖到图中
        
        Args:
            strategy_name: 策略名称
            dependencies: 依赖列表
        """
        if not self.enabled:
            return
            
        if strategy_name not in self.graph:
            self.graph.add_node(strategy_name)
            
        for dep in dependencies:
            if dep not in self.graph:
                self.graph.add_node(dep)
            self.graph.add_edge(dep, strategy_name)
    
    def get_dependencies(self, strategy_name: str) -> List[str]:
        """
        获取策略的所有依赖
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            List[str]: 依赖列表
        """
        if not self.enabled or strategy_name not in self.graph:
            return []
            
        try:
            return list(nx.ancestors(self.graph, strategy_name))
        except Exception as e:
            self.logger.error(f"获取依赖失败: {str(e)}")
            return []
    
    def get_dependents(self, module_name: str) -> List[str]:
        """
        获取依赖于指定模块的所有策略
        
        Args:
            module_name: 模块名称
            
        Returns:
            List[str]: 依赖该模块的策略列表
        """
        if not self.enabled or module_name not in self.graph:
            return []
            
        try:
            return list(nx.descendants(self.graph, module_name))
        except Exception as e:
            self.logger.error(f"获取依赖策略失败: {str(e)}")
            return []
    
    def check_circular_dependency(self) -> List[List[str]]:
        """
        检查是否存在循环依赖
        
        Returns:
            List[List[str]]: 循环依赖列表
        """
        if not self.enabled:
            return []
            
        try:
            return list(nx.simple_cycles(self.graph))
        except Exception as e:
            self.logger.error(f"检查循环依赖失败: {str(e)}")
            return []
    
    def visualize(self, output_file: str = "strategy_dependencies.png") -> bool:
        """
        可视化依赖图
        
        Args:
            output_file: 输出文件路径
            
        Returns:
            bool: 是否成功生成图像
        """
        if not self.enabled or not HAS_MATPLOTLIB:
            return False
            
        try:
            plt.figure(figsize=(12, 10))
            pos = nx.spring_layout(self.graph)
            nx.draw_networkx_nodes(self.graph, pos, node_size=700)
            nx.draw_networkx_edges(self.graph, pos, arrowstyle='->', arrowsize=15)
            nx.draw_networkx_labels(self.graph, pos)
            plt.title("Strategy Dependency Graph")
            plt.axis('off')
            plt.savefig(output_file)
            plt.close()
            return True
        except Exception as e:
            self.logger.error(f"可视化依赖图失败: {str(e)}")
            return False

# 策略缓存池
class StrategyPool:
    """策略实例缓存池，提高实例创建效率"""
    
    def __init__(self, max_size=100, ttl=3600):
        """
        初始化策略池
        
        Args:
            max_size: 最大缓存数量
            ttl: 缓存生存时间(秒)
        """
        self.pool = {}  # {strategy_type: {params_hash: (strategy_instance, timestamp)}}
        self.max_size = max_size
        self.ttl = ttl
        self.hit_count = 0
        self.miss_count = 0
        self.logger = logging.getLogger("fst.strategy_pool")
        
    def get(self, strategy_type: str, params: Dict) -> Optional[Any]:
        """
        从池中获取策略实例
        
        Args:
            strategy_type: 策略类型
            params: 策略参数
            
        Returns:
            Optional[Any]: 策略实例，不存在则返回None
        """
        self._clean_expired()
        
        if strategy_type not in self.pool:
            self.miss_count += 1
            return None
        
        # 计算参数哈希
        params_hash = self._hash_params(params)
        
        if params_hash not in self.pool[strategy_type]:
            self.miss_count += 1
            return None
        
        instance, timestamp = self.pool[strategy_type][params_hash]
        
        # 检查是否过期
        if time.time() - timestamp > self.ttl:
            del self.pool[strategy_type][params_hash]
            self.miss_count += 1
            return None
        
        self.hit_count += 1
        return instance
    
    def put(self, strategy_type: str, params: Dict, instance: Any) -> None:
        """
        将策略实例添加到池中
        
        Args:
            strategy_type: 策略类型
            params: 策略参数
            instance: 策略实例
        """
        # 初始化策略类型的字典
        if strategy_type not in self.pool:
            self.pool[strategy_type] = {}
        
        # 计算参数哈希
        params_hash = self._hash_params(params)
        
        # 检查池大小
        if len(self.pool[strategy_type]) >= self.max_size:
            self._evict_oldest(strategy_type)
        
        # 添加实例
        self.pool[strategy_type][params_hash] = (instance, time.time())
    
    def invalidate(self, strategy_type: str = None) -> None:
        """
        使缓存失效
        
        Args:
            strategy_type: 要使失效的策略类型，为None则使所有缓存失效
        """
        if strategy_type is None:
            self.pool.clear()
            self.logger.info("清空所有策略缓存")
        elif strategy_type in self.pool:
            del self.pool[strategy_type]
            self.logger.info(f"清空策略 {strategy_type} 的缓存")
    
    def _clean_expired(self) -> None:
        """清理过期的缓存项"""
        now = time.time()
        for strategy_type in list(self.pool.keys()):
            for params_hash in list(self.pool[strategy_type].keys()):
                _, timestamp = self.pool[strategy_type][params_hash]
                if now - timestamp > self.ttl:
                    del self.pool[strategy_type][params_hash]
    
    def _evict_oldest(self, strategy_type: str) -> None:
        """
        驱逐最老的缓存项
        
        Args:
            strategy_type: 策略类型
        """
        if not self.pool[strategy_type]:
            return
            
        oldest_time = float('inf')
        oldest_key = None
        
        for params_hash, (_, timestamp) in self.pool[strategy_type].items():
            if timestamp < oldest_time:
                oldest_time = timestamp
                oldest_key = params_hash
        
        if oldest_key:
            del self.pool[strategy_type][oldest_key]
    
    def _hash_params(self, params: Dict) -> str:
        """
        计算参数的哈希值
        
        Args:
            params: 参数字典
            
        Returns:
            str: 哈希值
        """
        if not params:
            return "empty"
        
        # 将参数转换为字符串并排序，确保相同参数生成相同哈希
        param_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(param_str.encode()).hexdigest()
    
    def get_stats(self) -> Dict:
        """
        获取缓存统计信息
        
        Returns:
            Dict: 统计信息
        """
        total = self.hit_count + self.miss_count
        hit_rate = self.hit_count / total if total > 0 else 0
        
        stats = {
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": hit_rate,
            "total_strategies": sum(len(s) for s in self.pool.values()),
            "strategy_types": len(self.pool)
        }
        
        return stats

# 天勤数据缓存
class TqDataCache:
    """天勤行情数据缓存，减少API调用"""
    
    def __init__(self, max_size=100, ttl=300):
        """
        初始化数据缓存
        
        Args:
            max_size: 最大缓存项数
            ttl: 缓存生存时间(秒)
        """
        self.cache = {}  # {key: (data, timestamp)}
        self.max_size = max_size
        self.ttl = ttl
        self.logger = logging.getLogger("fst.tq_data_cache")
    
    async def get_klines(self, api, symbol: str, duration: str, 
                        limit: int = 200) -> Optional[Any]:
        """
        获取K线数据，优先从缓存获取
        
        Args:
            api: 天勤API实例
            symbol: 合约代码
            duration: K线周期
            limit: 获取K线数量
            
        Returns:
            Optional[Any]: K线数据，获取失败返回None
        """
        if not HAS_TQSDK:
            return None
        
        key = f"{symbol}_{duration}_{limit}"
        cached = self._get_from_cache(key)
        
        if cached:
            return cached
        
        try:
            # 异步获取K线数据
            klines = await asyncio.to_thread(
                lambda: api.get_kline_serial(symbol, duration, limit)
            )
            
            # 缓存数据
            self._add_to_cache(key, klines)
            return klines
            
        except Exception as e:
            self.logger.error(f"获取K线数据失败: {str(e)}")
            return None
    
    async def get_ticks(self, api, symbol: str, limit: int = 100) -> Optional[Any]:
        """
        获取Tick数据，优先从缓存获取
        
        Args:
            api: 天勤API实例
            symbol: 合约代码
            limit: 获取Tick数量
            
        Returns:
            Optional[Any]: Tick数据，获取失败返回None
        """
        if not HAS_TQSDK:
            return None
            
        key = f"tick_{symbol}_{limit}"
        cached = self._get_from_cache(key)
        
        if cached:
            return cached
        
        try:
            # 异步获取Tick数据
            ticks = await asyncio.to_thread(
                lambda: api.get_tick_serial(symbol, limit)
            )
            
            # 缓存数据，Tick数据缓存时间较短
            self._add_to_cache(key, ticks, ttl=30)
            return ticks
            
        except Exception as e:
            self.logger.error(f"获取Tick数据失败: {str(e)}")
            return None
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """
        从缓存中获取数据
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[Any]: 缓存数据，不存在或已过期返回None
        """
        if key not in self.cache:
            return None
        
        data, timestamp = self.cache[key]
        
        # 检查是否过期
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None
        
        return data
    
    def _add_to_cache(self, key: str, data: Any, ttl: int = None) -> None:
        """
        添加数据到缓存
        
        Args:
            key: 缓存键
            data: 数据
            ttl: 缓存生存时间，为None则使用默认值
        """
        # 检查缓存大小
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        # 添加到缓存
        self.cache[key] = (data, time.time())
        
        # 设置自定义TTL
        if ttl:
            # 保存自定义TTL
            self.cache[f"{key}_ttl"] = ttl
    
    def _evict_oldest(self) -> None:
        """驱逐最老的缓存项"""
        if not self.cache:
            return
            
        oldest_time = float('inf')
        oldest_key = None
        
        for key, (_, timestamp) in self.cache.items():
            if key.endswith("_ttl"):
                continue
                
            if timestamp < oldest_time:
                oldest_time = timestamp
                oldest_key = key
        
        if oldest_key:
            del self.cache[oldest_key]
            # 同时删除对应的TTL记录
            if f"{oldest_key}_ttl" in self.cache:
                del self.cache[f"{oldest_key}_ttl"]
    
    def invalidate(self, symbol: str = None) -> None:
        """
        使缓存失效
        
        Args:
            symbol: 合约代码，为None则使所有缓存失效
        """
        if symbol is None:
            self.cache.clear()
            self.logger.info("清空所有数据缓存")
        else:
            # 删除与symbol相关的所有缓存
            for key in list(self.cache.keys()):
                if key.startswith(f"{symbol}_") or key.startswith(f"tick_{symbol}_"):
                    del self.cache[key]
            self.logger.info(f"清空合约 {symbol} 的数据缓存")

# 版本控制器
class VersionController:
    """策略版本控制器，支持灰度发布"""
    
    def __init__(self):
        """初始化版本控制器"""
        self.versions = {}  # {strategy_type: {version: {hash, status, users, timestamp}}}
        self.active_versions = {}  # {strategy_type: version}
        self.logger = logging.getLogger("fst.version_controller")
    
    def register_version(self, strategy_type: str, version: int, 
                        code_hash: str, status: str = "inactive") -> bool:
        """
        注册策略版本
        
        Args:
            strategy_type: 策略类型
            version: 版本号
            code_hash: 代码哈希
            status: 版本状态，可选值: inactive, testing, active
            
        Returns:
            bool: 是否成功注册
        """
        if strategy_type not in self.versions:
            self.versions[strategy_type] = {}
        
        # 检查版本是否已存在
        if version in self.versions[strategy_type]:
            self.logger.warning(f"策略 {strategy_type} 的版本 {version} 已存在")
            return False
        
        # 注册版本
        self.versions[strategy_type][version] = {
            "hash": code_hash,
            "status": status,
            "users": set(),
            "timestamp": datetime.now().isoformat()
        }
        
        # 如果是第一个版本，自动设为活跃版本
        if len(self.versions[strategy_type]) == 1:
            self.active_versions[strategy_type] = version
            self.versions[strategy_type][version]["status"] = "active"
        
        self.logger.info(f"注册策略 {strategy_type} 版本 {version} 成功")
        return True
    
    def activate_version(self, strategy_type: str, version: int) -> bool:
        """
        激活策略版本
        
        Args:
            strategy_type: 策略类型
            version: 版本号
            
        Returns:
            bool: 是否成功激活
        """
        if (strategy_type not in self.versions or 
            version not in self.versions[strategy_type]):
            self.logger.error(f"激活版本失败: 策略 {strategy_type} 的版本 {version} 不存在")
            return False
        
        # 设置之前的活跃版本为inactive
        if strategy_type in self.active_versions:
            old_version = self.active_versions[strategy_type]
            if old_version in self.versions[strategy_type]:
                self.versions[strategy_type][old_version]["status"] = "inactive"
        
        # 设置新的活跃版本
        self.active_versions[strategy_type] = version
        self.versions[strategy_type][version]["status"] = "active"
        
        self.logger.info(f"激活策略 {strategy_type} 版本 {version} 成功")
        return True
    
    def start_canary_release(self, strategy_type: str, version: int, 
                           ratio: float = 0.1) -> bool:
        """
        开始灰度发布
        
        Args:
            strategy_type: 策略类型
            version: 版本号
            ratio: 发布比例(0-1)
            
        Returns:
            bool: 是否成功开始灰度发布
        """
        if (strategy_type not in self.versions or 
            version not in self.versions[strategy_type]):
            self.logger.error(f"灰度发布失败: 策略 {strategy_type} 的版本 {version} 不存在")
            return False
        
        # 设置版本状态为testing
        self.versions[strategy_type][version]["status"] = "testing"
        self.versions[strategy_type][version]["ratio"] = ratio
        
        self.logger.info(f"开始策略 {strategy_type} 版本 {version} 的灰度发布，比例: {ratio}")
        return True
    
    def assign_version(self, strategy_type: str, user_id: str) -> int:
        """
        为用户分配策略版本
        
        Args:
            strategy_type: 策略类型
            user_id: 用户ID
            
        Returns:
            int: 分配的版本号
        """
        if strategy_type not in self.versions:
            # 没有版本记录，返回版本1
            return 1
        
        # 获取活跃版本
        active_version = self.active_versions.get(strategy_type, max(self.versions[strategy_type].keys()))
        
        # 检查是否有测试中的版本
        testing_versions = [v for v, info in self.versions[strategy_type].items() 
                          if info["status"] == "testing"]
        
        if not testing_versions:
            # 没有测试中的版本，使用活跃版本
            return active_version
        
        # 对用户ID进行哈希，确保同一用户始终得到相同结果
        user_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
        
        # 按照灰度比例分配版本
        for version in testing_versions:
            ratio = self.versions[strategy_type][version].get("ratio", 0.1)
            threshold = int(ratio * 100)
            if user_hash < threshold:
                # 记录使用此版本的用户
                self.versions[strategy_type][version]["users"].add(user_id)
                return version
        
        # 默认使用活跃版本
        return active_version
    
    def get_version_info(self, strategy_type: str, version: int = None) -> Dict:
        """
        获取版本信息
        
        Args:
            strategy_type: 策略类型
            version: 版本号，为None则获取活跃版本
            
        Returns:
            Dict: 版本信息
        """
        if strategy_type not in self.versions:
            return {}
        
        if version is None:
            version = self.active_versions.get(strategy_type)
            if version is None:
                return {}
        
        if version not in self.versions[strategy_type]:
            return {}
        
        info = copy.deepcopy(self.versions[strategy_type][version])
        # 转换用户集合为列表
        info["users"] = list(info["users"])
        info["user_count"] = len(info["users"])
        
        return info
    
    def rollback(self, strategy_type: str) -> Tuple[bool, int]:
        """
        回滚到上一个活跃版本
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            Tuple[bool, int]: (是否成功回滚, 回滚到的版本号)
        """
        if strategy_type not in self.versions:
            self.logger.error(f"回滚失败: 策略 {strategy_type} 没有版本记录")
            return False, 0
        
        if strategy_type not in self.active_versions:
            self.logger.error(f"回滚失败: 策略 {strategy_type} 没有活跃版本")
            return False, 0
        
        current_version = self.active_versions[strategy_type]
        
        # 获取所有版本并按时间戳排序
        versions = []
        for v, info in self.versions[strategy_type].items():
            if v != current_version:
                versions.append((v, info["timestamp"]))
        
        if not versions:
            self.logger.warning(f"回滚失败: 策略 {strategy_type} 只有一个版本")
            return False, current_version
        
        # 按时间戳降序排序
        versions.sort(key=lambda x: x[1], reverse=True)
        
        # 取最新的一个版本
        rollback_version = versions[0][0]
        
        # 激活回滚版本
        success = self.activate_version(strategy_type, rollback_version)
        
        if success:
            self.logger.info(f"策略 {strategy_type} 成功回滚到版本 {rollback_version}")
            return True, rollback_version
        else:
            return False, current_version
    
    def get_all_versions(self, strategy_type: str) -> List[Dict]:
        """
        获取策略的所有版本信息
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            List[Dict]: 版本信息列表
        """
        if strategy_type not in self.versions:
            return []
        
        result = []
        for version, info in self.versions[strategy_type].items():
            version_info = copy.deepcopy(info)
            version_info["version"] = version
            # 转换用户集合为列表长度
            version_info["users"] = len(info["users"])
            result.append(version_info)
        
        # 按版本号排序
        result.sort(key=lambda x: x["version"], reverse=True)
        
        return result

# 性能监控仪表盘
class PerformanceDashboard:
    """策略性能监控仪表盘"""
    
    def __init__(self):
        """初始化性能仪表盘"""
        self.logger = logging.getLogger("fst.performance_dashboard")
        
        # 初始化指标
        self.has_prometheus = HAS_PROMETHEUS
        if self.has_prometheus:
            self.metrics = {
                "strategy_count": Gauge("fst_strategy_count", "已注册策略数量"),
                "strategy_instance_count": Gauge("fst_strategy_instance_count", "策略实例数量"),
                "strategy_create_time": Histogram("fst_strategy_create_time", "策略创建时间"),
                "strategy_memory": Gauge("fst_strategy_memory", "策略内存占用", ["strategy_type"]),
                "strategy_cpu": Gauge("fst_strategy_cpu", "策略CPU占用", ["strategy_type"]),
                "strategy_load_count": Counter("fst_strategy_load_count", "策略加载次数", ["strategy_type"]),
                "cache_hit_rate": Gauge("fst_cache_hit_rate", "缓存命中率"),
                "event_count": Counter("fst_event_count", "事件计数", ["event_type"])
            }
        else:
            self.metrics = {}
            
        # 性能数据存储
        self.performance_data = defaultdict(lambda: deque(maxlen=100))  # {metric: deque([timestamp, value])}
        
    def update(self, metric: str, value: float, labels: Dict = None) -> None:
        """
        更新指标
        
        Args:
            metric: 指标名称
            value: 指标值
            labels: 标签
        """
        # 记录数据点
        self.performance_data[metric].append((time.time(), value))
        
        # 更新Prometheus指标
        if self.has_prometheus and metric in self.metrics:
            if labels:
                self.metrics[metric].labels(**labels).set(value)
            else:
                if isinstance(self.metrics[metric], Counter):
                    self.metrics[metric].inc(value)
                else:
                    self.metrics[metric].set(value)
    
    def inc_counter(self, metric: str, value: float = 1, labels: Dict = None) -> None:
        """
        增加计数器
        
        Args:
            metric: 指标名称
            value: 增加值
            labels: 标签
        """
        if self.has_prometheus and metric in self.metrics:
            if labels:
                self.metrics[metric].labels(**labels).inc(value)
            else:
                self.metrics[metric].inc(value)
    
    def get_metric_data(self, metric: str, 
                      time_range: int = 3600) -> List[Tuple[float, float]]:
        """
        获取指标历史数据
        
        Args:
            metric: 指标名称
            time_range: 时间范围(秒)
            
        Returns:
            List[Tuple[float, float]]: 数据点列表 [(timestamp, value)]
        """
        if metric not in self.performance_data:
            return []
            
        # 获取指定时间范围内的数据
        now = time.time()
        return [(t, v) for t, v in self.performance_data[metric] if now - t <= time_range]
    
    def get_summary(self) -> Dict:
        """
        获取性能摘要
        
        Returns:
            Dict: 性能摘要
        """
        summary = {}
        
        for metric, data in self.performance_data.items():
            if not data:
                continue
                
            values = [v for _, v in data]
            
            summary[metric] = {
                "current": values[-1] if values else 0,
                "average": sum(values) / len(values) if values else 0,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "count": len(values)
            }
        
        return summary
    
    def generate_report(self, output_file: str = "performance_report.html") -> bool:
        """
        生成性能报告
        
        Args:
            output_file: 输出文件路径
            
        Returns:
            bool: 是否成功生成报告
        """
        if not HAS_MATPLOTLIB:
            self.logger.error("无法生成性能报告: 缺少matplotlib库")
            return False
            
        try:
          
            # 创建HTML报告
            html_content = [
                "<!DOCTYPE html>",
                "<html>",
                "<head>",
                "<title>策略性能报告</title>",
                "<style>",
                "body { font-family: Arial, sans-serif; margin: 20px; }",
                ".chart { margin: 20px 0; width: 800px; height: 400px; }",
                ".summary { margin: 20px 0; }",
                "table { border-collapse: collapse; width: 100%; }",
                "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
                "th { background-color: #f2f2f2; }",
                "</style>",
                "</head>",
                "<body>",
                "<h1>策略性能报告</h1>",
                f"<p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
            ]
            
            # 添加性能摘要
            summary = self.get_summary()
            html_content.extend([
                "<h2>性能摘要</h2>",
                "<div class='summary'>",
                "<table>",
                "<tr><th>指标</th><th>当前值</th><th>平均值</th><th>最小值</th><th>最大值</th><th>数据点数</th></tr>"
            ])
            
            for metric, data in summary.items():
                html_content.append(
                    f"<tr><td>{metric}</td>"
                    f"<td>{data['current']:.2f}</td>"
                    f"<td>{data['average']:.2f}</td>"
                    f"<td>{data['min']:.2f}</td>"
                    f"<td>{data['max']:.2f}</td>"
                    f"<td>{data['count']}</td></tr>"
                )
            
            html_content.append("</table></div>")
            
            # 生成性能图表
            html_content.append("<h2>性能图表</h2>")
            
            for metric in self.performance_data.keys():
                # 获取最近24小时的数据
                data = self.get_metric_data(metric, time_range=86400)
                if not data:
                    continue
                
                # 创建图表
                plt.figure(figsize=(10, 6))
                timestamps, values = zip(*data)
                
                # 转换时间戳为可读时间
                times = [datetime.fromtimestamp(t).strftime('%H:%M:%S') for t in timestamps]
                
                plt.plot(times, values)
                plt.title(f"{metric} 趋势图")
                plt.xlabel("时间")
                plt.ylabel("值")
                plt.xticks(rotation=45)
                plt.grid(True)
                
                # 保存图表
                chart_filename = f"chart_{metric}.png"
                chart_path = os.path.join(os.path.dirname(output_file), chart_filename)
                plt.savefig(chart_path)
                plt.close()
                
                # 添加图表到HTML
                html_content.extend([
                    f"<div class='chart'>",
                    f"<h3>{metric} 趋势图</h3>",
                    f"<img src='{chart_filename}' alt='{metric} 趋势图'>",
                    "</div>"
                ])
            
            # 添加Prometheus指标(如果可用)
            if self.has_prometheus:
                html_content.extend([
                    "<h2>Prometheus指标</h2>",
                    "<div class='summary'>",
                    "<table>",
                    "<tr><th>指标名称</th><th>描述</th><th>类型</th></tr>"
                ])
                
                for name, metric in self.metrics.items():
                    metric_type = type(metric).__name__
                    html_content.append(
                        f"<tr><td>{name}</td><td>{metric._documentation}</td><td>{metric_type}</td></tr>"
                    )
                
                html_content.append("</table></div>")
            
            # 完成HTML
            html_content.extend([
                "</body>",
                "</html>"
            ])
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(html_content))
            
            self.logger.info(f"性能报告已生成: {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"生成性能报告失败: {str(e)}\n{traceback.format_exc()}")
            return False
# 分布式工厂
class DistributedFactory:
    """分布式策略工厂，支持多节点部署"""
    
    def __init__(self, redis_url: str, local_factory: Any = None):
        """
        初始化分布式工厂
        
        Args:
            redis_url: Redis连接URL
            local_factory: 本地策略工厂实例
        """
        self.local_factory = local_factory
        self.local_mode = not HAS_REDIS
        self.logger = logging.getLogger("fst.distributed_factory")
        
        if not self.local_mode:
            try:
                self.redis = redis.from_url(redis_url)
                self.node_id = str(uuid.uuid4())
                self.lock_prefix = "fst:lock:"
                self._start_heartbeat()
            except Exception as e:
                self.logger.error(f"初始化Redis连接失败: {str(e)}")
                self.local_mode = True
    
    def _start_heartbeat(self) -> None:
        """启动心跳线程"""
        if self.local_mode:
            return
            
        def heartbeat():
            while True:
                try:
                    # 更新节点心跳
                    self.redis.hset(
                        "fst:nodes",
                        self.node_id,
                        json.dumps({
                            "last_heartbeat": time.time(),
                            "status": "active"
                        })
                    )
                    
                    # 清理过期节点
                    self._clean_expired_nodes()
                    
                    time.sleep(30)  # 心跳间隔
                    
                except Exception as e:
                    self.logger.error(f"心跳更新失败: {str(e)}")
                    time.sleep(5)  # 出错后短暂等待
                            # 启动心跳线程
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
    
    def _clean_expired_nodes(self) -> None:
        """清理过期节点"""
        if self.local_mode:
            return
            
        try:
            # 获取所有节点
            nodes = self.redis.hgetall("fst:nodes")
            now = time.time()
            
            # 检查每个节点
            for node_id, node_info in nodes.items():
                node_data = json.loads(node_info)
                # 节点超过90秒未更新心跳则认为过期
                if now - node_data["last_heartbeat"] > 90:
                    self.redis.hdel("fst:nodes", node_id)
                    self.logger.info(f"清理过期节点: {node_id}")
                    
        except Exception as e:
            self.logger.error(f"清理过期节点失败: {str(e)}")
    
    def register_strategy(self, strategy_type: str, strategy_class: Type[T]) -> bool:
        """
        注册策略到分布式注册表
        
        Args:
            strategy_type: 策略类型
            strategy_class: 策略类
            
        Returns:
            bool: 是否成功注册
        """
        if self.local_mode:
            return self.local_factory.register_strategy(strategy_type, strategy_class)
            
        try:
            # 获取分布式锁
            with RedLock(self.redis, f"{self.lock_prefix}register:{strategy_type}"):
                # 检查是否已存在
                if self.redis.hexists("fst:strategies", strategy_type):
                    self.logger.warning(f"策略 {strategy_type} 已存在于分布式注册表")
                    return False
                
                # 序列化策略类
                try:
                    strategy_data = pickle.dumps(strategy_class)
                except Exception as e:
                    self.logger.error(f"序列化策略类失败: {str(e)}")
                    return False
                
                # 提取元数据
                metadata = self._extract_strategy_metadata(strategy_class)
                
                # 注册到Redis
                pipeline = self.redis.pipeline()
                pipeline.hset("fst:strategies", strategy_type, strategy_data)
                pipeline.hset("fst:metadata", strategy_type, json.dumps(metadata))
                pipeline.execute()
                
                self.logger.info(f"策略 {strategy_type} 已注册到分布式注册表")
                return True
                
        except Exception as e:
            self.logger.error(f"注册策略到分布式注册表失败: {str(e)}")
            return False
    
    def get_strategy_class(self, strategy_type: str) -> Optional[Type[T]]:
        """
        从分布式注册表获取策略类
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            Optional[Type[T]]: 策略类
        """
        if self.local_mode:
            return self.local_factory.get_strategy_class(strategy_type)
            
        try:
            # 从Redis获取策略类数据
            strategy_data = self.redis.hget("fst:strategies", strategy_type)
            if not strategy_data:
                return None
            
            # 反序列化策略类
            try:
                strategy_class = pickle.loads(strategy_data)
                return strategy_class
            except Exception as e:
                self.logger.error(f"反序列化策略类失败: {str(e)}")
                return None
                
        except Exception as e:
            self.logger.error(f"获取策略类失败: {str(e)}")
            return None
    
    def create_strategy(self, strategy_type: str, params: Dict = None,
                       use_sandbox: bool = True) -> Optional[T]:
        """
        创建策略实例
        
        Args:
            strategy_type: 策略类型
            params: 策略参数
            use_sandbox: 是否使用沙箱环境
            
        Returns:
            Optional[T]: 策略实例
        """
        if self.local_mode:
            return self.local_factory.create_strategy(
                strategy_type, params, use_sandbox
            )
            
        try:
            # 获取策略类
            strategy_class = self.get_strategy_class(strategy_type)
            if not strategy_class:
                return None
            
            # 创建实例
            if use_sandbox:
                with EnhancedSandbox():
                    instance = strategy_class(**(params or {}))
            else:
                instance = strategy_class(**(params or {}))
            
            return instance
            
        except Exception as e:
            self.logger.error(f"创建策略实例失败: {str(e)}")
            return None
    
    def _extract_strategy_metadata(self, strategy_class: Type[T]) -> Dict:
        """
        提取策略元数据
        
        Args:
            strategy_class: 策略类
            
        Returns:
            Dict: 元数据字典
        """
        metadata = {
            "name": strategy_class.__name__,
            "module": strategy_class.__module__,
            "doc": strategy_class.__doc__ or "",
            "created_at": datetime.now().isoformat(),
            "created_by": self.node_id
        }
        
        # 提取类属性
        for attr in ["description", "version", "author", "required_modules"]:
            if hasattr(strategy_class, attr):
                metadata[attr] = getattr(strategy_class, attr)
        
        # 检查必需方法
        required_methods = ["initialize", "on_bar", "on_order", "on_trade"]
        metadata["implemented_methods"] = [
            method for method in required_methods
            if hasattr(strategy_class, method)
        ]
        
        # 提取参数签名
        try:
            sig = inspect.signature(strategy_class.__init__)
            metadata["parameters"] = {
                name: str(param.annotation)
                for name, param in sig.parameters.items()
                if name != "self"
            }
        except Exception:
            metadata["parameters"] = {}
        
        return metadata
    
    def get_active_nodes(self) -> List[Dict]:
        """
        获取活跃节点列表
        
        Returns:
            List[Dict]: 节点信息列表
        """
        if self.local_mode:
            return [{
                "node_id": "local",
                "status": "active",
                "last_heartbeat": time.time()
            }]
            
        try:
            nodes = []
            for node_id, node_info in self.redis.hgetall("fst:nodes").items():
                node_data = json.loads(node_info)
                node_data["node_id"] = node_id
                nodes.append(node_data)
            
            return sorted(nodes, key=lambda x: x["last_heartbeat"], reverse=True)
            
        except Exception as e:
            self.logger.error(f"获取活跃节点失败: {str(e)}")
            return []
    
    def get_strategy_metadata(self, strategy_type: str) -> Optional[Dict]:
        """
        获取策略元数据
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            Optional[Dict]: 策略元数据
        """
        if self.local_mode:
            return self.local_factory.get_strategy_metadata(strategy_type)
            
        try:
            metadata = self.redis.hget("fst:metadata", strategy_type)
            return json.loads(metadata) if metadata else None
            
        except Exception as e:
            self.logger.error(f"获取策略元数据失败: {str(e)}")
            return None
    
    def get_all_strategies(self) -> List[str]:
        """
        获取所有已注册的策略类型
        
        Returns:
            List[str]: 策略类型列表
        """
        if self.local_mode:
            return self.local_factory.get_all_strategies()
            
        try:
            return list(self.redis.hkeys("fst:strategies"))
            
        except Exception as e:
            self.logger.error(f"获取策略列表失败: {str(e)}")
            return []
    
    def unregister_strategy(self, strategy_type: str) -> bool:
        """
        注销策略
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            bool: 是否成功注销
        """
        if self.local_mode:
            return self.local_factory.unregister_strategy(strategy_type)
            
        try:
            # 获取分布式锁
            with RedLock(self.redis, f"{self.lock_prefix}unregister:{strategy_type}"):
                # 检查是否存在
                if not self.redis.hexists("fst:strategies", strategy_type):
                    return False
                
                # 从Redis删除
                pipeline = self.redis.pipeline()
                pipeline.hdel("fst:strategies", strategy_type)
                pipeline.hdel("fst:metadata", strategy_type)
                pipeline.execute()
                
                self.logger.info(f"策略 {strategy_type} 已从分布式注册表注销")
                return True
                
        except Exception as e:
            self.logger.error(f"注销策略失败: {str(e)}")
            return False
# 策略工厂
class StrategyFactory:
    """增强版策略工厂，提供完整的策略管理功能"""
    
    def __init__(self, redis_url: str = None):
        """
        初始化策略工厂
        
        Args:
            redis_url: Redis连接URL，用于分布式部署
        """
        # 初始化组件
        self.registered_strategies = {}
        self.dependency_graph = DependencyGraph()
        self.strategy_pool = StrategyPool()
        self.data_cache = TqDataCache()
        self.version_controller = VersionController()
        self.performance_dashboard = PerformanceDashboard()
        
        # 创建分布式工厂
        self.distributed = DistributedFactory(redis_url, self) if redis_url else None
        
        # 初始化推荐器和优化器
        self.recommender = StrategyRecommender(self)
        self.optimizer = AutoOptimizer(self)
        
        self.logger = logging.getLogger("fst.strategy_factory")
    def register_strategy(self, strategy_type: str, strategy_class: Type[T]) -> bool:
        """
        注册策略类
        
        Args:
            strategy_type: 策略类型
            strategy_class: 策略类
            
        Returns:
            bool: 是否成功注册
        """
        try:
            # 验证策略类
            if not self._validate_strategy_class(strategy_class):
                return False
            
            # 如果已存在，先注销
            if strategy_type in self.registered_strategies:
                self.unregister_strategy(strategy_type)
            
            # 注册策略
            self.registered_strategies[strategy_type] = strategy_class
            
            # 提取依赖信息
            dependencies = self._extract_dependencies(strategy_class)
            self.dependency_graph.add_strategy(strategy_type, dependencies)
            
            # 提取元数据
            metadata = self._extract_metadata(strategy_class)
            
            # 注册版本
            version = metadata.get("version", 1)
            code_hash = self._calculate_code_hash(strategy_class)
            self.version_controller.register_version(
                strategy_type, version, code_hash
            )
            
            # 更新性能指标
            self.performance_dashboard.update(
                "strategy_count",
                len(self.registered_strategies)
            )
            
            # 同步到分布式注册表
            if self.distributed:
                self.distributed.register_strategy(strategy_type, strategy_class)
            
            self.logger.info(f"策略 {strategy_type} 注册成功")
            return True
            
        except Exception as e:
            self.logger.error(f"注册策略失败: {str(e)}")
            return False
    
    def create_strategy(self, strategy_type: str, params: Dict = None,
                       use_sandbox: bool = True) -> Optional[T]:
        """
        创建策略实例
        
        Args:
            strategy_type: 策略类型
            params: 策略参数
            use_sandbox: 是否使用沙箱环境
            
        Returns:
            Optional[T]: 策略实例
        """
        try:
            # 检查策略类型是否存在
            if strategy_type not in self.registered_strategies:
                self.logger.error(f"策略类型 {strategy_type} 不存在")
                return None
            
            # 尝试从缓存获取实例
            cached_instance = self.strategy_pool.get(strategy_type, params or {})
            if cached_instance:
                return cached_instance
            
            # 获取策略类
            strategy_class = self.registered_strategies[strategy_type]
            
            # 验证参数
            if not self._validate_params(strategy_class, params):
                return None
            
            # 创建实例
            start_time = time.time()
            
            if use_sandbox:
                with EnhancedSandbox():
                    instance = strategy_class(**(params or {}))
            else:
                instance = strategy_class(**(params or {}))
            
            # 记录创建时间
            create_time = time.time() - start_time
            self.performance_dashboard.update(
                "strategy_create_time",
                create_time
            )
            
            # 缓存实例
            self.strategy_pool.put(strategy_type, params or {}, instance)
            
            # 更新实例计数
            self.performance_dashboard.update(
                "strategy_instance_count",
                len(self.strategy_pool.pool)
            )
            
            return instance
            
        except Exception as e:
            self.logger.error(f"创建策略实例失败: {str(e)}")
            return None
    
    def unregister_strategy(self, strategy_type: str) -> bool:
        """
        注销策略
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            bool: 是否成功注销
        """
        try:
            if strategy_type not in self.registered_strategies:
                return False
            
            # 从注册表中移除
            del self.registered_strategies[strategy_type]
            
            # 清理相关资源
            self.strategy_pool.invalidate(strategy_type)
            self.data_cache.invalidate()
            
            # 更新性能指标
            self.performance_dashboard.update(
                "strategy_count",
                len(self.registered_strategies)
            )
            
            # 同步到分布式注册表
            if self.distributed:
                self.distributed.unregister_strategy(strategy_type)
            
            self.logger.info(f"策略 {strategy_type} 注销成功")
            return True
            
        except Exception as e:
            self.logger.error(f"注销策略失败: {str(e)}")
            return False
    
    def get_strategy_metadata(self, strategy_type: str) -> Optional[Dict]:
        """
        获取策略元数据
        
        Args:
            strategy_type: 策略类型
            
        Returns:
            Optional[Dict]: 策略元数据
        """
        try:
            if strategy_type not in self.registered_strategies:
                return None
            
            strategy_class = self.registered_strategies[strategy_type]
            return self._extract_metadata(strategy_class)
            
        except Exception as e:
            self.logger.error(f"获取策略元数据失败: {str(e)}")
            return None
    
    def _validate_strategy_class(self, strategy_class: Type[T]) -> bool:
        """
        验证策略类
        
        Args:
            strategy_class: 策略类
            
        Returns:
            bool: 是否通过验证
        """
        try:
            # 检查基类继承
            if not issubclass(strategy_class, BaseStrategy):
                self.logger.error(f"策略类 {strategy_class.__name__} 必须继承BaseStrategy")
                return False
            
            # 检查必需方法
            required_methods = ["initialize", "on_bar", "on_order", "on_trade"]
            for method in required_methods:
                if not hasattr(strategy_class, method):
                    self.logger.error(f"策略类缺少必需方法: {method}")
                    return False
            
            # 检查方法签名
            for method in required_methods:
                if not inspect.signature(getattr(strategy_class, method)):
                    self.logger.error(f"方法 {method} 签名无效")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"验证策略类失败: {str(e)}")
            return False
    
    def _validate_params(self, strategy_class: Type[T], params: Dict) -> bool:
        """
        验证策略参数
        
        Args:
            strategy_class: 策略类
            params: 策略参数
            
        Returns:
            bool: 是否通过验证
        """
        try:
            # 获取__init__方法的参数签名
            sig = inspect.signature(strategy_class.__init__)
            
            # 检查必需参数
            for name, param in sig.parameters.items():
                if name == "self":
                    continue
                    
                if param.default == inspect.Parameter.empty and name not in (params or {}):
                    self.logger.error(f"缺少必需参数: {name}")
                    return False
            
            # 检查参数类型
            for name, value in (params or {}).items():
                if name not in sig.parameters:
                    self.logger.warning(f"未知参数: {name}")
                    continue
                    
                param = sig.parameters[name]
                if param.annotation != inspect.Parameter.empty:
                    try:
                        # 尝试类型转换
                        param.annotation(value)
                    except Exception:
                        self.logger.error(f"参数 {name} 类型不匹配")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"验证参数失败: {str(e)}")
            return False
    
    def _extract_dependencies(self, strategy_class: Type[T]) -> List[str]:
        """
        提取策略依赖
        
        Args:
            strategy_class: 策略类
            
        Returns:
            List[str]: 依赖列表
        """
        dependencies = []
        
        # 从类属性获取显式声明的依赖
        if hasattr(strategy_class, "required_modules"):
            dependencies.extend(strategy_class.required_modules)
        
        # 分析代码获取隐式依赖
        try:
            source = inspect.getsource(strategy_class)
            tree = ast.parse(source)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        dependencies.append(name.name)
                elif isinstance(node, ast.ImportFrom):
                    dependencies.append(node.module)
        except Exception:
            pass
        
        return list(set(dependencies))
    
    def _extract_metadata(self, strategy_class: Type[T]) -> Dict:
        """
        提取策略元数据
        
        Args:
            strategy_class: 策略类
            
        Returns:
            Dict: 元数据字典
        """
        metadata = {
            "name": strategy_class.__name__,
            "module": strategy_class.__module__,
            "doc": strategy_class.__doc__ or "",
            "version": getattr(strategy_class, "version", 1),
            "author": getattr(strategy_class, "author", "unknown"),
            "created_at": datetime.now().isoformat()
        }
        
        # 提取类属性
        for attr in ["description", "risk_level", "required_modules"]:
            if hasattr(strategy_class, attr):
                metadata[attr] = getattr(strategy_class, attr)
        
        # 提取参数信息
        try:
            sig = inspect.signature(strategy_class.__init__)
            metadata["parameters"] = {
                name: {
                    "type": str(param.annotation),
                    "default": param.default if param.default != inspect.Parameter.empty else None,
                    "required": param.default == inspect.Parameter.empty
                }
                for name, param in sig.parameters.items()
                if name != "self"
            }
        except Exception:
            metadata["parameters"] = {}
        
        # 提取性能指标
        metadata["performance_metrics"] = self._get_performance_metrics(strategy_class)
        
        return metadata
    
    def _calculate_code_hash(self, strategy_class: Type[T]) -> str:
        """
        计算策略代码哈希
        
        Args:
            strategy_class: 策略类
            
        Returns:
            str: 代码哈希值
        """
        try:
            source = inspect.getsource(strategy_class)
            return hashlib.md5(source.encode()).hexdigest()
        except Exception:
            return "unknown"
    
    def _get_performance_metrics(self, strategy_class: Type[T]) -> Dict:
        """
        获取策略性能指标
        
        Args:
            strategy_class: 策略类
            
        Returns:
            Dict: 性能指标
        """
        metrics = {}
        
        # 从类属性获取性能指标
        if hasattr(strategy_class, "performance_metrics"):
            metrics.update(strategy_class.performance_metrics)
        
        # 从缓存获取实时指标
        if hasattr(strategy_class, "strategy_type"):
            strategy_type = strategy_class.strategy_type
            
            # 获取CPU和内存使用
            if HAS_PROMETHEUS:
                cpu_usage = self.performance_dashboard.metrics["strategy_cpu"].labels(
                    strategy_type=strategy_type
                )._value.get()
                
                memory_usage = self.performance_dashboard.metrics["strategy_memory"].labels(
                    strategy_type=strategy_type
                )._value.get()
                
                metrics.update({
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory_usage
                })
        
        return metrics
    
    async def optimize_strategy(self, strategy_type: str, param_space: Dict,
                              target_metric: str = "sharpe_ratio",
                              n_trials: int = 100,
                              timeout: int = 3600) -> Tuple[Dict, float]:
        """
        优化策略参数
        
        Args:
            strategy_type: 策略类型
            param_space: 参数空间
            target_metric: 优化目标
            n_trials: 优化次数
            timeout: 超时时间(秒)
            
        Returns:
            Tuple[Dict, float]: (最优参数, 最优得分)
        """
        return await self.optimizer.optimize(
            strategy_type, param_space, target_metric, n_trials, timeout
        )
    
    def recommend_strategies(self, market_condition: str,
                           top_k: int = 3) -> List[Tuple[str, float, str]]:
        """
        推荐策略
        
        Args:
            market_condition: 市场条件
            top_k: 返回数量
            
        Returns:
            List[Tuple[str, float, str]]: [(策略类型, 得分, 推荐原因)]
        """
        return self.recommender.recommend_for_market(market_condition, top_k)
    
    def generate_performance_report(self, output_file: str = "performance_report.html") -> bool:
        """
        生成性能报告
        
        Args:
            output_file: 输出文件路径
            
        Returns:
            bool: 是否成功生成报告
        """
        return self.performance_dashboard.generate_report(output_file)