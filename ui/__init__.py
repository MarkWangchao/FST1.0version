#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 用户界面模块

提供多平台的用户界面实现，包括：
- 桌面应用 (PyQt/QML)
- Web界面 (Flask/Vue.js)
- 移动应用 (Flutter)

UI Module for FST Framework:
- Desktop Application (PyQt/QML)
- Web Interface (Flask/Vue.js)
- Mobile Application (Flutter)
"""

from enum import Enum, auto
from typing import Dict, Any, Optional, List

class UIType(str, Enum):
    """UI类型枚举"""
    DESKTOP = "desktop"  # 桌面应用
    WEB = "web"         # Web界面
    MOBILE = "mobile"   # 移动应用

class UITheme(str, Enum):
    """UI主题枚举"""
    LIGHT = "light"     # 浅色主题
    DARK = "dark"       # 深色主题
    AUTO = "auto"       # 自动（跟随系统）

class UIConfig:
    """UI配置类"""
    
    def __init__(self,
                ui_type: UIType = UIType.DESKTOP,
                theme: UITheme = UITheme.AUTO,
                language: str = "zh_CN",
                custom_settings: Optional[Dict[str, Any]] = None):
        """
        初始化UI配置
        
        Args:
            ui_type: UI类型
            theme: UI主题
            language: 语言代码
            custom_settings: 自定义设置
        """
        self.ui_type = ui_type
        self.theme = theme
        self.language = language
        self.custom_settings = custom_settings or {}
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "ui_type": self.ui_type,
            "theme": self.theme,
            "language": self.language,
            "custom_settings": self.custom_settings
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UIConfig':
        """从字典创建配置"""
        return cls(
            ui_type=UIType(data.get("ui_type", UIType.DESKTOP)),
            theme=UITheme(data.get("theme", UITheme.AUTO)),
            language=data.get("language", "zh_CN"),
            custom_settings=data.get("custom_settings", {})
        )

class UIManager:
    """UI管理器"""
    
    def __init__(self, config: Optional[UIConfig] = None):
        """
        初始化UI管理器
        
        Args:
            config: UI配置
        """
        self.config = config or UIConfig()
        self._ui_instance = None
    
    def initialize(self) -> bool:
        """
        初始化UI
        
        Returns:
            bool: 是否初始化成功
        """
        try:
            if self.config.ui_type == UIType.DESKTOP:
                from ui.desktop.main import DesktopApp
                self._ui_instance = DesktopApp(self.config)
            elif self.config.ui_type == UIType.WEB:
                from ui.web.server import WebServer
                self._ui_instance = WebServer(self.config)
            elif self.config.ui_type == UIType.MOBILE:
                from ui.mobile.app.main import MobileApp
                self._ui_instance = MobileApp(self.config)
            else:
                raise ValueError(f"不支持的UI类型: {self.config.ui_type}")
            
            return True
        except Exception as e:
            print(f"初始化UI失败: {str(e)}")
            return False
    
    def start(self) -> bool:
        """
        启动UI
        
        Returns:
            bool: 是否启动成功
        """
        if not self._ui_instance:
            return False
        
        try:
            self._ui_instance.start()
            return True
        except Exception as e:
            print(f"启动UI失败: {str(e)}")
            return False
    
    def stop(self) -> bool:
        """
        停止UI
        
        Returns:
            bool: 是否停止成功
        """
        if not self._ui_instance:
            return False
        
        try:
            self._ui_instance.stop()
            return True
        except Exception as e:
            print(f"停止UI失败: {str(e)}")
            return False
    
    def get_instance(self) -> Any:
        """获取UI实例"""
        return self._ui_instance

# 全局UI管理器实例
_ui_manager = None

def get_ui_manager(config: Optional[UIConfig] = None) -> UIManager:
    """
    获取UI管理器实例
    
    Args:
        config: UI配置
        
    Returns:
        UIManager: UI管理器实例
    """
    global _ui_manager
    
    if _ui_manager is None:
        _ui_manager = UIManager(config)
        
    return _ui_manager

# 导出
__all__ = [
    'UIType',
    'UITheme',
    'UIConfig',
    'UIManager',
    'get_ui_manager'
]