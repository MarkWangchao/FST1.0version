#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - Web路由模块

提供Web应用的路由处理：
- API路由
- 页面路由
- WebSocket事件
"""

from flask import Blueprint, Flask

def init_routes(app: Flask):
    """
    初始化所有路由
    
    Args:
        app: Flask应用实例
    """
    # 注册API蓝图
    from ui.web.routes.account import account_bp
    from ui.web.routes.market import market_bp
    from ui.web.routes.trading import trading_bp
    from ui.web.routes.reports import reports_bp
    
    app.register_blueprint(account_bp, url_prefix='/api/account')
    app.register_blueprint(market_bp, url_prefix='/api/market')
    app.register_blueprint(trading_bp, url_prefix='/api/trading')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')

# 导出
__all__ = ['init_routes']