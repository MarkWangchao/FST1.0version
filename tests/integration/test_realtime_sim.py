# tests/integration/test_realtime_sim.py

import unittest
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List
from unittest.mock import Mock, patch

from infrastructure.event_bus.event_manager import (
    Event, EventType, OptimizedEventBus, TqEventAdapter
)

class RealtimeSimTest(unittest.TestCase):
    """模拟实盘环境的沙盒测试"""
    
    def setUp(self):
        """测试准备"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # 初始化事件总线
        self.event_bus = OptimizedEventBus(
            name="realtime_sim",
            config_file="config/event_bus.testing.yaml"
        )
        
        # 模拟账户状态
        self.account_state = {
            'balance': 1000000,  # 初始资金100万
            'available': 900000, # 可用资金90万
            'margin': 100000,   # 保证金10万
            'positions': {}      # 持仓信息
        }
        
        # 记录测试中的事件
        self.received_events = []
        
    def tearDown(self):
        """测试清理"""
        self.loop.run_until_complete(self.event_bus.stop())
        self.loop.close()

    async def simulate_market_data(self, symbol: str, 
                                 disconnect_at: int = None,
                                 price_jump: bool = False):
        """
        模拟行情数据推送
        
        Args:
            symbol: 合约代码
            disconnect_at: 在第几次推送后模拟断线
            price_jump: 是否模拟价格跳变
        """
        base_price = 3500.0
        for i in range(100):
            if disconnect_at and i == disconnect_at:
                # 模拟断线
                await asyncio.sleep(5)
                continue
                
            price = base_price
            if price_jump and i == 50:
                # 模拟价格跳变
                price += 100.0
                
            tick_data = {
                'symbol': symbol,
                'datetime': datetime.now().isoformat(),
                'last_price': price,
                'volume': 10,
                'bid_price1': price - 0.5,
                'ask_price1': price + 0.5,
                'bid_volume1': 5,
                'ask_volume1': 5
            }
            
            event = Event(
                event_type=EventType.TICK,
                data=tick_data,
                source='sim'
            )
            await self.event_bus.publish(event)
            await asyncio.sleep(0.1)

    def test_market_data_reconnection(self):
        """测试行情断线重连场景"""
        async def test():
            # 注册行情处理器
            received_ticks = []
            def tick_handler(event):
                received_ticks.append(event)
            
            self.event_bus.router.add_route("TICK", tick_handler)
            await self.event_bus.start()
            
            # 模拟行情推送(在第30次推送时断线)
            await self.simulate_market_data("SHFE.rb2405", disconnect_at=30)
            
            # 验证断线前后的行情连续性
            self.assertGreater(len(received_ticks), 31)
            
            # 检查断线期间是否有重复数据
            timestamps = [tick.data['datetime'] for tick in received_ticks]
            self.assertEqual(len(timestamps), len(set(timestamps)))
            
        self.loop.run_until_complete(test())

    def test_margin_insufficient(self):
        """测试保证金不足场景"""
        async def test():
            # 注册订单处理器
            order_events = []
            def order_handler(event):
                order_events.append(event)
            
            self.event_bus.router.add_route("ORDER_*", order_handler)
            await self.event_bus.start()
            
            # 模拟下单(资金不足)
            order_request = {
                'symbol': 'SHFE.rb2405',
                'direction': 'BUY',
                'offset': 'OPEN',
                'volume': 100,  # 大量开仓
                'price': 3500.0
            }
            
            event = Event(
                event_type=EventType.ORDER,
                data=order_request,
                source='strategy'
            )
            
            # 发送订单请求
            await self.event_bus.publish(event)
            await asyncio.sleep(0.1)
            
            # 验证是否触发风控
            self.assertTrue(any(e.event_type == EventType.RISK_ALERT 
                              for e in order_events))
            
            # 验证订单是否被拒绝
            self.assertTrue(any(e.event_type == EventType.ORDER_CANCELLED 
                              and "保证金不足" in str(e.data.get('reason'))
                              for e in order_events))
            
        self.loop.run_until_complete(test())

    def test_order_retry_mechanism(self):
        """测试订单重试逻辑"""
        async def test():
            # 模拟订单状态
            order_states = {
                'order1': {
                    'attempts': 0,
                    'status': 'PENDING'
                }
            }
            
            # 注册订单处理器
            async def order_handler(event):
                if event.event_type == EventType.ORDER:
                    order_id = event.data.get('order_id', 'order1')
                    state = order_states[order_id]
                    
                    # 模拟前两次发送失败
                    if state['attempts'] < 2:
                        state['attempts'] += 1
                        # 发送失败响应
                        error_event = Event(
                            event_type=EventType.ERROR,
                            data={
                                'order_id': order_id,
                                'error_code': 'TIMEOUT',
                                'error_msg': '发送超时'
                            }
                        )
                        await self.event_bus.publish(error_event)
                    else:
                        # 第三次成功
                        success_event = Event(
                            event_type=EventType.ORDER_COMPLETED,
                            data={
                                'order_id': order_id,
                                'status': 'FINISHED'
                            }
                        )
                        await self.event_bus.publish(success_event)
            
            self.event_bus.router.add_route("ORDER", order_handler)
            await self.event_bus.start()
            
            # 发送订单
            order_request = {
                'order_id': 'order1',
                'symbol': 'SHFE.rb2405',
                'direction': 'BUY',
                'offset': 'OPEN',
                'volume': 1,
                'price': 3500.0
            }
            
            event = Event(
                event_type=EventType.ORDER,
                data=order_request
            )
            
            # 发送订单并等待处理
            await self.event_bus.publish(event)
            await asyncio.sleep(1)  # 等待重试完成
            
            # 验证重试次数
            self.assertEqual(order_states['order1']['attempts'], 2)
            
            # 验证最终状态
            self.assertTrue(any(e.event_type == EventType.ORDER_COMPLETED 
                              for e in self.received_events))
            
        self.loop.run_until_complete(test())

    def test_target_pos_task(self):
        """测试目标持仓任务异常处理"""
        async def test():
            # 模拟当前持仓
            self.account_state['positions']['SHFE.rb2405'] = {
                'volume_long': 5,
                'volume_short': 0
            }
            
            # 注册持仓处理器
            position_updates = []
            def position_handler(event):
                if event.event_type == EventType.POSITION:
                    position_updates.append(event)
            
            self.event_bus.router.add_route("POSITION", position_handler)
            await self.event_bus.start()
            
            # 模拟目标持仓请求
            target_pos_request = {
                'symbol': 'SHFE.rb2405',
                'target_long': 3,  # 减仓到3手
                'target_short': 0
            }
            
            event = Event(
                event_type=EventType.POSITION,
                data=target_pos_request
            )
            
            # 发送请求
            await self.event_bus.publish(event)
            await asyncio.sleep(0.5)
            
            # 验证是否正确生成减仓订单
            self.assertTrue(any(e.event_type == EventType.ORDER 
                              and e.data['volume'] == 2  # 减仓2手
                              and e.data['offset'] == 'CLOSE'
                              for e in self.received_events))
            
        self.loop.run_until_complete(test())

if __name__ == '__main__':
    unittest.main()