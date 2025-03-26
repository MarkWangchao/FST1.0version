#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 多级存储管理器

提供分层数据存储功能：
- 实时数据层（高精度，短期存储）
- 小时聚合层（中等精度，中期存储）
- 日度聚合层（低精度，长期存储）
"""

import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from prometheus_client import Counter, Histogram

# 存储指标
STORAGE_OPS = Counter('storage_operations_total', '存储操作数', ['operation', 'tier'])
STORAGE_LATENCY = Histogram('storage_operation_latency_seconds', '存储操作延迟', ['operation'])

class TieredStorage:
    """多级存储管理器"""
    
    def __init__(self, config: Dict):
        """
        初始化存储管理器
        
        Args:
            config: 存储配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 存储层配置
        self.tiers = {
            'realtime': {
                'retention': timedelta(hours=72),  # 3天
                'resolution': timedelta(seconds=1)  # 1秒
            },
            'hourly': {
                'retention': timedelta(days=30),   # 30天
                'resolution': timedelta(minutes=1)  # 1分钟
            },
            'daily': {
                'retention': timedelta(days=365),  # 1年
                'resolution': timedelta(hours=1)   # 1小时
            }
        }
        
        # 初始化InfluxDB客户端
        self.client = InfluxDBClient(
            url=config['influxdb']['url'],
            token=config['influxdb']['token'],
            org=config['influxdb']['org']
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        
        # 缓存设置
        self.cache_size = config.get('cache_size', 10000)
        self.cache = {tier: [] for tier in self.tiers}
        
    async def start(self):
        """启动存储管理器"""
        self.logger.info("多级存储管理器已启动")
        asyncio.create_task(self._run_maintenance())
        
    async def _run_maintenance(self):
        """运行存储维护任务"""
        while True:
            try:
                # 数据聚合
                await self._aggregate_data()
                # 过期数据清理
                await self._cleanup_expired_data()
                # 缓存管理
                self._manage_cache()
                
                await asyncio.sleep(3600)  # 每小时运行一次
                
            except Exception as e:
                self.logger.error(f"存储维护任务失败: {str(e)}")
                await asyncio.sleep(60)
                
    async def write_metrics(self, metrics: Dict, tags: Dict = None):
        """写入指标数据"""
        try:
            with STORAGE_LATENCY.labels('write').time():
                # 创建数据点
                point = Point("metrics")
                
                # 添加标签
                if tags:
                    for key, value in tags.items():
                        point = point.tag(key, value)
                
                # 添加字段
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        point = point.field(key, value)
                
                # 写入实时层
                self.write_api.write(
                    bucket=self.config['influxdb']['bucket'],
                    record=point
                )
                
                # 更新缓存
                self.cache['realtime'].append({
                    'timestamp': datetime.now(),
                    'metrics': metrics,
                    'tags': tags or {}
                })
                
                STORAGE_OPS.labels(operation='write', tier='realtime').inc()
                
        except Exception as e:
            self.logger.error(f"写入指标数据失败: {str(e)}")
            raise
            
    async def read_metrics(self,
                          start_time: datetime,
                          end_time: datetime,
                          tags: Dict = None,
                          aggregation: str = None) -> pd.DataFrame:
        """读取指标数据"""
        try:
            with STORAGE_LATENCY.labels('read').time():
                # 确定合适的存储层
                tier = self._select_storage_tier(start_time, end_time)
                
                # 构建查询
                query = f'''
                from(bucket: "{self.config['influxdb']['bucket']}")
                    |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                '''
                
                # 添加标签过滤
                if tags:
                    for key, value in tags.items():
                        query += f'|> filter(fn: (r) => r["{key}"] == "{value}")\n'
                
                # 添加聚合
                if aggregation:
                    query += f'|> aggregateWindow(every: {self.tiers[tier]["resolution"]}, fn: {aggregation})\n'
                
                # 执行查询
                result = self.query_api.query_data_frame(query)
                
                STORAGE_OPS.labels(operation='read', tier=tier).inc()
                
                return result
                
        except Exception as e:
            self.logger.error(f"读取指标数据失败: {str(e)}")
            raise
            
    def _select_storage_tier(self, start_time: datetime, end_time: datetime) -> str:
        """选择合适的存储层"""
        duration = end_time - start_time
        
        if duration <= self.tiers['realtime']['retention']:
            return 'realtime'
        elif duration <= self.tiers['hourly']['retention']:
            return 'hourly'
        else:
            return 'daily'
            
    async def _aggregate_data(self):
        """聚合数据到更高层级"""
        try:
            # 聚合到小时层
            hourly_cutoff = datetime.now() - self.tiers['hourly']['retention']
            hourly_query = f'''
            from(bucket: "{self.config['influxdb']['bucket']}")
                |> range(start: {hourly_cutoff.isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "metrics")
                |> aggregateWindow(every: 1h, fn: mean)
            '''
            self.write_api.write(
                bucket=self.config['influxdb']['bucket'],
                record=self.query_api.query(hourly_query)
            )
            
            # 聚合到日度层
            daily_cutoff = datetime.now() - self.tiers['daily']['retention']
            daily_query = f'''
            from(bucket: "{self.config['influxdb']['bucket']}")
                |> range(start: {daily_cutoff.isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "metrics")
                |> aggregateWindow(every: 24h, fn: mean)
            '''
            self.write_api.write(
                bucket=self.config['influxdb']['bucket'],
                record=self.query_api.query(daily_query)
            )
            
        except Exception as e:
            self.logger.error(f"数据聚合失败: {str(e)}")
            
    async def _cleanup_expired_data(self):
        """清理过期数据"""
        try:
            for tier, config in self.tiers.items():
                cutoff = datetime.now() - config['retention']
                delete_query = f'''
                from(bucket: "{self.config['influxdb']['bucket']}")
                    |> range(start: 0, stop: {cutoff.isoformat()})
                    |> filter(fn: (r) => r["_measurement"] == "metrics")
                    |> drop()
                '''
                self.client.delete_api().delete(
                    start=datetime.min,
                    stop=cutoff,
                    predicate='_measurement="metrics"',
                    bucket=self.config['influxdb']['bucket']
                )
                
        except Exception as e:
            self.logger.error(f"清理过期数据失败: {str(e)}")
            
    def _manage_cache(self):
        """管理内存缓存"""
        try:
            for tier in self.tiers:
                # 移除过期数据
                cutoff = datetime.now() - self.tiers[tier]['retention']
                self.cache[tier] = [
                    item for item in self.cache[tier]
                    if item['timestamp'] > cutoff
                ]
                
                # 限制缓存大小
                if len(self.cache[tier]) > self.cache_size:
                    self.cache[tier] = self.cache[tier][-self.cache_size:]
                    
        except Exception as e:
            self.logger.error(f"缓存管理失败: {str(e)}")
            
    async def close(self):
        """关闭存储管理器"""
        try:
            self.write_api.close()
            self.client.close()
            self.logger.info("存储管理器已关闭")
        except Exception as e:
            self.logger.error(f"关闭存储管理器失败: {str(e)}")
            
    def get_storage_stats(self) -> Dict:
        """获取存储统计信息"""
        return {
            tier: {
                'cache_size': len(self.cache[tier]),
                'retention': str(self.tiers[tier]['retention']),
                'resolution': str(self.tiers[tier]['resolution'])
            }
            for tier in self.tiers
        }