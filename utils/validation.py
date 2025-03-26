#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 数据验证工具

提供数据验证和校验的工具函数，包括：
- 基本数据类型验证
- 交易相关数据验证
- 配置验证
- Schema验证
- 自定义验证规则
- 错误收集和报告

Data validation utilities for FST framework:
- Basic data type validation
- Trading data validation
- Configuration validation
- Schema validation
- Custom validation rules
- Error collection and reporting
"""

import re
import json
import decimal
from typing import Any, Dict, List, Optional, Union, Callable, Tuple, Set
from datetime import datetime, date, time
from decimal import Decimal
from enum import Enum


class ValidationError:
    """验证错误信息"""
    
    def __init__(self, field: str, message: str, code: str = None):
        """
        初始化验证错误
        
        Args:
            field: 字段名
            message: 错误消息
            code: 错误代码
        """
        self.field = field
        self.message = message
        self.code = code
        
    def __str__(self) -> str:
        return f"{self.field}: {self.message}"
        
    def to_dict(self) -> Dict[str, str]:
        """转换为字典格式"""
        return {
            'field': self.field,
            'message': self.message,
            'code': self.code
        }


class ValidationResult:
    """验证结果"""
    
    def __init__(self):
        """初始化验证结果"""
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        
    def add_error(self, field: str, message: str, code: str = None):
        """添加错误"""
        self.errors.append(ValidationError(field, message, code))
        
    def add_warning(self, field: str, message: str, code: str = None):
        """添加警告"""
        self.warnings.append(ValidationError(field, message, code))
        
    @property
    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0
        
    @property
    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0
        
    def __str__(self) -> str:
        parts = []
        if self.errors:
            parts.append("Errors:")
            parts.extend(f"  - {error}" for error in self.errors)
        if self.warnings:
            parts.append("Warnings:")
            parts.extend(f"  - {warning}" for warning in self.warnings)
        return "\n".join(parts) if parts else "Valid"


class Validator:
    """验证器基类"""
    
    def __init__(self, field: str = None, message: str = None):
        """
        初始化验证器
        
        Args:
            field: 字段名
            message: 自定义错误消息
        """
        self.field = field
        self.message = message
        
    def __call__(self, value: Any) -> Optional[str]:
        """
        执行验证
        
        Args:
            value: 要验证的值
            
        Returns:
            Optional[str]: 错误消息，None表示验证通过
        """
        raise NotImplementedError()


# 基本数据类型验证器
class Required(Validator):
    """必填验证器"""
    
    def __call__(self, value: Any) -> Optional[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return self.message or "此字段不能为空"
        return None


class TypeValidator(Validator):
    """类型验证器"""
    
    def __init__(self, type_: type, field: str = None, message: str = None):
        """
        初始化类型验证器
        
        Args:
            type_: 期望的类型
            field: 字段名
            message: 自定义错误消息
        """
        super().__init__(field, message)
        self.type = type_
        
    def __call__(self, value: Any) -> Optional[str]:
        if value is not None and not isinstance(value, self.type):
            return self.message or f"类型必须是 {self.type.__name__}"
        return None


class Range(Validator):
    """范围验证器"""
    
    def __init__(self, 
                min_value: Optional[Union[int, float]] = None,
                max_value: Optional[Union[int, float]] = None,
                field: str = None,
                message: str = None):
        """
        初始化范围验证器
        
        Args:
            min_value: 最小值
            max_value: 最大值
            field: 字段名
            message: 自定义错误消息
        """
        super().__init__(field, message)
        self.min_value = min_value
        self.max_value = max_value
        
    def __call__(self, value: Union[int, float]) -> Optional[str]:
        if value is None:
            return None
            
        if self.min_value is not None and value < self.min_value:
            return self.message or f"值必须大于等于 {self.min_value}"
            
        if self.max_value is not None and value > self.max_value:
            return self.message or f"值必须小于等于 {self.max_value}"
            
        return None


class Length(Validator):
    """长度验证器"""
    
    def __init__(self, 
                min_length: Optional[int] = None,
                max_length: Optional[int] = None,
                field: str = None,
                message: str = None):
        """
        初始化长度验证器
        
        Args:
            min_length: 最小长度
            max_length: 最大长度
            field: 字段名
            message: 自定义错误消息
        """
        super().__init__(field, message)
        self.min_length = min_length
        self.max_length = max_length
        
    def __call__(self, value: Union[str, List, Dict]) -> Optional[str]:
        if value is None:
            return None
            
        length = len(value)
        
        if self.min_length is not None and length < self.min_length:
            return self.message or f"长度必须大于等于 {self.min_length}"
            
        if self.max_length is not None and length > self.max_length:
            return self.message or f"长度必须小于等于 {self.max_length}"
            
        return None


class Pattern(Validator):
    """正则表达式验证器"""
    
    def __init__(self, pattern: str, field: str = None, message: str = None):
        """
        初始化正则验证器
        
        Args:
            pattern: 正则表达式
            field: 字段名
            message: 自定义错误消息
        """
        super().__init__(field, message)
        self.pattern = re.compile(pattern)
        
    def __call__(self, value: str) -> Optional[str]:
        if value is not None and not self.pattern.match(value):
            return self.message or "格式不正确"
        return None


# 交易相关验证器
class PriceValidator(Validator):
    """价格验证器"""
    
    def __init__(self, 
                min_price: Optional[Decimal] = None,
                max_price: Optional[Decimal] = None,
                field: str = None,
                message: str = None):
        """
        初始化价格验证器
        
        Args:
            min_price: 最小价格
            max_price: 最大价格
            field: 字段名
            message: 自定义错误消息
        """
        super().__init__(field, message)
        self.min_price = min_price
        self.max_price = max_price
        
    def __call__(self, value: Union[Decimal, float, str]) -> Optional[str]:
        if value is None:
            return None
            
        try:
            # 转换为Decimal
            if not isinstance(value, Decimal):
                value = Decimal(str(value))
                
            # 检查是否为正数
            if value <= 0:
                return self.message or "价格必须大于0"
                
            # 检查范围
            if self.min_price is not None and value < self.min_price:
                return self.message or f"价格必须大于等于 {self.min_price}"
                
            if self.max_price is not None and value > self.max_price:
                return self.message or f"价格必须小于等于 {self.max_price}"
                
        except decimal.InvalidOperation:
            return self.message or "无效的价格格式"
            
        return None


class VolumeValidator(Validator):
    """交易量验证器"""
    
    def __init__(self, 
                min_volume: Optional[int] = None,
                max_volume: Optional[int] = None,
                field: str = None,
                message: str = None):
        """
        初始化交易量验证器
        
        Args:
            min_volume: 最小交易量
            max_volume: 最大交易量
            field: 字段名
            message: 自定义错误消息
        """
        super().__init__(field, message)
        self.min_volume = min_volume
        self.max_volume = max_volume
        
    def __call__(self, value: Union[int, float]) -> Optional[str]:
        if value is None:
            return None
            
        try:
            # 确保是整数
            volume = int(value)
            
            # 检查是否为正数
            if volume <= 0:
                return self.message or "交易量必须大于0"
                
            # 检查范围
            if self.min_volume is not None and volume < self.min_volume:
                return self.message or f"交易量必须大于等于 {self.min_volume}"
                
            if self.max_volume is not None and volume > self.max_volume:
                return self.message or f"交易量必须小于等于 {self.max_volume}"
                
        except (ValueError, TypeError):
            return self.message or "无效的交易量格式"
            
        return None


class SymbolValidator(Validator):
    """交易品种代码验证器"""
    
    def __init__(self, 
                allowed_markets: Optional[Set[str]] = None,
                pattern: str = r'^[A-Za-z0-9.]{2,30}$',
                field: str = None,
                message: str = None):
        """
        初始化交易品种验证器
        
        Args:
            allowed_markets: 允许的市场代码集合
            pattern: 代码格式正则表达式
            field: 字段名
            message: 自定义错误消息
        """
        super().__init__(field, message)
        self.allowed_markets = allowed_markets
        self.pattern = re.compile(pattern)
        
    def __call__(self, value: str) -> Optional[str]:
        if value is None:
            return None
            
        # 检查格式
        if not self.pattern.match(value):
            return self.message or "无效的交易品种代码格式"
            
        # 检查市场
        if self.allowed_markets:
            market = value.split('.')[0] if '.' in value else None
            if market and market not in self.allowed_markets:
                return self.message or f"不支持的市场: {market}"
                
        return None


# Schema验证
class SchemaValidator:
    """Schema验证器"""
    
    def __init__(self, schema: Dict[str, List[Validator]]):
        """
        初始化Schema验证器
        
        Args:
            schema: 验证规则字典，键为字段名，值为验证器列表
        """
        self.schema = schema
        
    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """
        验证数据
        
        Args:
            data: 要验证的数据字典
            
        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult()
        
        # 验证每个字段
        for field, validators in self.schema.items():
            value = data.get(field)
            
            for validator in validators:
                # 设置字段名
                validator.field = field
                
                # 执行验证
                error = validator(value)
                if error:
                    result.add_error(field, error)
                    break  # 一个字段出错后不再继续验证
                    
        return result


