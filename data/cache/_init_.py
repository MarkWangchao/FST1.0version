"""
缓存模块 - 为应用提供高效的数据缓存功能

该模块提供了多种缓存实现，包括内存缓存、磁盘缓存和Redis缓存，
以及统一的缓存管理接口。

主要功能:
- 多种缓存策略支持(过期时间、访问后过期、写入后过期等)
- 支持缓存事件回调
- 支持缓存统计信息收集
- 支持序列化和反序列化复杂对象
- 支持分布式缓存(通过Redis)
"""

from .cache_item import CacheItem, CachePolicy
from .memory_cache import MemoryCache
from .disk_cache import DiskCache
from .cache_manager import CacheManager

# 尝试导入Redis缓存
try:
    from .redis_cache import RedisCache, RedisConfig
    __redis_available__ = True
except ImportError:
    __redis_available__ = False

# 导出公共接口
__all__ = [
    "CachePolicy",
    "CacheItem",
    "MemoryCache",
    "DiskCache",
    "CacheManager",
]

# 如果Redis可用，添加到导出列表
if __redis_available__:
    __all__ += ["RedisCache", "RedisConfig"]