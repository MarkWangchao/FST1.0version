"""
缓存项定义，包含缓存策略和过期机制
"""

from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from typing import Any, Optional, Dict


class CachePolicy(Enum):
    """缓存策略枚举"""
    NEVER_EXPIRE = "never_expire"  # 永不过期
    EXPIRE_AFTER_WRITE = "expire_after_write"  # 写入后固定时间过期
    EXPIRE_AFTER_ACCESS = "expire_after_access"  # 访问后固定时间过期
    EXPIRE_AT_TIME = "expire_at_time"  # 在特定时间点过期


@dataclass
class CacheItem:
    """
    缓存项，包含值和元数据
    """
    key: str
    value: Any
    created_at: datetime
    last_accessed: datetime
    policy: CachePolicy = CachePolicy.EXPIRE_AFTER_WRITE
    ttl: Optional[float] = 300  # 默认5分钟，单位：秒
    expire_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.metadata is None:
            self.metadata = {}
    
    def is_expired(self) -> bool:
        """
        检查缓存项是否已过期
        
        Returns:
            bool: 是否已过期
        """
        now = datetime.now()
        
        if self.policy == CachePolicy.NEVER_EXPIRE:
            return False
            
        elif self.policy == CachePolicy.EXPIRE_AT_TIME:
            return self.expire_at and now >= self.expire_at
            
        elif self.policy == CachePolicy.EXPIRE_AFTER_WRITE:
            if self.ttl is None:
                return False
            age = (now - self.created_at).total_seconds()
            return age >= self.ttl
            
        elif self.policy == CachePolicy.EXPIRE_AFTER_ACCESS:
            if self.ttl is None:
                return False
            age = (now - self.last_accessed).total_seconds()
            return age >= self.ttl
            
        # 未知策略，默认过期
        return True
    
    def access(self) -> None:
        """
        更新最后访问时间
        """
        self.last_accessed = datetime.now()
    
    def update(self, value: Any) -> None:
        """
        更新缓存项的值
        
        Args:
            value: 新值
        """
        self.value = value
        self.created_at = datetime.now()
        self.last_accessed = self.created_at
    
    def set_ttl(self, seconds: float) -> None:
        """
        设置生存时间
        
        Args:
            seconds: 秒数
        """
        self.ttl = seconds
        
        # 如果是定时过期策略，更新过期时间点
        if self.policy == CachePolicy.EXPIRE_AT_TIME:
            self.expire_at = datetime.now() + timedelta(seconds=seconds)
    
    def set_policy(self, policy: CachePolicy) -> None:
        """
        设置缓存策略
        
        Args:
            policy: 缓存策略
        """
        self.policy = policy
        
        # 如果切换到定时过期策略，计算过期时间点
        if policy == CachePolicy.EXPIRE_AT_TIME and self.ttl:
            self.expire_at = datetime.now() + timedelta(seconds=self.ttl)
    
    def set_expire_at(self, expire_time: datetime) -> None:
        """
        设置过期时间点
        
        Args:
            expire_time: 过期时间点
        """
        self.expire_at = expire_time
        self.policy = CachePolicy.EXPIRE_AT_TIME
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式，用于序列化
        
        Returns:
            Dict: 字典表示
        """
        return {
            'key': self.key,
            'value': self.value,
            'created_at': self.created_at.isoformat(),
            'last_accessed': self.last_accessed.isoformat(),
            'policy': self.policy.value,
            'ttl': self.ttl,
            'expire_at': self.expire_at.isoformat() if self.expire_at else None,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheItem':
        """
        从字典创建缓存项，用于反序列化
        
        Args:
            data: 字典数据
            
        Returns:
            CacheItem: 缓存项实例
        """
        policy = CachePolicy(data['policy'])
        created_at = datetime.fromisoformat(data['created_at'])
        last_accessed = datetime.fromisoformat(data['last_accessed'])
        expire_at = datetime.fromisoformat(data['expire_at']) if data.get('expire_at') else None
        
        return cls(
            key=data['key'],
            value=data['value'],
            created_at=created_at,
            last_accessed=last_accessed,
            policy=policy,
            ttl=data.get('ttl'),
            expire_at=expire_at,
            metadata=data.get('metadata', {})
        )