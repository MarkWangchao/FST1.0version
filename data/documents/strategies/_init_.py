"""
策略文档存储目录

该目录用于存储策略相关的文档数据，包括:
- 交易策略定义
- 策略参数配置
- 策略版本历史
- 策略元数据
- 策略性能特性

当使用文件系统存储（FileDocumentStore）时，
策略文档及其索引、版本历史等将物理存储在此目录中。
"""

# 策略类型常量
STRATEGY_TYPE_TREND_FOLLOWING = "trend_following"      # 趋势跟踪
STRATEGY_TYPE_MEAN_REVERSION = "mean_reversion"        # 均值回归
STRATEGY_TYPE_BREAKOUT = "breakout"                    # 突破
STRATEGY_TYPE_MOMENTUM = "momentum"                    # 动量
STRATEGY_TYPE_STATISTICAL_ARBITRAGE = "stat_arb"       # 统计套利
STRATEGY_TYPE_MACHINE_LEARNING = "machine_learning"    # 机器学习
STRATEGY_TYPE_FUNDAMENTAL = "fundamental"              # 基本面
STRATEGY_TYPE_MARKET_MAKING = "market_making"          # 做市
STRATEGY_TYPE_CUSTOM = "custom"                        # 自定义

# 策略时间框架常量
TIMEFRAME_TICK = "tick"                # 逐笔
TIMEFRAME_SECOND = "1s"                # 1秒
TIMEFRAME_MINUTE = "1m"                # 1分钟
TIMEFRAME_FIVE_MINUTE = "5m"           # 5分钟
TIMEFRAME_FIFTEEN_MINUTE = "15m"       # 15分钟
TIMEFRAME_THIRTY_MINUTE = "30m"        # 30分钟
TIMEFRAME_HOUR = "1h"                  # 1小时
TIMEFRAME_FOUR_HOUR = "4h"             # 4小时
TIMEFRAME_DAY = "1d"                   # 1天
TIMEFRAME_WEEK = "1w"                  # 1周
TIMEFRAME_MONTH = "1M"                 # 1月

# 策略风险级别常量
RISK_LEVEL_CONSERVATIVE = "conservative"   # 保守
RISK_LEVEL_MODERATE = "moderate"           # 适中
RISK_LEVEL_AGGRESSIVE = "aggressive"       # 激进

# 策略状态常量
STRATEGY_STATUS_DEVELOPMENT = "development"    # 开发中
STRATEGY_STATUS_TESTING = "testing"            # 测试中
STRATEGY_STATUS_PRODUCTION = "production"      # 生产中
STRATEGY_STATUS_ARCHIVED = "archived"          # 已归档
STRATEGY_STATUS_DEPRECATED = "deprecated"      # 已弃用

# 导出公共接口
__all__ = [
    # 策略类型
    'STRATEGY_TYPE_TREND_FOLLOWING',
    'STRATEGY_TYPE_MEAN_REVERSION',
    'STRATEGY_TYPE_BREAKOUT',
    'STRATEGY_TYPE_MOMENTUM',
    'STRATEGY_TYPE_STATISTICAL_ARBITRAGE',
    'STRATEGY_TYPE_MACHINE_LEARNING',
    'STRATEGY_TYPE_FUNDAMENTAL',
    'STRATEGY_TYPE_MARKET_MAKING',
    'STRATEGY_TYPE_CUSTOM',
    
    # 策略时间框架
    'TIMEFRAME_TICK',
    'TIMEFRAME_SECOND',
    'TIMEFRAME_MINUTE',
    'TIMEFRAME_FIVE_MINUTE',
    'TIMEFRAME_FIFTEEN_MINUTE',
    'TIMEFRAME_THIRTY_MINUTE',
    'TIMEFRAME_HOUR',
    'TIMEFRAME_FOUR_HOUR',
    'TIMEFRAME_DAY',
    'TIMEFRAME_WEEK',
    'TIMEFRAME_MONTH',
    
    # 策略风险级别
    'RISK_LEVEL_CONSERVATIVE',
    'RISK_LEVEL_MODERATE',
    'RISK_LEVEL_AGGRESSIVE',
    
    # 策略状态
    'STRATEGY_STATUS_DEVELOPMENT',
    'STRATEGY_STATUS_TESTING',
    'STRATEGY_STATUS_PRODUCTION',
    'STRATEGY_STATUS_ARCHIVED',
    'STRATEGY_STATUS_DEPRECATED',
]