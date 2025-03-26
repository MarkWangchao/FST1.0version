#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 日期时间工具

提供日期时间处理的工具函数，包括：
- 时间戳转换
- 日期格式化
- 交易日历处理
- 时区转换
- 日期范围生成

Date and time utilities for FST framework:
- Timestamp conversions
- Date formatting
- Trading calendar operations
- Timezone conversions
- Date range generation
"""

import datetime
import time
import calendar
import pytz
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from typing import List, Optional, Tuple, Union, Callable, Dict, Any

# 标准时间格式
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATETIME_MS_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# 主要时区
DEFAULT_TIMEZONE = 'Asia/Shanghai'
UTC_TIMEZONE = 'UTC'


def now(timezone: str = DEFAULT_TIMEZONE) -> datetime.datetime:
    """
    获取当前时间（指定时区）
    
    Args:
        timezone: 时区名称，默认为'Asia/Shanghai'
    
    Returns:
        datetime: 当前时间
    """
    tz = pytz.timezone(timezone)
    return datetime.datetime.now(tz)


def today(timezone: str = DEFAULT_TIMEZONE) -> datetime.date:
    """
    获取当前日期（指定时区）
    
    Args:
        timezone: 时区名称，默认为'Asia/Shanghai'
    
    Returns:
        date: 当前日期
    """
    return now(timezone).date()


def timestamp_to_datetime(
    timestamp: Union[int, float], 
    timezone: str = DEFAULT_TIMEZONE
) -> datetime.datetime:
    """
    时间戳转为日期时间对象
    
    Args:
        timestamp: Unix时间戳（秒）
        timezone: 目标时区，默认为'Asia/Shanghai'
    
    Returns:
        datetime: 日期时间对象
    """
    tz = pytz.timezone(timezone)
    dt = datetime.datetime.fromtimestamp(timestamp, pytz.UTC)
    return dt.astimezone(tz)


def datetime_to_timestamp(dt: datetime.datetime) -> float:
    """
    日期时间对象转为时间戳
    
    Args:
        dt: 日期时间对象
    
    Returns:
        float: Unix时间戳（秒）
    """
    # 确保日期时间对象有时区信息
    if dt.tzinfo is None:
        dt = pytz.timezone(DEFAULT_TIMEZONE).localize(dt)
        
    return dt.timestamp()


def format_datetime(
    dt: Union[datetime.datetime, datetime.date, None] = None, 
    fmt: str = DATETIME_FORMAT, 
    timezone: str = DEFAULT_TIMEZONE
) -> str:
    """
    格式化日期时间
    
    Args:
        dt: 日期时间对象，默认为当前时间
        fmt: 格式化字符串，默认为'%Y-%m-%d %H:%M:%S'
        timezone: 时区名称，默认为'Asia/Shanghai'
    
    Returns:
        str: 格式化后的字符串
    """
    if dt is None:
        dt = now(timezone)
    
    # 处理日期对象
    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        # 对于日期对象，只有日期部分的格式化是有效的
        return dt.strftime(fmt)
    
    # 确保日期时间对象有时区信息
    if dt.tzinfo is None:
        dt = pytz.timezone(DEFAULT_TIMEZONE).localize(dt)
        
    # 转换到目标时区
    target_tz = pytz.timezone(timezone)
    dt = dt.astimezone(target_tz)
    
    return dt.strftime(fmt)


def parse_datetime(
    date_str: str, 
    fmt: Optional[str] = None,
    timezone: str = DEFAULT_TIMEZONE
) -> datetime.datetime:
    """
    解析日期时间字符串
    
    如果指定了格式，则使用strptime解析
    否则使用dateutil.parser进行智能解析
    
    Args:
        date_str: 日期时间字符串
        fmt: 格式化字符串，为None时自动识别格式
        timezone: 时区名称，默认为'Asia/Shanghai'
    
    Returns:
        datetime: 日期时间对象
    """
    tz = pytz.timezone(timezone)
    
    if fmt:
        dt = datetime.datetime.strptime(date_str, fmt)
    else:
        dt = parse(date_str)
        
    # 如果解析的结果没有时区信息，则添加时区信息
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    else:
        # 如果已有时区信息，转换到目标时区
        dt = dt.astimezone(tz)
        
    return dt


def parse_date(date_str: str, fmt: Optional[str] = None) -> datetime.date:
    """
    解析日期字符串为日期对象
    
    Args:
        date_str: 日期字符串
        fmt: 格式化字符串，为None时自动识别格式
    
    Returns:
        date: 日期对象
    """
    if fmt:
        return datetime.datetime.strptime(date_str, fmt).date()
    else:
        return parse(date_str).date()


def add_days(
    dt: Union[datetime.datetime, datetime.date], 
    days: int
) -> Union[datetime.datetime, datetime.date]:
    """
    日期加减天数
    
    Args:
        dt: 日期时间对象
        days: 增加的天数，可以为负数
    
    Returns:
        与输入相同类型的日期时间对象
    """
    result = dt + datetime.timedelta(days=days)
    return result


def add_months(
    dt: Union[datetime.datetime, datetime.date], 
    months: int
) -> Union[datetime.datetime, datetime.date]:
    """
    日期加减月数
    
    Args:
        dt: 日期时间对象
        months: 增加的月数，可以为负数
    
    Returns:
        与输入相同类型的日期时间对象
    """
    result = dt + relativedelta(months=months)
    return result


def add_years(
    dt: Union[datetime.datetime, datetime.date], 
    years: int
) -> Union[datetime.datetime, datetime.date]:
    """
    日期加减年数
    
    Args:
        dt: 日期时间对象
        years: 增加的年数，可以为负数
    
    Returns:
        与输入相同类型的日期时间对象
    """
    result = dt + relativedelta(years=years)
    return result


def date_range(
    start_date: Union[datetime.date, datetime.datetime, str],
    end_date: Union[datetime.date, datetime.datetime, str],
    include_end: bool = True
) -> List[datetime.date]:
    """
    生成日期范围
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        include_end: 是否包含结束日期
    
    Returns:
        List[date]: 日期列表
    """
    # 处理字符串输入
    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
    
    # 确保日期类型
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    
    # 生成日期范围
    days = (end_date - start_date).days
    if include_end:
        days += 1
        
    return [start_date + datetime.timedelta(days=i) for i in range(days)]


def is_weekend(dt: Union[datetime.datetime, datetime.date]) -> bool:
    """
    判断日期是否为周末
    
    Args:
        dt: 日期时间对象
    
    Returns:
        bool: 是否为周末(周六或周日)
    """
    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday


def get_month_start_end(
    year: int, 
    month: int
) -> Tuple[datetime.date, datetime.date]:
    """
    获取指定年月的起止日期
    
    Args:
        year: 年份
        month: 月份(1-12)
    
    Returns:
        Tuple[date, date]: (月初日期, 月末日期)
    """
    start_date = datetime.date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end_date = datetime.date(year, month, last_day)
    return start_date, end_date


def get_quarter_start_end(
    year: int, 
    quarter: int
) -> Tuple[datetime.date, datetime.date]:
    """
    获取指定年季度的起止日期
    
    Args:
        year: 年份
        quarter: 季度(1-4)
    
    Returns:
        Tuple[date, date]: (季度初日期, 季度末日期)
    """
    if not 1 <= quarter <= 4:
        raise ValueError("季度必须在1-4之间")
        
    start_month = (quarter - 1) * 3 + 1
    end_month = quarter * 3
    
    start_date = datetime.date(year, start_month, 1)
    _, last_day = calendar.monthrange(year, end_month)
    end_date = datetime.date(year, end_month, last_day)
    
    return start_date, end_date


def get_year_start_end(year: int) -> Tuple[datetime.date, datetime.date]:
    """
    获取指定年的起止日期
    
    Args:
        year: 年份
    
    Returns:
        Tuple[date, date]: (年初日期, 年末日期)
    """
    start_date = datetime.date(year, 1, 1)
    end_date = datetime.date(year, 12, 31)
    return start_date, end_date


def convert_timezone(
    dt: datetime.datetime, 
    from_tz: str, 
    to_tz: str
) -> datetime.datetime:
    """
    转换时区
    
    Args:
        dt: 日期时间对象
        from_tz: 源时区
        to_tz: 目标时区
    
    Returns:
        datetime: 转换后的日期时间对象
    """
    # 如果没有时区信息，添加源时区
    if dt.tzinfo is None:
        dt = pytz.timezone(from_tz).localize(dt)
    
    # 转换到目标时区
    target_tz = pytz.timezone(to_tz)
    return dt.astimezone(target_tz)


def get_days_difference(
    start_date: Union[datetime.date, datetime.datetime, str],
    end_date: Union[datetime.date, datetime.datetime, str]
) -> int:
    """
    计算两个日期之间的天数差
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        int: 天数差
    """
    # 处理字符串输入
    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
    
    # 确保日期类型
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    
    return (end_date - start_date).days


def split_into_batch_dates(
    start_date: Union[datetime.date, str],
    end_date: Union[datetime.date, str],
    batch_days: int
) -> List[Tuple[datetime.date, datetime.date]]:
    """
    将日期范围分割成固定天数的批次
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        batch_days: 每批天数
    
    Returns:
        List[Tuple[date, date]]: 分割后的日期范围列表
    """
    # 处理字符串输入
    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
    
    # 确保日期类型
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    
    result = []
    current_start = start_date
    
    while current_start <= end_date:
        current_end = current_start + datetime.timedelta(days=batch_days-1)
        if current_end > end_date:
            current_end = end_date
        
        result.append((current_start, current_end))
        current_start = current_end + datetime.timedelta(days=1)
    
    return result


def is_same_day(
    dt1: Union[datetime.datetime, datetime.date],
    dt2: Union[datetime.datetime, datetime.date]
) -> bool:
    """
    判断两个日期是否为同一天
    
    Args:
        dt1: 第一个日期时间对象
        dt2: 第二个日期时间对象
    
    Returns:
        bool: 是否为同一天
    """
    # 提取日期部分
    if isinstance(dt1, datetime.datetime):
        dt1 = dt1.date()
    if isinstance(dt2, datetime.datetime):
        dt2 = dt2.date()
    
    return dt1 == dt2


def get_current_timestamp() -> float:
    """
    获取当前时间戳
    
    Returns:
        float: 当前Unix时间戳（秒）
    """
    return time.time()


def get_current_timestamp_ms() -> int:
    """
    获取当前毫秒时间戳
    
    Returns:
        int: 当前Unix时间戳（毫秒）
    """
    return int(time.time() * 1000)


def format_time_delta(seconds: Union[int, float]) -> str:
    """
    格式化时间差为可读字符串
    
    Args:
        seconds: 秒数
    
    Returns:
        str: 格式化后的时间差，如"2小时3分钟"
    """
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}秒")
    
    return "".join(parts)


# 交易日历相关，这里仅提供接口，实际实现可能需要外部数据源
def is_trading_day(
    date: Union[datetime.date, datetime.datetime, str], 
    market: str = 'CN'
) -> bool:
    """
    判断是否为交易日
    
    Args:
        date: 日期
        market: 市场代码，默认为'CN'(中国市场)
    
    Returns:
        bool: 是否为交易日
    
    Note:
        这是一个简单实现，仅判断是否为周末。
        实际应用中需要考虑法定假日，可连接外部数据源或使用本地日历数据。
    """
    # 处理字符串输入
    if isinstance(date, str):
        date = parse_date(date)
    
    # 提取日期部分
    if isinstance(date, datetime.datetime):
        date = date.date()
    
    # 简单实现，仅判断是否为周末
    return not is_weekend(date)


def get_next_trading_day(
    date: Union[datetime.date, datetime.datetime, str], 
    market: str = 'CN'
) -> datetime.date:
    """
    获取下一个交易日
    
    Args:
        date: 日期
        market: 市场代码，默认为'CN'(中国市场)
    
    Returns:
        date: 下一个交易日
    """
    # 处理字符串输入
    if isinstance(date, str):
        date = parse_date(date)
    
    # 提取日期部分
    if isinstance(date, datetime.datetime):
        date = date.date()
    
    next_day = date + datetime.timedelta(days=1)
    while not is_trading_day(next_day, market):
        next_day += datetime.timedelta(days=1)
    
    return next_day


def get_previous_trading_day(
    date: Union[datetime.date, datetime.datetime, str], 
    market: str = 'CN'
) -> datetime.date:
    """
    获取上一个交易日
    
    Args:
        date: 日期
        market: 市场代码，默认为'CN'(中国市场)
    
    Returns:
        date: 上一个交易日
    """
    # 处理字符串输入
    if isinstance(date, str):
        date = parse_date(date)
    
    # 提取日期部分
    if isinstance(date, datetime.datetime):
        date = date.date()
    
    prev_day = date - datetime.timedelta(days=1)
    while not is_trading_day(prev_day, market):
        prev_day -= datetime.timedelta(days=1)
    
    return prev_day