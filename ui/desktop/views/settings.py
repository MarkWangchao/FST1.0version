#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 设置视图

提供系统配置界面，包括：
- 基本设置
- 交易设置
- 风控设置
- 通知设置
- 数据源设置

Settings View:
- Basic settings
- Trading settings
- Risk control settings
- Notification settings
- Data source settings
"""

from typing import Dict, Any, Optional, List
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QTabWidget, QFormLayout, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui import UIConfig, UITheme
from ui.desktop.views import BaseView
from ui.desktop import event_bus

class SettingsTab(QWidget):
    """设置标签页基类"""
    
    # 设置更改信号
    settings_changed = pyqtSignal(dict)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        self.layout.addLayout(self.form_layout)
        
        # 添加保存按钮
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_settings)
        self.layout.addWidget(self.save_button)
        
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        pass
    
    def load_settings(self, settings: Dict[str, Any]):
        """加载设置"""
        pass
    
    def save_settings(self):
        """保存设置"""
        pass

class BasicSettingsTab(SettingsTab):
    """基本设置标签页"""
    
    def setup_ui(self):
        """设置UI"""
        # 主题设置
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["浅色", "深色", "自动"])
        self.form_layout.addRow("主题:", self.theme_combo)
        
        # 语言设置
        self.language_combo = QComboBox()
        self.language_combo.addItems(["简体中文", "English"])
        self.form_layout.addRow("语言:", self.language_combo)
        
        # 自动刷新间隔
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 60)
        self.refresh_spin.setValue(5)
        self.refresh_spin.setSuffix(" 秒")
        self.form_layout.addRow("刷新间隔:", self.refresh_spin)
        
        # 日志设置组
        log_group = QGroupBox("日志设置")
        log_layout = QFormLayout()
        
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        log_layout.addRow("日志级别:", self.log_level_combo)
        
        self.log_file_edit = QLineEdit()
        self.log_file_button = QPushButton("浏览...")
        log_file_layout = QHBoxLayout()
        log_file_layout.addWidget(self.log_file_edit)
        log_file_layout.addWidget(self.log_file_button)
        log_layout.addRow("日志文件:", log_file_layout)
        
        log_group.setLayout(log_layout)
        self.layout.addWidget(log_group)
    
    def load_settings(self, settings: Dict[str, Any]):
        """加载设置"""
        # 设置主题
        theme_map = {
            UITheme.LIGHT: 0,
            UITheme.DARK: 1,
            UITheme.AUTO: 2
        }
        self.theme_combo.setCurrentIndex(
            theme_map.get(settings.get('theme'), 2)
        )
        
        # 设置语言
        self.language_combo.setCurrentIndex(
            0 if settings.get('language') == 'zh_CN' else 1
        )
        
        # 设置刷新间隔
        self.refresh_spin.setValue(
            settings.get('refresh_interval', 5)
        )
        
        # 设置日志选项
        self.log_level_combo.setCurrentText(
            settings.get('log_level', 'INFO')
        )
        self.log_file_edit.setText(
            settings.get('log_file', '')
        )
    
    def save_settings(self):
        """保存设置"""
        theme_map = {
            0: UITheme.LIGHT,
            1: UITheme.DARK,
            2: UITheme.AUTO
        }
        
        settings = {
            'theme': theme_map[self.theme_combo.currentIndex()],
            'language': 'zh_CN' if self.language_combo.currentIndex() == 0 else 'en_US',
            'refresh_interval': self.refresh_spin.value(),
            'log_level': self.log_level_combo.currentText(),
            'log_file': self.log_file_edit.text()
        }
        
        self.settings_changed.emit(settings)
        QMessageBox.information(self, "成功", "设置已保存")

class TradingSettingsTab(SettingsTab):
    """交易设置标签页"""
    
    def setup_ui(self):
        """设置UI"""
        # 交易所设置
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(["Binance", "OKX", "Huobi"])
        self.form_layout.addRow("交易所:", self.exchange_combo)
        
        # API设置组
        api_group = QGroupBox("API设置")
        api_layout = QFormLayout()
        
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("API Key:", self.api_key_edit)
        
        self.api_secret_edit = QLineEdit()
        self.api_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("API Secret:", self.api_secret_edit)
        
        api_group.setLayout(api_layout)
        self.layout.addWidget(api_group)
        
        # 交易设置组
        trade_group = QGroupBox("交易设置")
        trade_layout = QFormLayout()
        
        self.leverage_spin = QDoubleSpinBox()
        self.leverage_spin.setRange(1, 100)
        self.leverage_spin.setValue(1)
        trade_layout.addRow("杠杆倍数:", self.leverage_spin)
        
        self.margin_type_combo = QComboBox()
        self.margin_type_combo.addItems(["全仓", "逐仓"])
        trade_layout.addRow("保证金模式:", self.margin_type_combo)
        
        trade_group.setLayout(trade_layout)
        self.layout.addWidget(trade_group)
    
    def load_settings(self, settings: Dict[str, Any]):
        """加载设置"""
        exchange_map = {
            'binance': 0,
            'okx': 1,
            'huobi': 2
        }
        self.exchange_combo.setCurrentIndex(
            exchange_map.get(settings.get('exchange', 'binance'), 0)
        )
        
        self.api_key_edit.setText(settings.get('api_key', ''))
        self.api_secret_edit.setText(settings.get('api_secret', ''))
        
        self.leverage_spin.setValue(settings.get('leverage', 1))
        self.margin_type_combo.setCurrentIndex(
            1 if settings.get('margin_type') == 'isolated' else 0
        )
    
    def save_settings(self):
        """保存设置"""
        exchange_map = {
            0: 'binance',
            1: 'okx',
            2: 'huobi'
        }
        
        settings = {
            'exchange': exchange_map[self.exchange_combo.currentIndex()],
            'api_key': self.api_key_edit.text(),
            'api_secret': self.api_secret_edit.text(),
            'leverage': self.leverage_spin.value(),
            'margin_type': 'isolated' if self.margin_type_combo.currentIndex() == 1 else 'cross'
        }
        
        self.settings_changed.emit(settings)
        QMessageBox.information(self, "成功", "设置已保存")

class RiskControlSettingsTab(SettingsTab):
    """风控设置标签页"""
    
    def setup_ui(self):
        """设置UI"""
        # 风控开关
        self.risk_control_check = QCheckBox("启用风控")
        self.layout.addWidget(self.risk_control_check)
        
        # 风控参数组
        risk_group = QGroupBox("风控参数")
        risk_layout = QFormLayout()
        
        self.max_position_spin = QDoubleSpinBox()
        self.max_position_spin.setRange(0, 1000000)
        self.max_position_spin.setValue(100000)
        risk_layout.addRow("最大持仓:", self.max_position_spin)
        
        self.max_loss_spin = QDoubleSpinBox()
        self.max_loss_spin.setRange(0, 100)
        self.max_loss_spin.setValue(10)
        self.max_loss_spin.setSuffix(" %")
        risk_layout.addRow("最大回撤:", self.max_loss_spin)
        
        self.stop_loss_spin = QDoubleSpinBox()
        self.stop_loss_spin.setRange(0, 100)
        self.stop_loss_spin.setValue(5)
        self.stop_loss_spin.setSuffix(" %")
        risk_layout.addRow("止损比例:", self.stop_loss_spin)
        
        risk_group.setLayout(risk_layout)
        self.layout.addWidget(risk_group)
    
    def load_settings(self, settings: Dict[str, Any]):
        """加载设置"""
        self.risk_control_check.setChecked(
            settings.get('risk_control_enabled', True)
        )
        self.max_position_spin.setValue(
            settings.get('max_position', 100000)
        )
        self.max_loss_spin.setValue(
            settings.get('max_loss_percentage', 10)
        )
        self.stop_loss_spin.setValue(
            settings.get('stop_loss_percentage', 5)
        )
    
    def save_settings(self):
        """保存设置"""
        settings = {
            'risk_control_enabled': self.risk_control_check.isChecked(),
            'max_position': self.max_position_spin.value(),
            'max_loss_percentage': self.max_loss_spin.value(),
            'stop_loss_percentage': self.stop_loss_spin.value()
        }
        
        self.settings_changed.emit(settings)
        QMessageBox.information(self, "成功", "设置已保存")

class SettingsView(BaseView):
    """设置视图"""
    
    def __init__(self, config: UIConfig, parent: Optional[QWidget] = None):
        self.config = config
        super().__init__(parent)
    
    def setup_ui(self):
        """设置UI"""
        # 创建标签页
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)
        
        # 添加设置标签页
        self.basic_settings = BasicSettingsTab()
        self.trading_settings = TradingSettingsTab()
        self.risk_settings = RiskControlSettingsTab()
        
        self.tab_widget.addTab(self.basic_settings, "基本设置")
        self.tab_widget.addTab(self.trading_settings, "交易设置")
        self.tab_widget.addTab(self.risk_settings, "风控设置")
        
        # 加载当前设置
        self.load_current_settings()
    
    def setup_events(self):
        """设置事件处理"""
        self.basic_settings.settings_changed.connect(self.handle_basic_settings_changed)
        self.trading_settings.settings_changed.connect(self.handle_trading_settings_changed)
        self.risk_settings.settings_changed.connect(self.handle_risk_settings_changed)
    
    def load_current_settings(self):
        """加载当前设置"""
        # 加载基本设置
        basic_settings = {
            'theme': self.config.theme,
            'language': self.config.language,
            'refresh_interval': self.config.custom_settings.get('refresh_interval', 5),
            'log_level': self.config.custom_settings.get('log_level', 'INFO'),
            'log_file': self.config.custom_settings.get('log_file', '')
        }
        self.basic_settings.load_settings(basic_settings)
        
        # 加载交易设置
        trading_settings = self.config.custom_settings.get('trading', {})
        self.trading_settings.load_settings(trading_settings)
        
        # 加载风控设置
        risk_settings = self.config.custom_settings.get('risk_control', {})
        self.risk_settings.load_settings(risk_settings)
    
    def handle_basic_settings_changed(self, settings: Dict[str, Any]):
        """处理基本设置变更"""
        self.config.theme = settings['theme']
        self.config.language = settings['language']
        self.config.custom_settings.update({
            'refresh_interval': settings['refresh_interval'],
            'log_level': settings['log_level'],
            'log_file': settings['log_file']
        })
        
        # 发送主题改变事件
        event_bus.theme_changed.emit(settings['theme'])
        
        # 发送语言改变事件
        event_bus.language_changed.emit(settings['language'])
    
    def handle_trading_settings_changed(self, settings: Dict[str, Any]):
        """处理交易设置变更"""
        self.config.custom_settings['trading'] = settings
    
    def handle_risk_settings_changed(self, settings: Dict[str, Any]):
        """处理风控设置变更"""
        self.config.custom_settings['risk_control'] = settings