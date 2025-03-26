#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 交易路由模块

提供交易相关的API接口：
- 下单
- 撤单
- 查询订单
- 获取活跃订单
- 获取历史订单
"""

from flask import Blueprint, jsonify, request
from utils.logging_utils import get_logger
from services.authentication.auth_service import AuthService
from core.trading.order_manager import OrderManager
from core.risk.risk_manager import RiskManager

# 创建蓝图
trading_bp = Blueprint('trading', __name__)

# 日志器
logger = get_logger(__name__)

# 服务实例
auth_service = AuthService()
order_manager = OrderManager()
risk_manager = RiskManager()

@trading_bp.route('/order', methods=['POST'])
def create_order():
    """创建订单"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取订单数据
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
        
        # 验证必要参数
        required_fields = ['symbol', 'type', 'side', 'quantity']
        if data.get('type', '').upper() == 'LIMIT':
            required_fields.append('price')
        
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'message': f'缺少必要参数: {field}'
                }), 400
        
        # 风控检查
        risk_check_result = risk_manager.check_order(user_id, data)
        if not risk_check_result['passed']:
            return jsonify({
                'status': 'error',
                'message': f"风控检查未通过: {risk_check_result['message']}",
                'risk_details': risk_check_result.get('details', {})
            }), 403
        
        # 创建订单
        order_result = order_manager.create_order(
            user_id=user_id,
            symbol=data['symbol'],
            order_type=data['type'].upper(),
            side=data['side'].upper(),
            quantity=float(data['quantity']),
            price=float(data.get('price', 0)),
            time_in_force=data.get('timeInForce', 'GTC'),
            stop_price=float(data.get('stopPrice', 0)),
            iceberg_qty=float(data.get('icebergQty', 0)),
            client_order_id=data.get('clientOrderId')
        )
        
        if order_result['success']:
            return jsonify({
                'status': 'success',
                'data': order_result['order']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': order_result.get('message', '创建订单失败')
            }), 500
    except Exception as e:
        logger.error(f"创建订单失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'创建订单失败: {str(e)}'
        }), 500

@trading_bp.route('/order', methods=['DELETE'])
def cancel_order():
    """取消订单"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取参数
        order_id = request.args.get('orderId')
        client_order_id = request.args.get('clientOrderId')
        symbol = request.args.get('symbol')
        
        if not order_id and not client_order_id:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: orderId或clientOrderId'
            }), 400
        
        # 取消订单
        cancel_result = order_manager.cancel_order(
            user_id=user_id,
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id
        )
        
        if cancel_result['success']:
            return jsonify({
                'status': 'success',
                'data': cancel_result['order']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': cancel_result.get('message', '取消订单失败')
            }), 500
    except Exception as e:
        logger.error(f"取消订单失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'取消订单失败: {str(e)}'
        }), 500

@trading_bp.route('/order', methods=['GET'])
def get_order():
    """查询订单"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取参数
        order_id = request.args.get('orderId')
        client_order_id = request.args.get('clientOrderId')
        symbol = request.args.get('symbol')
        
        if not symbol or (not order_id and not client_order_id):
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol和(orderId或clientOrderId)'
            }), 400
        
        # 查询订单
        order_result = order_manager.get_order(
            user_id=user_id,
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id
        )
        
        if order_result['success']:
            return jsonify({
                'status': 'success',
                'data': order_result['order']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': order_result.get('message', '查询订单失败')
            }), 404 if order_result.get('not_found', False) else 500
    except Exception as e:
        logger.error(f"查询订单失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'查询订单失败: {str(e)}'
        }), 500

@trading_bp.route('/openOrders', methods=['GET'])
def get_open_orders():
    """获取当前活跃订单"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取参数
        symbol = request.args.get('symbol')
        
        # 获取活跃订单
        if symbol:
            orders = order_manager.get_open_orders(user_id, symbol)
        else:
            orders = order_manager.get_all_open_orders(user_id)
        
        return jsonify({
            'status': 'success',
            'data': orders
        })
    except Exception as e:
        logger.error(f"获取活跃订单失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取活跃订单失败: {str(e)}'
        }), 500

@trading_bp.route('/allOrders', methods=['GET'])
def get_all_orders():
    """获取所有订单"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取参数
        symbol = request.args.get('symbol')
        status = request.args.get('status')
        start_time = request.args.get('startTime')
        end_time = request.args.get('endTime')
        limit = request.args.get('limit', 500, type=int)
        
        if not symbol:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: symbol'
            }), 400
        
        # 获取所有订单
        orders = order_manager.get_all_orders(
            user_id=user_id,
            symbol=symbol,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        return jsonify({
            'status': 'success',
            'data': orders
        })
    except Exception as e:
        logger.error(f"获取所有订单失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取所有订单失败: {str(e)}'
        }), 500

@trading_bp.route('/cancelAllOrders', methods=['DELETE'])
def cancel_all_orders():
    """取消所有订单"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取参数
        symbol = request.args.get('symbol')
        
        # 取消所有订单
        result = order_manager.cancel_all_orders(user_id, symbol)
        
        return jsonify({
            'status': 'success',
            'data': {
                'total': result.get('total', 0),
                'success': result.get('success', 0),
                'failed': result.get('failed', 0),
                'errors': result.get('errors', [])
            }
        })
    except Exception as e:
        logger.error(f"取消所有订单失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'取消所有订单失败: {str(e)}'
        }), 500

@trading_bp.route('/riskCheck', methods=['POST'])
def check_risk():
    """风控检查"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取订单数据
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
        
        # 风控检查
        risk_check_result = risk_manager.check_order(user_id, data)
        
        return jsonify({
            'status': 'success',
            'data': {
                'passed': risk_check_result['passed'],
                'message': risk_check_result.get('message', ''),
                'details': risk_check_result.get('details', {})
            }
        })
    except Exception as e:
        logger.error(f"风控检查失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'风控检查失败: {str(e)}'
        }), 500

@trading_bp.route('/exchangeInformation', methods=['GET'])
def get_exchange_trading_information():
    """获取交易所交易规则"""
    try:
        # 获取参数
        exchange = request.args.get('exchange')
        symbol = request.args.get('symbol')
        
        if not exchange:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: exchange'
            }), 400
        
        # 获取交易规则
        trading_rules = order_manager.get_exchange_trading_rules(exchange, symbol)
        
        return jsonify({
            'status': 'success',
            'data': trading_rules
        })
    except Exception as e:
        logger.error(f"获取交易所交易规则失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取交易所交易规则失败: {str(e)}'
        }), 500

# 导出
__all__ = ['trading_bp']