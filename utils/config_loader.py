#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 配置加载工具

提供配置文件的加载、保存和管理功能，支持YAML和JSON格式。
"""

import os
import yaml
import json
from typing import Dict, Any, Optional, Union
import logging
from copy import deepcopy

# 获取logger
logger = logging.getLogger(__name__)

def load_config(config_path: str) -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        Dict: 配置字典
    
    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 不支持的配置文件格式
        yaml.YAMLError: YAML解析错误
        json.JSONDecodeError: JSON解析错误
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件 {config_path} 未找到")
    
    logger.info(f"正在加载配置文件: {config_path}")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                config = yaml.safe_load(f)
                logger.debug(f"成功加载YAML配置文件: {config_path}")
                return config
            elif config_path.endswith('.json'):
                config = json.load(f)
                logger.debug(f"成功加载JSON配置文件: {config_path}")
                return config
            else:
                raise ValueError("仅支持 .yaml 和 .json 配置文件格式")
    except yaml.YAMLError as e:
        logger.error(f"YAML解析错误: {str(e)}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"加载配置文件时发生错误: {str(e)}")
        raise

def generate_default_config() -> Dict[str, Any]:
    """
    生成默认配置
    
    Returns:
        Dict: 默认配置字典
    """
    logger.debug("生成默认配置")
    
    default_config = {
        "app": {
            "name": "FST Trading System",
            "version": "1.0.0",
            "environment": "development",
            "debug": True,
            "locale": "zh_CN",
            "timezone": "Asia/Shanghai"
        },
        "trading": {
            "market_data": {
                "provider": "tqsdk",
                "update_interval": 1,
                "cache_size": 1000,
                "retry_times": 3,
                "timeout": 10,
                "heartbeat": 30,
                "use_mock_data": False
            },
            "risk_control": {
                "max_positions": 5,
                "max_loss_rate": 0.1,
                "daily_limit": 50000
            },
            "order": {
                "timeout": 30,
                "max_retries": 3,
                "retry_interval": 2,
                "price_tolerance": 0.02
            }
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "file": {
                "enabled": True,
                "path": "logs/app.log",
                "max_size": 10485760,
                "backup_count": 5
            }
        },
        "database": {
            "type": "sqlite",
            "path": "data/database.db",
            "backup_enabled": True,
            "backup_interval": 86400
        },
        "security": {
            "encryption": {
                "algorithm": "AES-256"
            },
            "authentication": {
                "jwt_expiry": 3600
            }
        }
    }
    
    return default_config

def save_config(config: Dict[str, Any], config_path: str) -> None:
    """
    保存配置到文件
    
    Args:
        config: 配置字典
        config_path: 配置文件路径
    
    Raises:
        ValueError: 不支持的配置文件格式
        OSError: 文件保存错误
    """
    logger.info(f"正在保存配置到: {config_path}")
    
    # 确保目录存在
    os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                logger.debug(f"成功保存YAML配置文件: {config_path}")
            elif config_path.endswith('.json'):
                json.dump(config, f, indent=4, ensure_ascii=False)
                logger.debug(f"成功保存JSON配置文件: {config_path}")
            else:
                raise ValueError("仅支持 .yaml 和 .json 配置文件格式")
    except OSError as e:
        logger.error(f"保存配置文件时发生IO错误: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"保存配置文件时发生错误: {str(e)}")
        raise

def merge_configs(default_config: Dict[str, Any], user_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    合并默认配置和用户配置
    
    Args:
        default_config: 默认配置字典
        user_config: 用户配置字典
    
    Returns:
        Dict: 合并后的配置字典
    """
    logger.debug("合并配置")
    
    # 深拷贝默认配置以避免修改原始数据
    merged = deepcopy(default_config)
    
    # 递归合并配置
    def _merge(base, override):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                _merge(base[key], value)
            else:
                base[key] = value
    
    _merge(merged, user_config)
    return merged

def get_config_value(config: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    获取配置中的特定值
    
    Args:
        config: 配置字典
        path: 点分隔的路径，如 "app.debug"
        default: 如果值不存在，返回的默认值
    
    Returns:
        Any: 配置值或默认值
    """
    keys = path.split('.')
    current = config
    
    try:
        for key in keys:
            current = current[key]
        return current
    except (KeyError, TypeError):
        return default

def validate_config(config: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    验证配置是否符合指定的模式
    简化版实现，实际项目可能需要更复杂的验证逻辑或使用专门的库如jsonschema
    
    Args:
        config: 要验证的配置
        schema: 配置模式定义
    
    Returns:
        bool: 配置是否有效
    """
    # 简单实现，实际项目可能需要更复杂的验证
    # 这里只检查必要字段是否存在
    def _validate(cfg, sch):
        for key, value in sch.items():
            if key not in cfg:
                logger.error(f"配置缺少必要字段: {key}")
                return False
            if isinstance(value, dict) and isinstance(cfg[key], dict):
                if not _validate(cfg[key], value):
                    return False
        return True
    
    return _validate(config, schema)

def create_local_config(template_path: str, output_path: str) -> Dict[str, Any]:
    """
    基于模板创建本地配置文件
    
    Args:
        template_path: 模板配置文件路径
        output_path: 输出配置文件路径
    
    Returns:
        Dict: 创建的配置字典
    """
    if os.path.exists(output_path):
        logger.warning(f"本地配置文件已存在: {output_path}")
        return load_config(output_path)
    
    logger.info(f"从模板创建本地配置: {template_path} -> {output_path}")
    
    # 加载模板配置
    template_config = load_config(template_path)
    
    # 根据环境修改一些值
    local_config = deepcopy(template_config)
    
    # 示例：为本地开发环境修改一些设置
    if "app" in local_config:
        local_config["app"]["environment"] = "development"
        local_config["app"]["debug"] = True
    
    if "logging" in local_config:
        local_config["logging"]["level"] = "DEBUG"
    
    # 保存到本地配置文件
    save_config(local_config, output_path)
    logger.info(f"已创建本地配置文件: {output_path}")
    
    return local_config