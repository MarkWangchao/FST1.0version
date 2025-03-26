#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 集群测试

测试内容:
- 集群节点管理
- 负载均衡
- 数据同步
- 集群监控
- 故障恢复
"""

import unittest
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.cluster.cluster_manager import ClusterManager
from infrastructure.cluster.node_manager import NodeManager
from infrastructure.cluster.sync_manager import SyncManager
from infrastructure.cluster.monitor import ClusterMonitor

class TestCluster(AsyncTestCase):
    """集群功能测试"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.cluster_config = {
            'cluster_id': 'test_cluster',
            'node_id': 'node_1',
            'redis_url': 'redis://localhost:6379/0',
            'heartbeat_interval': 1,
            'sync_interval': 2,
            'max_nodes': 5,
            'load_balance_threshold': 0.8
        }
        
        # 创建集群管理器
        self.cluster_manager = ClusterManager(self.cluster_config)
        self.node_manager = NodeManager(self.cluster_config)
        self.sync_manager = SyncManager(self.cluster_config)
        self.cluster_monitor = ClusterMonitor(self.cluster_config)
        
        # 测试数据
        self.test_data = {
            'market_data': DataGenerator.generate_market_data(
                'BTC/USDT',
                datetime.now(),
                datetime.now(),
                '1m'
            ),
            'tick_data': DataGenerator.generate_tick_data(
                'BTC/USDT',
                100,
                1.0
            )
        }
    
    def test_cluster_creation(self):
        """测试集群创建"""
        self.assertIsNotNone(self.cluster_manager)
        self.assertEqual(self.cluster_manager.cluster_id, 'test_cluster')
        self.assertEqual(self.cluster_manager.node_id, 'node_1')
    
    @async_test()
    async def test_node_management(self):
        """测试节点管理"""
        # 启动节点
        await self.node_manager.start()
        
        # 注册节点
        node_info = {
            'node_id': 'node_2',
            'ip': '127.0.0.1',
            'port': 8000,
            'capabilities': ['market_data', 'trading']
        }
        success = await self.node_manager.register_node(node_info)
        self.assertTrue(success)
        
        # 获取节点列表
        nodes = await self.node_manager.get_active_nodes()
        self.assertEqual(len(nodes), 2)
        
        # 更新节点状态
        await self.node_manager.update_node_status('node_2', 'active')
        status = await self.node_manager.get_node_status('node_2')
        self.assertEqual(status, 'active')
        
        # 移除节点
        await self.node_manager.remove_node('node_2')
        nodes = await self.node_manager.get_active_nodes()
        self.assertEqual(len(nodes), 1)
    
    @async_test()
    async def test_load_balancing(self):
        """测试负载均衡"""
        # 启动负载均衡器
        await self.cluster_manager.start_load_balancer()
        
        # 模拟节点负载
        node_loads = {
            'node_1': 0.6,
            'node_2': 0.9,
            'node_3': 0.4
        }
        
        # 更新节点负载
        for node_id, load in node_loads.items():
            await self.cluster_manager.update_node_load(node_id, load)
        
        # 检查负载均衡
        balanced = await self.cluster_manager.check_load_balance()
        self.assertTrue(balanced)
        
        # 获取负载分配
        assignments = await self.cluster_manager.get_load_assignments()
        self.assertIn('node_1', assignments)
        self.assertIn('node_2', assignments)
        self.assertIn('node_3', assignments)
    
    @async_test()
    async def test_data_synchronization(self):
        """测试数据同步"""
        # 启动同步管理器
        await self.sync_manager.start()
        
        # 模拟数据更新
        market_data = self.test_data['market_data']
        await self.sync_manager.sync_market_data(market_data)
        
        # 验证数据同步
        synced_data = await self.sync_manager.get_synced_data('market_data')
        self.assertIsNotNone(synced_data)
        self.assertEqual(len(synced_data), len(market_data))
        
        # 测试增量同步
        new_data = market_data.tail(10)
        await self.sync_manager.sync_incremental_data('market_data', new_data)
        
        # 验证增量同步
        updated_data = await self.sync_manager.get_synced_data('market_data')
        self.assertEqual(len(updated_data), len(market_data) + 10)
    
    @async_test()
    async def test_cluster_monitoring(self):
        """测试集群监控"""
        # 启动监控器
        await self.cluster_monitor.start()
        
        # 更新监控指标
        metrics = {
            'cpu_usage': 0.5,
            'memory_usage': 0.6,
            'network_usage': 0.3,
            'active_connections': 100
        }
        await self.cluster_monitor.update_metrics(metrics)
        
        # 获取监控数据
        cluster_metrics = await self.cluster_monitor.get_cluster_metrics()
        self.assertIn('cpu_usage', cluster_metrics)
        self.assertIn('memory_usage', cluster_metrics)
        
        # 检查告警
        alerts = await self.cluster_monitor.check_alerts()
        self.assertIsInstance(alerts, list)
    
    @async_test()
    async def test_failure_recovery(self):
        """测试故障恢复"""
        # 模拟节点故障
        await self.node_manager.update_node_status('node_2', 'failed')
        
        # 触发故障恢复
        await self.cluster_manager.handle_node_failure('node_2')
        
        # 验证恢复状态
        status = await self.node_manager.get_node_status('node_2')
        self.assertEqual(status, 'recovering')
        
        # 等待恢复完成
        await asyncio.sleep(2)
        
        # 验证最终状态
        status = await self.node_manager.get_node_status('node_2')
        self.assertEqual(status, 'active')
    
    @async_test()
    async def test_cluster_scaling(self):
        """测试集群扩缩容"""
        # 测试扩容
        new_node = {
            'node_id': 'node_4',
            'ip': '127.0.0.1',
            'port': 8001,
            'capabilities': ['market_data']
        }
        success = await self.cluster_manager.scale_up(new_node)
        self.assertTrue(success)
        
        # 验证扩容结果
        nodes = await self.node_manager.get_active_nodes()
        self.assertEqual(len(nodes), 2)  # 包括初始节点
        
        # 测试缩容
        success = await self.cluster_manager.scale_down('node_4')
        self.assertTrue(success)
        
        # 验证缩容结果
        nodes = await self.node_manager.get_active_nodes()
        self.assertEqual(len(nodes), 1)
    
    @async_test()
    async def test_data_consistency(self):
        """测试数据一致性"""
        # 启动数据同步
        await self.sync_manager.start()
        
        # 模拟数据写入
        test_data = {'key': 'value', 'timestamp': time.time()}
        await self.sync_manager.write_data('test_key', test_data)
        
        # 验证数据一致性
        for node_id in await self.node_manager.get_active_nodes():
            data = await self.sync_manager.read_data('test_key', node_id)
            self.assertEqual(data['key'], test_data['key'])
            self.assertEqual(data['timestamp'], test_data['timestamp'])
    
    @async_test()
    async def test_cluster_performance(self):
        """测试集群性能"""
        # 生成大量测试数据
        large_data = []
        for i in range(1000):
            data = {
                'id': i,
                'timestamp': time.time(),
                'value': i * 1.5
            }
            large_data.append(data)
        
        # 测试数据同步性能
        start_time = time.time()
        await self.sync_manager.sync_batch_data('performance_test', large_data)
        end_time = time.time()
        
        # 验证性能
        sync_time = end_time - start_time
        self.assertLess(sync_time, 2.0)  # 确保1000条数据同步时间小于2秒
        
        # 测试查询性能
        start_time = time.time()
        result = await self.sync_manager.query_data('performance_test', limit=100)
        end_time = time.time()
        
        # 验证查询性能
        query_time = end_time - start_time
        self.assertLess(query_time, 0.5)  # 确保查询时间小于0.5秒

if __name__ == '__main__':
    unittest.main()