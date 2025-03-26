#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 事件验证器测试

测试内容:
- 事件模式验证
- 数据类型检查
- 必填字段验证
- 范围和格式验证
- 自定义验证规则
"""

import unittest
import json
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any
from tests import AsyncTestCase, async_test, DataGenerator
from infrastructure.event_bus.event_manager import (
    EventType, Event, EventValidator
)

class TestEventValidator(AsyncTestCase):
    """事件验证器测试"""
    
    def setUp(self):
        """测试初始化"""
        super().setUp()
        self.validator = EventValidator()
        
        # 定义基本验证模式
        self.tick_schema = {
            "type": "object",
            "required": ["symbol", "price", "volume"],
            "properties": {
                "symbol": {"type": "string", "pattern": "^[A-Z]+/[A-Z]+$"},
                "price": {"type": "number", "minimum": 0},
                "volume": {"type": "number", "minimum": 0},
                "timestamp": {"type": "number"},
                "source": {"type": "string"}
            }
        }
        
        self.order_schema = {
            "type": "object",
            "required": ["order_id", "symbol", "direction", "price", "volume"],
            "properties": {
                "order_id": {"type": "string"},
                "symbol": {"type": "string"},
                "direction": {"type": "string", "enum": ["buy", "sell"]},
                "price": {"type": "number", "minimum": 0},
                "volume": {"type": "number", "minimum": 0},
                "order_type": {"type": "string", "enum": ["limit", "market"]},
                "status": {"type": "string"}
            }
        }
        
        # 生成测试事件
        self.valid_tick = Event(
            event_type=EventType.TICK,
            data={
                "symbol": "BTC/USDT",
                "price": 50000.0,
                "volume": 1.5,
                "timestamp": datetime.now().timestamp()
            }
        )
        
        self.valid_order = Event(
            event_type=EventType.ORDER,
            data={
                "order_id": "TEST001",
                "symbol": "BTC/USDT",
                "direction": "buy",
                "price": 50000.0,
                "volume": 1.0,
                "order_type": "limit",
                "status": "pending"
            }
        )
    
    def test_validator_creation(self):
        """测试验证器创建"""
        self.assertIsNotNone(self.validator)
        self.assertEqual(len(self.validator._validators), 0)
    
    @async_test()
    async def test_schema_registration(self):
        """测试验证模式注册"""
        # 测试添加验证模式
        self.validator.add_validator(EventType.TICK, self.tick_schema)
        self.assertEqual(len(self.validator._validators), 1)
        
        # 测试重复添加
        self.validator.add_validator(EventType.TICK, self.tick_schema)
        self.assertEqual(len(self.validator._validators), 1)
        
        # 测试移除验证模式
        self.validator.remove_validator(EventType.TICK)
        self.assertEqual(len(self.validator._validators), 0)
        
        # 测试移除不存在的模式
        with self.assertRaises(KeyError):
            self.validator.remove_validator("NON_EXISTENT")
    
    @async_test()
    async def test_basic_validation(self):
        """测试基本验证功能"""
        # 添加验证模式
        self.validator.add_validator(EventType.TICK, self.tick_schema)
        self.validator.add_validator(EventType.ORDER, self.order_schema)
        
        # 测试有效事件
        self.assertTrue(self.validator.validate(self.valid_tick))
        self.assertTrue(self.validator.validate(self.valid_order))
        
        # 测试无效事件 - 缺少必填字段
        invalid_tick = Event(
            event_type=EventType.TICK,
            data={
                "symbol": "BTC/USDT",
                "price": 50000.0
                # 缺少volume字段
            }
        )
        self.assertFalse(self.validator.validate(invalid_tick))
    
    @async_test()
    async def test_type_validation(self):
        """测试数据类型验证"""
        self.validator.add_validator(EventType.TICK, self.tick_schema)
        
        # 测试类型错误
        invalid_types = Event(
            event_type=EventType.TICK,
            data={
                "symbol": "BTC/USDT",
                "price": "50000",  # 应该是数字
                "volume": 1.5
            }
        )
        self.assertFalse(self.validator.validate(invalid_types))
        
        # 测试数字格式
        decimal_price = Event(
            event_type=EventType.TICK,
            data={
                "symbol": "BTC/USDT",
                "price": Decimal("50000.00"),  # Decimal类型
                "volume": 1.5
            }
        )
        self.assertTrue(self.validator.validate(decimal_price))
    
    @async_test()
    async def test_range_validation(self):
        """测试范围验证"""
        self.validator.add_validator(EventType.TICK, self.tick_schema)
        
        # 测试负数值
        negative_values = Event(
            event_type=EventType.TICK,
            data={
                "symbol": "BTC/USDT",
                "price": -50000.0,  # 负价格
                "volume": 1.5
            }
        )
        self.assertFalse(self.validator.validate(negative_values))
        
        # 测试零值
        zero_values = Event(
            event_type=EventType.TICK,
            data={
                "symbol": "BTC/USDT",
                "price": 50000.0,
                "volume": 0.0  # 零成交量
            }
        )
        self.assertTrue(self.validator.validate(zero_values))
    
    @async_test()
    async def test_format_validation(self):
        """测试格式验证"""
        self.validator.add_validator(EventType.TICK, self.tick_schema)
        
        # 测试无效的交易对格式
        invalid_symbol = Event(
            event_type=EventType.TICK,
            data={
                "symbol": "btc/usdt",  # 小写字母
                "price": 50000.0,
                "volume": 1.5
            }
        )
        self.assertFalse(self.validator.validate(invalid_symbol))
        
        # 测试有效的交易对格式
        valid_symbols = [
            "BTC/USDT",
            "ETH/BTC",
            "XRP/USDT"
        ]
        for symbol in valid_symbols:
            event = Event(
                event_type=EventType.TICK,
                data={
                    "symbol": symbol,
                    "price": 50000.0,
                    "volume": 1.5
                }
            )
            self.assertTrue(self.validator.validate(event))
    
    @async_test()
    async def test_enum_validation(self):
        """测试枚举值验证"""
        self.validator.add_validator(EventType.ORDER, self.order_schema)
        
        # 测试无效的订单方向
        invalid_direction = Event(
            event_type=EventType.ORDER,
            data={
                "order_id": "TEST001",
                "symbol": "BTC/USDT",
                "direction": "long",  # 无效的方向
                "price": 50000.0,
                "volume": 1.0
            }
        )
        self.assertFalse(self.validator.validate(invalid_direction))
        
        # 测试无效的订单类型
        invalid_order_type = Event(
            event_type=EventType.ORDER,
            data={
                "order_id": "TEST001",
                "symbol": "BTC/USDT",
                "direction": "buy",
                "price": 50000.0,
                "volume": 1.0,
                "order_type": "invalid"  # 无效的订单类型
            }
        )
        self.assertFalse(self.validator.validate(invalid_order_type))
    
    @async_test()
    async def test_custom_validation(self):
        """测试自定义验证规则"""
        # 定义带有自定义验证的模式
        custom_schema = {
            "type": "object",
            "required": ["price", "volume"],
            "properties": {
                "price": {"type": "number", "minimum": 0},
                "volume": {"type": "number", "minimum": 0}
            },
            "additionalProperties": False,  # 不允许额外的属性
            "custom_validator": lambda data: data["price"] * data["volume"] <= 1000000  # 最大交易额限制
        }
        
        self.validator.add_validator("CUSTOM", custom_schema)
        
        # 测试有效交易额
        valid_amount = Event(
            event_type="CUSTOM",
            data={
                "price": 100.0,
                "volume": 1000.0  # 总额 100,000
            }
        )
        self.assertTrue(self.validator.validate(valid_amount))
        
        # 测试超出限制的交易额
        invalid_amount = Event(
            event_type="CUSTOM",
            data={
                "price": 100000.0,
                "volume": 100.0  # 总额 10,000,000
            }
        )
        self.assertFalse(self.validator.validate(invalid_amount))
    
    @async_test()
    async def test_nested_validation(self):
        """测试嵌套对象验证"""
        # 定义带有嵌套对象的模式
        nested_schema = {
            "type": "object",
            "required": ["order", "execution"],
            "properties": {
                "order": {
                    "type": "object",
                    "required": ["id", "price"],
                    "properties": {
                        "id": {"type": "string"},
                        "price": {"type": "number"}
                    }
                },
                "execution": {
                    "type": "object",
                    "required": ["quantity", "timestamp"],
                    "properties": {
                        "quantity": {"type": "number"},
                        "timestamp": {"type": "number"}
                    }
                }
            }
        }
        
        self.validator.add_validator("NESTED", nested_schema)
        
        # 测试有效的嵌套对象
        valid_nested = Event(
            event_type="NESTED",
            data={
                "order": {
                    "id": "ORDER001",
                    "price": 50000.0
                },
                "execution": {
                    "quantity": 1.5,
                    "timestamp": datetime.now().timestamp()
                }
            }
        )
        self.assertTrue(self.validator.validate(valid_nested))
        
        # 测试无效的嵌套对象
        invalid_nested = Event(
            event_type="NESTED",
            data={
                "order": {
                    "id": "ORDER001"
                    # 缺少price字段
                },
                "execution": {
                    "quantity": 1.5,
                    "timestamp": datetime.now().timestamp()
                }
            }
        )
        self.assertFalse(self.validator.validate(invalid_nested))

if __name__ == '__main__':
    unittest.main()