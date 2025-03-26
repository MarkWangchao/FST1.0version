"""
磁盘缓存类，提供持久化的数据缓存功能
"""

import os
import json
import pickle
import hashlib
import shutil
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Callable, Union

from .cache_item import CacheItem, CachePolicy

logger = logging.getLogger(__name__)


class DiskCache:
    """
    磁盘缓存实现，具有以下特性:
    - 支持将数据持久化到磁盘
    - 支持序列化和反序列化复杂对象
    - 支持多种缓存过期策略
    - 定期清理过期文件
    - 支持内存与磁盘两级缓存
    """
    
    def __init__(self, 
                 cache_dir: str, 
                 name: str = "default", 
                 memory_cache_size: int = 1000,
                 cleanup_interval: float = 3600.0,
                 serializer: str = "json"):
        """
        初始化磁盘缓存
        
        Args:
            cache_dir: 缓存目录
            name: 缓存名称
            memory_cache_size: 内存缓存大小(0表示禁用内存缓存)
            cleanup_interval: 清理过期文件的间隔(秒)
            serializer: 序列化方式，支持"json"和"pickle"
        """
        self.name = name
        self.cache_dir = os.path.join(cache_dir, name)
        self.memory_cache_size = memory_cache_size
        self.cleanup_interval = cleanup_interval
        
        # 确保缓存目录存在
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 设置序列化器
        if serializer not in ("json", "pickle"):
            raise ValueError("Serializer must be either 'json' or 'pickle'")
        self.serializer = serializer
        
        # 内存缓存(LRU)
        self._memory_cache: Dict[str, CacheItem] = {}
        self._memory_keys_by_access: List[str] = []
        
        # 用于序列化操作的锁
        self._file_locks: Dict[str, threading.RLock] = {}
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            'hits': 0,
            'misses': 0,
            'memory_hits': 0,
            'file_hits': 0,
            'writes': 0,
            'evictions': 0,
            'cleanups': 0
        }
        
        # 启动清理线程
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, 
            daemon=True, 
            name=f"DiskCache-{name}-Cleanup"
        )
        self._cleanup_thread.start()
        
        logger.info(f"Disk cache '{name}' initialized at {self.cache_dir}")
    
    def _get_file_path(self, key: str) -> str:
        """
        获取缓存键对应的文件路径
        
        Args:
            key: 缓存键
            
        Returns:
            str: 文件路径
        """
        # 使用MD5哈希键名以避免文件系统问题
        hashed_key = hashlib.md5(key.encode('utf-8')).hexdigest()
        
        # 使用子目录分散文件，提高性能
        subdir = hashed_key[:2]
        subdir_path = os.path.join(self.cache_dir, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        
        return os.path.join(subdir_path, f"{hashed_key}.cache")
    
    def _get_file_lock(self, file_path: str) -> threading.RLock:
        """
        获取文件操作的锁
        
        Args:
            file_path: 文件路径
            
        Returns:
            threading.RLock: 文件锁
        """
        with self._lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = threading.RLock()
            return self._file_locks[file_path]
    
    def _serialize(self, item: CacheItem) -> bytes:
        """
        序列化缓存项
        
        Args:
            item: 缓存项
            
        Returns:
            bytes: 序列化后的数据
        """
        data = item.to_dict()
        
        if self.serializer == "json":
            return json.dumps(data).encode('utf-8')
        else:  # pickle
            return pickle.dumps(data)
    
    def _deserialize(self, data: bytes) -> CacheItem:
        """
        反序列化缓存项
        
        Args:
            data: 序列化的数据
            
        Returns:
            CacheItem: 缓存项
        """
        if self.serializer == "json":
            data_dict = json.loads(data.decode('utf-8'))
        else:  # pickle
            data_dict = pickle.loads(data)
            
        return CacheItem.from_dict(data_dict)
    
    def _update_memory_cache(self, key: str, item: CacheItem) -> None:
        """
        更新内存缓存
        
        Args:
            key: 缓存键
            item: 缓存项
        """
        if self.memory_cache_size <= 0:
            return
            
        with self._lock:
            # 如果内存缓存已满，删除最近最少使用的项
            if key not in self._memory_cache and len(self._memory_cache) >= self.memory_cache_size:
                if self._memory_keys_by_access:
                    lru_key = self._memory_keys_by_access.pop(0)
                    if lru_key in self._memory_cache:
                        del self._memory_cache[lru_key]
                        
            # 更新内存缓存
            self._memory_cache[key] = item
            
            # 更新访问顺序
            if key in self._memory_keys_by_access:
                self._memory_keys_by_access.remove(key)
            self._memory_keys_by_access.append(key)
    
    def _remove_from_memory_cache(self, key: str) -> None:
        """
        从内存缓存中移除项
        
        Args:
            key: 缓存键
        """
        if self.memory_cache_size <= 0:
            return
            
        with self._lock:
            if key in self._memory_cache:
                del self._memory_cache[key]
                
            if key in self._memory_keys_by_access:
                self._memory_keys_by_access.remove(key)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存项
        
        Args:
            key: 缓存键
            default: 如果键不存在或已过期时的默认值
            
        Returns:
            Any: 缓存值或默认值
        """
        # 检查内存缓存
        if self.memory_cache_size > 0:
            with self._lock:
                if key in self._memory_cache:
                    item = self._memory_cache[key]
                    
                    # 检查过期
                    if item.is_expired():
                        self._remove_from_memory_cache(key)
                    else:
                        # 更新访问时间并返回值
                        item.access()
                        self._stats['hits'] += 1
                        self._stats['memory_hits'] += 1
                        
                        # 更新访问顺序
                        if key in self._memory_keys_by_access:
                            self._memory_keys_by_access.remove(key)
                        self._memory_keys_by_access.append(key)
                        
                        return item.value
        
        # 检查磁盘缓存
        file_path = self._get_file_path(key)
        file_lock = self._get_file_lock(file_path)
        
        with file_lock:
            if not os.path.exists(file_path):
                self._stats['misses'] += 1
                return default
                
            try:
                with open(file_path, 'rb') as f:
                    item = self._deserialize(f.read())
                    
                # 检查过期
                if item.is_expired():
                    # 删除过期文件
                    try:
                        os.unlink(file_path)
                    except OSError:
                        pass
                    self._stats['misses'] += 1
                    return default
                    
                # 更新访问时间
                item.access()
                
                # 如果是EXPIRE_AFTER_ACCESS策略，需要更新文件
                if item.policy == CachePolicy.EXPIRE_AFTER_ACCESS:
                    with open(file_path, 'wb') as f:
                        f.write(self._serialize(item))
                        
                # 添加到内存缓存
                self._update_memory_cache(key, item)
                
                self._stats['hits'] += 1
                self._stats['file_hits'] += 1
                
                return item.value
                
            except (OSError, json.JSONDecodeError, pickle.PickleError) as e:
                logger.error(f"Error reading cache file {file_path}: {str(e)}")
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
        expire_at = None
        
        if policy == CachePolicy.EXPIRE_AT_TIME and ttl is not None:
            expire_at = now + timedelta(seconds=ttl)
            
        # 创建缓存项
        item = CacheItem(
            key=key,
            value=value,
            created_at=now,
            last_accessed=now,
            policy=policy,
            ttl=ttl if ttl is not None else 300,
            expire_at=expire_at,
            metadata=metadata or {}
        )
        
        # 更新内存缓存
        self._update_memory_cache(key, item)
        
        # 写入磁盘缓存
        file_path = self._get_file_path(key)
        file_lock = self._get_file_lock(file_path)
        
        with file_lock:
            try:
                with open(file_path, 'wb') as f:
                    f.write(self._serialize(item))
                self._stats['writes'] += 1
            except OSError as e:
                logger.error(f"Error writing cache file {file_path}: {str(e)}")
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否成功删除
        """
        # 从内存缓存删除
        self._remove_from_memory_cache(key)
        
        # 从磁盘缓存删除
        file_path = self._get_file_path(key)
        file_lock = self._get_file_lock(file_path)
        
        with file_lock:
            if os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                    return True
                except OSError as e:
                    logger.error(f"Error deleting cache file {file_path}: {str(e)}")
                    
        return False
    
    def clear(self) -> None:
        """清空缓存"""
        # 清空内存缓存
        with self._lock:
            self._memory_cache.clear()
            self._memory_keys_by_access.clear()
        
        # 清空磁盘缓存
        try:
            for root, dirs, files in os.walk(self.cache_dir):
                for file in files:
                    if file.endswith('.cache'):
                        try:
                            os.unlink(os.path.join(root, file))
                        except OSError:
                            pass
                            
            logger.info(f"Cache '{self.name}' cleared")
        except OSError as e:
            logger.error(f"Error clearing cache directory {self.cache_dir}: {str(e)}")
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        批量获取多个缓存项
        
        Args:
            keys: 缓存键列表
            
        Returns:
            Dict[str, Any]: 键值对字典
        """
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    def put_many(self, items: Dict[str, Any], ttl: Optional[float] = None,
                policy: CachePolicy = CachePolicy.EXPIRE_AFTER_WRITE,
                metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        批量存入多个缓存项
        
        Args:
            items: 键值对字典
            ttl: 生存时间(秒)
            policy: 缓存策略
            metadata: 元数据
        """
        for key, value in items.items():
            self.put(key, value, ttl, policy, metadata)
    
    def delete_many(self, keys: List[str]) -> int:
        """
        批量删除多个缓存项
        
        Args:
            keys: 缓存键列表
            
        Returns:
            int: 成功删除的数量
        """
        count = 0
        for key in keys:
            if self.delete(key):
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
        # 检查内存缓存
        if self.memory_cache_size > 0:
            with self._lock:
                if key in self._memory_cache:
                    item = self._memory_cache[key]
                    
                    # 检查过期
                    if item.is_expired():
                        self._remove_from_memory_cache(key)
                    else:
                        return True
        
        # 检查磁盘缓存
        file_path = self._get_file_path(key)
        file_lock = self._get_file_lock(file_path)
        
        with file_lock:
            if not os.path.exists(file_path):
                return False
                
            try:
                with open(file_path, 'rb') as f:
                    item = self._deserialize(f.read())
                    
                # 检查过期
                if item.is_expired():
                    # 删除过期文件
                    try:
                        os.unlink(file_path)
                    except OSError:
                        pass
                    return False
                    
                # 添加到内存缓存
                self._update_memory_cache(key, item)
                
                return True
                
            except (OSError, json.JSONDecodeError, pickle.PickleError):
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            stats = self._stats.copy()
            stats['memory_cache_size'] = len(self._memory_cache)
            stats['memory_cache_max'] = self.memory_cache_size
            
            # 计算磁盘缓存大小
            disk_size = 0
            file_count = 0
            
            try:
                for root, dirs, files in os.walk(self.cache_dir):
                    for file in files:
                        if file.endswith('.cache'):
                            file_path = os.path.join(root, file)
                            try:
                                disk_size += os.path.getsize(file_path)
                                file_count += 1
                            except OSError:
                                pass
            except OSError:
                pass
                
            stats['disk_cache_size'] = disk_size
            stats['disk_cache_files'] = file_count
            
            return stats
    
    def _cleanup_expired(self) -> int:
        """
        清理所有过期的缓存文件
        
        Returns:
            int: 清理的文件数量
        """
        count = 0
        
        # 清理内存缓存中过期的项
        if self.memory_cache_size > 0:
            with self._lock:
                for key in list(self._memory_cache.keys()):
                    item = self._memory_cache[key]
                    if item.is_expired():
                        self._remove_from_memory_cache(key)
                        count += 1
        
        # 清理磁盘缓存中过期的文件
        try:
            for root, dirs, files in os.walk(self.cache_dir):
                for file in files:
                    if file.endswith('.cache'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'rb') as f:
                                item = self._deserialize(f.read())
                                
                            if item.is_expired():
                                os.unlink(file_path)
                                count += 1
                                
                        except (OSError, json.JSONDecodeError, pickle.PickleError):
                            # 如果文件损坏，删除它
                            try:
                                os.unlink(file_path)
                                count += 1
                            except OSError:
                                pass
        except OSError as e:
            logger.error(f"Error during cleanup: {str(e)}")
            
        if count > 0:
            self._stats['cleanups'] += 1
            logger.debug(f"Cleaned up {count} expired items from disk cache '{self.name}'")
            
        return count
    
    def _cleanup_loop(self) -> None:
        """
        清理线程循环
        """
        while not self._stop_cleanup.is_set():
            try:
                time.sleep(self.cleanup_interval)
                self._cleanup_expired()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {str(e)}")
    
    def close(self) -> None:
        """
        关闭缓存，停止清理线程
        """
        self._stop_cleanup.set()
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1.0)
        logger.info(f"Disk cache '{self.name}' closed")
    
    def __del__(self) -> None:
        """
        析构函数，确保清理线程被停止
        """
        try:
            self.close()
        except:
            pass
            
    def get_file_path_for_key(self, key: str) -> str:
        """
        获取缓存键对应的文件路径
        
        Args:
            key: 缓存键
            
        Returns:
            str: 文件路径
        """
        return self._get_file_path(key)