# 配置验证
def validate_config(config: Dict[str, Any], schema: Dict[str, Any]) -> ValidationResult:
    """
    验证配置数据
    
    Args:
        config: 配置数据
        schema: 配置模式
        
    Returns:
        ValidationResult: 验证结果
    """
    result = ValidationResult()
    
    def validate_value(value: Any, schema_value: Any, path: str):
        """递归验证值"""
        
        # 处理基本类型
        if isinstance(schema_value, type):
            if not isinstance(value, schema_value):
                result.add_error(path, f"类型必须是 {schema_value.__name__}")
            return
            
        # 处理字典
        if isinstance(schema_value, dict):
            if not isinstance(value, dict):
                result.add_error(path, "必须是字典类型")
                return
                
            # 验证必需字段
            for key, sub_schema in schema_value.items():
                if key not in value:
                    result.add_error(f"{path}.{key}", "缺少必需字段")
                else:
                    validate_value(value[key], sub_schema, f"{path}.{key}")
                    
            # 检查未知字段
            for key in value:
                if key not in schema_value:
                    result.add_warning(f"{path}.{key}", "未知字段")
                    
        # 处理列表
        elif isinstance(schema_value, list):
            if not isinstance(value, list):
                result.add_error(path, "必须是列表类型")
                return
                
            # 验证列表元素
            if schema_value:
                item_schema = schema_value[0]
                for i, item in enumerate(value):
                    validate_value(item, item_schema, f"{path}[{i}]")
                    
        # 处理元组（用于范围验证）
        elif isinstance(schema_value, tuple):
            if len(schema_value) == 2:
                min_val, max_val = schema_value
                if value < min_val or value > max_val:
                    result.add_error(path, f"值必须在范围 [{min_val}, {max_val}] 内")
                    
    # 开始验证
    validate_value(config, schema, "root")
    return result


