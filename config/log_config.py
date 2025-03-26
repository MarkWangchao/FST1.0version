#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 增强型日志配置

提供企业级日志管理功能，包括：
- 异步日志处理
- 结构化日志支持
- 日志安全性
- 性能优化
- 监控集成
"""

import os
import re
import logging
import mmap
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from concurrent_log_handler import ConcurrentRotatingFileHandler
import structlog
from structlog.processors import JSONRenderer
from prometheus_client import Counter, Histogram
from logging.handlers import MemoryHandler
from .base_config import BaseConfig

# 性能指标
LOG_ERRORS = Counter('log_errors_total', '日志系统错误总数')
LOG_WRITES = Counter('log_writes_total', '日志写入总数')
LOG_LATENCY = Histogram('log_write_latency_seconds', '日志写入延迟')

class SensitiveDataFilter(logging.Filter):
    """敏感数据过滤器"""
    
    def __init__(self, patterns: Optional[List[str]] = None):
        super().__init__()
        self.patterns = patterns or [
            r'password=\S+',
            r'token=\S+',
            r'secret=\S+',
            r'key=\S+',
            r'"password":\s*"[^"]*"',
            r'"token":\s*"[^"]*"'
        ]
        self.compiled_patterns = [re.compile(pattern) for pattern in self.patterns]
    
    def filter(self, record):
        """过滤敏感信息"""
        try:
            message = str(record.msg)
            for pattern in self.compiled_patterns:
                message = pattern.sub(lambda m: m.group(0).split('=')[0] + '=***', message)
            record.msg = message
        except Exception as e:
            LOG_ERRORS.inc()
            logging.error(f"敏感数据过滤失败: {str(e)}")
        return True

class MMapFileHandler(logging.FileHandler):
    """零拷贝日志处理器"""
    
    def emit(self, record):
        """使用内存映射写入日志"""
        try:
            msg = self.format(record)
            with open(self.baseFilename, 'ab') as f:
                with mmap.mmap(f.fileno(), 0) as mm:
                    mm.write(msg.encode() + b'\n')
        except Exception as e:
            LOG_ERRORS.inc()
            self.handleError(record)

class AsyncLogHandler:
    """异步日志处理器"""
    
    def __init__(self, handler, loop=None):
        self.handler = handler
        self.loop = loop or asyncio.get_event_loop()
        self.queue = asyncio.Queue()
        self.task = None
    
    async def start(self):
        """启动异步处理"""
        self.task = self.loop.create_task(self._process_logs())
    
    async def stop(self):
        """停止异步处理"""
        if self.task:
            self.task.cancel()
            await self.queue.put(None)  # 发送停止信号
            try:
                await self.task
            except asyncio.CancelledError:
                pass
    
    async def emit(self, record):
        """异步发送日志"""
        await self.queue.put(record)
    
    async def _process_logs(self):
        """处理日志队列"""
        while True:
            record = await self.queue.get()
            if record is None:
                break
            try:
                with LOG_LATENCY.time():
                    self.handler.emit(record)
                    LOG_WRITES.inc()
            except Exception as e:
                LOG_ERRORS.inc()
                logging.error(f"异步日志处理失败: {str(e)}")
            finally:
                self.queue.task_done()

class EnhancedLogConfig:
    """增强型日志配置管理器"""
    
    def __init__(self, config: BaseConfig):
        """
        初始化日志配置
        
        Args:
            config: BaseConfig实例
        """
        self.config = config
        self.log_config = config.get('logging', {})
        self.async_handlers = []
        self._setup_logging()
    
    def _setup_logging(self):
        """配置日志系统"""
        try:
            # 基本配置
            log_level = self.log_config.get('level', 'INFO')
            log_format = self.log_config.get('format',
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            
            # 创建根日志记录器
            root_logger = logging.getLogger()
            root_logger.setLevel(log_level)
            
            # 清除现有处理器
            root_logger.handlers = []
            
            # 配置结构化日志
            if self.log_config.get('structured', False):
                self._setup_structured_logging()
            
            # 添加控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(console_handler)
            
            # 配置文件日志
            if self.log_config.get('file', {}).get('enabled', True):
                self._setup_file_logging(root_logger)
            
            # 添加敏感数据过滤
            sensitive_filter = SensitiveDataFilter()
            root_logger.addFilter(sensitive_filter)
            
            # 配置内存缓存
            self._setup_memory_cache(root_logger)
            
            # 启动异步处理器
            asyncio.create_task(self._start_async_handlers())
            
        except Exception as e:
            LOG_ERRORS.inc()
            logging.error(f"日志系统初始化失败: {str(e)}")
    
    def _setup_structured_logging(self):
        """配置结构化日志"""
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    def _setup_file_logging(self, logger: logging.Logger):
        """配置文件日志"""
        try:
            # 获取配置
            file_config = self.log_config.get('file', {})
            log_path = file_config.get('path', 'data/logs')
            max_size = file_config.get('max_size', 10 * 1024 * 1024)
            backup_count = file_config.get('backup_count', 5)
            permissions = file_config.get('permissions', '600')
            
            # 创建日志目录
            os.makedirs(log_path, exist_ok=True)
            
            # 创建日志文件
            current_time = datetime.now().strftime('%Y%m%d')
            log_file = os.path.join(log_path, f'fst_{current_time}.log')
            
            # 设置文件权限
            if not os.path.exists(log_file):
                Path(log_file).touch()
            os.chmod(log_file, int(permissions, 8))
            
            # 创建并配置处理器
            handler = ConcurrentRotatingFileHandler(
                filename=log_file,
                maxBytes=max_size,
                backupCount=backup_count,
                encoding='utf-8',
                use_gzip=True
            )
            
            # 设置格式化器
            handler.setFormatter(logging.Formatter(self.log_config.get('format')))
            
            # 创建异步处理器
            async_handler = AsyncLogHandler(handler)
            self.async_handlers.append(async_handler)
            
            # 添加到日志记录器
            logger.addHandler(handler)
            
        except Exception as e:
            LOG_ERRORS.inc()
            logging.error(f"文件日志配置失败: {str(e)}")
    
    def _setup_memory_cache(self, logger: logging.Logger):
        """配置内存缓存"""
        try:
            # 创建内存处理器
            buffer_size = self.log_config.get('buffer_size', 100)
            for handler in logger.handlers:
                if isinstance(handler, (ConcurrentRotatingFileHandler, MMapFileHandler)):
                    memory_handler = MemoryHandler(
                        capacity=buffer_size,
                        target=handler
                    )
                    logger.removeHandler(handler)
                    logger.addHandler(memory_handler)
        except Exception as e:
            LOG_ERRORS.inc()
            logging.error(f"内存缓存配置失败: {str(e)}")
    
    async def _start_async_handlers(self):
        """启动所有异步处理器"""
        for handler in self.async_handlers:
            await handler.start()
    
    async def cleanup_logs(self, retention_days: int = 30, max_total_size: int = 10*1024**3):
        """清理日志文件"""
        try:
            log_path = self.log_config.get('file', {}).get('path', 'data/logs')
            if not os.path.exists(log_path):
                return
                
            current_time = datetime.now()
            total_size = 0
            files_info = []
            
            # 收集文件信息
            for filename in os.listdir(log_path):
                if not filename.startswith('fst_') or not filename.endswith('.log'):
                    continue
                    
                file_path = os.path.join(log_path, filename)
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                file_size = os.path.getsize(file_path)
                
                files_info.append({
                    'path': file_path,
                    'time': file_time,
                    'size': file_size
                })
                total_size += file_size
            
            # 按时间排序
            files_info.sort(key=lambda x: x['time'])
            
            # 清理过期文件
            for file_info in files_info:
                if (current_time - file_info['time']).days > retention_days:
                    os.remove(file_info['path'])
                    total_size -= file_info['size']
                    logging.info(f"已删除过期日志文件: {file_info['path']}")
                
                # 检查总大小限制
                if total_size > max_total_size:
                    os.remove(file_info['path'])
                    total_size -= file_info['size']
                    logging.info(f"已删除超出大小限制的日志文件: {file_info['path']}")
                
        except Exception as e:
            LOG_ERRORS.inc()
            logging.error(f"清理日志文件失败: {str(e)}")
    
    async def shutdown(self):
        """关闭日志系统"""
        for handler in self.async_handlers:
            await handler.stop()
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取日志记录器"""
        return logging.getLogger(name)
    
    def set_level(self, level: str):
        """设置日志级别"""
        if level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError(f"无效的日志级别: {level}")
        
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        self.config.set('logging.level', level)
    
    def get_metrics(self) -> Dict:
        """获取日志指标"""
        return {
            'errors': LOG_ERRORS._value.get(),
            'writes': LOG_WRITES._value.get(),
            'latency': {
                'avg': LOG_LATENCY.describe()['avg'],
                'count': LOG_LATENCY._count.get()
            }
        }