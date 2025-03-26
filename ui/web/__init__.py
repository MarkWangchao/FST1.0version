#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - Web界面模块

基于Flask和Vue.js实现的Web界面，提供：
- RESTful API接口
- WebSocket实时数据
- 响应式布局
- 图表展示
- 用户认证

Web Interface Module:
- RESTful API endpoints
- WebSocket real-time data
- Responsive layout
- Chart visualization
- User authentication
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from flask import Flask
from flask_socketio import SocketIO

class WebUIEvents:
    """Web UI事件类型"""
    
    # 系统事件
    STARTUP = "startup"              # 启动事件
    SHUTDOWN = "shutdown"            # 关闭事件
    THEME_CHANGED = "theme_changed"  # 主题改变事件
    
    # 交易事件
    ORDER_CREATED = "order_created"    # 订单创建事件
    ORDER_UPDATED = "order_updated"    # 订单更新事件
    TRADE_EXECUTED = "trade_executed"  # 交易执行事件
    
    # 数据事件
    DATA_UPDATED = "data_updated"      # 数据更新事件
    ERROR_OCCURRED = "error_occurred"  # 错误事件
    
    # WebSocket事件
    CLIENT_CONNECTED = "client_connected"        # 客户端连接事件
    CLIENT_DISCONNECTED = "client_disconnected"  # 客户端断开事件
    MESSAGE_RECEIVED = "message_received"        # 消息接收事件

@dataclass
class WebConfig:
    """Web配置"""
    host: str = "localhost"           # 主机地址
    port: int = 5000                  # 端口号
    debug: bool = False               # 调试模式
    secret_key: str = "fst-secret"    # 密钥
    static_folder: str = "static"     # 静态文件目录
    template_folder: str = "templates"  # 模板目录
    enable_websocket: bool = True     # 启用WebSocket
    cors_origins: List[str] = None    # CORS来源

class WebServer:
    """Web服务器"""
    
    def __init__(self, config: Optional[WebConfig] = None):
        """
        初始化Web服务器
        
        Args:
            config: Web配置
        """
        self.config = config or WebConfig()
        
        # 创建Flask应用
        self.app = Flask(
            __name__,
            static_folder=self.config.static_folder,
            template_folder=self.config.template_folder
        )
        self.app.config['SECRET_KEY'] = self.config.secret_key
        
        # 创建SocketIO实例
        if self.config.enable_websocket:
            self.socketio = SocketIO(
                self.app,
                cors_allowed_origins=self.config.cors_origins
            )
        else:
            self.socketio = None
        
        # 注册路由和事件处理
        self._register_routes()
        self._register_events()
    
    def _register_routes(self):
        """注册路由"""
        from ui.web.server import register_routes
        register_routes(self.app)
    
    def _register_events(self):
        """注册事件处理"""
        if not self.socketio:
            return
            
        @self.socketio.on('connect')
        def handle_connect():
            self.emit_event(WebUIEvents.CLIENT_CONNECTED)
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            self.emit_event(WebUIEvents.CLIENT_DISCONNECTED)
        
        @self.socketio.on('message')
        def handle_message(message):
            self.emit_event(WebUIEvents.MESSAGE_RECEIVED, message)
    
    def emit_event(self, event_type: str, data: Any = None):
        """
        发送事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self.socketio:
            self.socketio.emit(event_type, data)
    
    def start(self):
        """启动服务器"""
        if self.socketio:
            self.socketio.run(
                self.app,
                host=self.config.host,
                port=self.config.port,
                debug=self.config.debug
            )
        else:
            self.app.run(
                host=self.config.host,
                port=self.config.port,
                debug=self.config.debug
            )
    
    def stop(self):
        """停止服务器"""
        if self.socketio:
            self.socketio.stop()

# 全局Web服务器实例
_web_server = None

def get_web_server(config: Optional[WebConfig] = None) -> WebServer:
    """
    获取Web服务器实例
    
    Args:
        config: Web配置
        
    Returns:
        WebServer: Web服务器实例
    """
    global _web_server
    
    if _web_server is None:
        _web_server = WebServer(config)
        
    return _web_server

# 导出
__all__ = [
    'WebUIEvents',
    'WebConfig',
    'WebServer',
    'get_web_server'
]