#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 消息队列

提供统一的消息队列接口，支持多种实现后端：
- 内存队列：用于单进程内通信
- Redis队列：用于分布式环境中的可靠消息传递
- Kafka队列：用于高吞吐量场景和事件流处理
"""

import json
import logging
import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import queue

# 尝试导入可选依赖
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

# 导入本地模块
from infrastructure.messaging.kafka_client import KafkaClient, get_kafka_client

# 日志配置
logger = logging.getLogger("fst.messaging.queue")


class QueueBackend(str, Enum):
    """队列后端类型"""
    MEMORY = "memory"  # 内存队列
    REDIS = "redis"    # Redis队列
    KAFKA = "kafka"    # Kafka队列


class Message:
    """
    消息对象
    
    封装消息数据和元数据，提供序列化和反序列化功能。
    """
    
    def __init__(self, 
                topic: str, 
                payload: Any,
                message_id: str = None,
                timestamp: float = None,
                headers: Dict[str, str] = None,
                reply_to: str = None):
        """
        初始化消息
        
        Args:
            topic: 消息主题
            payload: 消息内容
            message_id: 消息ID
            timestamp: 时间戳
            headers: 消息头部
            reply_to: 回复主题
        """
        self.topic = topic
        self.payload = payload
        self.message_id = message_id or str(uuid.uuid4())
        self.timestamp = timestamp or time.time()
        self.headers = headers or {}
        self.reply_to = reply_to
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "message_id": self.message_id,
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "headers": self.headers,
            "reply_to": self.reply_to
        }
    
    def to_json(self) -> str:
        """转换为JSON格式"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """从字典创建消息"""
        return cls(
            topic=data.get("topic", ""),
            payload=data.get("payload"),
            message_id=data.get("message_id"),
            timestamp=data.get("timestamp"),
            headers=data.get("headers"),
            reply_to=data.get("reply_to")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """从JSON创建消息"""
        data = json.loads(json_str)
        return cls.from_dict(data)


class MessageQueue:
    """
    消息队列
    
    提供统一的消息队列接口，支持不同的后端实现。
    """
    
    def __init__(self, 
                backend: Union[str, QueueBackend] = QueueBackend.MEMORY,
                config: Dict[str, Any] = None):
        """
        初始化消息队列
        
        Args:
            backend: 队列后端类型
            config: 后端配置
        """
        self.backend_type = QueueBackend(backend) if isinstance(backend, str) else backend
        self.config = config or {}
        self.backend = None
        self._subscribers = {}  # topic -> [callback]
        self._running = False
        self._consumer_thread = None
        
        # 初始化后端
        self._init_backend()
        
        logger.info(f"消息队列初始化完成: backend={self.backend_type.value}")
    
    def _init_backend(self):
        """初始化后端"""
        if self.backend_type == QueueBackend.MEMORY:
            self.backend = _MemoryBackend()
        elif self.backend_type == QueueBackend.REDIS:
            if not HAS_REDIS:
                logger.warning("未安装redis库，将降级使用内存队列。请使用pip install redis安装。")
                self.backend = _MemoryBackend()
            else:
                redis_config = self.config.get("redis", {})
                self.backend = _RedisBackend(
                    host=redis_config.get("host", "localhost"),
                    port=redis_config.get("port", 6379),
                    db=redis_config.get("db", 0),
                    password=redis_config.get("password", None),
                    prefix=redis_config.get("prefix", "fst:mq:")
                )
        elif self.backend_type == QueueBackend.KAFKA:
            kafka_config = self.config.get("kafka", {})
            client = get_kafka_client(
                bootstrap_servers=kafka_config.get("bootstrap_servers", "localhost:9092"),
                client_id=kafka_config.get("client_id", None),
                ssl_config=kafka_config.get("ssl_config", None)
            )
            self.backend = _KafkaBackend(
                client=client,
                consumer_group=kafka_config.get("consumer_group", f"fst-consumer-{uuid.uuid4().hex[:8]}")
            )
        else:
            raise ValueError(f"不支持的队列后端类型: {self.backend_type}")
    
    def publish(self, message: Union[Message, Dict[str, Any]]) -> bool:
        """
        发布消息
        
        Args:
            message: 消息对象或消息字典
            
        Returns:
            bool: 是否发布成功
        """
        # 转换字典为消息对象
        if isinstance(message, dict):
            if "topic" not in message:
                logger.error("发布消息失败: 缺少主题")
                return False
                
            message = Message(
                topic=message["topic"],
                payload=message.get("payload"),
                message_id=message.get("message_id"),
                timestamp=message.get("timestamp"),
                headers=message.get("headers"),
                reply_to=message.get("reply_to")
            )
        
        # 发布消息到后端
        try:
            result = self.backend.publish(message)
            return result
        except Exception as e:
            logger.error(f"发布消息失败: {str(e)}")
            return False
    
    def subscribe(self, 
                topics: Union[str, List[str]], 
                callback: Callable[[Message], None],
                start_consuming: bool = True) -> bool:
        """
        订阅主题
        
        Args:
            topics: 主题或主题列表
            callback: 回调函数
            start_consuming: 是否立即开始消费
            
        Returns:
            bool: 是否订阅成功
        """
        # 转换单个主题为列表
        if isinstance(topics, str):
            topics = [topics]
            
        # 注册订阅者
        for topic in topics:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            if callback not in self._subscribers[topic]:
                self._subscribers[topic].append(callback)
                logger.debug(f"订阅主题: {topic}")
        
        # 开始消费（如果尚未开始）
        if start_consuming and not self._running:
            self._start_consumer()
            
        return True
    
    def _start_consumer(self):
        """启动消费者线程"""
        if self._running:
            return
            
        self._running = True
        
        # 订阅所有主题
        topics = list(self._subscribers.keys())
        self.backend.subscribe(topics)
        
        # 启动消费线程
        self._consumer_thread = threading.Thread(
            target=self._consume_loop,
            name="message-queue-consumer",
            daemon=True
        )
        self._consumer_thread.start()
        
        logger.info(f"消息队列消费者已启动: topics={topics}")
    
    def _consume_loop(self):
        """消费循环"""
        try:
            while self._running:
                # 接收消息
                message = self.backend.receive(timeout=1.0)
                if not message:
                    continue
                    
                # 分发消息到订阅者
                self._dispatch_message(message)
                
        except Exception as e:
            logger.error(f"消息队列消费循环异常: {str(e)}")
            # 尝试重启消费者
            if self._running:
                time.sleep(1)
                self._start_consumer()
    
    def _dispatch_message(self, message: Message):
        """分发消息到订阅者"""
        topic = message.topic
        callbacks = self._subscribers.get(topic, []) + self._subscribers.get("*", [])
        
        if not callbacks:
            logger.debug(f"消息无订阅者: {topic}")
            return
            
        # 调用所有回调
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"处理消息时发生错误: {str(e)}")
    
    def unsubscribe(self, topics: Union[str, List[str]], callback: Callable[[Message], None] = None) -> bool:
        """
        取消订阅
        
        Args:
            topics: 主题或主题列表
            callback: 回调函数，如果为None则取消所有回调
            
        Returns:
            bool: 是否取消成功
        """
        # 转换单个主题为列表
        if isinstance(topics, str):
            topics = [topics]
            
        # 取消订阅
        for topic in topics:
            if topic in self._subscribers:
                if callback is None:
                    # 取消所有订阅
                    self._subscribers[topic] = []
                else:
                    # 取消特定回调
                    if callback in self._subscribers[topic]:
                        self._subscribers[topic].remove(callback)
                        
                # 如果没有订阅者，从列表中移除
                if not self._subscribers[topic]:
                    del self._subscribers[topic]
        
        # 如果没有任何订阅，停止消费
        if not self._subscribers and self._running:
            self._running = False
            if self._consumer_thread and self._consumer_thread.is_alive():
                self._consumer_thread.join(timeout=2)
                self._consumer_thread = None
            self.backend.unsubscribe()
            
        return True
    
    def request(self, 
              topic: str, 
              payload: Any,
              timeout: float = 30.0,
              headers: Dict[str, str] = None) -> Optional[Message]:
        """
        请求-响应模式
        
        发送请求并等待响应，实现同步调用模式。
        
        Args:
            topic: 目标主题
            payload: 请求数据
            timeout: 超时时间（秒）
            headers: 请求头
            
        Returns:
            Optional[Message]: 响应消息，超时返回None
        """
        # 创建临时响应队列
        reply_queue = str(uuid.uuid4())
        responses = queue.Queue()
        
        # 订阅响应
        def on_response(msg: Message):
            responses.put(msg)
            
        self.subscribe(reply_queue, on_response)
        
        # 发送请求
        request = Message(
            topic=topic,
            payload=payload,
            headers=headers,
            reply_to=reply_queue
        )
        self.publish(request)
        
        # 等待响应
        try:
            response = responses.get(timeout=timeout)
            return response
        except queue.Empty:
            logger.warning(f"请求超时: {topic}")
            return None
        finally:
            # 取消订阅
            self.unsubscribe(reply_queue)
    
    def reply(self, request: Message, payload: Any, headers: Dict[str, str] = None) -> bool:
        """
        回复请求
        
        Args:
            request: 原始请求
            payload: 响应数据
            headers: 响应头
            
        Returns:
            bool: 是否回复成功
        """
        if not request.reply_to:
            logger.error("无法回复请求：缺少reply_to字段")
            return False
            
        # 创建响应消息
        response = Message(
            topic=request.reply_to,
            payload=payload,
            headers=headers or {},
            message_id=f"reply-{request.message_id}"
        )
        
        # 添加关联ID
        response.headers["correlation_id"] = request.message_id
        
        # 发送响应
        return self.publish(response)
    
    def close(self):
        """关闭队列，释放资源"""
        # 停止消费
        self._running = False
        
        # 等待消费线程结束
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=2)
            self._consumer_thread = None
            
        # 关闭后端
        self.backend.close()
        
        logger.info("消息队列已关闭")


class _QueueBackend:
    """队列后端接口"""
    
    def publish(self, message: Message) -> bool:
        """发布消息"""
        raise NotImplementedError
    
    def subscribe(self, topics: List[str]) -> bool:
        """订阅主题"""
        raise NotImplementedError
    
    def unsubscribe(self) -> bool:
        """取消订阅"""
        raise NotImplementedError
    
    def receive(self, timeout: float = 1.0) -> Optional[Message]:
        """接收消息"""
        raise NotImplementedError
    
    def close(self):
        """关闭后端"""
        raise NotImplementedError


class _MemoryBackend(_QueueBackend):
    """内存队列后端"""
    
    def __init__(self):
        self._queues = {}  # topic -> queue
        self._subscribed_topics = set()
        self._queue_lock = threading.Lock()
        
    def publish(self, message: Message) -> bool:
        """发布消息到内存队列"""
        topic = message.topic
        
        with self._queue_lock:
            # 确保主题队列存在
            if topic not in self._queues:
                self._queues[topic] = queue.Queue()
                
            # 入队
            self._queues[topic].put(message)
            
        return True
    
    def subscribe(self, topics: List[str]) -> bool:
        """订阅主题列表"""
        with self._queue_lock:
            for topic in topics:
                self._subscribed_topics.add(topic)
                
                # 确保主题队列存在
                if topic not in self._queues:
                    self._queues[topic] = queue.Queue()
                    
        return True
    
    def unsubscribe(self) -> bool:
        """取消订阅"""
        with self._queue_lock:
            self._subscribed_topics.clear()
        return True
    
    def receive(self, timeout: float = 1.0) -> Optional[Message]:
        """从订阅的队列中接收消息"""
        if not self._subscribed_topics:
            time.sleep(timeout)
            return None
        
        # 获取所有订阅的队列
        subscribed_queues = []
        with self._queue_lock:
            for topic in self._subscribed_topics:
                if topic in self._queues:
                    subscribed_queues.append(self._queues[topic])
        
        # 没有订阅的队列
        if not subscribed_queues:
            time.sleep(timeout)
            return None
            
        # 轮询所有队列
        start_time = time.time()
        while time.time() - start_time < timeout:
            for q in subscribed_queues:
                try:
                    # 尝试非阻塞获取
                    return q.get_nowait()
                except queue.Empty:
                    continue
                    
            # 短暂休眠，避免忙等待
            time.sleep(0.01)
            
        # 超时，返回None
        return None
    
    def close(self):
        """关闭内存队列"""
        with self._queue_lock:
            self._queues.clear()
            self._subscribed_topics.clear()


class _RedisBackend(_QueueBackend):
    """Redis队列后端"""
    
    def __init__(self, 
                host: str = "localhost", 
                port: int = 6379, 
                db: int = 0,
                password: str = None,
                prefix: str = "fst:mq:"):
        """
        初始化Redis后端
        
        Args:
            host: Redis服务器地址
            port: Redis服务器端口
            db: Redis数据库
            password: Redis密码
            prefix: 键前缀
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.prefix = prefix
        self._client = None
        self._pubsub = None
        self._subscribed_topics = set()
        self._message_queue = queue.Queue()
        self._connect()
        
    def _connect(self):
        """连接Redis"""
        if not HAS_REDIS:
            raise RuntimeError("未安装redis库，请使用pip install redis安装")
            
        self._client = redis.Redis(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=False
        )
        
        # 测试连接
        try:
            self._client.ping()
        except redis.ConnectionError as e:
            logger.error(f"连接Redis失败: {str(e)}")
            raise
    
    def _get_topic_key(self, topic: str) -> str:
        """获取主题对应的Redis键"""
        return f"{self.prefix}{topic}"
    
    def publish(self, message: Message) -> bool:
        """发布消息到Redis"""
        try:
            # 序列化消息
            message_data = message.to_json().encode('utf-8')
            
            # 发布到Redis
            key = self._get_topic_key(message.topic)
            self._client.publish(key, message_data)
            
            return True
        except Exception as e:
            logger.error(f"Redis发布消息失败: {str(e)}")
            return False
    
    def subscribe(self, topics: List[str]) -> bool:
        """订阅Redis主题"""
        try:
            # 创建PubSub对象
            if self._pubsub is None:
                self._pubsub = self._client.pubsub()
                
                # 设置消息处理函数
                self._pubsub.parse_response = self._wrap_parse_response(self._pubsub.parse_response)
                
            # 转换主题名称
            redis_channels = [self._get_topic_key(topic) for topic in topics]
            
            # 订阅主题
            self._pubsub.subscribe(*redis_channels)
            
            # 记录已订阅主题
            self._subscribed_topics.update(topics)
            
            # 启动监听线程
            thread = threading.Thread(
                target=self._listen_pubsub,
                name="redis-pubsub-listener",
                daemon=True
            )
            thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Redis订阅主题失败: {str(e)}")
            return False
    
    def _wrap_parse_response(self, original_method):
        """包装解析响应方法"""
        def wrapped():
            # 调用原始方法
            response = original_method()
            
            # 处理消息
            if response and len(response) >= 3 and response[0] == b'message':
                try:
                    # 提取主题和数据
                    channel = response[1].decode('utf-8')
                    data = response[2].decode('utf-8')
                    
                    # 从Redis主题中提取原始主题
                    topic = channel.replace(self.prefix, '', 1)
                    
                    # 解析消息
                    message = Message.from_json(data)
                    
                    # 入队
                    self._message_queue.put(message)
                except Exception as e:
                    logger.error(f"处理Redis消息失败: {str(e)}")
                    
            return response
        return wrapped
    
    def _listen_pubsub(self):
        """监听PubSub消息"""
        try:
            self._pubsub.run_in_thread(sleep_time=0.001, daemon=True)
        except Exception as e:
            logger.error(f"Redis PubSub监听异常: {str(e)}")
    
    def unsubscribe(self) -> bool:
        """取消订阅"""
        try:
            if self._pubsub:
                # 转换主题名称
                redis_channels = [self._get_topic_key(topic) for topic in self._subscribed_topics]
                
                # 取消订阅
                self._pubsub.unsubscribe(*redis_channels)
                
                # 清除记录
                self._subscribed_topics.clear()
                
            return True
        except Exception as e:
            logger.error(f"Redis取消订阅失败: {str(e)}")
            return False
    
    def receive(self, timeout: float = 1.0) -> Optional[Message]:
        """接收消息"""
        try:
            # 从队列获取消息
            return self._message_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def close(self):
        """关闭Redis连接"""
        try:
            # 取消订阅
            self.unsubscribe()
            
            # 关闭PubSub
            if self._pubsub:
                self._pubsub.close()
                self._pubsub = None
                
            # 关闭Redis客户端
            if self._client:
                self._client.close()
                self._client = None
        except Exception as e:
            logger.error(f"关闭Redis连接失败: {str(e)}")


