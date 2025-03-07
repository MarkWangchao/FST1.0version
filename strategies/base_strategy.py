#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 策略基类

所有交易策略的基类
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import logging

class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, strategy_id: str, config: Dict):
        """
        初始化策略基类
        
        Args:
            strategy_id: 策略ID
            config: 策略配置
        """
        self.strategy_id = strategy_id
        self.config = config
        self.logger = logging.getLogger(f"fst.strategies.{strategy_id}")
        self.is_running = False
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        策略初始化
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    def run(self) -> List[Dict]:
        """
        运行策略逻辑
        
        Returns:
            List[Dict]: 产生的交易信号列表
        """
        pass
    
    def get_interval(self) -> float:
        """
        获取策略运行间隔时间(秒)
        
        Returns:
            float: 间隔时间
        """
        return self.config.get('interval', 60.0)
    
    def on_start(self) -> None:
        """策略启动时调用"""
        self.is_running = True
        self.logger.info(f"策略 {self.strategy_id} 启动")
    
    def on_stop(self) -> None:
        """策略停止时调用"""
        self.is_running = False
        self.logger.info(f"策略 {self.strategy_id} 停止")
    
    def on_error(self, error: Exception) -> None:
        """策略发生错误时调用"""
        self.logger.error(f"策略 {self.strategy_id} 发生错误: {error}")
