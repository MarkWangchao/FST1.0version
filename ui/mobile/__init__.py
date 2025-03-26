#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 移动应用模块

基于Flutter实现的移动应用界面，提供：
- 主界面管理
- 视图组件
- 主题支持
- 多语言支持
- 消息推送

Mobile Application Module:
- Main interface management
- View components
- Theme support
- Internationalization
- Push notifications
"""

from typing import Dict, Any, Optional, List
from PyQt6.QtCore import QObject, pyqtSignal

class MobileUIEvents(QObject):
    """移动UI事件"""
    
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
    
    # 推送事件
    push_notification = pyqtSignal(str, str)  # 推送通知事件
    push_alert = pyqtSignal(str, str)        # 推送警报事件

# 全局事件总线
event_bus = MobileUIEvents()

# 导出
__all__ = [
    'event_bus',
    'MobileUIEvents'
]