"""
FST (Full Self Trading) - 券商适配器引用模块

此模块仅用于重新导出 broker_adapters/broker_adapter.py 中的内容，保持向后兼容性。
"""

# 从正确的位置导入并重新导出所有内容
from infrastructure.api.broker_adapters.broker_adapter import (
    BrokerAdapter, 
    ConnectionState, 
    OrderStatus
)

# 重新导出所有符号
__all__ = ['BrokerAdapter', 'ConnectionState', 'OrderStatus']