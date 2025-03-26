"""
回测文档存储目录

该目录用于存储回测结果相关的文档数据，包括:
- 策略回测结果
- 参数优化结果
- 多策略组合回测
- 回测性能指标
- 回测交易记录

当使用文件系统存储（FileDocumentStore）时，
回测文档及其索引、版本历史等将物理存储在此目录中。
"""

# 回测类型常量
BACKTEST_TYPE_STANDARD = "standard"          # 标准回测
BACKTEST_TYPE_OPTIMIZATION = "optimization"  # 参数优化回测
BACKTEST_TYPE_PORTFOLIO = "portfolio"        # 投资组合回测
BACKTEST_TYPE_WALK_FORWARD = "walk_forward"  # 向前回测
BACKTEST_TYPE_MONTE_CARLO = "monte_carlo"    # 蒙特卡洛回测
BACKTEST_TYPE_EVENT_STUDY = "event_study"    # 事件研究回测

# 回测指标常量
METRIC_SHARPE_RATIO = "sharpe_ratio"         # 夏普比率
METRIC_MAX_DRAWDOWN = "max_drawdown"         # 最大回撤
METRIC_ANNUAL_RETURN = "annual_return"       # 年化收益
METRIC_VOLATILITY = "volatility"             # 波动率
METRIC_SORTINO_RATIO = "sortino_ratio"       # 索提诺比率
METRIC_CALMAR_RATIO = "calmar_ratio"         # 卡玛比率
METRIC_OMEGA_RATIO = "omega_ratio"           # 欧米伽比率
METRIC_WIN_RATE = "win_rate"                 # 胜率
METRIC_PROFIT_FACTOR = "profit_factor"       # 盈亏比

# 导出公共接口
__all__ = [
    # 回测类型
    'BACKTEST_TYPE_STANDARD',
    'BACKTEST_TYPE_OPTIMIZATION',
    'BACKTEST_TYPE_PORTFOLIO',
    'BACKTEST_TYPE_WALK_FORWARD',
    'BACKTEST_TYPE_MONTE_CARLO',
    'BACKTEST_TYPE_EVENT_STUDY',
    
    # 回测指标
    'METRIC_SHARPE_RATIO',
    'METRIC_MAX_DRAWDOWN',
    'METRIC_ANNUAL_RETURN',
    'METRIC_VOLATILITY',
    'METRIC_SORTINO_RATIO',
    'METRIC_CALMAR_RATIO',
    'METRIC_OMEGA_RATIO',
    'METRIC_WIN_RATE',
    'METRIC_PROFIT_FACTOR',
]