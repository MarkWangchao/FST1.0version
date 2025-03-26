"""
通知服务模块 - 提供多渠道消息通知功能

该模块提供了统一的消息通知接口，支持多种通知渠道:
- 邮件通知：支持HTML格式、附件、批量发送
- 短信通知：支持多个短信服务商、模板消息
- 自定义通知：可扩展支持其他通知渠道

主要功能:
- 统一的消息发送接口
- 消息模板管理
- 发送状态跟踪
- 失败重试机制
- 批量发送优化
- 限流保护
"""

from .email_service import EmailService, EmailMessage, EmailTemplate
from .sms_service import SMSService, SMSMessage, SMSTemplate

# 导出公共接口
__all__ = [
    # 邮件服务
    "EmailService",
    "EmailMessage",
    "EmailTemplate",
    
    # 短信服务
    "SMSService", 
    "SMSMessage",
    "SMSTemplate"
]

# 通知类型常量
NOTIFY_TYPE_EMAIL = "email"           # 邮件通知
NOTIFY_TYPE_SMS = "sms"               # 短信通知
NOTIFY_TYPE_WECHAT = "wechat"         # 微信通知
NOTIFY_TYPE_WEBHOOK = "webhook"       # Webhook通知
NOTIFY_TYPE_CUSTOM = "custom"         # 自定义通知

# 通知优先级常量
PRIORITY_LOW = "low"                  # 低优先级
PRIORITY_NORMAL = "normal"            # 普通优先级
PRIORITY_HIGH = "high"                # 高优先级
PRIORITY_URGENT = "urgent"            # 紧急优先级

# 通知状态常量
STATUS_PENDING = "pending"            # 等待发送
STATUS_SENDING = "sending"            # 发送中
STATUS_SENT = "sent"                  # 已发送
STATUS_FAILED = "failed"              # 发送失败
STATUS_CANCELLED = "cancelled"        # 已取消