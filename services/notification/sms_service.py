"""
短信服务 - 提供短信发送和管理功能

该模块提供短信发送服务，支持:
- 多个短信服务商
- 短信模板
- 批量发送
- 发送状态跟踪
- 失败重试
- 短信验证码
"""

import logging
import threading
import json
from typing import List, Dict, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from string import Template
import requests

logger = logging.getLogger(__name__)

@dataclass
class SMSTemplate:
    """短信模板"""
    template_id: str                      # 模板ID
    content: str                          # 模板内容
    provider_template_id: Optional[str] = None  # 服务商模板ID
    provider: str = "default"             # 服务商
    created_at: datetime = None           # 创建时间
    updated_at: datetime = None           # 更新时间
    variables: List[str] = None           # 模板变量列表
    description: str = ""                 # 模板描述
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = self.created_at
        if self.variables is None:
            self.variables = self._extract_variables()
    
    def _extract_variables(self) -> List[str]:
        """提取模板中的变量"""
        variables = set()
        template = Template(self.content)
        # 获取模板中的占位符
        for match in Template.pattern.finditer(template.template):
            variables.add(match.group('named') or match.group('braced'))
        return sorted(list(variables))
    
    def render(self, variables: Dict[str, Any]) -> str:
        """
        渲染模板
        
        Args:
            variables: 变量值字典
            
        Returns:
            str: 渲染后的内容
        """
        try:
            template = Template(self.content)
            return template.safe_substitute(variables)
        except Exception as e:
            logger.error(f"Template render error: {str(e)}")
            raise

@dataclass
class SMSMessage:
    """短信消息"""
    phone_numbers: Union[str, List[str]]   # 手机号码
    content: str                           # 短信内容
    template_id: Optional[str] = None      # 模板ID
    variables: Optional[Dict[str, Any]] = None  # 模板变量
    provider: str = "default"              # 服务商
    priority: str = "normal"               # 优先级
    retry_count: int = 0                   # 重试次数
    status: str = "pending"                # 发送状态
    error_msg: Optional[str] = None        # 错误信息
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保号码列表格式正确
        if isinstance(self.phone_numbers, str):
            self.phone_numbers = [self.phone_numbers]
        if self.variables is None:
            self.variables = {}

