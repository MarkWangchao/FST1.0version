#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 日志工具

提供日志记录功能的工具函数，包括：
- 日志配置管理
- 不同级别的日志记录
- 日志格式定制
- 文件和控制台日志输出
- 日志轮转和保留策略
- 性能监控日志

Logging utilities for FST framework:
- Log configuration management
- Different log levels
- Log format customization 
- File and console log output
- Log rotation and retention
- Performance monitoring logs
"""

import os
import sys
import logging
import logging.config
import logging.handlers
import json
import datetime
import time
import traceback
import threading
import yaml
import colorama
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Callable

# 初始化colorama，用于输出彩色日志
colorama.init()

# 日志级别映射
LOG_LEVELS = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    'critical': logging.CRITICAL
}

# 默认日志格式
DEFAULT_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 彩色日志配置
COLORED_LOG_FORMATS = {
    logging.DEBUG: f'{colorama.Fore.CYAN}%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s{colorama.Style.RESET_ALL}',
    logging.INFO: f'{colorama.Fore.GREEN}%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s{colorama.Style.RESET_ALL}',
    logging.WARNING: f'{colorama.Fore.YELLOW}%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s{colorama.Style.RESET_ALL}',
    logging.ERROR: f'{colorama.Fore.RED}%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s{colorama.Style.RESET_ALL}',
    logging.CRITICAL: f'{colorama.Fore.RED}{colorama.Back.WHITE}%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s{colorama.Style.RESET_ALL}'
}


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""

    def format(self, record):
        log_fmt = COLORED_LOG_FORMATS.get(record.levelno, DEFAULT_LOG_FORMAT)
        formatter = logging.Formatter(log_fmt, DEFAULT_DATE_FORMAT)
        return formatter.format(record)


def setup_logger(
    name: Optional[str] = None,
    level: Union[str, int] = 'info',
    log_file: Optional[str] = None,
    log_to_console: bool = True,
    log_format: Optional[str] = None,
    date_format: Optional[str] = None,
    colored_console: bool = True,
    file_mode: str = 'a',
    max_bytes: int = 10*1024*1024,  # 10MB
    backup_count: int = 5,
    encoding: str = 'utf-8'
) -> logging.Logger:
    """
    配置并返回日志器
    
    Args:
        name: 日志器名称，为None时返回根日志器
        level: 日志级别，可以是字符串或整数级别
        log_file: 日志文件路径，为None时不输出到文件
        log_to_console: 是否输出到控制台
        log_format: 日志格式，为None时使用默认格式
        date_format: 日期格式，为None时使用默认格式
        colored_console: 是否使用彩色控制台输出
        file_mode: 文件打开模式，'a'追加，'w'覆盖
        max_bytes: 单个日志文件最大字节数，用于轮转
        backup_count: 保留的备份文件数量
        encoding: 日志文件编码
    
    Returns:
        logging.Logger: 配置好的日志器
    """
    # 获取日志器
    logger = logging.getLogger(name)
    
    # 转换日志级别
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.lower(), logging.INFO)
    
    # 设置日志级别
    logger.setLevel(level)
    
    # 清除已有的处理器
    logger.handlers = []
    
    # 使用默认格式（如果未指定）
    log_format = log_format or DEFAULT_LOG_FORMAT
    date_format = date_format or DEFAULT_DATE_FORMAT
    
    # 添加控制台处理器
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # 根据设置使用彩色或普通格式化器
        if colored_console:
            console_formatter = ColoredFormatter()
        else:
            console_formatter = logging.Formatter(log_format, date_format)
            
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 添加文件处理器（如果指定了日志文件）
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 使用RotatingFileHandler进行日志轮转
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            mode=file_mode,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # 防止日志传播到父日志器
    logger.propagate = False
    
    return logger


def load_logging_config(config_file: str) -> bool:
    """
    从配置文件加载日志配置
    
    支持JSON和YAML格式，使用Python的logging.config模块
    
    Args:
        config_file: 配置文件路径
    
    Returns:
        bool: 是否成功加载配置
    """
    try:
        if not os.path.exists(config_file):
            print(f"日志配置文件不存在: {config_file}")
            return False
            
        # 根据文件扩展名决定解析方法
        ext = os.path.splitext(config_file)[1].lower()
        
        with open(config_file, 'r', encoding='utf-8') as f:
            if ext in ('.json', '.jsn'):
                config = json.load(f)
            elif ext in ('.yaml', '.yml'):
                config = yaml.safe_load(f)
            else:
                # 尝试按照fileConfig格式加载
                logging.config.fileConfig(config_file)
                return True
        
        # 使用dictConfig加载配置
        logging.config.dictConfig(config)
        return True
    except Exception as e:
        print(f"加载日志配置失败: {str(e)}")
        traceback.print_exc()
        return False


def get_logger(name: str = None) -> logging.Logger:
    """
    获取命名的日志器
    
    如果日志器未配置，将使用默认配置初始化
    
    Args:
        name: 日志器名称，默认为根日志器
    
    Returns:
        logging.Logger: 日志器实例
    """
    logger = logging.getLogger(name)
    
    # 如果根日志器未配置，初始化一个基本配置
    if not logging.getLogger().handlers and name is None:
        setup_logger()
    
    return logger


def set_log_level(level: Union[str, int], logger_name: str = None) -> None:
    """
    设置日志级别
    
    Args:
        level: 日志级别，可以是字符串或整数
        logger_name: 日志器名称，为None时设置根日志器
    """
    logger = logging.getLogger(logger_name)
    
    # 转换日志级别
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.lower(), logging.INFO)
    
    logger.setLevel(level)
    
    # 同时设置所有处理器的级别
    for handler in logger.handlers:
        handler.setLevel(level)


class LoggerAdapter(logging.LoggerAdapter):
    """
    日志适配器，用于添加上下文信息
    
    可以在每条日志中添加额外的上下文信息，如会话ID、用户信息等
    """
    
    def process(self, msg, kwargs):
        # 添加上下文信息
        context_str = " ".join(f"[{k}={v}]" for k, v in self.extra.items())
        if context_str:
            msg = f"{msg} {context_str}"
        return msg, kwargs


def get_logger_with_context(name: str, **context) -> LoggerAdapter:
    """
    获取带有上下文信息的日志器
    
    Args:
        name: 日志器名称
        **context: 上下文信息，会添加到每条日志中
    
    Returns:
        LoggerAdapter: 带有上下文的日志适配器
    """
    logger = get_logger(name)
    return LoggerAdapter(logger, context)


class LogCapture:
    """
    日志捕获器，用于临时捕获日志输出
    
    可用于测试或需要获取日志内容的场景
    """
    
    def __init__(self, logger_names=None, level=logging.DEBUG):
        """
        初始化日志捕获器
        
        Args:
            logger_names: 要捕获的日志器名称列表，None表示所有日志器
            level: 捕获的最低日志级别
        """
        self.logger_names = logger_names
        self.level = level
        self.records = []
        self.handlers = {}
        
    def __enter__(self):
        # 为指定的日志器添加内存处理器
        if self.logger_names is None:
            # 捕获根日志器
            loggers = [logging.getLogger()]
        else:
            loggers = [logging.getLogger(name) for name in self.logger_names]
            
        for logger in loggers:
            handler = logging.handlers.MemoryHandler(capacity=1024*1024, flushLevel=logging.CRITICAL+1)
            handler.setLevel(self.level)
            
            # 自定义的目标处理器，用于收集日志记录
            class CollectTarget:
                def handle(self, record):
                    self.records.append(record)
                    
                def close(self):
                    pass
                    
            target = CollectTarget()
            target.records = self.records
            handler.setTarget(target)
            
            logger.addHandler(handler)
            self.handlers[logger] = handler
            
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 移除处理器
        for logger, handler in self.handlers.items():
            logger.removeHandler(handler)
            handler.close()
            
    def get_records(self) -> List[logging.LogRecord]:
        """获取捕获的日志记录"""
        return self.records
        
    def get_messages(self) -> List[str]:
        """获取格式化后的日志消息"""
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)
        return [formatter.format(record) for record in self.records]


class TimedRotatingFileHandlerWithHeader(logging.handlers.TimedRotatingFileHandler):
    """
    带有文件头的定时轮转文件处理器
    
    在创建新的日志文件时会写入自定义的文件头内容
    """
    
    def __init__(self, filename, header=None, **kwargs):
        """
        初始化处理器
        
        Args:
            filename: 日志文件名
            header: 文件头内容
            **kwargs: 其他参数，与TimedRotatingFileHandler相同
        """
        super().__init__(filename, **kwargs)
        self.header = header or "# Log file created at: {}\n".format(datetime.datetime.now().isoformat())
        
        # 如果文件是新创建的，写入文件头
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            self._write_header()
    
    def doRollover(self):
        """执行轮转时，在新文件中写入文件头"""
        super().doRollover()
        self._write_header()
        
    def _write_header(self):
        """写入文件头"""
        if self.header:
            with open(self.baseFilename, 'a', encoding=self.encoding) as f:
                f.write(self.header)


class PerformanceLogger:
    """
    性能日志器，用于记录和分析代码执行性能
    
    可以作为上下文管理器或装饰器使用
    """
    
    def __init__(self, name=None, logger=None, level=logging.INFO):
        """
        初始化性能日志器
        
        Args:
            name: 性能日志的标识名称
            logger: 使用的日志器，为None时使用根日志器
            level: 日志级别
        """
        self.name = name
        self.logger = logger or logging.getLogger()
        self.level = level
        self.start_time = None
        self.end_time = None
        
    def __enter__(self):
        """进入上下文，开始计时"""
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，记录性能日志"""
        self.end_time = time.time()
        elapsed = (self.end_time - self.start_time) * 1000  # 转换为毫秒
        
        name_info = f"'{self.name}' " if self.name else ""
        self.logger.log(self.level, f"性能统计: {name_info}执行耗时 {elapsed:.2f} ms")
        
    def __call__(self, func):
        """作为装饰器使用"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper


def log_exceptions(logger=None, level=logging.ERROR, reraise=True):
    """
    异常日志装饰器，用于记录函数调用中的异常
    
    Args:
        logger: 使用的日志器，为None时使用根日志器
        level: 日志级别
        reraise: 是否重新抛出异常
    
    Returns:
        装饰器函数
    """
    import functools
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 获取异常详情
                log = logger or logging.getLogger()
                exc_info = sys.exc_info()
                
                # 构建函数调用信息
                arg_str = ", ".join([repr(a) for a in args])
                kwarg_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                call_str = f"{func.__name__}({arg_str}{', ' if arg_str and kwarg_str else ''}{kwarg_str})"
                
                # 记录异常
                log.log(level, f"异常发生于函数调用: {call_str}", exc_info=exc_info)
                
                # 根据设置决定是否重新抛出
                if reraise:
                    raise
                
        return wrapper
    return decorator


def configure_thread_logger(base_logger_name=None):
    """
    为每个线程配置独立的日志器
    
    Args:
        base_logger_name: 基础日志器名称，为None时使用根日志器
    
    Returns:
        thread_get_logger: 获取当前线程日志器的函数
    """
    thread_loggers = {}
    thread_lock = threading.Lock()
    
    def thread_get_logger():
        thread_id = threading.get_ident()
        
        with thread_lock:
            if thread_id not in thread_loggers:
                # 创建此线程的日志器
                thread_name = threading.current_thread().name
                logger_name = f"{base_logger_name}.thread.{thread_name}" if base_logger_name else f"thread.{thread_name}"
                thread_loggers[thread_id] = get_logger(logger_name)
                
        return thread_loggers[thread_id]
    
    return thread_get_logger


def get_default_log_dir() -> str:
    """
    获取默认日志目录
    
    Returns:
        str: 日志目录路径
    """
    # 基于用户目录创建日志目录
    home_dir = os.path.expanduser("~")
    log_dir = os.path.join(home_dir, '.fst', 'logs')
    
    # 确保目录存在
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
        
    return log_dir


def setup_trading_logger(
    name: str = 'fst',
    level: Union[str, int] = 'info',
    log_dir: Optional[str] = None,
    create_console_handler: bool = True,
    create_file_handler: bool = True,
    file_prefix: str = 'fst',
    rotation: str = 'midnight',
    backup_count: int = 14
) -> logging.Logger:
    """
    配置交易系统日志器
    
    Args:
        name: 日志器名称
        level: 日志级别
        log_dir: 日志目录，为None时使用默认目录
        create_console_handler: 是否创建控制台处理器
        create_file_handler: 是否创建文件处理器
        file_prefix: 日志文件前缀
        rotation: 轮转方式，'midnight'表示每天午夜轮转
        backup_count: 保留的备份文件数
    
    Returns:
        logging.Logger: 配置好的日志器
    """
    # 获取日志器
    logger = logging.getLogger(name)
    
    # 转换日志级别
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.lower(), logging.INFO)
    
    # 设置日志级别
    logger.setLevel(level)
    
    # 清除已有的处理器
    logger.handlers = []
    
    # 添加控制台处理器
    if create_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = ColoredFormatter()
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 添加文件处理器
    if create_file_handler:
        # 获取日志目录
        if log_dir is None:
            log_dir = get_default_log_dir()
        
        # 确保日志目录存在
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 创建当前日期日志文件名
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(log_dir, f"{file_prefix}_{today}.log")
        
        # 创建带有文件头的处理器
        header = f"# FST Trading System Log\n# Started at: {datetime.datetime.now().isoformat()}\n\n"
        file_handler = TimedRotatingFileHandlerWithHeader(
            filename=log_file,
            header=header,
            when=rotation,
            backupCount=backup_count,
            encoding='utf-8'
        )
        
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # 防止日志传播到父日志器
    logger.propagate = False
    
    return logger


def log_function_call(logger=None, level=logging.DEBUG, log_args=True, log_result=True):
    """
    记录函数调用的装饰器
    
    Args:
        logger: 使用的日志器，为None时使用根日志器
        level: 日志级别
        log_args: 是否记录函数参数
        log_result: 是否记录函数返回值
    
    Returns:
        装饰器函数
    """
    import functools
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 获取日志器
            log = logger or logging.getLogger()
            
            # 记录函数调用
            if log_args:
                arg_str = ", ".join([repr(a) for a in args])
                kwarg_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                call_str = f"{func.__name__}({arg_str}{', ' if arg_str and kwarg_str else ''}{kwarg_str})"
                log.log(level, f"函数调用: {call_str}")
            else:
                log.log(level, f"函数调用: {func.__name__}()")
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 记录返回值
            if log_result:
                log.log(level, f"函数返回: {func.__name__} -> {repr(result)}")
                
            return result
        return wrapper
    return decorator


# 创建一个简单的日志记录工具类，可全局导入使用
class LoggingUtils:
    """
    日志工具类，提供简单快捷的日志记录接口
    """
    
    @staticmethod
    def setup(
        name: str = None,
        level: Union[str, int] = 'info',
        log_file: Optional[str] = None
    ) -> logging.Logger:
        """配置并返回日志器"""
        return setup_logger(name=name, level=level, log_file=log_file)
    
    @staticmethod
    def setup_trading_logger(name: str = 'fst', level: Union[str, int] = 'info') -> logging.Logger:
        """配置交易系统日志器"""
        return setup_trading_logger(name=name, level=level)
        
    @staticmethod
    def get_logger(name: str = None) -> logging.Logger:
        """获取日志器"""
        return get_logger(name)
        
    @staticmethod
    def set_level(level: Union[str, int], name: str = None) -> None:
        """设置日志级别"""
        set_log_level(level, name)
        
    @staticmethod
    def get_context_logger(name: str, **context) -> LoggerAdapter:
        """获取带上下文的日志器"""
        return get_logger_with_context(name, **context)
        
    @staticmethod
    def get_default_log_dir() -> str:
        """获取默认日志目录"""
        return get_default_log_dir()
        
    @staticmethod
    def performance_logger(name=None, logger=None, level=logging.INFO):
        """获取性能日志记录器"""
        return PerformanceLogger(name, logger, level)
        
    @staticmethod
    def log_exceptions(logger=None, level=logging.ERROR, reraise=True):
        """获取异常日志装饰器"""
        return log_exceptions(logger, level, reraise)
        
    @staticmethod
    def log_function_call(logger=None, level=logging.DEBUG, log_args=True, log_result=True):
        """获取函数调用日志装饰器"""
        return log_function_call(logger, level, log_args, log_result)
        
    @staticmethod
    def load_config(config_file: str) -> bool:
        """从配置文件加载日志配置"""
        return load_logging_config(config_file)


# 导入缺失的模块
import functools