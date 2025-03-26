"""
微服务组件 - 提供独立部署的微服务功能

该模块提供了可独立部署的微服务实现，包括:
- 市场数据服务: 提供市场数据的采集和分发
- 执行服务: 处理交易指令的执行和状态跟踪
- 报告服务: 生成和分发交易报告

每个微服务可以独立部署，通过API网关或消息队列通信。
"""

__version__ = "0.1.0"

# 导出微服务接口
from .market_data_service.service import MarketDataService
from .execution_service.service import ExecutionService
from .reporting_service.service import ReportingService

__all__ = [
    "MarketDataService",
    "ExecutionService",
    "ReportingService"
]