#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 仪表盘视图

提供交易系统的主要监控界面，包括：
- 账户信息
- 持仓信息
- 订单状态
- 交易记录
- 市场行情
- 性能指标

Dashboard View:
- Account information
- Position information
- Order status
- Trade history
- Market data
- Performance metrics
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPalette

from ui.desktop.views import DataView, ChartView
from ui.desktop import event_bus

class AccountWidget(QFrame):
    """账户信息部件"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        
        self.layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("账户信息")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.layout.addWidget(title)
        
        # 信息网格
        info_layout = QHBoxLayout()
        
        # 账户余额
        balance_layout = QVBoxLayout()
        balance_label = QLabel("账户余额")
        self.balance_value = QLabel("0.00")
        self.balance_value.setStyleSheet("font-size: 18px; color: #2ecc71;")
        balance_layout.addWidget(balance_label)
        balance_layout.addWidget(self.balance_value)
        info_layout.addLayout(balance_layout)
        
        # 持仓市值
        position_layout = QVBoxLayout()
        position_label = QLabel("持仓市值")
        self.position_value = QLabel("0.00")
        self.position_value.setStyleSheet("font-size: 18px; color: #3498db;")
        position_layout.addWidget(position_label)
        position_layout.addWidget(self.position_value)
        info_layout.addLayout(position_layout)
        
        # 当日盈亏
        pnl_layout = QVBoxLayout()
        pnl_label = QLabel("当日盈亏")
        self.pnl_value = QLabel("0.00")
        self.pnl_value.setStyleSheet("font-size: 18px; color: #e74c3c;")
        pnl_layout.addWidget(pnl_label)
        pnl_layout.addWidget(self.pnl_value)
        info_layout.addLayout(pnl_layout)
        
        self.layout.addLayout(info_layout)
    
    def update_info(self, data: Dict[str, Any]):
        """更新账户信息"""
        self.balance_value.setText(f"{data.get('balance', 0.0):.2f}")
        self.position_value.setText(f"{data.get('position_value', 0.0):.2f}")
        
        pnl = data.get('daily_pnl', 0.0)
        self.pnl_value.setText(f"{pnl:.2f}")
        self.pnl_value.setStyleSheet(
            f"font-size: 18px; color: {'#2ecc71' if pnl >= 0 else '#e74c3c'};"
        )

class PositionTable(QTableWidget):
    """持仓信息表格"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # 设置列
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels([
            "代码", "名称", "持仓量", "持仓成本",
            "当前价格", "持仓盈亏"
        ])
        
        # 设置表格属性
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # 设置列宽
        header = self.horizontalHeader()
        for i in range(self.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
    
    def update_positions(self, positions: List[Dict[str, Any]]):
        """更新持仓信息"""
        self.setRowCount(len(positions))
        
        for row, pos in enumerate(positions):
            # 设置单元格
            self.setItem(row, 0, QTableWidgetItem(pos['symbol']))
            self.setItem(row, 1, QTableWidgetItem(pos['name']))
            self.setItem(row, 2, QTableWidgetItem(str(pos['volume'])))
            self.setItem(row, 3, QTableWidgetItem(f"{pos['cost']:.3f}"))
            self.setItem(row, 4, QTableWidgetItem(f"{pos['price']:.3f}"))
            
            # 设置盈亏颜色
            pnl = pos.get('pnl', 0.0)
            pnl_item = QTableWidgetItem(f"{pnl:.2f}")
            pnl_item.setForeground(
                QColor("#2ecc71") if pnl >= 0 else QColor("#e74c3c")
            )
            self.setItem(row, 5, pnl_item)

class MarketDataChart(ChartView):
    """市场数据图表"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # TODO: 实现图表功能
        self.placeholder = QLabel("市场数据图表")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.placeholder)

class DashboardView(DataView):
    """仪表盘视图"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # 创建定时器用于自动刷新
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(5000)  # 5秒刷新一次
    
    def setup_ui(self):
        """设置UI"""
        # 账户信息
        self.account_widget = AccountWidget()
        self.layout.addWidget(self.account_widget)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)
        
        # 持仓信息标签页
        self.position_table = PositionTable()
        self.tab_widget.addTab(self.position_table, "持仓信息")
        
        # 市场行情标签页
        self.market_chart = MarketDataChart()
        self.tab_widget.addTab(self.market_chart, "市场行情")
    
    def setup_events(self):
        """设置事件处理"""
        event_bus.data_updated.connect(self.handle_data_update)
        event_bus.trade_executed.connect(self.handle_trade)
    
    def handle_data_update(self, data_type: str, data: Dict[str, Any]):
        """处理数据更新"""
        if data_type == "account":
            self.account_widget.update_info(data)
        elif data_type == "positions":
            self.position_table.update_positions(data.get("positions", []))
    
    def handle_trade(self, trade_data: Dict[str, Any]):
        """处理成交信息"""
        # 刷新数据
        self.refresh()
    
    def cleanup(self):
        """清理资源"""
        self.refresh_timer.stop()
        super().cleanup()