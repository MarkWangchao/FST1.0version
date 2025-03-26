"""
市场数据服务 - 提供市场数据的微服务实现

该模块是市场数据微服务的实现，负责:
- 从各数据源获取市场数据
- 标准化和处理数据
- 提供REST和WebSocket API
- 数据缓存和历史数据管理
"""

from .service import MarketDataService

__all__ = ["MarketDataService"]