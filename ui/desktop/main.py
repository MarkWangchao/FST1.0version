#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 桌面应用主程序

Desktop Application Main Program
"""

import sys
import os
from typing import Optional, Dict, Any
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QStackedWidget, QMenuBar, QStatusBar, QMessageBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QAction

from ui import UIConfig, UITheme
from ui.desktop import event_bus
from ui.desktop.views.dashboard import DashboardView
from ui.desktop.views.settings import SettingsView

class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self, config: UIConfig):
        """
        初始化主窗口
        
        Args:
            config: UI配置
        """
        super().__init__()
        
        self.config = config
        self.setup_ui()
        self.setup_menu()
        self.setup_status_bar()
        self.setup_events()
        
    def setup_ui(self):
        """设置UI"""
        # 设置窗口属性
        self.setWindowTitle("FST Trading Platform")
        self.setMinimumSize(QSize(1024, 768))
        
        # 创建中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建布局
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建堆叠部件用于视图切换
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)
        
        # 添加视图
        self.dashboard = DashboardView()
        self.settings = SettingsView(self.config)
        
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.settings)
        
        # 默认显示仪表盘
        self.stack.setCurrentWidget(self.dashboard)
    
    def setup_menu(self):
        """设置菜单"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 视图菜单
        view_menu = menubar.addMenu("视图")
        
        dashboard_action = QAction("仪表盘", self)
        dashboard_action.triggered.connect(lambda: self.stack.setCurrentWidget(self.dashboard))
        view_menu.addAction(dashboard_action)
        
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(lambda: self.stack.setCurrentWidget(self.settings))
        view_menu.addAction(settings_action)
        
        # 主题菜单
        theme_menu = menubar.addMenu("主题")
        
        light_theme = QAction("浅色", self)
        light_theme.triggered.connect(lambda: self.change_theme(UITheme.LIGHT))
        theme_menu.addAction(light_theme)
        
        dark_theme = QAction("深色", self)
        dark_theme.triggered.connect(lambda: self.change_theme(UITheme.DARK))
        theme_menu.addAction(dark_theme)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_status_bar(self):
        """设置状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
    
    def setup_events(self):
        """设置事件处理"""
        event_bus.error_occurred.connect(self.handle_error)
        event_bus.theme_changed.connect(self.handle_theme_changed)
    
    def change_theme(self, theme: UITheme):
        """
        更改主题
        
        Args:
            theme: 主题类型
        """
        self.config.theme = theme
        event_bus.theme_changed.emit(theme)
    
    def handle_error(self, message: str):
        """
        处理错误
        
        Args:
            message: 错误信息
        """
        QMessageBox.critical(self, "错误", message)
    
    def handle_theme_changed(self, theme: str):
        """
        处理主题改变
        
        Args:
            theme: 主题名称
        """
        # TODO: 应用主题样式
        self.status_bar.showMessage(f"主题已更改为: {theme}")
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 FST",
            "FST (Full Self Trading)\n"
            "Version 1.0.0\n\n"
            "一个功能完整的量化交易平台"
        )
    
    def closeEvent(self, event):
        """
        关闭事件处理
        
        Args:
            event: 关闭事件
        """
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

class DesktopApp:
    """桌面应用"""
    
    def __init__(self, config: UIConfig):
        """
        初始化桌面应用
        
        Args:
            config: UI配置
        """
        self.config = config
        self.app = QApplication(sys.argv)
        self.window = None
    
    def start(self):
        """启动应用"""
        # 创建主窗口
        self.window = MainWindow(self.config)
        self.window.show()
        
        # 发送启动事件
        event_bus.startup.emit()
        
        # 运行应用
        return self.app.exec()
    
    def stop(self):
        """停止应用"""
        if self.window:
            self.window.close()