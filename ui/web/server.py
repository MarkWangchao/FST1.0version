#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - Web服务器实现

提供Web服务器的核心功能：
- 路由注册
- 请求处理
- WebSocket支持
- 错误处理
- 会话管理
"""

from typing import Dict, Any, Optional
from flask import Flask, render_template, jsonify, request, session
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from ui.web import WebConfig, WebUIEvents
from utils.logging_utils import get_logger

logger = get_logger(__name__)

def create_app(config: Optional[WebConfig] = None) -> Flask:
    """
    创建Flask应用实例
    
    Args:
        config: Web配置
        
    Returns:
        Flask: Flask应用实例
    """
    app = Flask(__name__)
    
    # 配置应用
    app.config.update(
        SECRET_KEY=config.secret_key if config else 'fst-secret',
        DEBUG=config.debug if config else False
    )
    
    # 启用CORS
    CORS(app, resources={
        r"/api/*": {"origins": config.cors_origins if config else "*"}
    })
    
    # 注册路由
    register_routes(app)
    
    # 注册错误处理
    register_error_handlers(app)
    
    return app

def create_socketio(app: Flask, config: Optional[WebConfig] = None) -> SocketIO:
    """
    创建SocketIO实例
    
    Args:
        app: Flask应用实例
        config: Web配置
        
    Returns:
        SocketIO: SocketIO实例
    """
    socketio = SocketIO(
        app,
        cors_allowed_origins=config.cors_origins if config else "*"
    )
    
    # 注册WebSocket事件处理
    register_socket_events(socketio)
    
    return socketio

def register_routes(app: Flask):
    """注册路由处理器"""
    # 主页
    @app.route('/')
    def index():
        return render_template('dashboard.html')
    
    # 仪表盘
    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')
    
    # 交易页面
    @app.route('/trading')
    def trading():
        return render_template('trading.html')
    
    # 市场页面
    @app.route('/market')
    def market():
        return render_template('market.html')
    
    # 报告页面
    @app.route('/reports')
    def reports():
        return render_template('reports.html')
    
    # 设置页面
    @app.route('/settings')
    def settings():
        return render_template('settings.html')
    
    # API路由
    register_api_routes(app)

def register_api_routes(app: Flask):
    """注册API路由"""
    # 用户信息API
    @app.route('/api/user/info')
    def get_user_info():
        # TODO: 实现用户信息获取
        return jsonify({
            'id': '1',
            'username': 'demo',
            'email': 'demo@example.com'
        })
    
    # 账户信息API
    @app.route('/api/account/info')
    def get_account_info():
        # TODO: 实现账户信息获取
        return jsonify({
            'balance': 100000.0,
            'positions': [],
            'orders': [],
            'trades': []
        })
    
    # 市场数据API
    @app.route('/api/market/symbols')
    def get_market_symbols():
        # TODO: 实现市场符号列表获取
        return jsonify([
            'BTC/USDT',
            'ETH/USDT',
            'BNB/USDT'
        ])

def register_socket_events(socketio: SocketIO):
    """注册WebSocket事件处理器"""
    @socketio.on('connect')
    def handle_connect():
        logger.info(f'Client connected: {request.sid}')
        emit(WebUIEvents.CLIENT_CONNECTED, {'sid': request.sid})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info(f'Client disconnected: {request.sid}')
        emit(WebUIEvents.CLIENT_DISCONNECTED, {'sid': request.sid})
    
    @socketio.on('subscribe')
    def handle_subscribe(data):
        logger.info(f'Subscribe request: {data}')
        # TODO: 实现订阅处理
        emit('subscribed', {'status': 'success'})

def register_error_handlers(app: Flask):
    """注册错误处理器"""
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Not found'}), 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f'Server error: {error}')
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500

# 导出
__all__ = [
    'create_app',
    'create_socketio'
]