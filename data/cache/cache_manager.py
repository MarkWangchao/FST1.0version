"""
缓存管理器类，提供统一的缓存管理接口
"""

import logging
import os
from typing import Any, Dict, List, Optional, Type, Union, Set, Callable

from .memory_cache import MemoryCache
from .cache_item import CachePolicy
from .disk_cache import DiskCache

# 尝试导入Redis缓存
try:
    from .redis_cache import RedisCache, RedisConfig
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    RedisCache = None
    RedisConfig = None

logger = logging.getLogger(__name__)


class CacheManager:
    """
    缓存管理器类，提供统一的缓存管理接口
    
    特性:
    - 管理多个不同类型的缓存
    - 支持多层缓存策略
    - 提供统一的缓存访问方法
    - 支持回调函数注册
    """
    
    def __init__(self, app_name: str = "app", cache_dir: str = None):
        """
        初始化缓存管理器
        
        Args:
            app_name: 应用名称，用于命名缓存
            cache_dir: 缓存目录，用于磁盘缓存
        """
        self.app_name = app_name
        
        # 确定缓存目录
        if cache_dir is None:
            cache_dir = os.path.join(os.getcwd(), ".cache")
        self.cache_dir = cache_dir
        
        # 创建默认内存缓存
        self.default_cache = MemoryCache(name=f"{app_name}_default")
        
        # 缓存注册表
        self._caches: Dict[str, Any] = {
            "default": self.default_cache
        }
        
        # 回调函数
        self._callbacks: Dict[str, List[Callable]] = {
            'on_get': [],
            'on_put': [],
            'on_delete': [],
            'on_expire': []
        }
        
        logger.info(f"Cache manager initialized for application '{app_name}'")
    
    def create_memory_cache(self, name: str, max_size: int = 1000, 
                          cleanup_interval: float = 60.0) -> MemoryCache:
        """
        创建内存缓存
        
        Args:
            name: 缓存名称
            max_size: 最大缓存项数量
            cleanup_interval: 过期项清理间隔(秒)
            
        Returns:
            MemoryCache: 内存缓存实例
        """
        cache_name = f"{self.app_name}_{name}"
        
        if name in self._caches:
            logger.warning(f"Cache '{name}' already exists, returning existing instance")
            return self._caches[name]
            
        cache = MemoryCache(
            name=cache_name,
            max_size=max_size,
            cleanup_interval=cleanup_interval
        )
        
        # 添加全局回调
        for event, callbacks in self._callbacks.items():
            for callback in callbacks:
                cache.add_callback(event, callback)
                
        self._caches[name] = cache
        logger.info(f"Created memory cache '{name}'")
        return cache
    
    def create_disk_cache(self, name: str, memory_cache_size: int = 500,
                        cleanup_interval: float = 300.0,
                        serializer: str = "pickle") -> DiskCache:
        """
        创建磁盘缓存
        
        Args:
            name: 缓存名称
            memory_cache_size: 内存缓存最大项数量
            cleanup_interval: 过期项清理间隔(秒)
            serializer: 序列化方式 ("json" or "pickle")
            
        Returns:
            DiskCache: 磁盘缓存实例
        """
        cache_name = f"{self.app_name}_{name}"
        
        if name in self._caches:
            logger.warning(f"Cache '{name}' already exists, returning existing instance")
            return self._caches[name]
            
        # 确保缓存目录存在
        cache_dir = os.path.join(self.cache_dir, name)
        
        cache = DiskCache(
            cache_dir=cache_dir,
            name=cache_name,
            memory_cache_size=memory_cache_size,
            cleanup_interval=cleanup_interval,
            serializer=serializer
        )
        
        # 添加全局回调
        for event, callbacks in self._callbacks.items():
            for callback in callbacks:
                cache.add_callback(event, callback)
                
        self._caches[name] = cache
        logger.info(f"Created disk cache '{name}' at {cache_dir}")
        return cache
    
    def create_redis_cache(self, name: str, config: Optional['RedisConfig'] = None) -> Optional['RedisCache']:
        """
        创建Redis缓存
        
        Args:
            name: 缓存名称
            config: Redis配置
            
        Returns:
            Optional[RedisCache]: Redis缓存实例，如果Redis不可用则返回None
        """
        if not REDIS_AVAILABLE:
            logger.error("Redis package not available, cannot create Redis cache")
            return None
            
        if name in self._caches:
            logger.warning(f"Cache '{name}' already exists, returning existing instance")
            return self._caches[name]
            
        # 使用默认配置或自定义配置
        if config is None:
            config = RedisConfig(
                prefix=f"{self.app_name}:{name}:"
            )
            
        try:
            cache = RedisCache(config=config)
            
            # 添加全局回调
            for event, callbacks in self._callbacks.items():
                for callback in callbacks:
                    cache.add_callback(event, callback)
                    
            self._caches[name] = cache
            logger.info(f"Created Redis cache '{name}'")
            return cache
            
        except Exception as e:
            logger.error(f"Failed to create Redis cache '{name}': {str(e)}")
            return None
    
    def get_cache(self, name: str) -> Any:
        """
        获取缓存实例
        
        Args:
            name: 缓存名称
            
        Returns:
            Any: 缓存实例或None
        """
        return self._caches.get(name)
    
    def get(self, key: str, default: Any = None, cache_name: str = "default") -> Any:
        """
        从指定缓存获取值
        
        Args:
            key: 缓存键
            default: 如果键不存在或已过期时的默认值
            cache_name: 缓存名称
            
        Returns:
            Any: 缓存值或默认值
        """
        cache = self._caches.get(cache_name)
        
        if cache is None:
            logger.warning(f"Cache '{cache_name}' not found, using default cache")
            cache = self.default_cache
            
        return cache.get(key, default)
    
    def put(self, key: str, value: Any, ttl: Optional[float] = None,
           policy: CachePolicy = CachePolicy.EXPIRE_AFTER_WRITE,
           metadata: Optional[Dict[str, Any]] = None,
           cache_name: str = "default") -> None:
        """
        存入值到指定缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间(秒)
            policy: 缓存策略
            metadata: 元数据
            cache_name: 缓存名称
        """
        cache = self._caches.get(cache_name)
        
        if cache is None:
            logger.warning(f"Cache '{cache_name}' not found, using default cache")
            cache = self.default_cache
            
        cache.put(key, value, ttl, policy, metadata)
    
    def delete(self, key: str, cache_name: str = "default") -> bool:
        """
        从指定缓存删除值
        
        Args:
            key: 缓存键
            cache_name: 缓存名称
            
        Returns:
            bool: 是否成功删除
        """
        cache = self._caches.get(cache_name)
        
        if cache is None:
            logger.warning(f"Cache '{cache_name}' not found, using default cache")
            cache = self.default_cache
            
        return cache.delete(key)
    
    def clear(self, cache_name: str = None) -> None:
        """
        清空缓存
        
        Args:
            cache_name: 缓存名称，如果为None则清空所有缓存
        """
        if cache_name is None:
            # 清空所有缓存
            for name, cache in self._caches.items():
                try:
                    cache.clear()
                    logger.info(f"Cleared cache '{name}'")
                except Exception as e:
                    logger.error(f"Error clearing cache '{name}': {str(e)}")
        else:
            # 清空指定缓存
            cache = self._caches.get(cache_name)
            
            if cache is None:
                logger.warning(f"Cache '{cache_name}' not found")
                return
                
            cache.clear()
            logger.info(f"Cleared cache '{cache_name}'")
    
    def get_many(self, keys: List[str], cache_name: str = "default") -> Dict[str, Any]:
        """
        从指定缓存批量获取多个值
        
        Args:
            keys: 缓存键列表
            cache_name: 缓存名称
            
        Returns:
            Dict[str, Any]: 键值对字典
        """
        cache = self._caches.get(cache_name)
        
        if cache is None:
            logger.warning(f"Cache '{cache_name}' not found, using default cache")
            cache = self.default_cache
            
        return cache.get_many(keys)
    
    def put_many(self, items: Dict[str, Any], ttl: Optional[float] = None,
               policy: CachePolicy = CachePolicy.EXPIRE_AFTER_WRITE,
               metadata: Optional[Dict[str, Any]] = None,
               cache_name: str = "default") -> int:
        """
        批量存入多个值到指定缓存
        
        Args:
            items: 键值对字典
            ttl: 生存时间(秒)
            policy: 缓存策略
            metadata: 元数据
            cache_name: 缓存名称
            
        Returns:
            int: 成功存入的数量
        """
        cache = self._caches.get(cache_name)
        
        if cache is None:
            logger.warning(f"Cache '{cache_name}' not found, using default cache")
            cache = self.default_cache
            
        return cache.put_many(items, ttl, policy, metadata)
    
    def delete_many(self, keys: List[str], cache_name: str = "default") -> int:
        """
        批量删除多个值
        
        Args:
            keys: 缓存键列表
            cache_name: 缓存名称
            
        Returns:
            int: 成功删除的数量
        """
        cache = self._caches.get(cache_name)
        
        if cache is None:
            logger.warning(f"Cache '{cache_name}' not found, using default cache")
            cache = self.default_cache
            
        return cache.delete_many(keys)
    
    def exists(self, key: str, cache_name: str = "default") -> bool:
        """
        检查键是否存在于指定缓存
        
        Args:
            key: 缓存键
            cache_name: 缓存名称
            
        Returns:
            bool: 是否存在
        """
        cache = self._caches.get(cache_name)
        
        if cache is None:
            logger.warning(f"Cache '{cache_name}' not found, using default cache")
            cache = self.default_cache
            
        return cache.exists(key)
    
    def add_global_callback(self, event: str, callback: Callable) -> bool:
        """
        添加全局事件回调函数
        
        Args:
            event: 事件名称 ('on_get', 'on_put', 'on_delete', 'on_expire')
            callback: 回调函数
            
        Returns:
            bool: 是否成功添加
        """
        if event not in self._callbacks:
            return False
            
        self._callbacks[event].append(callback)
        
        # 添加到所有现有缓存
        for cache in self._caches.values():
            if hasattr(cache, 'add_callback'):
                cache.add_callback(event, callback)
                
        return True
    
    def remove_global_callback(self, event: str, callback: Callable) -> bool:
        """
        移除全局事件回调函数
        
        Args:
            event: 事件名称
            callback: 回调函数
            
        Returns:
            bool: 是否成功移除
        """
        if event not in self._callbacks:
            return False
            
        if callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)
            
            # 从所有现有缓存移除
            for cache in self._caches.values():
                if hasattr(cache, 'remove_callback'):
                    cache.remove_callback(event, callback)
                    
            return True
            
        return False
    
    def get_stats(self, cache_name: str = None) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Args:
            cache_name: 缓存名称，如果为None则返回所有缓存的统计信息
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        if cache_name is not None:
            cache = self._caches.get(cache_name)
            
            if cache is None:
                logger.warning(f"Cache '{cache_name}' not found")
                return {}
                
            return cache.get_stats()
        else:
            # 获取所有缓存的统计信息
            stats = {}
            
            for name, cache in self._caches.items():
                if hasattr(cache, 'get_stats'):
                    stats[name] = cache.get_stats()
                    
            return stats
    
    def close(self, cache_name: str = None) -> None:
        """
        关闭缓存
        
        Args:
            cache_name: 缓存名称，如果为None则关闭所有缓存
        """
        if cache_name is None:
            # 关闭所有缓存
            for name, cache in list(self._caches.items()):
                try:
                    if hasattr(cache, 'close'):
                        cache.close()
                        logger.info(f"Closed cache '{name}'")
                except Exception as e:
                    logger.error(f"Error closing cache '{name}': {str(e)}")
        else:
            # 关闭指定缓存
            cache = self._caches.get(cache_name)
            
            if cache is None:
                logger.warning(f"Cache '{cache_name}' not found")
                return
                
            if hasattr(cache, 'close'):
                cache.close()
                logger.info(f"Closed cache '{cache_name}'")
    
    def __del__(self):
        """
        析构函数，关闭所有缓存
        """
        try:
            self.close()
        except:
            pass