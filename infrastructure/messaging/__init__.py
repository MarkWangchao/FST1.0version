#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 消息服务

提供统一的消息传递接口，支持点对点通信、发布订阅模式和请求-响应模式。
可用于组件间的解耦通信、分布式处理和事件通知。

Created on 2025-03-07
"""

from infrastructure.messaging.kafka_client import KafkaClient, get_kafka_client
from infrastructure.messaging.message_queue import (
    Message, 
    MessageQueue, 
    QueueBackend,
    get_message_queue
)

__all__ = [
    'KafkaClient',
    'get_kafka_client',
    'Message',
    'MessageQueue',
    'QueueBackend',
    'get_message_queue',
]