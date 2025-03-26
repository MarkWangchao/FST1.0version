#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 桌面应用模块

基于PyQt6实现的桌面应用界面，提供：
- 主窗口管理
- 视图组件
- 主题支持
- 多语言支持

Desktop Application Module:
- Main window management
- View components
- Theme support
- Internationalization
"""

from typing import Dict, Any, Optional, List
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal

class DesktopUIEvents(QObject):
    """桌面UI事件"""
    
    # 系统事件
    startup = pyqtSignal()              # 启动事件
    shutdown = pyqtSignal()             # 关闭事件
    theme_changed = pyqtSignal(str)     # 主题改变事件
    language_changed = pyqtSignal(str)  # 语言改变事件
    
    # 交易事件
    order_created = pyqtSignal(dict)    # 订单创建事件
    order_updated = pyqtSignal(dict)    # 订单更新事件
    trade_executed = pyqtSignal(dict)   # 交易执行事件
    
    # 数据事件
    data_updated = pyqtSignal(str, dict)  # 数据更新事件
    error_occurred = pyqtSignal(str)      # 错误事件

# 全局事件总线
event_bus = DesktopUIEvents()

# 导出
__all__ = [
    'event_bus',
    'DesktopUIEvents'
]