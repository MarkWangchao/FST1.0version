"""
邮件服务 - 提供邮件发送和管理功能

该模块提供邮件发送服务，支持:
- HTML格式邮件
- 附件支持
- 邮件模板
- 批量发送
- 发送状态跟踪
- 失败重试
"""

import os
import logging
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import List, Dict, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from string import Template

logger = logging.getLogger(__name__)

@dataclass
class EmailTemplate:
    """邮件模板"""
    template_id: str                      # 模板ID
    subject: str                          # 邮件主题模板
    content: str                          # 邮件内容模板
    content_type: str = "html"            # 内容类型: plain/html
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
        for text in [self.subject, self.content]:
            template = Template(text)
            # 获取模板中的占位符
            for match in Template.pattern.finditer(template.template):
                variables.add(match.group('named') or match.group('braced'))
        return sorted(list(variables))
    
    def render(self, variables: Dict[str, Any]) -> tuple[str, str]:
        """
        渲染模板
        
        Args:
            variables: 变量值字典
            
        Returns:
            tuple: (渲染后的主题, 渲染后的内容)
        """
        try:
            subject_template = Template(self.subject)
            content_template = Template(self.content)
            
            rendered_subject = subject_template.safe_substitute(variables)
            rendered_content = content_template.safe_substitute(variables)
            
            return rendered_subject, rendered_content
        except Exception as e:
            logger.error(f"Template render error: {str(e)}")
            raise

@dataclass
class EmailMessage:
    """邮件消息"""
    to_addrs: Union[str, List[str]]      # 收件人地址
    subject: str                          # 邮件主题
    content: str                          # 邮件内容
    content_type: str = "html"            # 内容类型: plain/html
    from_addr: Optional[str] = None       # 发件人地址
    cc_addrs: Optional[List[str]] = None  # 抄送地址
    bcc_addrs: Optional[List[str]] = None # 密送地址
    attachments: Optional[List[str]] = None  # 附件路径列表
    template_id: Optional[str] = None     # 模板ID
    variables: Optional[Dict[str, Any]] = None  # 模板变量
    priority: str = "normal"              # 优先级
    retry_count: int = 0                  # 重试次数
    status: str = "pending"              # 发送状态
    error_msg: Optional[str] = None      # 错误信息
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保地址列表格式正确
        if isinstance(self.to_addrs, str):
            self.to_addrs = [self.to_addrs]
        if self.cc_addrs is None:
            self.cc_addrs = []
        if self.bcc_addrs is None:
            self.bcc_addrs = []
        if self.attachments is None:
            self.attachments = []
        if self.variables is None:
            self.variables = {}
    
    def to_mime_message(self) -> MIMEMultipart:
        """
        转换为MIME消息
        
        Returns:
            MIMEMultipart: MIME消息对象
        """
        # 创建邮件对象
        msg = MIMEMultipart()
        msg['Subject'] = self.subject
        msg['From'] = self.from_addr
        msg['To'] = ', '.join(self.to_addrs)
        if self.cc_addrs:
            msg['Cc'] = ', '.join(self.cc_addrs)
        
        # 添加正文
        content_part = MIMEText(self.content, self.content_type, 'utf-8')
        msg.attach(content_part)
        
        # 添加附件
        for attachment in self.attachments:
            if os.path.exists(attachment):
                try:
                    with open(attachment, 'rb') as f:
                        part = MIMEApplication(f.read())
                        part.add_header('Content-Disposition', 'attachment', 
                                      filename=os.path.basename(attachment))
                        msg.attach(part)
                except Exception as e:
                    logger.error(f"Failed to attach file {attachment}: {str(e)}")
        
        return msg

class EmailService:
    """
    邮件服务
    
    提供邮件发送和管理功能，支持:
    - 基于SMTP的邮件发送
    - 邮件模板管理
    - 批量发送
    - 异步发送
    - 失败重试
    """
    
    def __init__(self, 
                smtp_host: str,
                smtp_port: int,
                username: str,
                password: str,
                use_ssl: bool = True,
                max_retries: int = 3,
                retry_interval: int = 60,
                pool_size: int = 5):
        """
        初始化邮件服务
        
        Args:
            smtp_host: SMTP服务器地址
            smtp_port: SMTP服务器端口
            username: 用户名
            password: 密码
            use_ssl: 是否使用SSL
            max_retries: 最大重试次数
            retry_interval: 重试间隔(秒)
            pool_size: 发送线程池大小
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        
        # 初始化线程池
        self.pool = ThreadPoolExecutor(max_workers=pool_size)
        
        # 模板存储
        self.templates: Dict[str, EmailTemplate] = {}
        
        # 发送队列和状态跟踪
        self.message_queue: List[EmailMessage] = []
        self.sending_lock = threading.Lock()
        
        logger.info(f"Email service initialized with SMTP server {smtp_host}:{smtp_port}")
    
    def add_template(self, template: EmailTemplate) -> bool:
        """
        添加邮件模板
        
        Args:
            template: 邮件模板对象
            
        Returns:
            bool: 是否添加成功
        """
        try:
            self.templates[template.template_id] = template
            logger.info(f"Added email template: {template.template_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add template: {str(e)}")
            return False
    
    def get_template(self, template_id: str) -> Optional[EmailTemplate]:
        """
        获取邮件模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            Optional[EmailTemplate]: 模板对象
        """
        return self.templates.get(template_id)
    
    def send_email(self, message: EmailMessage) -> bool:
        """
        发送单个邮件
        
        Args:
            message: 邮件消息对象
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 如果使用模板，先渲染内容
            if message.template_id:
                template = self.get_template(message.template_id)
                if template:
                    message.subject, message.content = template.render(message.variables)
                else:
                    raise ValueError(f"Template not found: {message.template_id}")
            
            # 设置发件人
            if not message.from_addr:
                message.from_addr = self.username
            
            # 转换为MIME消息
            mime_msg = message.to_mime_message()
            
            # 连接SMTP服务器并发送
            smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
            with smtp_class(self.smtp_host, self.smtp_port) as server:
                server.login(self.username, self.password)
                server.send_message(mime_msg)
            
            message.status = "sent"
            logger.info(f"Email sent successfully to {message.to_addrs}")
            return True
            
        except Exception as e:
            message.status = "failed"
            message.error_msg = str(e)
            message.retry_count += 1
            
            if message.retry_count < self.max_retries:
                logger.warning(f"Email sending failed, will retry later: {str(e)}")
                self.retry_later(message)
            else:
                logger.error(f"Email sending failed after {self.max_retries} retries: {str(e)}")
            
            return False
    
    def send_email_async(self, message: EmailMessage) -> None:
        """
        异步发送邮件
        
        Args:
            message: 邮件消息对象
        """
        self.pool.submit(self.send_email, message)
    
    def send_bulk_emails(self, messages: List[EmailMessage]) -> Dict[str, bool]:
        """
        批量发送邮件
        
        Args:
            messages: 邮件消息列表
            
        Returns:
            Dict[str, bool]: 发送结果字典
        """
        results = {}
        for message in messages:
            key = f"{message.to_addrs}_{datetime.now().timestamp()}"
            results[key] = self.send_email(message)
        return results
    
    def retry_later(self, message: EmailMessage) -> None:
        """
        稍后重试发送
        
        Args:
            message: 邮件消息对象
        """
        def _retry():
            import time
            time.sleep(self.retry_interval)
            self.send_email(message)
        
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
        logger.info("Email service shutdown completed")