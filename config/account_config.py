#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 账户配置

用于管理交易账户相关配置
"""

from typing import Dict, List, Optional
from .base_config import BaseConfig

class AccountConfig(BaseConfig):
    """账户配置类"""
    
    def __init__(self, config_file: Optional[str] = None):
        super().__init__(config_file)
        
    def get_accounts(self) -> List[Dict]:
        """获取所有账户配置"""
        return self.get('accounts', [])
    
    def get_account(self, account_id: str) -> Optional[Dict]:
        """获取指定账户配置"""
        accounts = self.get_accounts()
        for account in accounts:
            if account.get('account_id') == account_id:
                return account
        return None
    
    def add_account(self, account_info: Dict) -> bool:
        """添加账户配置"""
        if not account_info.get('account_id'):
            print("账户信息必须包含account_id")
            return False
            
        accounts = self.get_accounts()
        
        # 检查是否已存在相同ID的账户
        for i, account in enumerate(accounts):
            if account.get('account_id') == account_info['account_id']:
                # 更新已存在的账户信息
                accounts[i] = account_info
                self.set('accounts', accounts)
                return True
        
        # 添加新账户
        accounts.append(account_info)
        self.set('accounts', accounts)
        return True
    
    def remove_account(self, account_id: str) -> bool:
        """删除指定账户配置"""
        accounts = self.get_accounts()
        for i, account in enumerate(accounts):
            if account.get('account_id') == account_id:
                accounts.pop(i)
                self.set('accounts', accounts)
                return True
        return False
