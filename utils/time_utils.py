#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 时间工具模块

提供与交易日历和交易时间相关的工具函数，支持不同市场的交易时间计算。
"""

import datetime
import pytz
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import holidays
import logging

# 获取logger
logger = logging.getLogger(__name__)

# 交易时段配置 - 可以根据实际需要在配置文件中调整
DEFAULT_TRADING_HOURS = {
    "stock": {  # 股票市场
        "CN": [  # 中国市场
            {"start": "09:30:00", "end": "11:30:00"},
            {"start": "13:00:00", "end": "15:00:00"}
        ],
        "US": [  # 美国市场
            {"start": "09:30:00", "end": "16:00:00"}
        ]
    },
    "future": {  # 期货市场
        "CN": {  # 中国市场
            "day": [  # 日盘
                {"start": "09:00:00", "end": "10:15:00"},
                {"start": "10:30:00", "end": "11:30:00"},
                {"start": "13:30:00", "end": "15:00:00"}
            ],
            "night": [  # 夜盘
                {"start": "21:00:00", "end": "23:00:00"}
            ]
        }
    },
    "crypto": {  # 加密货币市场 - 24小时交易
        "global": [
            {"start": "00:00:00", "end": "23:59:59"}
        ]
    }
}

# 假期配置
MARKET_HOLIDAYS = {
    "CN": holidays.CN(),  # 中国节假日
    "US": holidays.US(),  # 美国节假日
    # 可以添加其他市场的假期配置
}


def get_current_time(timezone: str = "Asia/Shanghai") -> datetime.datetime:
    """
    获取指定时区的当前时间
    
    Args:
        timezone: 时区名称，默认为上海时区
        
    Returns:
        datetime: 当前时间(带时区信息)
    """
    tz = pytz.timezone(timezone)
    return datetime.datetime.now(tz)


def get_current_trading_date(market: str = "CN", asset_type: str = "stock") -> datetime.date:
    """
    获取当前交易日期
    规则：
    1. 如果当前是交易日且在收盘前，返回当前日期
    2. 如果当前是交易日但已收盘，返回下一个交易日
    3. 如果当前不是交易日，返回下一个交易日
    
    Args:
        market: 市场代码，如CN(中国)、US(美国)等
        asset_type: 资产类型，如stock(股票)、future(期货)等
        
    Returns:
        date: 当前交易日期
    """
    now = get_current_time(get_timezone_for_market(market))
    today = now.date()
    
    # 如果今天不是交易日，找下一个交易日
    if not is_trading_day(today, market):
        return get_next_trading_day(today, market)
    
    # 如果今天是交易日，但当前时间已经过了收盘时间，找下一个交易日
    if not is_trading_time(now, market, asset_type):
        # 检查是否已经过了最后一个交易时段
        last_session_end = get_last_trading_session_end(now, market, asset_type)
        if last_session_end and now.time() > last_session_end:
            return get_next_trading_day(today, market)
    
    return today


def is_trading_day(date: Union[datetime.date, datetime.datetime, str], market: str = "CN") -> bool:
    """
    判断指定日期是否为交易日
    
    Args:
        date: 要检查的日期，可以是date对象、datetime对象或字符串
        market: 市场代码
        
    Returns:
        bool: 是否为交易日
    """
    # 将输入转换为date对象
    if isinstance(date, str):
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    elif isinstance(date, datetime.datetime):
        date = date.date()
    
    # 周末不是交易日
    if date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    
    # 节假日不是交易日
    if market in MARKET_HOLIDAYS and date in MARKET_HOLIDAYS[market]:
        return False
    
    return True


def is_trading_time(dt: Union[datetime.datetime, str], 
                   market: str = "CN", 
                   asset_type: str = "stock",
                   session_type: Optional[str] = None) -> bool:
    """
    判断指定时间是否在交易时间内
    
    Args:
        dt: 要检查的时间，可以是datetime对象或字符串
        market: 市场代码
        asset_type: 资产类型
        session_type: 交易时段类型，如day(日盘)、night(夜盘)，默认为None表示检查所有时段
        
    Returns:
        bool: 是否在交易时间内
    """
    # 将输入转换为datetime对象
    if isinstance(dt, str):
        dt = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
    
    # 检查是否为交易日
    if not is_trading_day(dt.date(), market):
        return False
    
    # 获取当前市场和资产类型的交易时段
    sessions = get_trading_sessions(market, asset_type, session_type)
    
    # 检查当前时间是否在任何一个交易时段内
    current_time = dt.time()
    for session in sessions:
        start_time = datetime.datetime.strptime(session["start"], "%H:%M:%S").time()
        end_time = datetime.datetime.strptime(session["end"], "%H:%M:%S").time()
        
        if start_time <= current_time <= end_time:
            return True
    
    return False


def get_trading_sessions(market: str, 
                        asset_type: str, 
                        session_type: Optional[str] = None) -> List[Dict[str, str]]:
    """
    获取指定市场和资产类型的交易时段
    
    Args:
        market: 市场代码
        asset_type: 资产类型
        session_type: 交易时段类型，如day(日盘)、night(夜盘)，默认为None表示获取所有时段
        
    Returns:
        List[Dict[str, str]]: 交易时段列表
    """
    try:
        # 特殊处理期货市场，它有日盘和夜盘之分
        if asset_type == "future" and market in DEFAULT_TRADING_HOURS[asset_type]:
            if session_type and session_type in DEFAULT_TRADING_HOURS[asset_type][market]:
                return DEFAULT_TRADING_HOURS[asset_type][market][session_type]
            elif not session_type:
                # 返回所有时段
                all_sessions = []
                for sessions in DEFAULT_TRADING_HOURS[asset_type][market].values():
                    all_sessions.extend(sessions)
                return all_sessions
        
        # 一般处理
        elif asset_type in DEFAULT_TRADING_HOURS and market in DEFAULT_TRADING_HOURS[asset_type]:
            return DEFAULT_TRADING_HOURS[asset_type][market]
        
        # 加密货币处理（全球24小时交易）
        elif asset_type == "crypto":
            return DEFAULT_TRADING_HOURS[asset_type]["global"]
        
        # 默认返回空列表
        return []
    
    except KeyError:
        logger.warning(f"未找到市场 {market} 和资产类型 {asset_type} 的交易时段配置")
        return []


def get_last_trading_session_end(dt: datetime.datetime, 
                               market: str, 
                               asset_type: str) -> Optional[datetime.time]:
    """
    获取指定日期最后一个交易时段的结束时间
    
    Args:
        dt: 日期时间
        market: 市场代码
        asset_type: 资产类型
        
    Returns:
        time: 最后一个交易时段的结束时间，如果没有交易时段则返回None
    """
    sessions = get_trading_sessions(market, asset_type)
    if not sessions:
        return None
    
    # 找出最晚的结束时间
    latest_end = datetime.datetime.strptime("00:00:00", "%H:%M:%S").time()
    for session in sessions:
        end_time = datetime.datetime.strptime(session["end"], "%H:%M:%S").time()
        if end_time > latest_end:
            latest_end = end_time
    
    return latest_end


def get_next_trading_day(date: Union[datetime.date, datetime.datetime, str], 
                        market: str = "CN") -> datetime.date:
    """
    获取指定日期之后的下一个交易日
    
    Args:
        date: 起始日期
        market: 市场代码
        
    Returns:
        date: 下一个交易日
    """
    # 将输入转换为date对象
    if isinstance(date, str):
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    elif isinstance(date, datetime.datetime):
        date = date.date()
    
    # 从下一天开始查找交易日
    next_day = date + datetime.timedelta(days=1)
    while not is_trading_day(next_day, market):
        next_day += datetime.timedelta(days=1)
    
    return next_day


def get_previous_trading_day(date: Union[datetime.date, datetime.datetime, str], 
                           market: str = "CN") -> datetime.date:
    """
    获取指定日期之前的上一个交易日
    
    Args:
        date: 起始日期
        market: 市场代码
        
    Returns:
        date: 上一个交易日
    """
    # 将输入转换为date对象
    if isinstance(date, str):
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    elif isinstance(date, datetime.datetime):
        date = date.date()
    
    # 从前一天开始查找交易日
    prev_day = date - datetime.timedelta(days=1)
    while not is_trading_day(prev_day, market):
        prev_day -= datetime.timedelta(days=1)
    
    return prev_day


def get_trading_days_between(start_date: Union[datetime.date, datetime.datetime, str],
                          end_date: Union[datetime.date, datetime.datetime, str],
                          market: str = "CN") -> List[datetime.date]:
    """
    获取两个日期之间的所有交易日
    
    Args:
        start_date: 开始日期（包含）
        end_date: 结束日期（包含）
        market: 市场代码
        
    Returns:
        List[date]: 交易日列表
    """
    # 将输入转换为date对象
    if isinstance(start_date, str):
        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    elif isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    
    if isinstance(end_date, str):
        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    elif isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    
    # 验证日期范围
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    
    # 获取范围内的所有交易日
    trading_days = []
    current_date = start_date
    while current_date <= end_date:
        if is_trading_day(current_date, market):
            trading_days.append(current_date)
        current_date += datetime.timedelta(days=1)
    
    return trading_days


def get_timezone_for_market(market: str) -> str:
    """
    获取指定市场的时区
    
    Args:
        market: 市场代码
        
    Returns:
        str: 时区名称
    """
    market_timezones = {
        "CN": "Asia/Shanghai",
        "HK": "Asia/Hong_Kong",
        "US": "America/New_York",
        "UK": "Europe/London",
        "JP": "Asia/Tokyo",
        "EU": "Europe/Paris",
        # 可以添加更多市场的时区
    }
    
    return market_timezones.get(market, "UTC")


def convert_timezone(dt: datetime.datetime, 
                   from_timezone: str, 
                   to_timezone: str) -> datetime.datetime:
    """
    将时间从一个时区转换到另一个时区
    
    Args:
        dt: 要转换的时间
        from_timezone: 源时区
        to_timezone: 目标时区
        
    Returns:
        datetime: 转换后的时间
    """
    # 确保时间带有时区信息
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.timezone(from_timezone))
    
    # 转换到目标时区
    return dt.astimezone(pytz.timezone(to_timezone))


def time_delta_in_trading_hours(start_dt: datetime.datetime,
                              end_dt: datetime.datetime,
                              market: str = "CN",
                              asset_type: str = "stock") -> datetime.timedelta:
    """
    计算交易时间内的时间差
    (仅计算交易日的交易时段内的时间)
    
    Args:
        start_dt: 开始时间
        end_dt: 结束时间
        market: 市场代码
        asset_type: 资产类型
        
    Returns:
        timedelta: 交易时间内的时间差
    """
    if start_dt > end_dt:
        raise ValueError("开始时间不能晚于结束时间")
    
    # 确保时间在同一时区
    start_tz = start_dt.tzinfo
    end_tz = end_dt.tzinfo
    if start_tz != end_tz:
        if start_tz is None:
            start_dt = start_dt.replace(tzinfo=pytz.timezone(get_timezone_for_market(market)))
        if end_tz is None:
            end_dt = end_dt.replace(tzinfo=pytz.timezone(get_timezone_for_market(market)))
        end_dt = end_dt.astimezone(start_dt.tzinfo)
    
    # 获取交易时段
    trading_sessions = get_trading_sessions(market, asset_type)
    if not trading_sessions:
        return datetime.timedelta()
    
    # 将交易时段转换为datetime
    def _time_to_delta(time_str):
        time_obj = datetime.datetime.strptime(time_str, "%H:%M:%S").time()
        return datetime.timedelta(hours=time_obj.hour, minutes=time_obj.minute, seconds=time_obj.second)
    
    # 计算每个交易日的交易时长
    sessions_duration = datetime.timedelta()
    for session in trading_sessions:
        start_delta = _time_to_delta(session["start"])
        end_delta = _time_to_delta(session["end"])
        sessions_duration += (end_delta - start_delta)
    
    # 如果开始和结束时间在同一天
    if start_dt.date() == end_dt.date():
        if not is_trading_day(start_dt.date(), market):
            return datetime.timedelta()
        
        # 计算交易时段内的重叠时间
        overlap = datetime.timedelta()
        start_time = start_dt.time()
        end_time = end_dt.time()
        
        for session in trading_sessions:
            session_start = datetime.datetime.strptime(session["start"], "%H:%M:%S").time()
            session_end = datetime.datetime.strptime(session["end"], "%H:%M:%S").time()
            
            # 检查是否有重叠
            if end_time <= session_start or start_time >= session_end:
                continue
            
            # 计算重叠部分
            overlap_start = max(start_time, session_start)
            overlap_end = min(end_time, session_end)
            
            overlap_start_delta = datetime.timedelta(hours=overlap_start.hour, 
                                                  minutes=overlap_start.minute, 
                                                  seconds=overlap_start.second)
            overlap_end_delta = datetime.timedelta(hours=overlap_end.hour, 
                                                minutes=overlap_end.minute, 
                                                seconds=overlap_end.second)
            
            overlap += (overlap_end_delta - overlap_start_delta)
        
        return overlap
    
    # 如果跨越多天
    total_duration = datetime.timedelta()
    
    # 第一天的交易时间
    if is_trading_day(start_dt.date(), market):
        for session in trading_sessions:
            session_start = datetime.datetime.strptime(session["start"], "%H:%M:%S").time()
            session_end = datetime.datetime.strptime(session["end"], "%H:%M:%S").time()
            
            if start_dt.time() <= session_end:
                overlap_start = max(start_dt.time(), session_start)
                overlap_start_delta = datetime.timedelta(hours=overlap_start.hour, 
                                                      minutes=overlap_start.minute, 
                                                      seconds=overlap_start.second)
                session_end_delta = datetime.timedelta(hours=session_end.hour, 
                                                    minutes=session_end.minute, 
                                                    seconds=session_end.second)
                
                total_duration += (session_end_delta - overlap_start_delta)
    
    # 中间的完整交易日
    current_date = start_dt.date() + datetime.timedelta(days=1)
    while current_date < end_dt.date():
        if is_trading_day(current_date, market):
            total_duration += sessions_duration
        current_date += datetime.timedelta(days=1)
    
    # 最后一天的交易时间
    if is_trading_day(end_dt.date(), market):
        for session in trading_sessions:
            session_start = datetime.datetime.strptime(session["start"], "%H:%M:%S").time()
            session_end = datetime.datetime.strptime(session["end"], "%H:%M:%S").time()
            
            if end_dt.time() >= session_start:
                overlap_end = min(end_dt.time(), session_end)
                session_start_delta = datetime.timedelta(hours=session_start.hour, 
                                                      minutes=session_start.minute, 
                                                      seconds=session_start.second)
                overlap_end_delta = datetime.timedelta(hours=overlap_end.hour, 
                                                    minutes=overlap_end.minute, 
                                                    seconds=overlap_end.second)
                
                total_duration += (overlap_end_delta - session_start_delta)
    
    return total_duration


def get_session_start_end(market: str, 
                        asset_type: str, 
                        date: Optional[Union[datetime.date, datetime.datetime, str]] = None) -> List[Tuple[datetime.datetime, datetime.datetime]]:
    """
    获取指定日期的交易时段开始和结束时间
    
    Args:
        market: 市场代码
        asset_type: 资产类型
        date: 日期，默认为今天
        
    Returns:
        List[Tuple[datetime, datetime]]: 交易时段的开始和结束时间列表
    """
    # 处理日期参数
    if date is None:
        date = datetime.date.today()
    elif isinstance(date, str):
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    elif isinstance(date, datetime.datetime):
        date = date.date()
    
    # 检查是否为交易日
    if not is_trading_day(date, market):
        return []
    
    # 获取交易时段
    sessions = get_trading_sessions(market, asset_type)
    if not sessions:
        return []
    
    # 转换为datetime对象
    result = []
    for session in sessions:
        start_time = datetime.datetime.strptime(session["start"], "%H:%M:%S").time()
        end_time = datetime.datetime.strptime(session["end"], "%H:%M:%S").time()
        
        start_dt = datetime.datetime.combine(date, start_time)
        end_dt = datetime.datetime.combine(date, end_time)
        
        # 为时间添加时区信息
        tz = pytz.timezone(get_timezone_for_market(market))
        start_dt = tz.localize(start_dt)
        end_dt = tz.localize(end_dt)
        
        result.append((start_dt, end_dt))
    
    return result


def get_market_status(market: str, asset_type: str) -> str:
    """
    获取市场当前状态
    
    Args:
        market: 市场代码
        asset_type: 资产类型
        
    Returns:
        str: 市场状态，可能的值为
             - "pre_market": 盘前
             - "trading": 交易中
             - "post_market": 盘后
             - "closed": 休市
    """
    now = get_current_time(get_timezone_for_market(market))
    today = now.date()
    
    # 检查是否为交易日
    if not is_trading_day(today, market):
        return "closed"
    
    # 获取交易时段
    sessions = get_trading_sessions(market, asset_type)
    if not sessions:
        return "closed"
    
    # 排序交易时段
    sessions = sorted(sessions, key=lambda x: datetime.datetime.strptime(x["start"], "%H:%M:%S").time())
    
    # 第一个交易时段的开始时间
    first_session_start = datetime.datetime.strptime(sessions[0]["start"], "%H:%M:%S").time()
    
    # 最后一个交易时段的结束时间
    last_session_end = datetime.datetime.strptime(sessions[-1]["end"], "%H:%M:%S").time()
    
    current_time = now.time()
    
    # 检查是否在盘前
    if current_time < first_session_start:
        return "pre_market"
    
    # 检查是否在交易中
    for session in sessions:
        start_time = datetime.datetime.strptime(session["start"], "%H:%M:%S").time()
        end_time = datetime.datetime.strptime(session["end"], "%H:%M:%S").time()
        
        if start_time <= current_time <= end_time:
            return "trading"
    
    # 检查是否在盘后
    if current_time > last_session_end:
        return "post_market"
    
    # 检查是否在交易时段之间的休息时间
    for i in range(len(sessions) - 1):
        current_session_end = datetime.datetime.strptime(sessions[i]["end"], "%H:%M:%S").time()
        next_session_start = datetime.datetime.strptime(sessions[i + 1]["start"], "%H:%M:%S").time()
        
        if current_session_end < current_time < next_session_start:
            return "trading_break"
    
    return "closed"