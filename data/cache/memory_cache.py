"""
内存缓存类，提供高性能的内存中数据缓存
"""

import threading
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
import time
import json

from .cache_item import CacheItem, CachePolicy

logger = logging.getLogger(__name__)


class MemoryCache:
    """
    内存缓存实现，具有以下特性:
    - 线程安全的操作
    - 支持多种缓存过期策略
    - 定期清理过期项
    - 支持自定义回调函数
    - 统计功能
    """
    
    def __init__(self, name: str = "default", max_size: int = 10000, 
                cleanup_interval: float = 60.0):
        """
        初始化内存缓存
        
        Args:
            name: 缓存名称
            max_size: 最大缓存项数量
            cleanup_interval: 清理过期项的间隔(秒)
        """
        self.name = name
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval
        
        # 使用字典存储缓存项
        self._cache: Dict[str, CacheItem] = {}
        
        # 统计信息
        self._stats = {
            'hits': 0,
            'misses': 0,
            'puts': 0,
            'evictions': 0,
            'cleanups': 0
        }
        
        # 事件回调
        self._callbacks: Dict[str, List[Callable]] = {
            'on_get': [],
            'on_put': [],
            'on_delete': [],
            'on_evict': [],
            'on_cleanup': []
        }
        
        # 线程安全锁
        self._lock = threading.RLock()
        
        # 启动清理线程
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, 
            daemon=True, 
            name=f"MemoryCache-{name}-Cleanup"
        )
        self._cleanup_thread.start()
        
        logger.info(f"Memory cache '{name}' initialized with max size {max_size}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存项
        
        Args:
            key: 缓存键
            default: 如果键不存在或已过期时的默认值
            
        Returns:
            Any: 缓存值或默认值
        """
        with self._lock:
            if key in self._cache:
                cache_item = self._cache[key]
                
                # 检查过期
                if cache_item.is_expired():
                    self._delete(key)
                    self._stats['misses'] += 1
                    return default
                
                # 更新访问时间并返回值
                cache_item.access()
                self._stats['hits'] += 1
                
                # 触发回调
                for callback in self._callbacks['on_get']:
                    try:
                        callback(key, cache_item.value)
                    except Exception as e:
                        logger.error(f"Error in on_get callback: {str(e)}")
                
                return cache_item.value
            
            self._stats['misses'] += 1
            return default
    
    def put(self, key: str, value: Any, ttl: Optional[float] = None, 
           policy: CachePolicy = CachePolicy.EXPIRE_AFTER_WRITE,
           metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        存入缓存项
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间(秒)
            policy: 缓存策略
            metadata: 元数据
        """
        now = datetime.now()
        
        with self._lock:
            # 检查缓存大小，如果达到最大值则清理最旧的项
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict_oldest()
            
            # 创建或更新缓存项
            if key in self._cache:
                item = self._cache[key]
                item.update(value)
                if ttl is not None:
                    item.set_ttl(ttl)
                item.set_policy(policy)
                if metadata:
                    item.metadata.update(metadata)
            else:
                item = CacheItem(
                    key=key,
                    value=value,
                    created_at=now,
                    last_accessed=now,
                    policy=policy,
                    ttl=ttl if ttl is not None else 300,
                    metadata=metadata or {}
                )
                self._cache[key] = item
            
            self._stats['puts'] += 1
            
            # 触发回调
            for callback in self._callbacks['on_put']:
                try:
                    callback(key, value)
                except Exception as e:
                    logger.error(f"Error in on_put callback: {str(e)}")
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否成功删除
        """
        with self._lock:
            return self._delete(key)
    
    def _delete(self, key: str) -> bool:
        """
        内部删除方法，不加锁
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否成功删除
        """
        if key in self._cache:
            item = self._cache[key]
            del self._cache[key]
            
            # 触发回调
            for callback in self._callbacks['on_delete']:
                try:
                    callback(key, item.value)
                except Exception as e:
                    logger.error(f"Error in on_delete callback: {str(e)}")
                    
            return True
        return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            logger.info(f"Cache '{self.name}' cleared")
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        批量获取多个缓存项
        
        Args:
            keys: 缓存键列表
            
        Returns:
            Dict[str, Any]: 键值对字典
        """
        result = {}
        with self._lock:
            for key in keys:
                value = self.get(key)
                if value is not None:
                    result[key] = value
        return result
    
    def put_many(self, items: Dict[str, Any], ttl: Optional[float] = None,
                policy: CachePolicy = CachePolicy.EXPIRE_AFTER_WRITE) -> None:
        """
        批量存入多个缓存项
        
        Args:
            items: 键值对字典
            ttl: 生存时间(秒)
            policy: 缓存策略
        """
        with self._lock:
            for key, value in items.items():
                self.put(key, value, ttl, policy)
    
    def delete_many(self, keys: List[str]) -> int:
        """
        批量删除多个缓存项
        
        Args:
            keys: 缓存键列表
            
        Returns:
            int: 成功删除的数量
        """
        count = 0
        with self._lock:
            for key in keys:
                if self._delete(key):
                    count += 1
        return count
    
    def exists(self, key: str) -> bool:
        """
        检查键是否存在且未过期
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在有效的缓存项
        """
        with self._lock:
            if key in self._cache:
                item = self._cache[key]
                if item.is_expired():
                    self._delete(key)
                    return False
                return True
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            stats = self._stats.copy()
            stats['size'] = len(self._cache)
            stats['max_size'] = self.max_size
            return stats
    
    def get_all_keys(self) -> List[str]:
        """
        获取所有有效的缓存键
        
        Returns:
            List[str]: 键列表
        """
        result = []
        with self._lock:
            for key, item in list(self._cache.items()):
                if item.is_expired():
                    self._delete(key)
                else:
                    result.append(key)
        return result
    
    def get_oldest(self) -> Optional[Tuple[str, Any]]:
        """
        获取最旧的缓存项
        
        Returns:
            Optional[Tuple[str, Any]]: (键, 值)元组
        """
        with self._lock:
            if not self._cache:
                return None
                
            oldest_key = None
            oldest_time = None
            
            for key, item in self._cache.items():
                if item.is_expired():
                    self._delete(key)
                    continue
                    
                if oldest_time is None or item.created_at < oldest_time:
                    oldest_key = key
                    oldest_time = item.created_at
            
            if oldest_key:
                return (oldest_key, self._cache[oldest_key].value)
            return None
    
    def get_ttl(self, key: str) -> Optional[float]:
        """
        获取缓存项的剩余生存时间
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[float]: 剩余秒数，或None表示永不过期或不存在
        """
        with self._lock:
            if key in self._cache:
                item = self._cache[key]
                
                if item.is_expired():
                    self._delete(key)
                    return None
                    
                if item.policy == CachePolicy.NEVER_EXPIRE:
                    return None
                
                now = datetime.now()
                
                if item.policy == CachePolicy.EXPIRE_AT_TIME:
                    if item.expire_at:
                        return max(0, (item.expire_at - now).total_seconds())
                    return None
                    
                elif item.policy == CachePolicy.EXPIRE_AFTER_WRITE:
                    if item.ttl is None:
                        return None
                    age = (now - item.created_at).total_seconds()
                    return max(0, item.ttl - age)
                    
                elif item.policy == CachePolicy.EXPIRE_AFTER_ACCESS:
                    if item.ttl is None:
                        return None
                    age = (now - item.last_accessed).total_seconds()
                    return max(0, item.ttl - age)
            
            return None
    
    def _evict_oldest(self) -> bool:
        """
        淘汰最旧的缓存项
        
        Returns:
            bool: 是否成功淘汰
        """
        if not self._cache:
            return False
            
        oldest_key = None
        oldest_time = None
        
        # 先淘汰已过期的
        for key, item in list(self._cache.items()):
            if item.is_expired():
                self._delete(key)
                self._stats['evictions'] += 1
                return True
                
        # 如果没有过期的，淘汰最旧的
        for key, item in self._cache.items():
            if oldest_time is None or item.created_at < oldest_time:
                oldest_key = key
                oldest_time = item.created_at
        
        if oldest_key:
            item = self._cache[oldest_key]
            self._delete(oldest_key)
            
            # 触发淘汰回调
            for callback in self._callbacks['on_evict']:
                try:
                    callback(oldest_key, item.value)
                except Exception as e:
                    logger.error(f"Error in on_evict callback: {str(e)}")
                    
            self._stats['evictions'] += 1
            return True
            
        return False
    
    def _cleanup_expired(self) -> int:
        """
        清理所有过期的缓存项
        
        Returns:
            int: 清理的项数量
        """
        if not self._cache:
            return 0
            
        count = 0
        now = datetime.now()
        
        for key, item in list(self._cache.items()):
            if item.is_expired():
                self._delete(key)
                count += 1
        
        if count > 0:
            # 触发清理回调
            for callback in self._callbacks['on_cleanup']:
                try:
                    callback(count)
                except Exception as e:
                    logger.error(f"Error in on_cleanup callback: {str(e)}")
                    
            self._stats['cleanups'] += 1
            logger.debug(f"Cleaned up {count} expired items from cache '{self.name}'")
            
        return count
    
    def _cleanup_loop(self) -> None:
        """
        清理线程循环
        """
        while not self._stop_cleanup.is_set():
            try:
                time.sleep(self.cleanup_interval)
                with self._lock:
                    self._cleanup_expired()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {str(e)}")
    
    def add_callback(self, event: str, callback: Callable) -> bool:
        """
        添加事件回调函数
        
        Args:
            event: 事件名称 ('on_get', 'on_put', 'on_delete', 'on_evict', 'on_cleanup')
            callback: 回调函数
            
        Returns:
            bool: 是否成功添加
        """
        if event not in self._callbacks:
            return False
            
        with self._lock:
            self._callbacks[event].append(callback)
            return True
    
    def remove_callback(self, event: str, callback: Callable) -> bool:
        """
        移除事件回调函数
        
        Args:
            event: 事件名称
            callback: 回调函数
            
        Returns:
            bool: 是否成功移除
        """
        if event not in self._callbacks:
            return False
            
        with self._lock:
            if callback in self._callbacks[event]:
                self._callbacks[event].remove(callback)
                return True
            return False
    
    def close(self) -> None:
        """
        关闭缓存，停止清理线程
        """
        self._stop_cleanup.set()
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1.0)
        logger.info(f"Memory cache '{self.name}' closed")
    
    def __del__(self) -> None:
        """
        析构函数，确保清理线程被停止
        """
        try:
            self.close()
        except:
            pass
            
    def to_json(self, file_path: str) -> None:
        """
        将缓存内容保存为JSON文件
        
        Args:
            file_path: 文件路径
        """
        with self._lock:
            serializable_cache = {}
            
            for key, item in self._cache.items():
                if not item.is_expired():
                    try:
                        # 尝试将缓存项序列化为字典
                        serializable_cache[key] = item.to_dict()
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Could not serialize cache item {key}: {str(e)}")
            
            try:
                with open(file_path, 'w') as f:
                    json.dump(serializable_cache, f, indent=2)
                    
                logger.info(f"Cache '{self.name}' saved to {file_path}")
            except Exception as e:
                logger.error(f"Error saving cache to file: {str(e)}")
    
    @classmethod
    def from_json(cls, file_path: str, name: str = "default", 
                max_size: int = 10000) -> 'MemoryCache':
        """
        从JSON文件加载缓存
        
        Args:
            file_path: 文件路径
            name: 缓存名称
            max_size: 最大缓存项数量
            
        Returns:
            MemoryCache: 加载的缓存对象
        """
        cache = cls(name=name, max_size=max_size)
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            for key, item_dict in data.items():
                try:
                    cache_item = CacheItem.from_dict(item_dict)
                    
                    # 只加载未过期的项
                    if not cache_item.is_expired():
                        cache._cache[key] = cache_item
                except Exception as e:
                    logger.warning(f"Could not load cache item {key}: {str(e)}")
                    
            logger.info(f"Loaded {len(cache._cache)} items into cache '{name}' from {file_path}")
            
        except FileNotFoundError:
            logger.warning(f"Cache file {file_path} not found, starting with empty cache")
        except Exception as e:
            logger.error(f"Error loading cache from file: {str(e)}")
            
        return cache