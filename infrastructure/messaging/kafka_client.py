#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - Kafka 客户端

提供与Kafka消息中间件的集成，支持消息的生产和消费，
以及高级功能如消息分区、主题管理和可靠性保证。
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

# 尝试导入kafka库，如果没有安装则提供一个优雅的降级
try:
    from kafka import KafkaConsumer, KafkaProducer
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import KafkaError
    HAS_KAFKA = True
except ImportError:
    HAS_KAFKA = False
    # 创建模拟类，使得即使没有安装kafka库也能保持API兼容
    class KafkaConsumer:
        pass
    class KafkaProducer:
        pass
    class KafkaAdminClient:
        pass
    class NewTopic:
        pass
    class KafkaError(Exception):
        pass

# 日志配置
logger = logging.getLogger("fst.messaging.kafka")


class KafkaClient:
    """
    Kafka客户端
    
    提供Kafka生产者和消费者的统一接口，简化消息的发送和接收流程。
    支持消息序列化、反序列化、重试机制和异常处理。
    """
    
    def __init__(self, 
                 bootstrap_servers: Union[str, List[str]] = 'localhost:9092',
                 client_id: str = None,
                 ssl_config: Dict[str, str] = None,
                 compression_type: str = 'gzip',
                 max_retries: int = 3):
        """
        初始化Kafka客户端
        
        Args:
            bootstrap_servers: Kafka服务器地址，可以是单个地址或地址列表
            client_id: 客户端ID，如果为None则自动生成
            ssl_config: SSL配置，用于安全连接
            compression_type: 压缩类型（gzip, snappy, lz4）
            max_retries: 最大重试次数
        """
        if not HAS_KAFKA:
            logger.warning("未安装kafka-python库，Kafka功能将不可用。请使用pip install kafka-python安装。")
            self.available = False
            return
            
        self.available = True
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id or f"fst-kafka-{uuid.uuid4().hex[:8]}"
        self.ssl_config = ssl_config
        self.compression_type = compression_type
        self.max_retries = max_retries
        
        # 初始状态
        self._producer = None
        self._admin = None
        self._consumers = {}
        self._running = False
        
        logger.info(f"Kafka客户端初始化: client_id={self.client_id}, servers={bootstrap_servers}")
    
    def _get_producer_config(self) -> Dict[str, Any]:
        """获取生产者配置"""
        config = {
            'bootstrap_servers': self.bootstrap_servers,
            'client_id': f"{self.client_id}-producer",
            'retries': self.max_retries,
            'acks': 'all',  # 所有副本确认
            'compression_type': self.compression_type,
            'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
            'key_serializer': lambda k: k.encode('utf-8') if isinstance(k, str) else str(k).encode('utf-8'),
        }
        
        # 添加SSL配置（如果有）
        if self.ssl_config:
            config.update({
                'security_protocol': 'SSL',
                'ssl_cafile': self.ssl_config.get('cafile'),
                'ssl_certfile': self.ssl_config.get('certfile'),
                'ssl_keyfile': self.ssl_config.get('keyfile'),
            })
            
        return config
    
    def _get_consumer_config(self, group_id: str) -> Dict[str, Any]:
        """获取消费者配置"""
        config = {
            'bootstrap_servers': self.bootstrap_servers,
            'client_id': f"{self.client_id}-consumer-{group_id}",
            'group_id': group_id,
            'auto_offset_reset': 'earliest',
            'enable_auto_commit': True,
            'value_deserializer': lambda v: json.loads(v.decode('utf-8')),
            'key_deserializer': lambda k: k.decode('utf-8'),
        }
        
        # 添加SSL配置（如果有）
        if self.ssl_config:
            config.update({
                'security_protocol': 'SSL',
                'ssl_cafile': self.ssl_config.get('cafile'),
                'ssl_certfile': self.ssl_config.get('certfile'),
                'ssl_keyfile': self.ssl_config.get('keyfile'),
            })
            
        return config
    
    def _get_admin_config(self) -> Dict[str, Any]:
        """获取管理客户端配置"""
        config = {
            'bootstrap_servers': self.bootstrap_servers,
            'client_id': f"{self.client_id}-admin",
        }
        
        # 添加SSL配置（如果有）
        if self.ssl_config:
            config.update({
                'security_protocol': 'SSL',
                'ssl_cafile': self.ssl_config.get('cafile'),
                'ssl_certfile': self.ssl_config.get('certfile'),
                'ssl_keyfile': self.ssl_config.get('keyfile'),
            })
            
        return config
    
    def _get_producer(self) -> KafkaProducer:
        """获取或创建生产者"""
        if not self.available:
            raise RuntimeError("Kafka功能不可用，请确保已安装kafka-python库")
            
        if self._producer is None:
            try:
                config = self._get_producer_config()
                self._producer = KafkaProducer(**config)
                logger.info("Kafka生产者已创建")
            except KafkaError as e:
                logger.error(f"创建Kafka生产者失败: {str(e)}")
                raise
                
        return self._producer
    
    def _get_admin(self) -> KafkaAdminClient:
        """获取或创建管理客户端"""
        if not self.available:
            raise RuntimeError("Kafka功能不可用，请确保已安装kafka-python库")
            
        if self._admin is None:
            try:
                config = self._get_admin_config()
                self._admin = KafkaAdminClient(**config)
                logger.info("Kafka管理客户端已创建")
            except KafkaError as e:
                logger.error(f"创建Kafka管理客户端失败: {str(e)}")
                raise
                
        return self._admin
    
    def publish_message(self, 
                      topic: str, 
                      message: Dict[str, Any], 
                      key: str = None,
                      partition: int = None,
                      timestamp_ms: int = None,
                      headers: List[tuple] = None) -> bool:
        """
        发布消息到Kafka主题
        
        Args:
            topic: 目标主题
            message: 消息内容（字典格式）
            key: 消息键（用于分区）
            partition: 指定分区ID
            timestamp_ms: 消息时间戳（毫秒）
            headers: 消息头部列表，每个元素为(key, value)元组
            
        Returns:
            bool: 是否发送成功
        """
        if not self.available:
            logger.warning("Kafka功能不可用，消息发送失败")
            return False
            
        try:
            producer = self._get_producer()
            
            # 生成默认key
            if key is None:
                key = str(uuid.uuid4())
                
            # 添加消息元数据
            message_with_metadata = message.copy()
            if 'metadata' not in message_with_metadata:
                message_with_metadata['metadata'] = {}
            
            message_with_metadata['metadata'].update({
                'timestamp': timestamp_ms or int(time.time() * 1000),
                'producer_id': self.client_id,
                'message_id': str(uuid.uuid4()),
            })
            
            # 异步发送
            future = producer.send(
                topic=topic,
                value=message_with_metadata,
                key=key,
                partition=partition,
                timestamp_ms=timestamp_ms,
                headers=headers,
            )
            
            # 可选：等待发送结果
            # future.get(timeout=10)
            
            return True
            
        except KafkaError as e:
            logger.error(f"发送Kafka消息失败: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"发送Kafka消息时发生未知错误: {str(e)}")
            return False
    
    def subscribe(self, 
                topics: Union[str, List[str]], 
                group_id: str,
                callback: Callable[[Dict[str, Any], str, int, int, List[tuple]], None]) -> bool:
        """
        订阅主题并处理消息
        
        Args:
            topics: 主题或主题列表
            group_id: 消费者组ID
            callback: 回调函数，参数为(message, topic, partition, offset, headers)
            
        Returns:
            bool: 是否订阅成功
        """
        if not self.available:
            logger.warning("Kafka功能不可用，无法订阅主题")
            return False
            
        # 转换单个主题为列表
        if isinstance(topics, str):
            topics = [topics]
            
        # 创建消费者
        try:
            config = self._get_consumer_config(group_id)
            consumer = KafkaConsumer(*topics, **config)
            
            # 存储消费者
            consumer_id = f"{group_id}-{'-'.join(topics)}"
            self._consumers[consumer_id] = {
                'consumer': consumer,
                'callback': callback,
                'topics': topics,
                'group_id': group_id,
                'thread': None,
                'running': False
            }
            
            # 启动消费线程
            self._start_consumer_thread(consumer_id)
            return True
            
        except KafkaError as e:
            logger.error(f"订阅Kafka主题失败: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"订阅Kafka主题时发生未知错误: {str(e)}")
            return False
    
    def _start_consumer_thread(self, consumer_id: str) -> None:
        """启动消费者线程"""
        consumer_data = self._consumers.get(consumer_id)
        if not consumer_data:
            logger.error(f"消费者 {consumer_id} 不存在")
            return
            
        # 标记为运行状态
        consumer_data['running'] = True
        
        # 创建并启动线程
        thread = threading.Thread(
            target=self._consume_messages,
            args=(consumer_id,),
            name=f"kafka-consumer-{consumer_id}",
            daemon=True
        )
        consumer_data['thread'] = thread
        thread.start()
        
        logger.info(f"Kafka消费者线程已启动: {consumer_id}, 主题: {consumer_data['topics']}")
    
    def _consume_messages(self, consumer_id: str) -> None:
        """消费消息的线程函数"""
        consumer_data = self._consumers.get(consumer_id)
        if not consumer_data:
            return
            
        consumer = consumer_data['consumer']
        callback = consumer_data['callback']
        
        try:
            while consumer_data['running']:
                # 轮询消息，超时100ms
                messages = consumer.poll(timeout_ms=100, max_records=10)
                
                # 处理消息
                for tp, records in messages.items():
                    for record in records:
                        try:
                            # 调用回调函数
                            callback(
                                record.value,
                                record.topic,
                                record.partition,
                                record.offset,
                                record.headers
                            )
                        except Exception as e:
                            logger.error(f"处理Kafka消息时发生错误: {str(e)}")
                
        except Exception as e:
            if consumer_data['running']:
                logger.error(f"Kafka消费者线程异常: {str(e)}")
                # 尝试重启
                time.sleep(5)
                self._start_consumer_thread(consumer_id)
    
    def unsubscribe(self, topics: Union[str, List[str]], group_id: str) -> bool:
        """
        取消订阅主题
        
        Args:
            topics: 主题或主题列表
            group_id: 消费者组ID
            
        Returns:
            bool: 是否取消成功
        """
        if not self.available:
            return False
            
        # 转换单个主题为列表
        if isinstance(topics, str):
            topics = [topics]
            
        # 查找对应的消费者
        consumer_id = f"{group_id}-{'-'.join(topics)}"
        consumer_data = self._consumers.get(consumer_id)
        
        if consumer_data:
            # 停止消费线程
            consumer_data['running'] = False
            
            # 如果线程还活着，等待结束
            thread = consumer_data['thread']
            if thread and thread.is_alive():
                thread.join(timeout=5)
                
            # 关闭消费者
            try:
                consumer_data['consumer'].close()
            except Exception as e:
                logger.error(f"关闭Kafka消费者时发生错误: {str(e)}")
                
            # 移除消费者
            del self._consumers[consumer_id]
            logger.info(f"已取消订阅主题: {topics}, 消费者组: {group_id}")
            return True
        else:
            logger.warning(f"未找到对应的消费者: 主题={topics}, 组={group_id}")
            return False
    
    def create_topic(self, 
                   topic: str, 
                   num_partitions: int = 1, 
                   replication_factor: int = 1) -> bool:
        """
        创建Kafka主题
        
        Args:
            topic: 主题名称
            num_partitions: 分区数量
            replication_factor: 副本因子
            
        Returns:
            bool: 是否创建成功
        """
        if not self.available:
            logger.warning("Kafka功能不可用，无法创建主题")
            return False
            
        try:
            admin = self._get_admin()
            
            # 创建主题
            topic_list = [
                NewTopic(
                    name=topic,
                    num_partitions=num_partitions,
                    replication_factor=replication_factor
                )
            ]
            
            admin.create_topics(new_topics=topic_list, validate_only=False)
            logger.info(f"已创建Kafka主题: {topic}, 分区: {num_partitions}, 副本: {replication_factor}")
            return True
            
        except KafkaError as e:
            logger.error(f"创建Kafka主题失败: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"创建Kafka主题时发生未知错误: {str(e)}")
            return False
    
    def delete_topic(self, topic: str) -> bool:
        """
        删除Kafka主题
        
        Args:
            topic: 主题名称
            
        Returns:
            bool: 是否删除成功
        """
        if not self.available:
            logger.warning("Kafka功能不可用，无法删除主题")
            return False
            
        try:
            admin = self._get_admin()
            
            # 删除主题
            admin.delete_topics([topic])
            logger.info(f"已删除Kafka主题: {topic}")
            return True
            
        except KafkaError as e:
            logger.error(f"删除Kafka主题失败: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"删除Kafka主题时发生未知错误: {str(e)}")
            return False
    
    def list_topics(self) -> List[str]:
        """
        列出所有主题
        
        Returns:
            List[str]: 主题列表
        """
        if not self.available:
            logger.warning("Kafka功能不可用，无法列出主题")
            return []
            
        try:
            # 使用消费者临时列出主题
            consumer = KafkaConsumer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=f"{self.client_id}-topic-lister"
            )
            
            # 获取主题列表
            topics = list(consumer.topics())
            
            # 关闭临时消费者
            consumer.close()
            
            return topics
            
        except KafkaError as e:
            logger.error(f"列出Kafka主题失败: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"列出Kafka主题时发生未知错误: {str(e)}")
            return []
    
    def close(self) -> None:
        """关闭Kafka客户端，释放所有资源"""
        if not self.available:
            return
            
        # 关闭所有消费者
        for consumer_id, consumer_data in list(self._consumers.items()):
            self.unsubscribe(consumer_data['topics'], consumer_data['group_id'])
            
        # 关闭生产者
        if self._producer:
            try:
                self._producer.close()
                self._producer = None
            except Exception as e:
                logger.error(f"关闭Kafka生产者时发生错误: {str(e)}")
                
        # 关闭管理客户端
        if self._admin:
            try:
                self._admin.close()
                self._admin = None
            except Exception as e:
                logger.error(f"关闭Kafka管理客户端时发生错误: {str(e)}")
                
        logger.info("Kafka客户端已关闭")


# 可选：提供一个单例实例
_default_client = None

def get_kafka_client(
    bootstrap_servers: Union[str, List[str]] = 'localhost:9092',
    client_id: str = None,
    ssl_config: Dict[str, str] = None
) -> KafkaClient:
    """
    获取Kafka客户端单例
    
    Args:
        bootstrap_servers: Kafka服务器地址
        client_id: 客户端ID
        ssl_config: SSL配置
        
    Returns:
        KafkaClient: Kafka客户端实例
    """
    global _default_client
    
    if _default_client is None:
        _default_client = KafkaClient(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            ssl_config=ssl_config
        )
        
    return _default_client