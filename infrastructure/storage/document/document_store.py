#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强型文档数据存储器

提供高性能文档数据存储功能：
- 分片集群支持
- 高可用性配置
- 字段级加密
- 自动索引优化
- 查询计划缓存
- 聚合管道优化
"""

import logging
import asyncio
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import motor.motor_asyncio
from bson.objectid import ObjectId
from prometheus_client import Counter, Histogram, Gauge
import json
from pathlib import Path
import zlib
import pickle
from cryptography.fernet import Fernet
import psutil

# 存储指标
DOC_OPS = Counter('document_operations_total', '文档操作数', ['operation', 'collection'])
QUERY_TIME = Histogram('document_query_time_seconds', '查询时间', 
                      ['collection', 'operation'],
                      buckets=[0.01, 0.05, 0.1, 0.5, 1.0])
COLLECTION_SIZE = Gauge('document_collection_size_bytes', '集合大小', ['collection'])

# 分片配置
SHARDING_CONFIG = {
    'strategy_config': {
        'shard_key': ('strategy_id', 'version'),
        'chunk_size': 64  # MB
    },
    'backtest': {
        'shard_key': ('start_time', 'strategy_id'),
        'chunk_size': 128
    },
    'report': {
        'shard_key': ('report_type', 'created_at'),
        'chunk_size': 32
    }
}

class QueryPlanner:
    """查询计划缓存"""
    
    def __init__(self, max_plans=1000):
        self.plan_cache = {}
        self.max_plans = max_plans
        
    def get_plan(self, query: Dict) -> Optional[Dict]:
        cache_key = self._hash_query(query)
        return self.plan_cache.get(cache_key)
        
    def add_plan(self, query: Dict, plan: Dict):
        cache_key = self._hash_query(query)
        if len(self.plan_cache) >= self.max_plans:
            self.plan_cache.pop(next(iter(self.plan_cache)))
        self.plan_cache[cache_key] = plan
        
    def _hash_query(self, query: Dict) -> str:
        return hash(json.dumps(query, sort_keys=True))

class IndexOptimizer:
    """索引优化器"""
    
    def __init__(self, db):
        self.db = db
        self.logger = logging.getLogger(__name__)
        
    async def analyze_and_optimize(self, collection: str):
        """分析并优化索引"""
        try:
            # 获取索引统计
            stats = await self.db.command({
                'aggregate': collection,
                'pipeline': [{'$indexStats': {}}],
                'cursor': {}
            })
            
            # 分析查询模式
            query_patterns = await self._analyze_query_patterns(collection)
            
            # 生成索引建议
            suggestions = self._generate_index_suggestions(stats, query_patterns)
            
            # 应用索引变更
            await self._apply_index_changes(collection, suggestions)
            
        except Exception as e:
            self.logger.error(f"索引优化失败: {str(e)}")
            
    async def _analyze_query_patterns(self, collection: str) -> List[Dict]:
        """分析查询模式"""
        return await self.db[collection].aggregate([
            {'$indexStats': {}},
            {'$sort': {'accesses.ops': -1}},
            {'$limit': 10}
        ]).to_list(None)
        
    def _generate_index_suggestions(self, stats: Dict, patterns: List[Dict]) -> List[Dict]:
        """生成索引建议"""
        suggestions = []
        # 实现索引建议生成逻辑
        return suggestions

class DocumentStore:
    """增强型文档数据存储器"""
    
    def __init__(self, config: Dict):
        """初始化存储器"""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化MongoDB客户端
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            config['mongodb']['uri'],
            readPreference=config['mongodb'].get('read_preference', 'secondaryPreferred'),
            w=config['mongodb'].get('write_concern', {}).get('w', 'majority'),
            j=config['mongodb'].get('write_concern', {}).get('j', True)
        )
        self.db = self.client[config['mongodb']['database']]
        
        # 初始化集合
        self.collections = {
            'strategy_config': self.db[config['mongodb']['collections']['strategy']],
            'backtest': self.db[config['mongodb']['collections']['backtest']],
            'report': self.db[config['mongodb']['collections']['report']]
        }
        
        # 初始化加密
        if config.get('encryption', {}).get('enabled', False):
            self.cipher = Fernet(config['encryption']['key'].encode())
        else:
            self.cipher = None
            
        # 初始化查询计划缓存
        self.query_planner = QueryPlanner()
        
        # 初始化索引优化器
        self.index_optimizer = IndexOptimizer(self.db)
        
    async def start(self):
        """启动存储器"""
        self.logger.info("增强型文档数据存储器已启动")
        await self._initialize_sharding()
        await self._ensure_indexes()
        asyncio.create_task(self._run_maintenance())
        
    async def _initialize_sharding(self):
        """初始化分片"""
        try:
            for collection, config in SHARDING_CONFIG.items():
                await self.db.command({
                    'shardCollection': f"{self.db.name}.{collection}",
                    'key': {k: 1 for k in config['shard_key']}
                })
                await self.db.command({
                    'collMod': collection,
                    'chunckSize': config['chunk_size']
                })
        except Exception as e:
            self.logger.error(f"初始化分片失败: {str(e)}")
            
    async def _run_maintenance(self):
        """运行维护任务"""
        while True:
            try:
                # 优化索引
                for collection in self.collections:
                    await self.index_optimizer.analyze_and_optimize(collection)
                    
                # 更新集合统计
                await self._update_collection_stats()
                
                await asyncio.sleep(3600)  # 每小时运行一次
                
            except Exception as e:
                self.logger.error(f"维护任务失败: {str(e)}")
                await asyncio.sleep(60)

    async def save_strategy_config(self, config: Dict) -> str:
        """保存策略配置"""
        try:
            with QUERY_TIME.labels(collection='strategy_config', operation='save').time():
                # 加密敏感字段
                if self.cipher:
                    config = self._encrypt_sensitive_fields(config)
                    
                # 添加元数据
                config['updated_at'] = datetime.now()
                if '_id' not in config:
                    config['created_at'] = config['updated_at']
                    
                # 保存配置
                result = await self.collections['strategy_config'].replace_one(
                    {'strategy_id': config['strategy_id'], 'version': config['version']},
                    config,
                    upsert=True
                )
                
                DOC_OPS.labels(operation='save', collection='strategy_config').inc()
                return str(result.upserted_id) if result.upserted_id else None
                
        except Exception as e:
            self.logger.error(f"保存策略配置失败: {str(e)}")
            raise

    async def get_backtest_stats(self, strategy_id: str) -> Dict:
        """获取回测统计信息"""
        try:
            with QUERY_TIME.labels(collection='backtest', operation='aggregate').time():
                pipeline = [
                    {'$match': {'strategy_id': strategy_id}},
                    {'$group': {
                        '_id': None,
                        'avg_profit': {'$avg': '$total_profit'},
                        'max_drawdown': {'$min': '$max_drawdown'},
                        'win_rate': {'$avg': {'$cond': [{'$gt': ['$total_profit', 0]}, 1, 0]}},
                        'total_trades': {'$sum': 1}
                    }},
                    {'$project': {
                        '_id': 0,
                        'avg_profit': 1,
                        'max_drawdown': 1,
                        'win_rate': 1,
                        'total_trades': 1
                    }}
                ]
                
                result = await self.collections['backtest'].aggregate(pipeline).to_list(1)
                return result[0] if result else {}
                
        except Exception as e:
            self.logger.error(f"获取回测统计失败: {str(e)}")
            return {}

    def _encrypt_sensitive_fields(self, data: Dict) -> Dict:
        """加密敏感字段"""
        if not self.cipher:
            return data
            
        sensitive_fields = ['params', 'api_key', 'secret_key']
        encrypted_data = data.copy()
        
        for field in sensitive_fields:
            if field in encrypted_data:
                encrypted_data[field] = self.cipher.encrypt(
                    json.dumps(encrypted_data[field]).encode()
                ).decode()
                
        return encrypted_data

    def _decrypt_sensitive_fields(self, data: Dict) -> Dict:
        """解密敏感字段"""
        if not self.cipher:
            return data
            
        sensitive_fields = ['params', 'api_key', 'secret_key']
        decrypted_data = data.copy()
        
        for field in sensitive_fields:
            if field in decrypted_data:
                try:
                    decrypted_data[field] = json.loads(
                        self.cipher.decrypt(decrypted_data[field].encode()).decode()
                    )
                except:
                    pass
                    
        return decrypted_data

    async def _update_collection_stats(self):
        """更新集合统计信息"""
        try:
            for collection in self.collections:
                stats = await self.db.command('collStats', collection)
                COLLECTION_SIZE.labels(collection=collection).set(stats['size'])
        except Exception as e:
            self.logger.error(f"更新集合统计失败: {str(e)}")