class _KafkaBackend(_QueueBackend):
    """Kafka队列后端"""
    
    def __init__(self, client: KafkaClient, consumer_group: str = None):
        """
        初始化Kafka后端
        
        Args:
            client: Kafka客户端
            consumer_group: 消费者组ID
        """
        self.client = client
        self.consumer_group = consumer_group or f"fst-mq-{uuid.uuid4().hex[:8]}"
        self._subscribed_topics = set()
        self._message_queue = queue.Queue()
        
    def publish(self, message: Message) -> bool:
        """发布消息到Kafka"""
        try:
            # 转换为字典
            message_dict = message.to_dict()
            
            # 发送消息
            return self.client.publish_message(
                topic=message.topic,
                message=message_dict,
                key=message.message_id
            )
        except Exception as e:
            logger.error(f"Kafka发布消息失败: {str(e)}")
            return False
    
    def subscribe(self, topics: List[str]) -> bool:
        """订阅Kafka主题"""
        try:
            # 记录主题
            new_topics = set(topics) - self._subscribed_topics
            if not new_topics:
                return True
                
            # 订阅新主题
            self.client.subscribe(
                topics=list(new_topics),
                group_id=self.consumer_group,
                callback=self._on_kafka_message
            )
            
            # 更新记录
            self._subscribed_topics.update(new_topics)
            
            return True
        except Exception as e:
            logger.error(f"Kafka订阅主题失败: {str(e)}")
            return False
    
    def _on_kafka_message(self, 
                        message_data: Dict[str, Any], 
                        topic: str, 
                        partition: int, 
                        offset: int,
                        headers: List[tuple]):
        """处理Kafka消息"""
        try:
            # 创建消息对象
            message = Message.from_dict(message_data)
            
            # 入队
            self._message_queue.put(message)
        except Exception as e:
            logger.error(f"处理Kafka消息失败: {str(e)}")
    
    def unsubscribe(self) -> bool:
        """取消订阅"""
        try:
            if self._subscribed_topics:
                # 取消订阅
                self.client.unsubscribe(
                    topics=list(self._subscribed_topics),
                    group_id=self.consumer_group
                )
                
                # 清除记录
                self._subscribed_topics.clear()
                
            return True
        except Exception as e:
            logger.error(f"Kafka取消订阅失败: {str(e)}")
            return False
    
    def receive(self, timeout: float = 1.0) -> Optional[Message]:
        """接收消息"""
        try:
            # 从队列获取消息
            return self._message_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def close(self):
        """关闭Kafka连接"""
        try:
            # 取消订阅
            self.unsubscribe()
        except Exception as e:
            logger.error(f"关闭Kafka连接失败: {str(e)}")


# 默认消息队列实例
_default_queue = None

def get_message_queue(
    backend: Union[str, QueueBackend] = None,
    config: Dict[str, Any] = None
) -> MessageQueue:
    """
    获取消息队列实例
    
    Args:
        backend: 队列后端类型
        config: 后端配置
        
    Returns:
        MessageQueue: 消息队列实例
    """
    global _default_queue
    
    if _default_queue is None:
        # 使用默认后端
        if backend is None:
            # 尝试按可用性选择后端
            if HAS_REDIS:
                backend = QueueBackend.REDIS
            else:
                backend = QueueBackend.MEMORY
                
        # 创建实例
        _default_queue = MessageQueue(backend=backend, config=config)
        
    return _default_queue