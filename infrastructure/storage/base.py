#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强型存储基类和接口定义

提供增强的存储接口功能:
- 多存储后端支持
- 性能优化接口
- 高可用性支持
- 安全增强
- 监控与维护
- 查询增强
- 资源管理
- 插件扩展
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Type, Literal
from datetime import datetime
import pandas as pd
from prometheus_client import Counter, Histogram, Gauge

class StoragePlugin(ABC):
    """存储插件基类"""
    
    @abstractmethod
    def pre_write_hook(self, data: Dict) -> Dict:
        """写入前处理钩子"""
        pass
        
    @abstractmethod
    def post_write_hook(self, data: Dict) -> None:
        """写入后处理钩子"""
        pass
        
    @abstractmethod
    def pre_read_hook(self, query: Dict) -> Dict:
        """读取前处理钩子"""
        pass
        
    @abstractmethod
    def post_read_hook(self, data: Any) -> Any:
        """读取后处理钩子"""
        pass

class BaseStorage(ABC):
    """增强型存储基类"""
    
    _backends: Dict[str, Type['BaseStorage']] = {}
    _plugins: List[StoragePlugin] = []
    
    @classmethod
    def register_backend(cls, name: str, implementation: Type['BaseStorage']):
        """注册存储后端"""
        cls._backends[name] = implementation
        
    @abstractmethod
    async def start(self):
        """启动存储服务"""
        pass
        
    @abstractmethod
    async def stop(self):
        """停止存储服务"""
        pass
        
    @abstractmethod
    async def health_check(self) -> Dict:
        """存储健康状态检查"""
        pass
        
    @property
    @abstractmethod
    def replication_factor(self) -> int:
        """数据副本数量"""
        pass
        
    @abstractmethod
    async def failover(self):
        """故障转移"""
        pass
        
    @abstractmethod
    def get_retry_policy(self) -> Dict:
        """获取重试策略"""
        return {
            'max_retries': 3,
            'backoff_factor': 0.5,
            'retryable_errors': [500, 503]
        }
        
    @abstractmethod
    def get_metrics(self) -> Dict:
        """获取Prometheus格式指标"""
        pass
        
    @abstractmethod
    async def run_maintenance(self):
        """运行存储维护任务"""
        pass
        
    @abstractmethod
    def connection_pool_status(self) -> Dict:
        """获取连接池状态"""
        pass
        
    def add_plugin(self, plugin: StoragePlugin):
        """添加存储插件"""
        self._plugins.append(plugin)
        
    async def _execute_pre_write_hooks(self, data: Dict) -> Dict:
        """执行写入前钩子"""
        for plugin in self._plugins:
            data = await plugin.pre_write_hook(data)
        return data
        
    async def _execute_post_write_hooks(self, data: Dict):
        """执行写入后钩子"""
        for plugin in self._plugins:
            await plugin.post_write_hook(data)
            
    async def _execute_pre_read_hooks(self, query: Dict) -> Dict:
        """执行读取前钩子"""
        for plugin in self._plugins:
            query = await plugin.pre_read_hook(query)
        return query
        
    async def _execute_post_read_hooks(self, data: Any) -> Any:
        """执行读取后钩子"""
        for plugin in self._plugins:
            data = await plugin.post_read_hook(data)
        return data

class TimeSeriesStorage(BaseStorage):
    """增强型时序数据存储接口"""
    
    _supported_backends = ['influxdb', 'timescaledb', 'clickhouse']
    
    @abstractmethod
    async def write_market_data(self,
                              symbol: str,
                              data_type: Literal['kline', 'tick'],
                              data: Union[Dict, List[Dict]]):
        """写入市场数据"""
        pass
        
    @abstractmethod
    async def write_trading_data(self,
                               data_type: Literal['order', 'trade', 'position'],
                               data: Union[Dict, List[Dict]]):
        """写入交易数据"""
        pass
        
    @abstractmethod
    async def write_metrics(self,
                          metric_type: Literal['system', 'trading', 'strategy'],
                          metrics: Union[Dict, List[Dict]]):
        """写入监控指标"""
        pass
        
    @abstractmethod
    async def bulk_write(self,
                        data_type: str,
                        batch: List[Dict],
                        compression: str = 'zstd') -> int:
        """批量写入数据"""
        pass
        
    @abstractmethod
    async def query_market_data(self,
                              symbol: str,
                              data_type: str,
                              start_time: datetime,
                              end_time: datetime,
                              fields: Optional[List[str]] = None) -> pd.DataFrame:
        """查询市场数据"""
        pass
        
    @abstractmethod
    async def flux_query(self, query: str) -> pd.DataFrame:
        """执行Flux查询"""
        pass
        
    @abstractmethod
    async def downsampling(self,
                          retention_policy: str,
                          aggregation: str) -> bool:
        """执行降采样"""
        pass

class DocumentStorage(BaseStorage):
    """增强型文档数据存储接口"""
    
    @abstractmethod
    async def save_strategy_config(self, config: Dict) -> str:
        """保存策略配置"""
        pass
        
    @abstractmethod
    async def get_strategy_config(self,
                                strategy_id: str,
                                version: Optional[int] = None) -> Optional[Dict]:
        """获取策略配置"""
        pass
        
    @abstractmethod
    async def save_backtest_result(self, result: Dict) -> str:
        """保存回测结果"""
        pass
        
    @abstractmethod
    async def get_backtest_results(self,
                                 strategy_id: Optional[str] = None,
                                 start_time: Optional[datetime] = None,
                                 end_time: Optional[datetime] = None,
                                 limit: int = 100) -> List[Dict]:
        """获取回测结果"""
        pass
        
    @abstractmethod
    async def create_index(self,
                         index_spec: Dict,
                         background: bool = True) -> str:
        """创建索引"""
        pass
        
    @abstractmethod
    async def encrypt_field(self,
                          field_name: str,
                          encryption_type: str = 'aes-256-gcm') -> bool:
        """字段加密"""
        pass
        
    @abstractmethod
    async def aggregate(self,
                       pipeline: List[Dict],
                       timeout: int = 30) -> List[Dict]:
        """聚合查询"""
        pass

class CacheStorage(BaseStorage):
    """增强型缓存存储接口"""
    
    @abstractmethod
    async def get(self, cache_type: str, key: str) -> Optional[Any]:
        """获取缓存项"""
        pass
        
    @abstractmethod
    async def set(self,
                  cache_type: str,
                  key: str,
                  value: Any,
                  ttl: Optional[int] = None) -> bool:
        """设置缓存项"""
        pass
        
    @abstractmethod
    async def delete(self, cache_type: str, key: str) -> bool:
        """删除缓存项"""
        pass
        
    @abstractmethod
    async def clear(self, cache_type: str) -> bool:
        """清空缓存"""
        pass
        
    @abstractmethod
    async def sanitize_key(self, key: str) -> str:
        """键值安全处理"""
        pass
        
    @abstractmethod
    async def memory_guard(self, threshold: float = 0.8):
        """内存保护"""
        pass

# 存储指标
STORAGE_OPS = Counter('storage_operations_total', '存储操作数',
                     ['operation', 'storage_type'])
STORAGE_ERRORS = Counter('storage_errors_total', '存储错误数',
                        ['error_type', 'storage_type'])
STORAGE_LATENCY = Histogram('storage_operation_latency_seconds', '存储操作延迟',
                           ['operation', 'storage_type'])
STORAGE_CONNECTIONS = Gauge('storage_connections', '存储连接数',
                          ['storage_type'])
STORAGE_MEMORY = Gauge('storage_memory_bytes', '存储内存使用',
                      ['storage_type'])