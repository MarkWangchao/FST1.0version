#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - InfluxDB存储实现

优化的高频交易时序数据存储实现:
- 智能高可用
- 性能优化
- 资源管理
- 安全增强
- 监控诊断
"""

import os
import logging
import asyncio
import hashlib
import ssl
import pickle
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
import pandas as pd
import psutil
from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
from prometheus_client import Counter, Histogram, Gauge
import zstd
import lz4.frame
import snappy
from cryptography.fernet import Fernet
import diskqueue
from cachetools import LRUCache
from opentelemetry import trace
from ..base import TimeSeriesStorage

# 压缩算法配置
COMPRESSION_ALGORITHMS = {
    'zstd': zstd.compress,
    'lz4': lz4.frame.compress,
    'snappy': snappy.compress
}

# 监控指标定义
WRITE_OPS = Counter('influxdb_write_operations_total', '写入操作数', ['type'])
READ_OPS = Counter('influxdb_read_operations_total', '读取操作数', ['type'])
WRITE_LATENCY = Histogram('influxdb_write_latency_seconds', 
                         '写入延迟分布', ['bucket'],
                         buckets=[0.001, 0.005, 0.01, 0.05, 0.1])
QUERY_LATENCY = Histogram('influxdb_query_latency_seconds',
                         '查询延迟分布', ['operation'])
ERROR_COUNTER = Counter('influxdb_error_total', '错误类型统计', ['error_code'])
BUFFER_SIZE = Gauge('influxdb_buffer_size', '缓冲区大小', ['bucket'])
BATCH_SIZE = Gauge('influxdb_batch_size', '批量大小')

class InfluxDBWriteError(Exception):
    """InfluxDB写入错误"""
    pass

class HighAvailabilityClient:
    """智能高可用客户端"""
    
    def __init__(self, nodes: List[Dict]):
        self.nodes = nodes
        self.clients = []
        self.current_node = 0
        self.tracer = trace.get_tracer(__name__)
        
        # 初始化客户端池
        for node in nodes:
            client = InfluxDBClient(
                url=node['url'],
                token=node['token'],
                org=node['org'],
                ssl=True,
                ssl_ca_cert=node.get('ssl_ca_cert'),
                ssl_cert_reqs=ssl.CERT_REQUIRED,
                ssl_keyfile=node.get('ssl_keyfile'),
                ssl_certfile=node.get('ssl_certfile')
            )
            self.clients.append(client)
            
    def get_optimal_node(self) -> InfluxDBClient:
        """基于健康检查的智能节点选择"""
        with self.tracer.start_as_current_span("get_optimal_node") as span:
            health_scores = []
            for i, client in enumerate(self.clients):
                try:
                    ping_time = client.ping().get('latency', 1000)
                    health = client.health().status == 'pass'
                    score = ping_time * (0.5 if health else 2)
                    health_scores.append((i, score))
                    span.set_attribute(f"node_{i}_score", score)
                except Exception as e:
                    health_scores.append((i, float('inf')))
                    span.record_exception(e)
                    
            optimal_index = sorted(health_scores, key=lambda x: x[1])[0][0]
            return self.clients[optimal_index]
            
    def switch_node(self):
        """切换节点"""
        self.current_node = (self.current_node + 1) % len(self.clients)
        
class QueryCache:
    """查询缓存"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.cache = LRUCache(max_size)
        self.query_signatures = {}
        self.ttl = ttl
        
    def get_cache_key(self, query: str) -> str:
        """生成查询签名"""
        return hashlib.sha256(query.encode()).hexdigest()
        
    def get(self, query: str) -> Optional[pd.DataFrame]:
        """获取缓存结果"""
        key = self.get_cache_key(query)
        if key in self.cache:
            result, timestamp = self.cache[key]
            if (datetime.now() - timestamp).total_seconds() < self.ttl:
                return result
        return None
        
    def set(self, query: str, result: pd.DataFrame):
        """设置缓存结果"""
        key = self.get_cache_key(query)
        self.cache[key] = (result, datetime.now())
        
