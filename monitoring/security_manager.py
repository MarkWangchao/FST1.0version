#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 安全管理器

提供安全功能：
- 密钥管理
- 数据加密
- 敏感信息保护
- 审计日志
"""

import os
import logging
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime
import hvac
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from base64 import b64encode, b64decode
from prometheus_client import Counter, Gauge

# 安全指标
SECURITY_OPS = Counter('security_operations_total', '安全操作数', ['operation'])
KEY_ROTATIONS = Counter('key_rotations_total', '密钥轮换次数')
AUDIT_EVENTS = Counter('audit_events_total', '审计事件数', ['event_type'])

class SecurityManager:
    """安全管理器"""
    
    def __init__(self, config: Dict):
        """
        初始化安全管理器
        
        Args:
            config: 安全配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化Vault客户端
        self.vault_client = hvac.Client(
            url=config['vault']['address'],
            token=config['vault']['token']
        )
        
        # 加密配置
        self.key_rotation_interval = config['encryption'].get('key_rotation', 86400)
        self.current_key = None
        self.key_created_at = None
        
        # 审计配置
        self.audit_enabled = config['audit'].get('enabled', True)
        self.audit_retention = config['audit'].get('retention', 90)
        
    async def start(self):
        """启动安全管理器"""
        self.logger.info("安全管理器已启动")
        await self._initialize_encryption()
        asyncio.create_task(self._run_key_rotation())
        
    async def _initialize_encryption(self):
        """初始化加密系统"""
        try:
            # 从Vault获取或生成主密钥
            if not self.vault_client.read('secret/fst/master_key'):
                master_key = Fernet.generate_key()
                self.vault_client.write('secret/fst/master_key', data={'key': master_key.decode()})
            
            master_key = self.vault_client.read('secret/fst/master_key')['data']['key'].encode()
            
            # 生成当前会话密钥
            self.current_key = self._derive_key(master_key)
            self.key_created_at = datetime.now()
            
            self.logger.info("加密系统已初始化")
            
        except Exception as e:
            self.logger.error(f"初始化加密系统失败: {str(e)}")
            raise
            
    async def _run_key_rotation(self):
        """运行密钥轮换任务"""
        while True:
            try:
                if (datetime.now() - self.key_created_at).total_seconds() >= self.key_rotation_interval:
                    await self._rotate_key()
                await asyncio.sleep(60)
            except Exception as e:
                self.logger.error(f"密钥轮换失败: {str(e)}")
                await asyncio.sleep(60)
                
    async def _rotate_key(self):
        """轮换加密密钥"""
        try:
            # 从Vault获取主密钥
            master_key = self.vault_client.read('secret/fst/master_key')['data']['key'].encode()
            
            # 生成新的会话密钥
            new_key = self._derive_key(master_key)
            
            # 更新密钥
            self.current_key = new_key
            self.key_created_at = datetime.now()
            
            KEY_ROTATIONS.inc()
            self.logger.info("密钥已轮换")
            
            # 记录审计事件
            await self.log_audit_event('key_rotation', {
                'timestamp': self.key_created_at.isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"轮换密钥失败: {str(e)}")
            raise
            
    def _derive_key(self, master_key: bytes) -> bytes:
        """从主密钥派生会话密钥"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=os.urandom(16),
            iterations=100000,
        )
        return b64encode(kdf.derive(master_key))
        
    async def encrypt_data(self, data: str) -> str:
        """加密数据"""
        try:
            SECURITY_OPS.labels(operation='encrypt').inc()
            
            if not self.current_key:
                await self._initialize_encryption()
                
            f = Fernet(self.current_key)
            encrypted = f.encrypt(data.encode())
            return b64encode(encrypted).decode()
            
        except Exception as e:
            self.logger.error(f"加密数据失败: {str(e)}")
            raise
            
    async def decrypt_data(self, encrypted_data: str) -> str:
        """解密数据"""
        try:
            SECURITY_OPS.labels(operation='decrypt').inc()
            
            if not self.current_key:
                await self._initialize_encryption()
                
            f = Fernet(self.current_key)
            decrypted = f.decrypt(b64decode(encrypted_data))
            return decrypted.decode()
            
        except Exception as e:
            self.logger.error(f"解密数据失败: {str(e)}")
            raise
            
    async def store_secret(self, path: str, data: Dict):
        """存储敏感信息"""
        try:
            SECURITY_OPS.labels(operation='store_secret').inc()
            
            # 加密数据
            encrypted_data = {}
            for key, value in data.items():
                if isinstance(value, str):
                    encrypted_data[key] = await self.encrypt_data(value)
                else:
                    encrypted_data[key] = value
                    
            # 存储到Vault
            self.vault_client.write(f'secret/fst/{path}', data=encrypted_data)
            
            # 记录审计事件
            await self.log_audit_event('store_secret', {
                'path': path,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"存储敏感信息失败: {str(e)}")
            raise
            
    async def get_secret(self, path: str) -> Dict:
        """获取敏感信息"""
        try:
            SECURITY_OPS.labels(operation='get_secret').inc()
            
            # 从Vault读取
            secret = self.vault_client.read(f'secret/fst/{path}')
            if not secret:
                return None
                
            # 解密数据
            decrypted_data = {}
            for key, value in secret['data'].items():
                if isinstance(value, str):
                    try:
                        decrypted_data[key] = await self.decrypt_data(value)
                    except:
                        decrypted_data[key] = value
                else:
                    decrypted_data[key] = value
                    
            return decrypted_data
            
        except Exception as e:
            self.logger.error(f"获取敏感信息失败: {str(e)}")
            raise
            
    async def log_audit_event(self, event_type: str, details: Dict):
        """记录审计事件"""
        if not self.audit_enabled:
            return
            
        try:
            AUDIT_EVENTS.labels(event_type=event_type).inc()
            
            audit_data = {
                'timestamp': datetime.now().isoformat(),
                'event_type': event_type,
                'details': details
            }
            
            # 存储审计日志
            self.vault_client.write(
                f'secret/fst/audit/{event_type}/{audit_data["timestamp"]}',
                data=audit_data
            )
            
        except Exception as e:
            self.logger.error(f"记录审计事件失败: {str(e)}")
            
    async def cleanup_audit_logs(self):
        """清理过期审计日志"""
        try:
            cutoff = datetime.now().timestamp() - (self.audit_retention * 86400)
            
            # 获取所有审计日志
            audit_logs = self.vault_client.list('secret/fst/audit')
            if not audit_logs:
                return
                
            # 清理过期日志
            for event_type in audit_logs['data']['keys']:
                events = self.vault_client.list(f'secret/fst/audit/{event_type}')
                if not events:
                    continue
                    
                for timestamp in events['data']['keys']:
                    if float(timestamp) < cutoff:
                        self.vault_client.delete(
                            f'secret/fst/audit/{event_type}/{timestamp}'
                        )
                        
        except Exception as e:
            self.logger.error(f"清理审计日志失败: {str(e)}")
            
    def get_security_stats(self) -> Dict:
        """获取安全统计信息"""
        return {
            'key_age': (datetime.now() - self.key_created_at).total_seconds(),
            'audit_enabled': self.audit_enabled,
            'audit_retention': self.audit_retention,
            'operations': {
                'encrypt': SECURITY_OPS.labels(operation='encrypt')._value.get(),
                'decrypt': SECURITY_OPS.labels(operation='decrypt')._value.get(),
                'store_secret': SECURITY_OPS.labels(operation='store_secret')._value.get(),
                'get_secret': SECURITY_OPS.labels(operation='get_secret')._value.get()
            },
            'key_rotations': KEY_ROTATIONS._value.get()
        }