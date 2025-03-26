#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 移动应用主程序

Mobile Application Main Program
"""

import sys
import os
from typing import Optional, Dict, Any
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QStackedWidget, QTabBar, QStatusBar, QMessageBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon

from ui import UIConfig, UITheme
from ui.mobile import event_bus

class MobileNavigationBar(QTabBar):
    """移动导航栏"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # 设置导航栏样式
        self.setExpanding(True)
        self.setDrawBase(False)
        self.setIconSize(QSize(24, 24))
        
        # 添加导航项
        self.addTab("仪表盘")
        self.addTab("交易")
        self.addTab("行情")
        self.addTab("设置")

class MobileMainWindow(QMainWindow):
    """移动主窗口"""
    
    def __init__(self, config: UIConfig):
        super().__init__()
        
        self.config = config
        self.setup_ui()
        self.setup_status_bar()
        self.setup_events()
        
    def setup_ui(self):
        """设置UI"""
        # 设置窗口属性
        self.setWindowTitle("FST Mobile")
        self.setMinimumSize(QSize(360, 640))
        
        # 创建中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建布局
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 创建堆叠部件用于视图切换
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)
        
        # 添加导航栏
        self.nav_bar = MobileNavigationBar()
        self.nav_bar.currentChanged.connect(self.stack.setCurrentIndex)
        self.layout.addWidget(self.nav_bar)
    
    def setup_status_bar(self):
        """设置状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
    
    def setup_events(self):
        """设置事件处理"""
        event_bus.error_occurred.connect(self.handle_error)
        event_bus.theme_changed.connect(self.handle_theme_changed)
        event_bus.push_notification.connect(self.handle_notification)
        event_bus.push_alert.connect(self.handle_alert)
    
    def handle_error(self, message: str):
        """处理错误"""
        QMessageBox.critical(self, "错误", message)
    
    def handle_theme_changed(self, theme: str):
        """处理主题改变"""
        self.status_bar.showMessage(f"主题已更改为: {theme}")
    
    def handle_notification(self, title: str, message: str):
        """处理推送通知"""
        self.status_bar.showMessage(message)
    
    def handle_alert(self, title: str, message: str):
        """处理推送警报"""
        QMessageBox.warning(self, title, message)
    
    def closeEvent(self, event):
        """关闭事件处理"""
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            event_bus.shutdown.emit()
            event.accept()
        else:
            event.ignore()

class MobileApp:
    """移动应用"""
    
    def __init__(self, config: UIConfig):
        self.config = config
        self.app = QApplication(sys.argv)
        self.window = None
    
    def start(self):
        """启动应用"""
        # 创建主窗口
        self.window = MobileMainWindow(self.config)
        self.window.show()
        
        # 发送启动事件
        event_bus.startup.emit()
        
        # 运行应用
        return self.app.exec()
    
    def stop(self):
        """停止应用"""
        if self.window:
            self.window.close()