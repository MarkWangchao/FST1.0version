"""
Redis缓存类，提供分布式的缓存功能
"""

import json
import pickle
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Callable, Union
import time
import threading
from dataclasses import dataclass

from .cache_item import CacheItem, CachePolicy

# 尝试导入redis，如果不可用则提供错误信息
try:
    import redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    RedisError = Exception

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """Redis配置"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    decode_responses: bool = False
    max_connections: int = 10
    retry_on_timeout: bool = True
    prefix: str = "cache:"
    serializer: str = "json"


class RedisCache:
    """
    Redis缓存实现，具有以下特性:
    - 支持分布式缓存
    - 支持序列化和反序列化复杂对象
    - 支持多种缓存过期策略
    - 支持键空间通知(keyspace notifications)
    - 支持事件回调
    """
    
    def __init__(self, config: Optional[RedisConfig] = None, 
                client: Optional['redis.Redis'] = None):
        """
        初始化Redis缓存
        
        Args:
            config: Redis配置，如果提供client则忽略此参数
            client: 现有的Redis客户端实例
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis package is not installed. "
                "Please install it with 'pip install redis'"
            )
            
        self.config = config or RedisConfig()
        
        # 使用提供的客户端或创建新客户端
        if client:
            self.client = client
        else:
            self.pool = redis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                decode_responses=self.config.decode_responses,
                max_connections=self.config.max_connections,
                retry_on_timeout=self.config.retry_on_timeout
            )
            self.client = redis.Redis(connection_pool=self.pool)
            
        # 键前缀
        self.prefix = self.config.prefix
        
        # 序列化方式
        if self.config.serializer not in ("json", "pickle"):
            raise ValueError("Serializer must be either 'json' or 'pickle'")
        self.serializer = self.config.serializer
        
        # 事件回调
        self._callbacks: Dict[str, List[Callable]] = {
            'on_get': [],
            'on_put': [],
            'on_delete': [],
            'on_expire': []
        }
        
        # 统计信息
        self._stats = {
            'hits': 0,
            'misses': 0,
            'puts': 0,
            'deletes': 0
        }
        self._stats_lock = threading.RLock()
        
        # 测试连接
        try:
            self.client.ping()
            logger.info(f"Redis cache connected to {self.config.host}:{self.config.port}")
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise
    
    def _get_key(self, key: str) -> str:
        """
        获取带前缀的Redis键
        
        Args:
            key: 缓存键
            
        Returns:
            str: 带前缀的Redis键
        """
        return f"{self.prefix}{key}"
    
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
        if data is None:
            return None
            
        if self.serializer == "json":
            try:
                data_dict = json.loads(data.decode('utf-8'))
            except UnicodeDecodeError:
                # 尝试使用pickle反序列化
                data_dict = pickle.loads(data)
        else:  # pickle
            data_dict = pickle.loads(data)
            
        return CacheItem.from_dict(data_dict)
    
    def _calculate_ttl(self, item: CacheItem) -> Optional[int]:
        """
        计算Redis TTL
        
        Args:
            item: 缓存项
            
        Returns:
            Optional[int]: TTL值(秒)或None表示永不过期
        """
        if item.policy == CachePolicy.NEVER_EXPIRE:
            return None
            
        if item.policy == CachePolicy.EXPIRE_AT_TIME:
            if item.expire_at:
                now = datetime.now()
                ttl = (item.expire_at - now).total_seconds()
                return max(1, int(ttl)) if ttl > 0 else 1
            return None
            
        if item.ttl is not None:
            return max(1, int(item.ttl))
            
        return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存项
        
        Args:
            key: 缓存键
            default: 如果键不存在或已过期时的默认值
            
        Returns:
            Any: 缓存值或默认值
        """
        redis_key = self._get_key(key)
        
        try:
            data = self.client.get(redis_key)
            
            if data is None:
                with self._stats_lock:
                    self._stats['misses'] += 1
                return default
                
            item = self._deserialize(data)
            
            if item is None:
                with self._stats_lock:
                    self._stats['misses'] += 1
                return default
                
            # 检查是否过期（仅针对EXPIRE_AFTER_ACCESS策略）
            if item.policy == CachePolicy.EXPIRE_AFTER_ACCESS:
                # 更新访问时间
                item.access()
                
                # 重新设置过期时间
                ttl = self._calculate_ttl(item)
                if ttl is not None:
                    pipe = self.client.pipeline()
                    pipe.set(redis_key, self._serialize(item))
                    pipe.expire(redis_key, ttl)
                    pipe.execute()
            
            with self._stats_lock:
                self._stats['hits'] += 1
                
            # 触发回调
            for callback in self._callbacks['on_get']:
                try:
                    callback(key, item.value)
                except Exception as e:
                    logger.error(f"Error in on_get callback: {str(e)}")
                
            return item.value
            
        except RedisError as e:
            logger.error(f"Redis error in get({key}): {str(e)}")
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
        
        redis_key = self._get_key(key)
        serialized = self._serialize(item)
        redis_ttl = self._calculate_ttl(item)
        
        try:
            if redis_ttl is not None:
                self.client.setex(redis_key, redis_ttl, serialized)
            else:
                self.client.set(redis_key, serialized)
                
            with self._stats_lock:
                self._stats['puts'] += 1
                
            # 触发回调
            for callback in self._callbacks['on_put']:
                try:
                    callback(key, value)
                except Exception as e:
                    logger.error(f"Error in on_put callback: {str(e)}")
                    
        except RedisError as e:
            logger.error(f"Redis error in put({key}): {str(e)}")
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否成功删除
        """
        redis_key = self._get_key(key)
        
        try:
            # 获取旧值（用于回调）
            old_value = None
            try:
                data = self.client.get(redis_key)
                if data:
                    item = self._deserialize(data)
                    if item:
                        old_value = item.value
            except:
                pass
                
            # 删除键
            result = self.client.delete(redis_key)
            success = result > 0
            
            if success:
                with self._stats_lock:
                    self._stats['deletes'] += 1
                    
                # 触发回调
                if old_value is not None:
                    for callback in self._callbacks['on_delete']:
                        try:
                            callback(key, old_value)
                        except Exception as e:
                            logger.error(f"Error in on_delete callback: {str(e)}")
                            
            return success
            
        except RedisError as e:
            logger.error(f"Redis error in delete({key}): {str(e)}")
            return False
    
    def clear(self, pattern: str = "*") -> int:
        """
        清空缓存
        
        Args:
            pattern: 匹配模式，默认清空所有
            
        Returns:
            int: 删除的键数量
        """
        try:
            # 获取所有匹配的键
            full_pattern = f"{self.prefix}{pattern}"
            keys = self.client.keys(full_pattern)
            
            # 如果没有键，直接返回
            if not keys:
                return 0
                
            # 删除所有键
            result = self.client.delete(*keys)
            
            logger.info(f"Cleared {result} keys from Redis cache")
            return result
            
        except RedisError as e:
            logger.error(f"Redis error in clear({pattern}): {str(e)}")
            return 0
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        批量获取多个缓存项
        
        Args:
            keys: 缓存键列表
            
        Returns:
            Dict[str, Any]: 键值对字典
        """
        if not keys:
            return {}
            
        # 转换为Redis键
        redis_keys = [self._get_key(key) for key in keys]
        
        try:
            # 使用MGET命令批量获取
            values = self.client.mget(redis_keys)
            
            result = {}
            hits = 0
            
            for i, (key, value) in enumerate(zip(keys, values)):
                if value is not None:
                    try:
                        item = self._deserialize(value)
                        if item and not item.is_expired():
                            result[key] = item.value
                            hits += 1
                            
                            # 对于EXPIRE_AFTER_ACCESS策略，需要更新访问时间
                            if item.policy == CachePolicy.EXPIRE_AFTER_ACCESS:
                                item.access()
                                redis_key = redis_keys[i]
                                ttl = self._calculate_ttl(item)
                                if ttl is not None:
                                    self.client.setex(redis_key, ttl, self._serialize(item))
                    except:
                        pass
            
            with self._stats_lock:
                self._stats['hits'] += hits
                self._stats['misses'] += (len(keys) - hits)
                
            return result
            
        except RedisError as e:
            logger.error(f"Redis error in get_many({keys}): {str(e)}")
            return {}
    
    def put_many(self, items: Dict[str, Any], ttl: Optional[float] = None,
                policy: CachePolicy = CachePolicy.EXPIRE_AFTER_WRITE,
                metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        批量存入多个缓存项
        
        Args:
            items: 键值对字典
            ttl: 生存时间(秒)
            policy: 缓存策略
            metadata: 元数据
            
        Returns:
            int: 成功存入的数量
        """
        if not items:
            return 0
            
        now = datetime.now()
        expire_at = None
        
        if policy == CachePolicy.EXPIRE_AT_TIME and ttl is not None:
            expire_at = now + timedelta(seconds=ttl)
        
        try:
            pipe = self.client.pipeline()
            count = 0
            
            for key, value in items.items():
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
                
                redis_key = self._get_key(key)
                serialized = self._serialize(item)
                redis_ttl = self._calculate_ttl(item)
                
                if redis_ttl is not None:
                    pipe.setex(redis_key, redis_ttl, serialized)
                else:
                    pipe.set(redis_key, serialized)
                    
                count += 1
            
            pipe.execute()
            
            with self._stats_lock:
                self._stats['puts'] += count
                
            return count
            
        except RedisError as e:
            logger.error(f"Redis error in put_many({list(items.keys())}): {str(e)}")
            return 0
    
    def delete_many(self, keys: List[str]) -> int:
        """
        批量删除多个缓存项
        
        Args:
            keys: 缓存键列表
            
        Returns:
            int: 成功删除的数量
        """
        if not keys:
            return 0
            
        # 转换为Redis键
        redis_keys = [self._get_key(key) for key in keys]
        
        try:
            result = self.client.delete(*redis_keys)
            
            with self._stats_lock:
                self._stats['deletes'] += result
                
            return result
            
        except RedisError as e:
            logger.error(f"Redis error in delete_many({keys}): {str(e)}")
            return 0
    
    def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在
        """
        redis_key = self._get_key(key)
        
        try:
            return self.client.exists(redis_key) > 0
        except RedisError as e:
            logger.error(f"Redis error in exists({key}): {str(e)}")
            return False
    
    def get_ttl(self, key: str) -> Optional[float]:
        """
        获取键的剩余生存时间
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[float]: 剩余秒数，或None表示永不过期或不存在
        """
        redis_key = self._get_key(key)
        
        try:
            ttl = self.client.ttl(redis_key)
            
            # -2表示键不存在，-1表示永不过期
            if ttl == -2:
                return None
            elif ttl == -1:
                return None  # 永不过期
            else:
                return float(ttl)
                
        except RedisError as e:
            logger.error(f"Redis error in get_ttl({key}): {str(e)}")
            return None
    
    def incr(self, key: str, amount: int = 1) -> int:
        """
        增加键的值（仅适用于整数值）
        
        Args:
            key: 缓存键
            amount: 增加的数量
            
        Returns:
            int: 增加后的值
        """
        redis_key = self._get_key(key)
        
        try:
            # 先检查键是否存在
            if not self.client.exists(redis_key):
                # 不存在则创建并设置为0
                self.put(key, 0)
                
            # 增加值
            return self.client.incrby(redis_key, amount)
            
        except RedisError as e:
            logger.error(f"Redis error in incr({key}): {str(e)}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._stats_lock:
            stats = self._stats.copy()
            
        # 添加Redis特有的统计信息
        try:
            info = self.client.info()
            
            # 添加内存使用信息
            if 'used_memory_human' in info:
                stats['used_memory'] = info['used_memory_human']
                
            # 添加键数量信息
            if 'db' + str(self.config.db) in info:
                db_info = info['db' + str(self.config.db)]
                stats['total_keys'] = db_info.get('keys', 0)
                
            # 添加服务器信息
            if 'redis_version' in info:
                stats['redis_version'] = info['redis_version']
                
        except RedisError as e:
            logger.error(f"Redis error in get_stats(): {str(e)}")
            
        return stats
    
    def add_callback(self, event: str, callback: Callable) -> bool:
        """
        添加事件回调函数
        
        Args:
            event: 事件名称 ('on_get', 'on_put', 'on_delete', 'on_expire')
            callback: 回调函数
            
        Returns:
            bool: 是否成功添加
        """
        if event not in self._callbacks:
            return False
            
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
            
        if callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)
            return True
            
        return False
    
    def keys(self, pattern: str = "*") -> List[str]:
        """
        获取匹配模式的所有键
        
        Args:
            pattern: 匹配模式
            
        Returns:
            List[str]: 键列表
        """
        try:
            # 构建完整模式
            full_pattern = f"{self.prefix}{pattern}"
            
            # 获取所有匹配的键
            redis_keys = self.client.keys(full_pattern)
            
            # 移除前缀
            prefix_len = len(self.prefix)
            return [key.decode('utf-8')[prefix_len:] if isinstance(key, bytes) else key[prefix_len:] 
                  for key in redis_keys]
                  
        except RedisError as e:
            logger.error(f"Redis error in keys({pattern}): {str(e)}")
            return []
    
    def flush(self) -> bool:
        """
        刷新所有缓存数据到磁盘
        
        Returns:
            bool: 是否成功刷新
        """
        try:
            self.client.save()
            return True
        except RedisError as e:
            logger.error(f"Redis error in flush(): {str(e)}")
            return False
    
    def close(self) -> None:
        """
        关闭Redis连接
        """
        try:
            self.client.close()
            logger.info("Redis cache connection closed")
        except:
            pass