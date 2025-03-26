#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 工具模块

提供框架所需的各种工具函数和实用程序，包括：
- 日期时间处理工具
- 文件操作工具
- 日志记录工具
- 数据验证工具

FST Framework Utilities Module:
- Date and time utilities
- File operation utilities
- Logging utilities
- Data validation utilities
"""

# 日期时间工具
from utils.date_utils import (
    # 时间戳和日期时间转换
    now,
    today,
    timestamp_to_datetime,
    datetime_to_timestamp,
    
    # 日期时间格式化
    format_datetime,
    parse_datetime,
    parse_date,
    
    # 日期操作
    add_days,
    add_months,
    add_years,
    date_range,
    
    # 日期判断
    is_weekend,
    is_same_day,
    
    # 日期范围
    get_month_start_end,
    get_quarter_start_end,
    get_year_start_end,
    get_days_difference,
    split_into_batch_dates,
    
    # 时区转换
    convert_timezone,
    
    # 时间戳
    get_current_timestamp,
    get_current_timestamp_ms,
    
    # 时间差格式化
    format_time_delta,
    
    # 交易日历
    is_trading_day,
    get_next_trading_day,
    get_previous_trading_day,
    
    # 常量
    DATE_FORMAT,
    DATETIME_FORMAT,
    DATETIME_MS_FORMAT,
    ISO_FORMAT,
    DEFAULT_TIMEZONE,
    UTC_TIMEZONE
)

# 文件操作工具
from utils.file_utils import (
    # 目录操作
    ensure_directory,
    delete_directory,
    ensure_parent_directory,
    copy_directory,
    
    # 文件读写
    read_text_file,
    read_text_file_lines,
    write_text_file,
    append_text_file,
    read_binary_file,
    write_binary_file,
    delete_file,
    copy_file,
    move_file,
    
    # 文件信息
    get_file_size,
    get_file_mtime,
    get_file_extension,
    is_file_extension,
    
    # 文件列表
    list_files,
    list_directories,
    
    # 路径处理
    normalize_path,
    make_relative_path,
    join_path,
    get_filename,
    get_directory_name,
    is_subpath,
    
    # 特殊文件处理
    read_json_file,
    write_json_file,
    read_yaml_file,
    write_yaml_file,
    read_csv_file,
    write_csv_file,
    
    # 压缩和解压
    create_zip_file,
    extract_zip_file,
    list_zip_contents,
    compress_file,
    decompress_file,
    
    # 文件校验
    calculate_file_md5,
    calculate_file_sha256,
    
    # 临时文件
    get_temp_file,
    get_temp_dir,
    
    # 文件搜索
    find_files_by_content,
    
    # 符号链接
    create_symlink
)

# 日志工具
from utils.logging_utils import (
    # 日志配置
    setup_logger,
    load_logging_config,
    get_logger,
    set_log_level,
    
    # 日志格式化
    ColoredFormatter,
    TimedRotatingFileHandlerWithHeader,
    
    # 上下文日志
    LoggerAdapter,
    get_logger_with_context,
    
    # 日志捕获
    LogCapture,
    
    # 性能日志
    PerformanceLogger,
    
    # 日志装饰器
    log_exceptions,
    log_function_call,
    
    # 交易日志
    setup_trading_logger,
    
    # 工具类
    LoggingUtils,
    
    # 常量
    LOG_LEVELS,
    DEFAULT_LOG_FORMAT,
    DEFAULT_DATE_FORMAT,
    COLORED_LOG_FORMATS
)

# 数据验证工具
from utils.validation import (
    # 核心类
    ValidationError,
    ValidationResult,
    Validator,
    
    # 基本验证器
    Required,
    TypeValidator,
    Range,
    Length,
    Pattern,
    
    # 交易验证器
    PriceValidator,
    VolumeValidator,
    SymbolValidator,
    
    # Schema验证
    SchemaValidator,
    validate_config,
    
    # 辅助函数
    is_valid_email,
    is_valid_phone,
    is_valid_date,
    is_valid_time,
    is_valid_json,
    is_chinese_id_card,
    validate_trading_time
)

# 版本信息
__version__ = '1.0.0'

# 模块导出
__all__ = [
    # 日期时间工具
    'now', 'today', 'timestamp_to_datetime', 'datetime_to_timestamp',
    'format_datetime', 'parse_datetime', 'parse_date',
    'add_days', 'add_months', 'add_years', 'date_range',
    'is_weekend', 'is_same_day',
    'get_month_start_end', 'get_quarter_start_end', 'get_year_start_end',
    'get_days_difference', 'split_into_batch_dates',
    'convert_timezone',
    'get_current_timestamp', 'get_current_timestamp_ms',
    'format_time_delta',
    'is_trading_day', 'get_next_trading_day', 'get_previous_trading_day',
    'DATE_FORMAT', 'DATETIME_FORMAT', 'DATETIME_MS_FORMAT', 'ISO_FORMAT',
    'DEFAULT_TIMEZONE', 'UTC_TIMEZONE',
    
    # 文件操作工具
    'ensure_directory', 'delete_directory', 'ensure_parent_directory', 'copy_directory',
    'read_text_file', 'read_text_file_lines', 'write_text_file', 'append_text_file',
    'read_binary_file', 'write_binary_file', 'delete_file', 'copy_file', 'move_file',
    'get_file_size', 'get_file_mtime', 'get_file_extension', 'is_file_extension',
    'list_files', 'list_directories',
    'normalize_path', 'make_relative_path', 'join_path',
    'get_filename', 'get_directory_name', 'is_subpath',
    'read_json_file', 'write_json_file', 'read_yaml_file', 'write_yaml_file',
    'read_csv_file', 'write_csv_file',
    'create_zip_file', 'extract_zip_file', 'list_zip_contents',
    'compress_file', 'decompress_file',
    'calculate_file_md5', 'calculate_file_sha256',
    'get_temp_file', 'get_temp_dir',
    'find_files_by_content',
    'create_symlink',
    
    # 日志工具
    'setup_logger', 'load_logging_config', 'get_logger', 'set_log_level',
    'ColoredFormatter', 'TimedRotatingFileHandlerWithHeader',
    'LoggerAdapter', 'get_logger_with_context',
    'LogCapture',
    'PerformanceLogger',
    'log_exceptions', 'log_function_call',
    'setup_trading_logger',
    'LoggingUtils',
    'LOG_LEVELS', 'DEFAULT_LOG_FORMAT', 'DEFAULT_DATE_FORMAT', 'COLORED_LOG_FORMATS',
    
    # 数据验证工具
    'ValidationError', 'ValidationResult', 'Validator',
    'Required', 'TypeValidator', 'Range', 'Length', 'Pattern',
    'PriceValidator', 'VolumeValidator', 'SymbolValidator',
    'SchemaValidator', 'validate_config',
    'is_valid_email', 'is_valid_phone', 'is_valid_date', 'is_valid_time',
    'is_valid_json', 'is_chinese_id_card', 'validate_trading_time'
]