class PersistentWriteQueue:
    """持久化写入队列"""
    
    def __init__(self, queue_dir: str):
        self.queue = diskqueue.Queue(queue_dir)
        
    async def add_batch(self, points: List[Point]):
        """添加批量数据到队列"""
        self.queue.put(pickle.dumps(points))
        
    async def process_queue(self):
        """处理队列数据"""
        while not self.queue.empty():
            data = pickle.loads(self.queue.get())
            yield data
            self.queue.task_done()
            
class FieldEncryptor:
    """字段加密器"""
    
    def __init__(self, key: bytes):
        self.cipher = Fernet(key)
        
    def encrypt_field(self, data: Dict, fields: List[str]) -> Dict:
        """加密敏感字段"""
        encrypted = data.copy()
        for field in fields:
            if field in encrypted:
                encrypted[field] = self.cipher.encrypt(
                    str(encrypted[field]).encode()
                ).decode()
        return encrypted
        
    def decrypt_field(self, data: Dict, fields: List[str]) -> Dict:
        """解密敏感字段"""
        decrypted = data.copy()
        for field in fields:
            if field in decrypted:
                decrypted[field] = self.cipher.decrypt(
                    decrypted[field].encode()
                ).decode()
        return decrypted
        
class InfluxDBStore(TimeSeriesStorage):
    """优化的InfluxDB存储实现"""
    
    def __init__(self, config: Dict):
        """初始化存储"""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.tracer = trace.get_tracer(__name__)
        
        # 高可用客户端
        self.ha_client = HighAvailabilityClient(config['nodes'])
        self.client = self.ha_client.get_optimal_node()
        
        # 写入配置
        self.write_api = self.client.write_api(
            write_options=WriteOptions(
                batch_size=config.get('batch_size', 1000),
                flush_interval=config.get('flush_interval', 1000),
                jitter_interval=config.get('jitter_interval', 100),
                retry_interval=config.get('retry_interval', 5000),
                **config.get('quorum_settings', {})
            )
        )
        
        # 查询配置
        self.query_api = self.client.query_api()
        self.query_cache = QueryCache(
            max_size=config.get('cache_size', 1000),
            ttl=config.get('cache_ttl', 300)
        )
        
        # 持久化队列
        self.write_queue = PersistentWriteQueue(config.get('queue_dir', 'data/queue'))
        
        # 字段加密
        self.encryptor = FieldEncryptor(config['encryption_key'])
        self.sensitive_fields = config.get('sensitive_fields', [])
        
        # 资源监控
        self.memory_limit = config.get('memory_limit', 0.8)  # 80% 内存限制
        self.batch_size = config.get('batch_size', 1000)
        
        # 写入缓冲区
        self.write_buffers = {
            'market': [],
            'trading': [],
            'metrics': []
        }
        
    @property
    def replication_factor(self) -> int:
        """获取副本数量"""
        return len(self.ha_client.nodes)
        
    async def start(self):
        """启动存储服务"""
        self.logger.info("InfluxDB存储服务已启动")
        asyncio.create_task(self._batch_writer())
        asyncio.create_task(self._resource_monitor())
        
    async def stop(self):
        """停止存储服务"""
        await self._flush_buffers()
        self.write_api.close()
        self.client.close()
        
    async def write_with_retry(self, points: List[Point]):
        """带重试的写入操作"""
        retries = 0
        max_retries = 5
        base_delay = 0.1
        
        while retries < max_retries:
            try:
                with WRITE_LATENCY.labels(bucket='write').time():
                    self.write_api.write(
                        bucket=self.config['bucket'],
                        record=points
                    )
                return
            except Exception as e:
                delay = base_delay * (2 ** retries)
                await asyncio.sleep(delay)
                retries += 1
                if retries == max_retries:
                    ERROR_COUNTER.labels(error_code='write_retry_failed').inc()
                    raise InfluxDBWriteError(f"写入失败: {str(e)}")
                    
    async def write_market_data(self,
                              symbol: str,
                              data_type: str,
                              data: Union[Dict, List[Dict]]):
        """写入市场数据"""
        with self.tracer.start_as_current_span("write_market_data") as span:
            try:
                if isinstance(data, dict):
                    data = [data]
                    
                points = []
                for item in data:
                    # 加密敏感字段
                    if self.sensitive_fields:
                        item = self.encryptor.encrypt_field(item, self.sensitive_fields)
                        
                    point = Point("market_data") \
                        .tag("symbol", symbol) \
                        .tag("type", data_type)
                        
                    for field, value in item.items():
                        if field != "timestamp":
                            point = point.field(field, value)
                            
                    if "timestamp" in item:
                        point = point.time(item["timestamp"])
                        
                    points.append(point)
                    
                # 添加到写入缓冲区
                self.write_buffers['market'].extend(points)
                BUFFER_SIZE.labels(bucket='market').set(len(self.write_buffers['market']))
                
                span.set_attributes({
                    "points.count": len(points),
                    "symbol": symbol,
                    "data_type": data_type
                })
                
                WRITE_OPS.labels(type='market').inc(len(points))
                
            except Exception as e:
                span.record_exception(e)
                self.logger.error(f"写入市场数据失败: {str(e)}")
                ERROR_COUNTER.labels(error_code='write_market_data').inc()
                raise
                
    async def bulk_write(self,
                        data_type: str,
                        batch: List[Dict],
                        compression: str = 'auto') -> int:
        """批量写入数据"""
        with self.tracer.start_as_current_span("bulk_write") as span:
            try:
                # 选择最优压缩算法
                if compression == 'auto':
                    sample = str(batch[:100]).encode()
                    algo_scores = {
                        name: len(func(sample))
                        for name, func in COMPRESSION_ALGORITHMS.items()
                    }
                    best_algo = min(algo_scores, key=algo_scores.get)
                    compressed = COMPRESSION_ALGORITHMS[best_algo](str(batch).encode())
                else:
                    compressed = COMPRESSION_ALGORITHMS[compression](str(batch).encode())
                    
                # 写入数据
                points = []
                for item in batch:
                    point = Point(data_type)
                    for key, value in item.items():
                        if key == "tags":
                            for tag_key, tag_value in value.items():
                                point = point.tag(tag_key, tag_value)
                        elif key == "fields":
                            for field_key, field_value in value.items():
                                point = point.field(field_key, field_value)
                        elif key == "timestamp":
                            point = point.time(value)
                    points.append(point)
                    
                await self.write_with_retry(points)
                
                span.set_attributes({
                    "batch.size": len(batch),
                    "compression.algorithm": best_algo if compression == 'auto' else compression,
                    "compressed.size": len(compressed)
                })
                
                return len(batch)
                
            except Exception as e:
                span.record_exception(e)
                self.logger.error(f"批量写入失败: {str(e)}")
                ERROR_COUNTER.labels(error_code='bulk_write').inc()
                raise
                
    async def query_market_data(self,
                              symbol: str,
                              data_type: str,
                              start_time: datetime,
                              end_time: datetime,
                              fields: Optional[List[str]] = None) -> pd.DataFrame:
        """查询市场数据"""
        with self.tracer.start_as_current_span("query_market_data") as span:
            try:
                # 构建查询
                query = f'''
                from(bucket: "{self.config['bucket']}")
                    |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                    |> filter(fn: (r) => r["_measurement"] == "market_data")
                    |> filter(fn: (r) => r["symbol"] == "{symbol}")
                    |> filter(fn: (r) => r["type"] == "{data_type}")
                '''
                
                if fields:
                    field_list = '", "'.join(fields)
                    query += f'|> filter(fn: (r) => contains(value: r["_field"], set: ["{field_list}"]))'
                    
                # 检查缓存
                cached_result = self.query_cache.get(query)
                if cached_result is not None:
                    return cached_result
                    
                # 执行查询
                with QUERY_LATENCY.labels(operation='market_data').time():
                    result = self.query_api.query_data_frame(query)
                    
                # 解密敏感字段
                if self.sensitive_fields:
                    for field in self.sensitive_fields:
                        if field in result.columns:
                            result[field] = result[field].apply(
                                lambda x: self.encryptor.decrypt_field({'value': x}, ['value'])['value']
                            )
                            
                # 更新缓存
                self.query_cache.set(query, result)
                
                span.set_attributes({
                    "symbol": symbol,
                    "data_type": data_type,
                    "rows": len(result)
                })
                
                READ_OPS.labels(type='market').inc()
                return result
                
            except Exception as e:
                span.record_exception(e)
                self.logger.error(f"查询市场数据失败: {str(e)}")
                ERROR_COUNTER.labels(error_code='query_market_data').inc()
                raise
                
    async def _batch_writer(self):
        """批量写入处理"""
        while True:
            try:
                await self._flush_buffers()
                # 处理持久化队列
                async for batch in self.write_queue.process_queue():
                    await self.write_with_retry(batch)
                await asyncio.sleep(self.config.get('flush_interval', 1000) / 1000)
            except Exception as e:
                self.logger.error(f"批量写入处理失败: {str(e)}")
                ERROR_COUNTER.labels(error_code='batch_writer').inc()
                await asyncio.sleep(1)
                
    async def _resource_monitor(self):
        """资源监控"""
        while True:
            try:
                # 监控内存使用
                mem_usage = psutil.virtual_memory().percent
                cpu_usage = psutil.cpu_percent()
                
                # 动态调整批量大小
                if mem_usage > 80 or cpu_usage > 90:
                    self.batch_size = max(100, self.batch_size // 2)
                else:
                    self.batch_size = min(5000, self.batch_size * 2)
                    
                BATCH_SIZE.set(self.batch_size)
                
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"资源监控失败: {str(e)}")
                await asyncio.sleep(5)
                
    async def _flush_buffers(self):
        """刷新写入缓冲区"""
        for bucket, buffer in self.write_buffers.items():
            if buffer:
                try:
                    # 如果内存使用过高，写入持久化队列
                    if psutil.virtual_memory().percent > self.memory_limit * 100:
                        await self.write_queue.add_batch(buffer)
                    else:
                        await self.write_with_retry(buffer)
                        
                    buffer.clear()
                    BUFFER_SIZE.labels(bucket=bucket).set(0)
                    
                except Exception as e:
                    self.logger.error(f"刷新缓冲区失败: {str(e)}")
                    ERROR_COUNTER.labels(error_code='flush_buffers').inc()
                    
    async def failover(self):
        """故障转移"""
        self.client = self.ha_client.get_optimal_node()
        self.write_api = self.client.write_api(
            write_options=WriteOptions(
                batch_size=self.batch_size,
                flush_interval=self.config.get('flush_interval', 1000),
                jitter_interval=self.config.get('jitter_interval', 100),
                retry_interval=self.config.get('retry_interval', 5000)
            )
        )
        self.query_api = self.client.query_api()
        
    def get_storage_stats(self) -> Dict:
        """获取存储统计信息"""
        try:
            return {
                'write_ops': {
                    'market': WRITE_OPS.labels(type='market')._value.get(),
                    'trading': WRITE_OPS.labels(type='trading')._value.get(),
                    'metrics': WRITE_OPS.labels(type='metrics')._value.get()
                },
                'read_ops': {
                    'market': READ_OPS.labels(type='market')._value.get(),
                    'trading': READ_OPS.labels(type='trading')._value.get(),
                    'metrics': READ_OPS.labels(type='metrics')._value.get()
                },
                'buffer_size': {
                    bucket: len(buffer)
                    for bucket, buffer in self.write_buffers.items()
                },
                'batch_size': self.batch_size,
                'memory_usage': psutil.virtual_memory().percent,
                'cpu_usage': psutil.cpu_percent()
            }
        except Exception as e:
            self.logger.error(f"获取存储统计信息失败: {str(e)}")
            ERROR_COUNTER.labels(error_code='get_stats').inc()
            return {}