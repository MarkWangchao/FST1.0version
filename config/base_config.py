#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 基础配置

基础配置类，所有其他配置继承自此类
"""

import os
import yaml
import json
from typing import Dict, Any, Optional

class BaseConfig:
    """基础配置类"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_data = {}
        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
    
    def load_config(self, config_file: str) -> bool:
        """加载配置文件"""
        try:
            ext = os.path.splitext(config_file)[1].lower()
            if ext in ['.yaml', '.yml']:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.config_data = yaml.safe_load(f)
            elif ext in ['.json']:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
            else:
                raise ValueError(f"不支持的配置文件类型: {ext}")
            return True
        except Exception as e:
            print(f"加载配置文件出错: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config_data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        self.config_data[key] = value
    
    def save(self, config_file: str) -> bool:
        """保存配置到文件"""
        try:
            ext = os.path.splitext(config_file)[1].lower()
            os.makedirs(os.path.dirname(os.path.abspath(config_file)), exist_ok=True)
            
            if ext in ['.yaml', '.yml']:
                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config_data, f, default_flow_style=False)
            elif ext in ['.json']:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config_data, f, indent=4, ensure_ascii=False)
            else:
                raise ValueError(f"不支持的配置文件类型: {ext}")
            return True
        except Exception as e:
            print(f"保存配置文件出错: {e}")
            return False
