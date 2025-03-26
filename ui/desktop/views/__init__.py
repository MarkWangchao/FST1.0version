#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 桌面视图模块

提供桌面应用的各种视图组件，包括：
- 基础视图类
- 仪表盘视图
- 设置视图

Desktop Views Module:
- Base view classes
- Dashboard view
- Settings view
"""

from typing import Optional, Dict, Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal

class BaseView(QWidget):
    """基础视图类"""
    
    # 视图事件信号
    view_ready = pyqtSignal()      # 视图准备就绪
    view_closing = pyqtSignal()    # 视图即将关闭
    view_refresh = pyqtSignal()    # 视图刷新
    
    def __init__(self, parent: Optional[QWidget] = None):
        """
        初始化基础视图
        
        Args:
            parent: 父部件
        """
        super().__init__(parent)
        
        # 创建主布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # 初始化UI
        self.setup_ui()
        self.setup_events()
    
    def setup_ui(self):
        """设置UI"""
        pass
    
    def setup_events(self):
        """设置事件处理"""
        pass
    
    def refresh(self):
        """刷新视图"""
        self.view_refresh.emit()
    
    def cleanup(self):
        """清理资源"""
        self.view_closing.emit()

class DataView(BaseView):
    """数据视图基类"""
    
    # 数据事件信号
    data_loaded = pyqtSignal(dict)     # 数据加载完成
    data_updated = pyqtSignal(dict)    # 数据更新
    data_error = pyqtSignal(str)       # 数据错误
    
    def __init__(self, parent: Optional[QWidget] = None):
        """
        初始化数据视图
        
        Args:
            parent: 父部件
        """
        super().__init__(parent)
        self._data: Dict[str, Any] = {}
    
    def load_data(self):
        """加载数据"""
        pass
    
    def update_data(self, data: Dict[str, Any]):
        """
        更新数据
        
        Args:
            data: 新数据
        """
        self._data.update(data)
        self.data_updated.emit(self._data)
    
    def get_data(self) -> Dict[str, Any]:
        """
        获取数据
        
        Returns:
            Dict[str, Any]: 当前数据
        """
        return self._data.copy()

class ChartView(DataView):
    """图表视图基类"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        """
        初始化图表视图
        
        Args:
            parent: 父部件
        """
        super().__init__(parent)
        self._chart = None
    
    def setup_chart(self):
        """设置图表"""
        pass
    
    def update_chart(self):
        """更新图表"""
        pass
    
    def clear_chart(self):
        """清空图表"""
        pass

# 导出
__all__ = [
    'BaseView',
    'DataView',
    'ChartView'
]