class SMSProvider:
    """短信服务商基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化服务商
        
        Args:
            config: 配置信息
        """
        self.config = config
    
    def send_sms(self, message: SMSMessage) -> bool:
        """
        发送短信
        
        Args:
            message: 短信消息
            
        Returns:
            bool: 是否发送成功
        """
        raise NotImplementedError
    
    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        获取服务商模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            Optional[Dict[str, Any]]: 模板信息
        """
        raise NotImplementedError

class AliyunSMSProvider(SMSProvider):
    """阿里云短信服务商"""
    
    def send_sms(self, message: SMSMessage) -> bool:
        """实现阿里云短信发送"""
        try:
            # TODO: 实现阿里云短信发送逻辑
            return True
        except Exception as e:
            logger.error(f"Aliyun SMS sending failed: {str(e)}")
            return False

class TencentSMSProvider(SMSProvider):
    """腾讯云短信服务商"""
    
    def send_sms(self, message: SMSMessage) -> bool:
        """实现腾讯云短信发送"""
        try:
            # TODO: 实现腾讯云短信发送逻辑
            return True
        except Exception as e:
            logger.error(f"Tencent SMS sending failed: {str(e)}")
            return False

class SMSService:
    """
    短信服务
    
    提供短信发送和管理功能，支持:
    - 多个短信服务商
    - 短信模板管理
    - 批量发送
    - 异步发送
    - 失败重试
    """
    
    def __init__(self, 
                default_provider: str = "aliyun",
                max_retries: int = 3,
                retry_interval: int = 60,
                pool_size: int = 5):
        """
        初始化短信服务
        
        Args:
            default_provider: 默认服务商
            max_retries: 最大重试次数
            retry_interval: 重试间隔(秒)
            pool_size: 发送线程池大小
        """
        self.default_provider = default_provider
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        
        # 初始化线程池
        self.pool = ThreadPoolExecutor(max_workers=pool_size)
        
        # 服务商和模板存储
        self.providers: Dict[str, SMSProvider] = {}
        self.templates: Dict[str, SMSTemplate] = {}
        
        # 发送队列和状态跟踪
        self.message_queue: List[SMSMessage] = []
        self.sending_lock = threading.Lock()
        
        logger.info(f"SMS service initialized with default provider: {default_provider}")
    
    def add_provider(self, name: str, provider: SMSProvider) -> bool:
        """
        添加短信服务商
        
        Args:
            name: 服务商名称
            provider: 服务商实例
            
        Returns:
            bool: 是否添加成功
        """
        try:
            self.providers[name] = provider
            logger.info(f"Added SMS provider: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to add provider: {str(e)}")
            return False
    
    def add_template(self, template: SMSTemplate) -> bool:
        """
        添加短信模板
        
        Args:
            template: 短信模板对象
            
        Returns:
            bool: 是否添加成功
        """
        try:
            self.templates[template.template_id] = template
            logger.info(f"Added SMS template: {template.template_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add template: {str(e)}")
            return False
    
    def get_template(self, template_id: str) -> Optional[SMSTemplate]:
        """
        获取短信模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            Optional[SMSTemplate]: 模板对象
        """
        return self.templates.get(template_id)
    
    def send_sms(self, message: SMSMessage) -> bool:
        """
        发送单条短信
        
        Args:
            message: 短信消息对象
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 如果使用模板，先渲染内容
            if message.template_id:
                template = self.get_template(message.template_id)
                if template:
                    message.content = template.render(message.variables)
                else:
                    raise ValueError(f"Template not found: {message.template_id}")
            
            # 获取服务商
            provider = self.providers.get(message.provider or self.default_provider)
            if not provider:
                raise ValueError(f"Provider not found: {message.provider}")
            
            # 发送短信
            success = provider.send_sms(message)
            
            if success:
                message.status = "sent"
                logger.info(f"SMS sent successfully to {message.phone_numbers}")
            else:
                raise Exception("Provider failed to send SMS")
            
            return success
            
        except Exception as e:
            message.status = "failed"
            message.error_msg = str(e)
            message.retry_count += 1
            
            if message.retry_count < self.max_retries:
                logger.warning(f"SMS sending failed, will retry later: {str(e)}")
                self.retry_later(message)
            else:
                logger.error(f"SMS sending failed after {self.max_retries} retries: {str(e)}")
            
            return False
    
    def send_sms_async(self, message: SMSMessage) -> None:
        """
        异步发送短信
        
        Args:
            message: 短信消息对象
        """
        self.pool.submit(self.send_sms, message)
    
    def send_bulk_sms(self, messages: List[SMSMessage]) -> Dict[str, bool]:
        """
        批量发送短信
        
        Args:
            messages: 短信消息列表
            
        Returns:
            Dict[str, bool]: 发送结果字典
        """
        results = {}
        for message in messages:
            key = f"{message.phone_numbers}_{datetime.now().timestamp()}"
            results[key] = self.send_sms(message)
        return results
    
    def retry_later(self, message: SMSMessage) -> None:
        """
        稍后重试发送
        
        Args:
            message: 短信消息对象
        """
        def _retry():
            import time
            time.sleep(self.retry_interval)
            self.send_sms(message)
        
        self.pool.submit(_retry)
    
    def get_sending_status(self) -> Dict[str, int]:
        """
        获取发送状态统计
        
        Returns:
            Dict[str, int]: 状态统计
        """
        status_count = {
            "pending": 0,
            "sending": 0,
            "sent": 0,
            "failed": 0,
            "cancelled": 0
        }
        
        with self.sending_lock:
            for message in self.message_queue:
                status_count[message.status] += 1
        
        return status_count
    
    def shutdown(self) -> None:
        """关闭服务"""
        self.pool.shutdown(wait=True)
        logger.info("SMS service shutdown completed")