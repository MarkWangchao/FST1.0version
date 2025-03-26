#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 账户路由模块

提供账户相关的API接口：
- 账户信息查询
- 资金管理
- 持仓管理
- 用户设置
- 认证
"""

from flask import Blueprint, jsonify, request, session
from utils.logging_utils import get_logger
from services.authentication.auth_service import AuthService
from core.trading.account_manager import AccountManager
from core.trading.position_manager import PositionManager

# 创建蓝图
account_bp = Blueprint('account', __name__)

# 日志器
logger = get_logger(__name__)

# 服务实例
auth_service = AuthService()
account_manager = AccountManager()
position_manager = PositionManager()

@account_bp.route('/info', methods=['GET'])
def get_account_info():
    """获取账户基本信息"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取账户信息
        account_info = account_manager.get_account_info(user_id)
        
        return jsonify({
            'status': 'success',
            'data': account_info
        })
    except Exception as e:
        logger.error(f"获取账户信息失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取账户信息失败: {str(e)}'
        }), 500

@account_bp.route('/balance', methods=['GET'])
def get_balance():
    """获取账户资金信息"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取账户资金信息
        balance_info = account_manager.get_balance(user_id)
        
        return jsonify({
            'status': 'success',
            'data': balance_info
        })
    except Exception as e:
        logger.error(f"获取账户资金信息失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取账户资金信息失败: {str(e)}'
        }), 500

@account_bp.route('/positions', methods=['GET'])
def get_positions():
    """获取持仓信息"""
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
        
        # 获取持仓信息
        if symbol:
            positions = position_manager.get_position(user_id, symbol)
        else:
            positions = position_manager.get_all_positions(user_id)
        
        return jsonify({
            'status': 'success',
            'data': positions
        })
    except Exception as e:
        logger.error(f"获取持仓信息失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取持仓信息失败: {str(e)}'
        }), 500

@account_bp.route('/trades', methods=['GET'])
def get_trades():
    """获取成交记录"""
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
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        limit = request.args.get('limit', 50, type=int)
        
        # 获取成交记录
        trades = account_manager.get_trades(
            user_id, 
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        return jsonify({
            'status': 'success',
            'data': trades
        })
    except Exception as e:
        logger.error(f"获取成交记录失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取成交记录失败: {str(e)}'
        }), 500

@account_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.get_json()
        
        # 验证参数
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
        
        # 登录认证
        username = data['username']
        password = data['password']
        result = auth_service.login(username, password)
        
        if result['success']:
            # 登录成功，保存会话
            session['user_id'] = result['user_id']
            
            return jsonify({
                'status': 'success',
                'data': {
                    'user_id': result['user_id'],
                    'username': username,
                    'token': result.get('token')
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result.get('message', '用户名或密码错误')
            }), 401
    except Exception as e:
        logger.error(f"登录失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'登录失败: {str(e)}'
        }), 500

@account_bp.route('/logout', methods=['POST'])
def logout():
    """用户注销"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 清除会话
        session.pop('user_id', None)
        
        # 注销认证
        auth_service.logout()
        
        return jsonify({
            'status': 'success',
            'message': '已成功注销'
        })
    except Exception as e:
        logger.error(f"注销失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'注销失败: {str(e)}'
        }), 500

@account_bp.route('/settings', methods=['GET'])
def get_settings():
    """获取用户设置"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取用户设置
        settings = account_manager.get_settings(user_id)
        
        return jsonify({
            'status': 'success',
            'data': settings
        })
    except Exception as e:
        logger.error(f"获取用户设置失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取用户设置失败: {str(e)}'
        }), 500

@account_bp.route('/settings', methods=['POST'])
def update_settings():
    """更新用户设置"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取设置数据
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
        
        # 更新用户设置
        success = account_manager.update_settings(user_id, data)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': '设置已更新'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '更新设置失败'
            }), 500
    except Exception as e:
        logger.error(f"更新用户设置失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'更新用户设置失败: {str(e)}'
        }), 500

@account_bp.route('/password', methods=['POST'])
def change_password():
    """修改密码"""
    try:
        # 检查认证状态
        if not auth_service.is_authenticated():
            return jsonify({
                'status': 'error',
                'message': '未认证'
            }), 401
        
        # 获取用户ID
        user_id = auth_service.get_current_user_id()
        
        # 获取密码数据
        data = request.get_json()
        if not data or 'old_password' not in data or 'new_password' not in data:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数'
            }), 400
        
        # 修改密码
        result = auth_service.change_password(
            user_id,
            data['old_password'],
            data['new_password']
        )
        
        if result['success']:
            return jsonify({
                'status': 'success',
                'message': '密码已修改'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result.get('message', '密码修改失败')
            }), 400
    except Exception as e:
        logger.error(f"修改密码失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'修改密码失败: {str(e)}'
        }), 500

# 导出
__all__ = ['account_bp']