#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 插件钩子

定义系统中可用的所有插件钩子点，插件通过这些钩子点扩展系统功能。
每个钩子点具有明确的接口契约和执行上下文，用于保证插件的正确集成。
"""

import inspect
import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# 日志配置
logger = logging.getLogger("fst.plugins.hooks")


class HookType(str, Enum):
    """钩子类型定义"""
    
    # 系统钩子
    STARTUP = "startup"                    # 系统启动
    SHUTDOWN = "shutdown"                  # 系统关闭
    CONFIG_LOADED = "config_loaded"        # 配置加载完成
    
    # 市场数据钩子
    MARKET_DATA_RECEIVED = "market_data_received"  # 接收到市场数据
    TICK_RECEIVED = "tick_received"        # 接收到Tick数据
    BAR_RECEIVED = "bar_received"          # 接收到K线数据
    BAR_GENERATED = "bar_generated"        # 生成K线数据
    
    # 交易钩子
    PRE_ORDER = "pre_order"                # 下单前
    POST_ORDER = "post_order"              # 下单后
    ORDER_STATUS_CHANGED = "order_status_changed"  # 订单状态变更
    TRADE_EXECUTED = "trade_executed"      # 成交
    POSITION_CHANGED = "position_changed"  # 持仓变化
    ACCOUNT_CHANGED = "account_changed"    # 账户变化
    
    # 策略钩子
    PRE_STRATEGY_INIT = "pre_strategy_init"  # 策略初始化前
    POST_STRATEGY_INIT = "post_strategy_init"  # 策略初始化后
    PRE_STRATEGY_START = "pre_strategy_start"  # 策略启动前
    POST_STRATEGY_START = "post_strategy_start"  # 策略启动后
    PRE_STRATEGY_STOP = "pre_strategy_stop"  # 策略停止前
    POST_STRATEGY_STOP = "post_strategy_stop"  # 策略停止后
    STRATEGY_ERROR = "strategy_error"      # 策略错误
    
    # 风控钩子
    RISK_CHECK = "risk_check"              # 风控检查
    RISK_RULE_TRIGGERED = "risk_rule_triggered"  # 风控规则触发
    POSITION_RISK = "position_risk"        # 持仓风险
    
    # 性能分析钩子
    PERFORMANCE_STATS = "performance_stats"  # 性能统计
    
    # 数据存储钩子
    PRE_PERSIST = "pre_persist"            # 数据持久化前
    POST_PERSIST = "post_persist"          # 数据持久化后
    DATA_LOADED = "data_loaded"            # 数据加载
    
    # UI钩子
    UI_REFRESH = "ui_refresh"              # UI刷新
    UI_EVENT = "ui_event"                  # UI事件
    
    # 自定义钩子
    CUSTOM = "custom"                      # 自定义钩子


class HookSpecification:
    """
    钩子规范定义
    
    定义钩子的接口规范，包括参数、返回值和执行模式。
    """
    
    def __init__(self, 
                hook_type: HookType,
                name: str,
                description: str,
                parameters: List[str] = None,
                return_type: Optional[type] = None,
                async_execution: bool = False,
                sequential: bool = True,
                required: bool = False):
        """
        初始化钩子规范
        
        Args:
            hook_type: 钩子类型
            name: 钩子名称
            description: 钩子描述
            parameters: 参数列表
            return_type: 返回值类型
            async_execution: 是否异步执行
            sequential: 是否顺序执行多个处理器
            required: 是否为必需钩子
        """
        self.hook_type = hook_type if isinstance(hook_type, HookType) else HookType(hook_type)
        self.name = name
        self.description = description
        self.parameters = parameters or []
        self.return_type = return_type
        self.async_execution = async_execution
        self.sequential = sequential
        self.required = required
        
    def validate_handler(self, handler: Callable) -> bool:
        """
        验证处理器是否符合规范
        
        Args:
            handler: 要验证的处理器函数
            
        Returns:
            bool: 是否有效
        """
        try:
            # 获取函数签名
            sig = inspect.signature(handler)
            params = list(sig.parameters.keys())
            
            # 检查参数数量
            if len(params) != len(self.parameters):
                logger.warning(f"处理器 {handler.__name__} 参数数量不匹配: 期望 {len(self.parameters)}, 实际 {len(params)}")
                return False
            
            # 验证返回值类型（运行时无法完全验证）
            # 这里只是简单验证有无返回值
            if self.return_type is not None and sig.return_annotation is inspect.Signature.empty:
                logger.warning(f"处理器 {handler.__name__} 未指定返回值类型")
            
            return True
        except Exception as e:
            logger.error(f"验证处理器 {handler.__name__} 时出错: {str(e)}")
            return False
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.name}({', '.join(self.parameters)})"


class HookContext:
    """
    钩子执行上下文
    
    包含钩子执行的相关信息和数据。
    """
    
    def __init__(self,
                hook_spec: HookSpecification,
                args: Tuple[Any, ...] = None,
                kwargs: Dict[str, Any] = None,
                source: str = None,
                metadata: Dict[str, Any] = None):
        """
        初始化钩子上下文
        
        Args:
            hook_spec: 钩子规范
            args: 位置参数
            kwargs: 关键字参数
            source: 来源标识
            metadata: 元数据
        """
        self.hook_spec = hook_spec
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.source = source
        self.metadata = metadata or {}
        self.results = []
        self.error = None
        
    def add_result(self, result: Any):
        """添加执行结果"""
        self.results.append(result)
        
    def set_error(self, error: Exception):
        """设置错误信息"""
        self.error = error


class HookRegistry:
    """
    钩子注册表
    
    管理系统中所有已注册的钩子和处理器。
    """
    
    def __init__(self):
        """初始化钩子注册表"""
        self._specs = {}  # name -> HookSpecification
        self._handlers = {}  # name -> [handler]
        
    def register_spec(self, spec: HookSpecification) -> bool:
        """
        注册钩子规范
        
        Args:
            spec: 钩子规范
            
        Returns:
            bool: 是否注册成功
        """
        if spec.name in self._specs:
            logger.warning(f"钩子规范 {spec.name} 已存在，将被覆盖")
            
        self._specs[spec.name] = spec
        
        # 确保处理器列表存在
        if spec.name not in self._handlers:
            self._handlers[spec.name] = []
            
        logger.debug(f"注册钩子规范: {spec.name}")
        return True
    
    def register_handler(self, 
                       hook_name: str, 
                       handler: Callable,
                       priority: int = 100) -> bool:
        """
        注册钩子处理器
        
        Args:
            hook_name: 钩子名称
            handler: 处理器函数
            priority: 优先级（值越小优先级越高）
            
        Returns:
            bool: 是否注册成功
        """
        # 检查钩子是否已定义
        if hook_name not in self._specs:
            logger.warning(f"钩子 {hook_name} 未定义，无法注册处理器")
            return False
            
        # 验证处理器是否符合规范
        spec = self._specs[hook_name]
        if not spec.validate_handler(handler):
            logger.warning(f"处理器 {handler.__name__} 不符合钩子 {hook_name} 的规范")
            return False
            
        # 确保处理器列表存在
        if hook_name not in self._handlers:
            self._handlers[hook_name] = []
            
        # 添加处理器和优先级
        handler_info = {
            'handler': handler,
            'priority': priority,
            'name': handler.__name__
        }
        
        # 避免重复添加
        for existing in self._handlers[hook_name]:
            if existing['handler'] == handler:
                logger.warning(f"处理器 {handler.__name__} 已注册到钩子 {hook_name}，将更新优先级")
                existing['priority'] = priority
                return True
                
        # 添加新处理器
        self._handlers[hook_name].append(handler_info)
        
        # 按优先级排序
        self._handlers[hook_name].sort(key=lambda x: x['priority'])
        
        logger.debug(f"注册处理器: {handler.__name__} -> {hook_name} (优先级: {priority})")
        return True
    
    def unregister_handler(self, hook_name: str, handler: Callable) -> bool:
        """
        取消注册钩子处理器
        
        Args:
            hook_name: 钩子名称
            handler: 处理器函数
            
        Returns:
            bool: 是否取消成功
        """
        # 检查钩子是否存在
        if hook_name not in self._handlers:
            logger.warning(f"钩子 {hook_name} 未注册处理器")
            return False
            
        # 查找处理器
        for i, handler_info in enumerate(self._handlers[hook_name]):
            if handler_info['handler'] == handler:
                # 移除处理器
                del self._handlers[hook_name][i]
                logger.debug(f"取消注册处理器: {handler.__name__} -> {hook_name}")
                return True
                
        logger.warning(f"处理器 {handler.__name__} 未注册到钩子 {hook_name}")
        return False
    
    def get_spec(self, hook_name: str) -> Optional[HookSpecification]:
        """获取钩子规范"""
        return self._specs.get(hook_name)
    
    def get_handlers(self, hook_name: str) -> List[Dict[str, Any]]:
        """获取钩子处理器列表"""
        return self._handlers.get(hook_name, []).copy()
    
    def get_all_specs(self) -> Dict[str, HookSpecification]:
        """获取所有钩子规范"""
        return self._specs.copy()
    
    def list_hooks(self) -> List[str]:
        """列出所有钩子名称"""
        return list(self._specs.keys())
    
    def clear(self):
        """清除所有注册的钩子和处理器"""
        self._specs.clear()
        self._handlers.clear()
        logger.debug("清除所有钩子和处理器")


# 创建全局钩子注册表
_hook_registry = HookRegistry()

def get_hook_registry() -> HookRegistry:
    """获取全局钩子注册表"""
    return _hook_registry


# 预定义系统钩子

# 系统钩子
def define_system_hooks():
    """定义系统钩子"""
    registry = get_hook_registry()
    
    # 系统启动
    registry.register_spec(HookSpecification(
        hook_type=HookType.STARTUP,
        name="system.startup",
        description="系统启动时调用",
        parameters=["config"],
        sequential=True
    ))
    
    # 系统关闭
    registry.register_spec(HookSpecification(
        hook_type=HookType.SHUTDOWN,
        name="system.shutdown",
        description="系统关闭时调用",
        parameters=["exit_code"],
        sequential=True
    ))
    
    # 配置加载完成
    registry.register_spec(HookSpecification(
        hook_type=HookType.CONFIG_LOADED,
        name="system.config_loaded",
        description="配置加载完成时调用",
        parameters=["config"],
        sequential=True
    ))


# 市场数据钩子
def define_market_data_hooks():
    """定义市场数据钩子"""
    registry = get_hook_registry()
    
    # 接收到市场数据
    registry.register_spec(HookSpecification(
        hook_type=HookType.MARKET_DATA_RECEIVED,
        name="market.data_received",
        description="接收到市场数据时调用",
        parameters=["data", "source"],
        sequential=True
    ))
    
    # 接收到Tick数据
    registry.register_spec(HookSpecification(
        hook_type=HookType.TICK_RECEIVED,
        name="market.tick_received",
        description="接收到Tick数据时调用",
        parameters=["tick", "symbol"],
        sequential=False,
        async_execution=True
    ))
    
    # 接收到K线数据
    registry.register_spec(HookSpecification(
        hook_type=HookType.BAR_RECEIVED,
        name="market.bar_received",
        description="接收到K线数据时调用",
        parameters=["bar", "symbol", "period"],
        sequential=False,
        async_execution=True
    ))
    
    # 生成K线数据
    registry.register_spec(HookSpecification(
        hook_type=HookType.BAR_GENERATED,
        name="market.bar_generated",
        description="生成K线数据时调用",
        parameters=["bar", "symbol", "period"],
        sequential=True
    ))


# 交易钩子
def define_trading_hooks():
    """定义交易钩子"""
    registry = get_hook_registry()
    
    # 下单前
    registry.register_spec(HookSpecification(
        hook_type=HookType.PRE_ORDER,
        name="trading.pre_order",
        description="下单前调用，可以修改或取消订单",
        parameters=["order", "account"],
        return_type=bool,
        sequential=True
    ))
    
    # 下单后
    registry.register_spec(HookSpecification(
        hook_type=HookType.POST_ORDER,
        name="trading.post_order",
        description="下单后调用，可以进行后续处理",
        parameters=["order", "result"],
        sequential=True
    ))
    
    # 订单状态变更
    registry.register_spec(HookSpecification(
        hook_type=HookType.ORDER_STATUS_CHANGED,
        name="trading.order_status_changed",
        description="订单状态变更时调用",
        parameters=["order", "previous_status", "current_status"],
        sequential=True
    ))
    
    # 成交
    registry.register_spec(HookSpecification(
        hook_type=HookType.TRADE_EXECUTED,
        name="trading.trade_executed",
        description="成交时调用",
        parameters=["trade", "order"],
        sequential=True
    ))
    
    # 持仓变化
    registry.register_spec(HookSpecification(
        hook_type=HookType.POSITION_CHANGED,
        name="trading.position_changed",
        description="持仓变化时调用",
        parameters=["position", "account", "change"],
        sequential=True
    ))
    
    # 账户变化
    registry.register_spec(HookSpecification(
        hook_type=HookType.ACCOUNT_CHANGED,
        name="trading.account_changed",
        description="账户变化时调用",
        parameters=["account", "changes"],
        sequential=True
    ))


# 策略钩子
def define_strategy_hooks():
    """定义策略钩子"""
    registry = get_hook_registry()
    
    # 策略初始化前
    registry.register_spec(HookSpecification(
        hook_type=HookType.PRE_STRATEGY_INIT,
        name="strategy.pre_init",
        description="策略初始化前调用",
        parameters=["strategy", "config"],
        return_type=dict,
        sequential=True
    ))
    
    # 策略初始化后
    registry.register_spec(HookSpecification(
        hook_type=HookType.POST_STRATEGY_INIT,
        name="strategy.post_init",
        description="策略初始化后调用",
        parameters=["strategy"],
        sequential=True
    ))
    
    # 策略启动前
    registry.register_spec(HookSpecification(
        hook_type=HookType.PRE_STRATEGY_START,
        name="strategy.pre_start",
        description="策略启动前调用",
        parameters=["strategy"],
        return_type=bool,
        sequential=True
    ))
    
    # 策略启动后
    registry.register_spec(HookSpecification(
        hook_type=HookType.POST_STRATEGY_START,
        name="strategy.post_start",
        description="策略启动后调用",
        parameters=["strategy"],
        sequential=True
    ))
    
    # 策略停止前
    registry.register_spec(HookSpecification(
        hook_type=HookType.PRE_STRATEGY_STOP,
        name="strategy.pre_stop",
        description="策略停止前调用",
        parameters=["strategy", "reason"],
        return_type=bool,
        sequential=True
    ))
    
    # 策略停止后
    registry.register_spec(HookSpecification(
        hook_type=HookType.POST_STRATEGY_STOP,
        name="strategy.post_stop",
        description="策略停止后调用",
        parameters=["strategy", "stats"],
        sequential=True
    ))
    
    # 策略错误
    registry.register_spec(HookSpecification(
        hook_type=HookType.STRATEGY_ERROR,
        name="strategy.error",
        description="策略发生错误时调用",
        parameters=["strategy", "error", "context"],
        sequential=True
    ))


# 风控钩子
def define_risk_hooks():
    """定义风控钩子"""
    registry = get_hook_registry()
    
    # 风控检查
    registry.register_spec(HookSpecification(
        hook_type=HookType.RISK_CHECK,
        name="risk.check",
        description="风控检查时调用",
        parameters=["context", "account", "positions"],
        return_type=bool,
        sequential=True
    ))
    
    # 风控规则触发
    registry.register_spec(HookSpecification(
        hook_type=HookType.RISK_RULE_TRIGGERED,
        name="risk.rule_triggered",
        description="风控规则触发时调用",
        parameters=["rule", "trigger_value", "account"],
        sequential=True
    ))
    
    # 持仓风险
    registry.register_spec(HookSpecification(
        hook_type=HookType.POSITION_RISK,
        name="risk.position_risk",
        description="持仓风险检查时调用",
        parameters=["position", "account", "risk_metrics"],
        return_type=dict,
        sequential=True
    ))


# 性能分析钩子
def define_performance_hooks():
    """定义性能分析钩子"""
    registry = get_hook_registry()
    
    # 性能统计
    registry.register_spec(HookSpecification(
        hook_type=HookType.PERFORMANCE_STATS,
        name="performance.stats",
        description="性能统计时调用",
        parameters=["stats", "context"],
        return_type=dict,
        sequential=True
    ))


# 数据存储钩子
def define_storage_hooks():
    """定义数据存储钩子"""
    registry = get_hook_registry()
    
    # 数据持久化前
    registry.register_spec(HookSpecification(
        hook_type=HookType.PRE_PERSIST,
        name="storage.pre_persist",
        description="数据持久化前调用",
        parameters=["data", "store_name", "key"],
        return_type=tuple,
        sequential=True
    ))
    
    # 数据持久化后
    registry.register_spec(HookSpecification(
        hook_type=HookType.POST_PERSIST,
        name="storage.post_persist",
        description="数据持久化后调用",
        parameters=["result", "data", "store_name", "key"],
        sequential=True
    ))
    
    # 数据加载
    registry.register_spec(HookSpecification(
        hook_type=HookType.DATA_LOADED,
        name="storage.data_loaded",
        description="数据加载后调用",
        parameters=["data", "store_name", "key"],
        return_type=Any,
        sequential=True
    ))


# UI钩子
def define_ui_hooks():
    """定义UI钩子"""
    registry = get_hook_registry()
    
    # UI刷新
    registry.register_spec(HookSpecification(
        hook_type=HookType.UI_REFRESH,
        name="ui.refresh",
        description="UI刷新时调用",
        parameters=["context", "data"],
        sequential=True
    ))
    
    # UI事件
    registry.register_spec(HookSpecification(
        hook_type=HookType.UI_EVENT,
        name="ui.event",
        description="UI事件发生时调用",
        parameters=["event", "source"],
        sequential=True
    ))


# 定义所有系统钩子
def define_all_hooks():
    """定义所有系统钩子"""
    define_system_hooks()
    define_market_data_hooks()
    define_trading_hooks()
    define_strategy_hooks()
    define_risk_hooks()
    define_performance_hooks()
    define_storage_hooks()
    define_ui_hooks()
    
    logger.debug(f"已定义 {len(get_hook_registry().list_hooks())} 个系统钩子")


# 自动定义所有系统钩子
define_all_hooks()