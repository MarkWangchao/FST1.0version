#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强型基础配置

提供安全、高性能、可监控的配置管理系统
"""

import os
import yaml
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from collections import deque
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, ValidationError, confloat, conint
from cryptography.fernet import Fernet
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置模型定义
class MarketDataConfig(BaseModel):
    """市场数据配置验证模型"""
    provider: str
    update_interval: conint(gt=0)
    cache_size: conint(gt=0)
    retry_times: conint(ge=0)

class RiskControlConfig(BaseModel):
    """风险控制配置验证模型"""
    max_positions: conint(gt=0)
    max_loss_rate: confloat(gt=0, lt=1)
    daily_limit: conint(gt=0)

class OrderConfig(BaseModel):
    """订单配置验证模型"""
    timeout: conint(gt=0)
    max_retries: conint(ge=0)

class LoggingConfig(BaseModel):
    """日志配置验证模型"""
    level: str
    format: str
    file: Dict[str, Any]

class DatabaseConfig(BaseModel):
    """数据库配置验证模型"""
    type: str
    path: str
    backup_enabled: bool
    backup_interval: conint(gt=0)

class ConfigWatcher(FileSystemEventHandler):
    """配置文件变更监视器"""
    def __init__(self, config):
        self.config = config
        
    def on_modified(self, event):
        if event.src_path == self.config.config_file:
            self.config.load_config(event.src_path)
            self.config.on_config_updated()

class BaseConfig:
    """增强型基础配置类"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        "meta": {
            "schema_version": "1.2.0",
            "created_at": datetime.now().isoformat()
        },
        "app": {
            "name": "FST Trading System",
            "version": "1.0.0",
            "environment": "development",  # development, production, testing
            "debug": True
        },
        "trading": {
            "market_data": {
                "provider": "tqsdk",
                "update_interval": 1,  # 数据更新间隔(秒)
                "cache_size": 1000,    # 缓存大小
                "retry_times": 3       # 重试次数
            },
            "risk_control": {
                "max_positions": 5,     # 最大持仓数
                "max_loss_rate": 0.1,   # 最大亏损率
                "daily_limit": 100000   # 日交易限额
            },
            "order": {
                "timeout": 30,          # 订单超时时间(秒)
                "max_retries": 3        # 最大重试次数
            }
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "file": {
                "enabled": True,
                "path": "data/logs",
                "max_size": 10485760,    # 10MB
                "backup_count": 5
            }
        },
        "database": {
            "type": "sqlite",
            "path": "data/database",
            "backup_enabled": True,
            "backup_interval": 86400     # 24小时
        }
    }
    
    # 访问控制列表
    ACCESS_CONTROL = {
        'trading.risk_control': ['admin'],
        'database.password': ['sysadmin'],
        'app.debug': ['admin', 'developer']
    }
    
    def __init__(self, config_file: Optional[str] = None, env: Optional[str] = None):
        """
        初始化配置
        
        Args:
            config_file: 配置文件路径
            env: 环境名称，如果为None则从环境变量FST_ENV获取
        """
        self.config_data = self.DEFAULT_CONFIG.copy()
        self.config_file = config_file
        self.env = env or os.getenv("FST_ENV", "development")
        self.logger = logging.getLogger(__name__)
        self.history = deque(maxlen=50)  # 配置变更历史
        self.observer = None  # 配置文件监视器
        self._setup_encryption()
        self._load_environment_config()
        
        if config_file:
            if os.path.exists(config_file):
                self.load_config(config_file)
            else:
                self.logger.warning(f"配置文件不存在: {config_file}")
    
    def _setup_encryption(self):
        """初始化加密系统"""
        key_file = os.getenv("FST_KEY_FILE", "secret.key")
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
        self.cipher = Fernet(key)
    
    def _load_environment_config(self):
        """加载环境特定配置"""
        env_file = f"config/{self.env}.yaml"
        if os.path.exists(env_file):
            self.load_config(env_file)
            self.logger.info(f"已加载环境配置: {env_file}")
    
    def enable_hot_reload(self):
        """启用配置热重载"""
        if self.config_file:
            self.observer = Observer()
            self.observer.schedule(ConfigWatcher(self), 
                                 os.path.dirname(self.config_file))
            self.observer.start()
            self.logger.info("已启用配置热重载")
    
    def disable_hot_reload(self):
        """禁用配置热重载"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.logger.info("已禁用配置热重载")
    
    @lru_cache(maxsize=512)
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项(带缓存)
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        try:
            value = self.config_data
            for k in key.split('.'):
                value = value[k]
            
            # 如果是加密值，进行解密
            if isinstance(value, bytes):
                value = self._decrypt_value(value)
            
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any, user_role: str = 'user') -> None:
        """
        设置配置项(带权限检查)
        
        Args:
            key: 配置键
            value: 配置值
            user_role: 用户角色
        """
        # 权限检查
        for protected_key, allowed_roles in self.ACCESS_CONTROL.items():
            if key.startswith(protected_key) and user_role not in allowed_roles:
                raise PermissionError(f"无权修改配置项 {key}")
        
        # 记录历史
        old_value = self.get(key)
        self.history.append({
            'timestamp': datetime.now(),
            'key': key,
            'old_value': old_value,
            'new_value': value,
            'user_role': user_role
        })
        
        # 更新配置
        keys = key.split('.')
        current = self.config_data
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # 如果是敏感信息，进行加密
        if any(key.startswith(k) for k in ['database.password', 'accounts.password']):
            value = self._encrypt_value(str(value))
        
        current[keys[-1]] = value
        
        # 清除缓存
        self.get.cache_clear()
        
        # 触发配置更新事件
        self.on_config_updated()
    
    def _encrypt_value(self, value: str) -> bytes:
        """加密敏感信息"""
        return self.cipher.encrypt(value.encode())
    
    def _decrypt_value(self, token: bytes) -> str:
        """解密敏感信息"""
        return self.cipher.decrypt(token).decode()
    
    async def async_load_config(self, config_file: str) -> bool:
        """异步加载配置"""
        loop = asyncio.get_running_loop()
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                if config_file.endswith('.json'):
                    config = await loop.run_in_executor(None, json.load, f)
                else:
                    config = await loop.run_in_executor(None, yaml.safe_load, f)
            self._update_config_recursive(self.config_data, config)
            return True
        except Exception as e:
            self.logger.error(f"异步加载配置失败: {str(e)}")
            return False
    
    def load_config(self, config_file: str) -> bool:
        """同步加载配置"""
        try:
            ext = os.path.splitext(config_file)[1].lower()
            if ext in ['.yaml', '.yml']:
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
            elif ext in ['.json']:
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
            else:
                raise ValueError(f"不支持的配置文件类型: {ext}")
            
            # 检查配置版本并迁移
            if 'meta' in file_config:
                self._migrate_config(file_config['meta'].get('schema_version', '1.0.0'))
            
            # 递归更新配置
            self._update_config_recursive(self.config_data, file_config)
            self.logger.info(f"成功加载配置文件: {config_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"加载配置文件出错: {str(e)}")
            return False
    
    def _migrate_config(self, version: str):
        """配置版本迁移"""
        if version == '1.0.0':
            self._migrate_v1_to_v2()
        elif version == '1.1.0':
            self._migrate_v2_to_v3()
    
    def _migrate_v1_to_v2(self):
        """从v1迁移到v2"""
        # 示例迁移逻辑
        if 'meta' not in self.config_data:
            self.config_data['meta'] = {
                'schema_version': '1.1.0',
                'created_at': datetime.now().isoformat()
            }
    
    def _migrate_v2_to_v3(self):
        """从v2迁移到v3"""
        # 未来版本迁移逻辑
        pass
    
    def validate(self) -> List[Dict]:
        """使用Pydantic进行配置验证"""
        errors = []
        try:
            MarketDataConfig(**self.get('trading.market_data', {}))
        except ValidationError as e:
            errors.extend(e.errors())
            
        try:
            RiskControlConfig(**self.get('trading.risk_control', {}))
        except ValidationError as e:
            errors.extend(e.errors())
            
        try:
            OrderConfig(**self.get('trading.order', {}))
        except ValidationError as e:
            errors.extend(e.errors())
            
        try:
            LoggingConfig(**self.get('logging', {}))
        except ValidationError as e:
            errors.extend(e.errors())
            
        try:
            DatabaseConfig(**self.get('database', {}))
        except ValidationError as e:
            errors.extend(e.errors())
            
        return errors
    
    def generate_docs(self, output_file: str = "docs/CONFIG.md"):
        """生成配置文档"""
        doc = "# FST Trading System 配置说明\n\n"
        doc += f"当前版本: {self.get('meta.schema_version')}\n\n"
        
        for section, settings in self.DEFAULT_CONFIG.items():
            if section == 'meta':
                continue
                
            doc += f"## {section.upper()}\n\n"
            doc += "| 配置项 | 类型 | 默认值 | 权限 | 说明 |\n"
            doc += "| --- | --- | --- | --- | --- |\n"
            
            self._generate_section_docs(doc, section, settings)
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(doc)
        
        self.logger.info(f"配置文档已生成: {output_file}")
    
    def _generate_section_docs(self, doc: str, prefix: str, settings: Dict):
        """生成配置节文档"""
        for key, value in settings.items():
            full_key = f"{prefix}.{key}"
            required_role = next((roles for k, roles in self.ACCESS_CONTROL.items() 
                                if full_key.startswith(k)), ['user'])
            
            if isinstance(value, dict):
                doc += f"| {key} | dict | - | {', '.join(required_role)} | 配置组 |\n"
                self._generate_section_docs(doc, full_key, value)
            else:
                doc += (f"| {key} | {type(value).__name__} | "
                       f"`{str(value)}` | {', '.join(required_role)} | - |\n")
    
    def on_config_updated(self):
        """配置更新事件处理"""
        self.logger.info("配置已更新")
        # 这里可以添加配置更新后的回调逻辑
    
    def get_history(self) -> List[Dict]:
        """获取配置变更历史"""
        return list(self.history)
    
    def clear_cache(self):
        """清除配置缓存"""
        self.get.cache_clear()
        self.logger.info("配置缓存已清除")