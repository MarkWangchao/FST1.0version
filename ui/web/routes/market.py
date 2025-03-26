#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 市场数据路由模块

提供市场数据相关的API接口：
- 获取交易对列表
- 获取实时行情
- 获取K线数据
- 获取深度信息
- 获取成交记录
"""

from flask import Blueprint, jsonify, request
from utils.logging_utils import get_logger
from services.authentication.auth_service import AuthService
from core.market.data_provider import DataProvider
from core.market.market_data import MarketDataManager

# 创建蓝图
market_bp = Blueprint('market', __name__)

# 日志器
logger = get_logger(__name__)

# 服务实例
auth_service = AuthService()
data_provider = DataProvider()
market_data_manager = MarketDataManager()

@market_bp.route('/symbols', methods=['GET'])
def get_symbols():
    """获取交易对列表"""
    try:
        # 获取交易所参数（可选）
        exchange = request.args.get('exchange')
        
        # 获取交易对列表
        symbols = data_provider.get_symbols(exchange)
        
        return jsonify({
            'status': 'success',
            'data': symbols
        })
    except Exception as e:
        logger.error(f"获取交易对列表失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取交易对列表失败: {str(e)}'
        }), 500

@market_bp.route('/ticker', methods=['GET'])
def get_ticker():
    """获取市场行情"""
    try:
        # 获取Symbol参数
        symbol = request.args.get('symbol')
        
        if not symbol:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol'
            }), 400
        
        # 获取市场行情
        ticker = data_provider.get_ticker(symbol)
        
        return jsonify({
            'status': 'success',
            'data': ticker
        })
    except Exception as e:
        logger.error(f"获取市场行情失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取市场行情失败: {str(e)}'
        }), 500

@market_bp.route('/tickers', methods=['GET'])
def get_tickers():
    """获取多个交易对的市场行情"""
    try:
        # 获取交易所参数（可选）
        exchange = request.args.get('exchange')
        
        # 获取多个交易对的市场行情
        tickers = data_provider.get_tickers(exchange)
        
        return jsonify({
            'status': 'success',
            'data': tickers
        })
    except Exception as e:
        logger.error(f"获取多个交易对的市场行情失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取多个交易对的市场行情失败: {str(e)}'
        }), 500

@market_bp.route('/klines', methods=['GET'])
def get_klines():
    """获取K线数据"""
    try:
        # 获取参数
        symbol = request.args.get('symbol')
        interval = request.args.get('interval', '1m')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        limit = request.args.get('limit', 100, type=int)
        
        if not symbol:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol'
            }), 400
        
        # 获取K线数据
        klines = data_provider.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        return jsonify({
            'status': 'success',
            'data': klines
        })
    except Exception as e:
        logger.error(f"获取K线数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取K线数据失败: {str(e)}'
        }), 500

@market_bp.route('/depth', methods=['GET'])
def get_order_book():
    """获取市场深度"""
    try:
        # 获取参数
        symbol = request.args.get('symbol')
        limit = request.args.get('limit', 20, type=int)
        
        if not symbol:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol'
            }), 400
        
        # 获取市场深度
        depth = data_provider.get_order_book(symbol, limit)
        
        return jsonify({
            'status': 'success',
            'data': depth
        })
    except Exception as e:
        logger.error(f"获取市场深度失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取市场深度失败: {str(e)}'
        }), 500

@market_bp.route('/trades', methods=['GET'])
def get_recent_trades():
    """获取最近成交记录"""
    try:
        # 获取参数
        symbol = request.args.get('symbol')
        limit = request.args.get('limit', 50, type=int)
        
        if not symbol:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol'
            }), 400
        
        # 获取最近成交记录
        trades = data_provider.get_recent_trades(symbol, limit)
        
        return jsonify({
            'status': 'success',
            'data': trades
        })
    except Exception as e:
        logger.error(f"获取最近成交记录失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取最近成交记录失败: {str(e)}'
        }), 500

@market_bp.route('/price', methods=['GET'])
def get_price():
    """获取最新价格"""
    try:
        # 获取Symbol参数
        symbol = request.args.get('symbol')
        
        if not symbol:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol'
            }), 400
        
        # 获取最新价格
        price = data_provider.get_price(symbol)
        
        return jsonify({
            'status': 'success',
            'data': {
                'symbol': symbol,
                'price': price
            }
        })
    except Exception as e:
        logger.error(f"获取最新价格失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取最新价格失败: {str(e)}'
        }), 500

@market_bp.route('/prices', methods=['GET'])
def get_all_prices():
    """获取所有交易对价格"""
    try:
        # 获取交易所参数（可选）
        exchange = request.args.get('exchange')
        
        # 获取所有交易对价格
        prices = data_provider.get_all_prices(exchange)
        
        return jsonify({
            'status': 'success',
            'data': prices
        })
    except Exception as e:
        logger.error(f"获取所有交易对价格失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取所有交易对价格失败: {str(e)}'
        }), 500

@market_bp.route('/exchangeInfo', methods=['GET'])
def get_exchange_info():
    """获取交易所信息"""
    try:
        # 获取交易所参数
        exchange = request.args.get('exchange')
        
        if not exchange:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: exchange'
            }), 400
        
        # 获取交易所信息
        exchange_info = data_provider.get_exchange_info(exchange)
        
        return jsonify({
            'status': 'success',
            'data': exchange_info
        })
    except Exception as e:
        logger.error(f"获取交易所信息失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取交易所信息失败: {str(e)}'
        }), 500

@market_bp.route('/marketStatus', methods=['GET'])
def get_market_status():
    """获取市场状态"""
    try:
        # 获取市场状态信息
        market_status = market_data_manager.get_market_status()
        
        return jsonify({
            'status': 'success',
            'data': market_status
        })
    except Exception as e:
        logger.error(f"获取市场状态失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取市场状态失败: {str(e)}'
        }), 500

@market_bp.route('/historical', methods=['GET'])
def get_historical_data():
    """获取历史数据"""
    try:
        # 验证认证状态（可能需要认证才能获取大量历史数据）
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取参数
        symbol = request.args.get('symbol')
        data_type = request.args.get('type', 'kline')
        interval = request.args.get('interval', '1d')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        
        if not symbol or not start_time or not end_time:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol, start_time, end_time'
            }), 400
        
        # 获取历史数据
        historical_data = market_data_manager.get_historical_data(
            symbol=symbol,
            data_type=data_type,
            interval=interval,
            start_time=start_time,
            end_time=end_time
        )
        
        return jsonify({
            'status': 'success',
            'data': historical_data
        })
    except Exception as e:
        logger.error(f"获取历史数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取历史数据失败: {str(e)}'
        }), 500

# 导出
__all__ = ['market_bp']