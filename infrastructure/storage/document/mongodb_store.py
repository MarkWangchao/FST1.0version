#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - MongoDB存储实现

提供基于MongoDB的高性能文档存储实现:
- 动态索引管理
- 智能连接池
- 优化分片策略
- 高性能批量写入
- 查询性能优化
- 数据生命周期管理
- 安全加密
"""

import logging
import asyncio
from typing import Dict, List, Optional, Union, Any
from datetime import datetime, timedelta
from collections import defaultdict
import motor.motor_asyncio
from pymongo import IndexModel, ASCENDING, DESCENDING, WriteConcern
from pymongo.errors import AutoReconnect, DuplicateKeyError, OperationFailure
from prometheus_client import Counter, Histogram, Gauge
from tenacity import retry, stop_after_attempt, wait_exponential
from cryptography.fernet import Fernet
import hashlib
from ..base import DocumentStorage

# 监控指标
DOC_OPS = Counter('mongodb_operations_total', '文档操作数', ['operation', 'collection'])
QUERY_TIME = Histogram('mongodb_query_time_seconds', '查询时间', ['collection'])
COLLECTION_SIZE = Gauge('mongodb_collection_size', '集合大小', ['collection'])

class AdaptiveIndexer:
    """动态索引管理器"""
    
    def __init__(self):
        self.query_patterns = defaultdict(lambda: defaultdict(int))
        self.index_weights = {
            'strategy': {
                ('strategy_id', 'version'): 0.8,
                ('status', 'created_at'): 0.6,
                ('type', 'updated_at'): 0.4
            },
            'backtest': {
                ('strategy_id', 'start_time'): 0.9,
                ('performance.sharpe', 'status'): 0.7,
                ('created_at', 'status'): 0.5
            }
        }
        self.logger = logging.getLogger(__name__)
        
    async def optimize_indexes(self, collection, db):
        """根据查询模式动态调整索引"""
        try:
            current_indexes = await db[collection].list_indexes().to_list(None)
            current_index_keys = {
                tuple(idx['key'].items()) for idx in current_indexes
                if idx.get('name') != '_id_'
            }
            
            # 生成最优索引组合
            optimal_indexes = self._generate_optimal_indexes(collection)
            
            # 创建缺失的索引
            for idx in optimal_indexes - current_index_keys:
                await db[collection].create_index(
                    [(field, order) for field, order in idx],
                    background=True
                )
                
            # 删除不再需要的索引
            for idx in current_index_keys - optimal_indexes:
                if idx in self.index_weights[collection]:
                    continue  # 保留基本索引
                await db[collection].drop_index(idx)
                
        except Exception as e:
            self.logger.error(f"索引优化失败: {str(e)}")
            
    def _generate_optimal_indexes(self, collection: str) -> set:
        """生成最优索引组合"""
        weights = self.index_weights[collection]
        query_freq = self.query_patterns[collection]
        
        optimal_set = set()
        for fields, base_weight in weights.items():
            # 结合查询频率计算权重
            weight = base_weight * sum(query_freq[f] for f in fields)
            if weight > 0.3:  # 权重阈值
                optimal_set.add(fields)
                
        return optimal_set
        
    def record_query(self, collection: str, query: Dict):
        """记录查询模式"""
        for field in query.keys():
            self.query_patterns[collection][field] += 1

class ConnectionGovernor:
    """智能连接池管理器"""
    
    def __init__(self):
        self.pool_metrics = {
            'in_use': Gauge('mongodb_conn_in_use', '使用中连接数'),
            'available': Gauge('mongodb_conn_available', '可用连接数'),
            'latency': Histogram('mongodb_conn_latency', '连接延迟')
        }
        self.adjustment_strategy = {
            'scale_up_threshold': 0.8,
            'scale_down_threshold': 0.3,
            'max_conn': 500,
            'min_conn': 20,
            'step_size': 10
        }
        self.logger = logging.getLogger(__name__)
        
    async def adjust_pool(self, client):
        """动态调整连接池大小"""
        try:
            stats = await client.admin.command('serverStatus')
            current_conns = stats['connections']
            
            usage_ratio = current_conns['current'] / current_conns['available']
            
            if usage_ratio > self.adjustment_strategy['scale_up_threshold']:
                new_size = min(
                    client.options.pool_options.max_pool_size + self.adjustment_strategy['step_size'],
                    self.adjustment_strategy['max_conn']
                )
                await self._reset_pool_size(client, new_size)
                
            elif usage_ratio < self.adjustment_strategy['scale_down_threshold']:
                new_size = max(
                    client.options.pool_options.max_pool_size - self.adjustment_strategy['step_size'],
                    self.adjustment_strategy['min_conn']
                )
                await self._reset_pool_size(client, new_size)
                
            # 更新指标
            self.pool_metrics['in_use'].set(current_conns['current'])
            self.pool_metrics['available'].set(current_conns['available'])
            
        except Exception as e:
            self.logger.error(f"连接池调整失败: {str(e)}")
            
    async def _reset_pool_size(self, client, new_size: int):
        """重置连接池大小"""
        try:
            client.options.pool_options.max_pool_size = new_size
            self.logger.info(f"连接池大小已调整为: {new_size}")
        except Exception as e:
            self.logger.error(f"重置连接池大小失败: {str(e)}")

class BulkWriter:
    """批量写入管理器"""
    
    def __init__(self):
        self.batch_size = {
            'strategy': 5000,
            'backtest': 10000,
            'report': 2000
        }
        self.write_concern = {
            'critical': WriteConcern(w='majority', j=True),
            'normal': WriteConcern(w=1, j=False)
        }
        self.logger = logging.getLogger(__name__)
        
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, max=10))
    async def bulk_save(self, collection, docs: List[Dict], 
                       write_concern: str = 'normal') -> bool:
        """智能批量写入"""
        try:
            if not docs:
                return True
                
            # 分批处理
            batch_size = self.batch_size.get(collection.name, 1000)
            for i in range(0, len(docs), batch_size):
                batch = docs[i:i + batch_size]
                
                # 构建批量操作
                bulk_ops = []
                for doc in batch:
                    if '_id' in doc:
                        bulk_ops.append(
                            ReplaceOne({'_id': doc['_id']}, doc, upsert=True)
                        )
                    else:
                        bulk_ops.append(InsertOne(doc))
                        
                # 执行批量写入
                result = await collection.bulk_write(
                    bulk_ops,
                    ordered=False,  # 无序写入提高性能
                    bypass_document_validation=True,
                    write_concern=self.write_concern[write_concern]
                )
                
                self.logger.info(
                    f"批量写入完成: {result.inserted_count} 插入, "
                    f"{result.modified_count} 修改"
                )
                
            return True
            
        except Exception as e:
            self.logger.error(f"批量写入失败: {str(e)}")
            raise

class QueryPlanner:
    """查询优化器"""
    
    def __init__(self, cache_size: int = 1000):
        self.cache_size = cache_size
        self.plan_cache = {}  # 简单LRU缓存
        self.logger = logging.getLogger(__name__)
        
    async def optimize_query(self, collection, query: Dict) -> Dict:
        """优化查询"""
        try:
            # 生成查询计划
            plan = await collection.find(query).explain()
            
            # 验证查询计划
            if self._is_collection_scan(plan):
                self.logger.warning(f"全表扫描检测: {query}")
                self._suggest_index(collection, query)
                
            # 缓存查询计划
            query_hash = self._hash_query(query)
            self.plan_cache[query_hash] = plan
            
            if len(self.plan_cache) > self.cache_size:
                self.plan_cache.pop(next(iter(self.plan_cache)))
                
            return plan
            
        except Exception as e:
            self.logger.error(f"查询优化失败: {str(e)}")
            return None
            
    def _is_collection_scan(self, plan: Dict) -> bool:
        """检查是否为全表扫描"""
        return plan['queryPlanner']['winningPlan']['stage'] == 'COLLSCAN'
        
    def _suggest_index(self, collection, query: Dict):
        """建议创建索引"""
        fields = list(query.keys())
        if fields:
            self.logger.info(f"建议为 {collection.name} 创建索引: {fields}")
            
    def _hash_query(self, query: Dict) -> str:
        """生成查询哈希值"""
        return hashlib.md5(str(sorted(query.items())).encode()).hexdigest()

class FieldLevelEncryption:
    """字段级加密管理器"""
    
    def __init__(self, encryption_key: bytes):
        self.fernet = Fernet(encryption_key)
        self.schema_map = {
            'strategy': ['secret_config', 'api_key'],
            'backtest': ['credentials'],
            'report': ['sensitive_data']
        }
        self.logger = logging.getLogger(__name__)
        
    def encrypt_document(self, collection: str, doc: Dict) -> Dict:
        """加密文档敏感字段"""
        try:
            if collection not in self.schema_map:
                return doc
                
            encrypted_doc = doc.copy()
            for field in self.schema_map[collection]:
                if field in encrypted_doc:
                    encrypted_doc[field] = self.fernet.encrypt(
                        str(encrypted_doc[field]).encode()
                    ).decode()
                    
            return encrypted_doc
            
        except Exception as e:
            self.logger.error(f"文档加密失败: {str(e)}")
            return doc
            
    def decrypt_document(self, collection: str, doc: Dict) -> Dict:
        """解密文档敏感字段"""
        try:
            if collection not in self.schema_map:
                return doc
                
            decrypted_doc = doc.copy()
            for field in self.schema_map[collection]:
                if field in decrypted_doc:
                    decrypted_doc[field] = self.fernet.decrypt(
                        decrypted_doc[field].encode()
                    ).decode()
                    
            return decrypted_doc
            
        except Exception as e:
            self.logger.error(f"文档解密失败: {str(e)}")
            return doc

class MongoDBStore(DocumentStorage):
    """MongoDB存储实现"""
    
    def __init__(self, config: Dict):
        """初始化MongoDB存储"""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 组件初始化
        self.indexer = AdaptiveIndexer()
        self.conn_governor = ConnectionGovernor()
        self.bulk_writer = BulkWriter()
        self.query_planner = QueryPlanner()
        self.encryption = FieldLevelEncryption(config['encryption_key'])
        
        # 客户端配置
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            config['uri'],
            maxPoolSize=config.get('max_pool_size', 100),
            minPoolSize=config.get('min_pool_size', 10),
            maxIdleTimeMS=config.get('max_idle_time', 300000),
            connectTimeoutMS=config.get('connect_timeout', 20000),
            serverSelectionTimeoutMS=config.get('server_selection_timeout', 30000),
            retryWrites=True,
            w='majority'
        )
        
        # 数据库初始化
        self.db = self.client[config['database']]
        
        # 集合配置
        self.collections = {
            'strategy': self.db[config.get('strategy_collection', 'strategies')],
            'backtest': self.db[config.get('backtest_collection', 'backtest_results')],
            'report': self.db[config.get('report_collection', 'reports')],
            'audit': self.db[config.get('audit_collection', 'audit_logs')]
        }
        
        # 分片配置
        self.sharding = {
            'strategy': {
                'shard_key': {'strategy_id': 'hashed'},
                'chunk_size': 128,
                'balancing': 'dynamic'
            },
            'backtest': {
                'shard_key': {'start_time': 1},
                'chunk_size': 256,
                'balancing': 'auto'
            }
        }
        
    async def start(self):
        """启动存储服务"""
        self.logger.info("MongoDB存储服务启动中...")
        
        try:
            # 初始化索引
            await self._setup_indexes()
            
            # 设置分片
            if self.config.get('enable_sharding', False):
                await self._setup_sharding()
                
            # 启动维护任务
            asyncio.create_task(self._maintenance_task())
            
            self.logger.info("MongoDB存储服务已启动")
            
        except Exception as e:
            self.logger.error(f"存储服务启动失败: {str(e)}")
            raise

    async def _setup_indexes(self):
        """初始化索引"""
        try:
            # 基础索引
            for collection in self.collections.values():
                await self.indexer.optimize_indexes(collection.name, self.db)
                
            # TTL索引
            await self._setup_ttl_indexes()
            
            self.logger.info("索引初始化完成")
            
        except Exception as e:
            self.logger.error(f"索引初始化失败: {str(e)}")
            raise
            
    async def _setup_ttl_indexes(self):
        """设置TTL索引"""
        ttl_config = {
            'strategy': {'field': 'expire_at', 'seconds': 0},
            'backtest': {'field': 'created_at', 'seconds': 180*86400},
            'audit': {'field': 'timestamp', 'seconds': 30*86400}
        }
        
        for col, config in ttl_config.items():
            await self.collections[col].create_index(
                [(config['field'], ASCENDING)],
                expireAfterSeconds=config['seconds']
            )
            
    async def _setup_sharding(self):
        """设置分片"""
        try:
            for collection, config in self.sharding.items():
                await self.db.command({
                    'shardCollection': f"{self.config['database']}.{collection}",
                    'key': config['shard_key'],
                    'numInitialChunks': config.get('num_chunks', 10),
                    'presplitHashedZones': True
                })
                
            self.logger.info("分片设置完成")
            
        except Exception as e:
            self.logger.error(f"分片设置失败: {str(e)}")
