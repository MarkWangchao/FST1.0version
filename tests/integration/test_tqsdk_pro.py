# tests/integration/test_tqsdk_pro.py

import unittest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from unittest.mock import Mock, patch

from infrastructure.event_bus.event_manager import (
    Event, EventType, OptimizedEventBus, TqEventAdapter
)

class TqsdkProTest(unittest.TestCase):
    """天勤专业版API测试"""
    
    def setUp(self):
        """测试准备"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # 初始化事件总线
        self.event_bus = OptimizedEventBus(
            name="tqsdk_pro_test",
            config_file="config/event_bus.testing.yaml"
        )
        
        # 模拟多账户配置
        self.accounts = {
            'account1': {
                'broker': 'simnow',
                'account_id': '123456',
                'password': '******'
            },
            'account2': {
                'broker': 'ctp',
                'account_id': '789012',
                'password': '******'
            }
        }
        
        # 记录测试事件
        self.received_events = []
        
    def tearDown(self):
        """测试清理"""
        self.loop.run_until_complete(self.event_bus.stop())
        self.loop.close()

    def test_multi_account_trading(self):
        """测试多账户交易"""
        async def test():
            # 注册账户处理器
            account_events = []
            def account_handler(event):
                if event.event_type in [EventType.ACCOUNT, EventType.POSITION]:
                    account_events.append(event)
            
            self.event_bus.router.add_route("ACCOUNT", account_handler)
            self.event_bus.router.add_route("POSITION", account_handler)
            await self.event_bus.start()
            
            # 模拟多账户同时下单
            orders = [
                {
                    'account_id': 'account1',
                    'symbol': 'SHFE.rb2405',
                    'direction': 'BUY',
                    'offset': 'OPEN',
                    'volume': 1,
                    'price': 3500.0
                },
                {
                    'account_id': 'account2',
                    'symbol': 'SHFE.rb2405',
                    'direction': 'SELL',
                    'offset': 'OPEN',
                    'volume': 1,
                    'price': 3500.0
                }
            ]
            
            # 发送订单
            for order in orders:
                event = Event(
                    event_type=EventType.ORDER,
                    data=order
                )
                await self.event_bus.publish(event)
            
            await asyncio.sleep(0.5)
            
            # 验证每个账户是否都收到响应
            account_ids = set(e.data.get('account_id') for e in account_events)
            self.assertEqual(len(account_ids), 2)
            
        self.loop.run_until_complete(test())

    def test_customized_datafeed(self):
        """测试自定义行情源"""
        async def test():
            # 模拟自定义行情源配置
            custom_datafeed = {
                'type': 'websocket',
                'url': 'ws://custom.datafeed.com/market',
                'symbols': ['SHFE.rb2405', 'SHFE.rb2406']
            }
            
            # 注册行情处理器
            market_data = []
            def market_handler(event):
                if event.event_type == EventType.TICK:
                    market_data.append(event)
            
            self.event_bus.router.add_route("TICK", market_handler)
            await self.event_bus.start()
            
            # 模拟行情推送
            for i in range(10):
                tick_data = {
                    'symbol': 'SHFE.rb2405',
                    'datetime': datetime.now().isoformat(),
                    'last_price': 3500.0 + i,
                    'volume': 10
                }
                
                event = Event(
                    event_type=EventType.TICK,
                    data=tick_data,
                    source='custom_feed'
                )
                await self.event_bus.publish(event)
            
            await asyncio.sleep(0.5)
            
            # 验证行情处理
            self.assertEqual(len(market_data), 10)
            self.assertEqual(
                market_data[-1].data['last_price'] - market_data[0].data['last_price'],
                9.0
            )
            
        self.loop.run_until_complete(test())

    def test_high_frequency_subscription(self):
        """测试高频行情订阅"""
        async def test():
            # 模拟高频订阅配置
            subscription = {
                'symbols': ['SHFE.rb2405'],
                'frequency': 'tick',  # tick级别
                'batch_size': 100,    # 批量处理大小
                'rate_limit': 10000   # 每秒最大处理量
            }
            
            # 注册高频处理器
            processed_count = 0
            last_process_time = time.time()
            
            def high_freq_handler(event):
                nonlocal processed_count, last_process_time
                if event.event_type == EventType.TICK:
                    processed_count += 1
                    
                    # 检查处理速率
                    current_time = time.time()
                    if current_time - last_process_time >= 1.0:
                        # 重置计数器
                        processed_count = 0
                        last_process_time = current_time
            
            self.event_bus.router.add_route("TICK", high_freq_handler)
            await self.event_bus.start()
            
            # 模拟高频数据推送
            start_time = time.time()
            tick_count = 0
            
            while time.time() - start_time < 1.0:  # 测试1秒
                tick_data = {
                    'symbol': 'SHFE.rb2405',
                    'datetime': datetime.now().isoformat(),
                    'last_price': 3500.0,
                    'volume': 1
                }
                
                event = Event(
                    event_type=EventType.TICK,
                    data=tick_data,
                    source='high_freq'
                )
                await self.event_bus.publish(event)
                tick_count += 1
                
                # 控制发送速率
                if tick_count % 100 == 0:
                    await asyncio.sleep(0.001)
            
            # 验证处理性能
            self.assertGreater(processed_count, 5000)  # 至少处理5000个tick
            
        self.loop.run_until_complete(test())

    def test_private_deployment(self):
        """测试私有化部署"""
        async def test():
            # 模拟私有化配置
            private_config = {
                'market_server': 'tcp://private.market.com:7777',
                'trade_server': 'tcp://private.trade.com:8888',
                'auth_server': 'http://private.auth.com:9999',
                'web_gui': 'http://private.gui.com'
            }
            
            # 注册连接状态处理器
            connection_status = {}
            def connection_handler(event):
                if event.event_type == EventType.SYSTEM:
                    connection_status[event.data['component']] = event.data['status']
            
            self.event_bus.router.add_route("SYSTEM", connection_handler)
            await self.event_bus.start()
            
            # 模拟连接事件
            components = ['market', 'trade', 'auth', 'gui']
            for component in components:
                event = Event(
                    event_type=EventType.SYSTEM,
                    data={
                        'component': component,
                        'status': 'connected',
                        'timestamp': datetime.now().isoformat()
                    }
                )
                await self.event_bus.publish(event)
            
            await asyncio.sleep(0.5)
            
            # 验证所有组件连接状态
            self.assertEqual(len(connection_status), len(components))
            self.assertTrue(all(status == 'connected' 
                              for status in connection_status.values()))
            
        self.loop.run_until_complete(test())

if __name__ == '__main__':
    unittest.main()