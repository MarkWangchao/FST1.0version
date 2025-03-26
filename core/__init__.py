#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 核心功能层

此模块包含交易系统的核心功能组件，包括：
- 市场数据处理
- 风险管理
- 交易执行
- 策略管理
- 事件总线

Created on 2025-03-07
"""

# 版本信息
__version__ = '1.0.0'

# 子模块
from core import market
from core import risk
from core import security
from core import strategy
from core import trading
from core import event

# 导出的组件
__all__ = [
    'market',
    'risk',
    'security',
    'strategy',
    'trading',
    'event',
]