# 辅助函数
def is_valid_email(email: str) -> bool:
    """
    验证邮箱格式
    
    Args:
        email: 邮箱地址
        
    Returns:
        bool: 是否有效
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_phone(phone: str) -> bool:
    """
    验证手机号格式（中国大陆）
    
    Args:
        phone: 手机号
        
    Returns:
        bool: 是否有效
    """
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


def is_valid_date(date_str: str, fmt: str = '%Y-%m-%d') -> bool:
    """
    验证日期格式
    
    Args:
        date_str: 日期字符串
        fmt: 日期格式
        
    Returns:
        bool: 是否有效
    """
    try:
        datetime.strptime(date_str, fmt)
        return True
    except ValueError:
        return False


def is_valid_time(time_str: str, fmt: str = '%H:%M:%S') -> bool:
    """
    验证时间格式
    
    Args:
        time_str: 时间字符串
        fmt: 时间格式
        
    Returns:
        bool: 是否有效
    """
    try:
        datetime.strptime(time_str, fmt)
        return True
    except ValueError:
        return False


def is_valid_json(json_str: str) -> bool:
    """
    验证JSON格式
    
    Args:
        json_str: JSON字符串
        
    Returns:
        bool: 是否有效
    """
    try:
        json.loads(json_str)
        return True
    except ValueError:
        return False


def is_chinese_id_card(id_card: str) -> bool:
    """
    验证中国身份证号
    
    Args:
        id_card: 身份证号
        
    Returns:
        bool: 是否有效
    """
    # 18位身份证号码验证
    if len(id_card) != 18:
        return False
        
    # 验证格式
    pattern = r'^\d{17}[\dXx]$'
    if not re.match(pattern, id_card):
        return False
        
    # 验证校验码
    factors = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    verify_code = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
    
    # 计算校验码
    sum_ = 0
    for i in range(17):
        sum_ += int(id_card[i]) * factors[i]
    
    # 验证校验码
    if verify_code[sum_ % 11].upper() != id_card[-1].upper():
        return False
        
    return True


def validate_trading_time(time_str: str, trading_periods: List[Tuple[str, str]]) -> bool:
    """
    验证交易时间
    
    Args:
        time_str: 时间字符串（格式：HH:MM:SS）
        trading_periods: 交易时段列表，每个元素为(start_time, end_time)元组
        
    Returns:
        bool: 是否在交易时段内
    """
    try:
        current_time = datetime.strptime(time_str, '%H:%M:%S').time()
        
        for start_str, end_str in trading_periods:
            start_time = datetime.strptime(start_str, '%H:%M:%S').time()
            end_time = datetime.strptime(end_str, '%H:%M:%S').time()
            
            if start_time <= current_time <= end_time:
                return True
                
        return False
        
    except ValueError:
        return False