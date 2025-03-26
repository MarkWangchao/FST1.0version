"""
回测结果文档结构定义

定义回测结果文档的标准结构，包括:
- 回测基本信息
- 性能指标
- 交易记录
- 权益曲线
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

# 回测结果标准结构
BACKTEST_SCHEMA = {
    "schema_version": "1.0",
    "backtest_info": {
        "id": str,                      # 回测ID
        "type": str,                    # 回测类型
        "strategy_id": str,             # 策略ID
        "strategy_name": str,           # 策略名称
        "start_date": str,              # 开始日期 (ISO格式)
        "end_date": str,                # 结束日期 (ISO格式)
        "created_at": str,              # 创建时间 (ISO格式)
        "created_by": str,              # 创建者
        "description": str,             # 描述
        "status": str,                  # 状态
        "parameters": dict,             # 参数配置
        "instruments": list,            # 交易品种列表
        "timeframe": str,               # 时间框架
        "tags": list                    # 标签列表
    },
    "performance_metrics": {
        "sharpe_ratio": float,          # 夏普比率
        "sortino_ratio": float,         # 索提诺比率
        "calmar_ratio": float,          # 卡尔马比率
        "max_drawdown": float,          # 最大回撤 (%)
        "max_drawdown_duration": int,   # 最大回撤持续时间(天)
        "annual_return": float,         # 年化收益率 (%)
        "volatility": float,            # 波动率 (%)
        "win_rate": float,              # 胜率 (%)
        "profit_factor": float,         # 盈亏比
        "avg_trade": float,             # 平均每笔交易盈亏
        "max_trade": float,             # 最大单笔盈利
        "min_trade": float,             # 最大单笔亏损
        "total_trades": int,            # 总交易次数
        "winning_trades": int,          # 盈利交易次数
        "losing_trades": int,           # 亏损交易次数
        "custom_metrics": dict          # 自定义指标
    },
    "trades": [                         # 交易记录列表
        {
            "id": str,                  # 交易ID
            "instrument": str,          # 交易品种
            "direction": str,           # 方向 (buy/sell)
            "entry_time": str,          # 开仓时间
            "entry_price": float,       # 开仓价格
            "entry_reason": str,        # 开仓原因
            "exit_time": str,           # 平仓时间
            "exit_price": float,        # 平仓价格
            "exit_reason": str,         # 平仓原因
            "quantity": float,          # 数量
            "pnl": float,               # 盈亏
            "pnl_pct": float,           # 盈亏百分比
            "fees": float,              # 手续费
            "holding_period": int,      # 持仓周期(天/小时/分钟)
            "tags": list                # 交易标签
        }
    ],
    "equity_curve": [                   # 权益曲线
        {
            "date": str,                # 日期 (ISO格式)
            "equity": float,            # 权益
            "drawdown": float,          # 回撤 (%)
            "returns": float,           # 回报率 (%)
            "position_value": float,    # 持仓价值
            "cash": float               # 现金
        }
    ],
    "position_history": [               # 持仓历史
        {
            "date": str,                # 日期 (ISO格式)
            "instrument": str,          # 交易品种
            "quantity": float,          # 数量
            "price": float,             # 价格
            "value": float,             # 价值
            "side": str                 # 方向 (long/short)
        }
    ],
    "additional_data": dict             # 附加数据
}

# 标准化回测结果
def standardize_backtest_result(backtest_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    标准化回测结果数据
    
    Args:
        backtest_data: 原始回测数据
        
    Returns:
        Dict[str, Any]: 标准化后的回测数据
    """
    result = {
        "schema_version": "1.0",
        "backtest_info": {},
        "performance_metrics": {},
        "trades": [],
        "equity_curve": [],
        "position_history": [],
        "additional_data": {}
    }
    
    # 复制回测基本信息
    info_keys = [
        "id", "type", "strategy_id", "strategy_name", 
        "start_date", "end_date", "created_at", "created_by",
        "description", "status", "parameters", "instruments", 
        "timeframe", "tags"
    ]
    
    for key in info_keys:
        if key in backtest_data.get("backtest_info", {}):
            result["backtest_info"][key] = backtest_data["backtest_info"][key]
    
    # 确保必要字段存在
    if "created_at" not in result["backtest_info"]:
        result["backtest_info"]["created_at"] = datetime.now().isoformat()
    
    # 复制性能指标
    metric_keys = [
        "sharpe_ratio", "sortino_ratio", "calmar_ratio", 
        "max_drawdown", "max_drawdown_duration", "annual_return",
        "volatility", "win_rate", "profit_factor", "avg_trade",
        "max_trade", "min_trade", "total_trades", "winning_trades",
        "losing_trades", "custom_metrics"
    ]
    
    for key in metric_keys:
        if key in backtest_data.get("performance_metrics", {}):
            result["performance_metrics"][key] = backtest_data["performance_metrics"][key]
    
    # 复制交易记录
    if "trades" in backtest_data:
        result["trades"] = backtest_data["trades"]
    
    # 复制权益曲线
    if "equity_curve" in backtest_data:
        result["equity_curve"] = backtest_data["equity_curve"]
    
    # 复制持仓历史
    if "position_history" in backtest_data:
        result["position_history"] = backtest_data["position_history"]
    
    # 复制附加数据
    if "additional_data" in backtest_data:
        result["additional_data"] = backtest_data["additional_data"]
    
    return result

# 验证回测数据是否符合标准结构
def validate_backtest_data(backtest_data: Dict[str, Any]) -> List[str]:
    """
    验证回测数据是否符合标准结构
    
    Args:
        backtest_data: 回测数据
        
    Returns:
        List[str]: 错误消息列表，空列表表示验证通过
    """
    errors = []
    
    # 检查基本信息
    required_info_fields = ["strategy_id", "strategy_name", "start_date", "end_date"]
    for field in required_info_fields:
        if field not in backtest_data.get("backtest_info", {}):
            errors.append(f"缺少必要的基本信息字段: {field}")
    
    # 检查性能指标
    required_metric_fields = ["sharpe_ratio", "max_drawdown", "annual_return", "total_trades"]
    for field in required_metric_fields:
        if field not in backtest_data.get("performance_metrics", {}):
            errors.append(f"缺少必要的性能指标字段: {field}")
    
    # 如果有交易记录，检查交易记录结构
    if "trades" in backtest_data and backtest_data["trades"]:
        for i, trade in enumerate(backtest_data["trades"]):
            required_trade_fields = ["instrument", "direction", "entry_time", "exit_time", "pnl"]
            for field in required_trade_fields:
                if field not in trade:
                    errors.append(f"交易记录 #{i+1} 缺少必要字段: {field}")
    
    # 如果有权益曲线，检查权益曲线结构
    if "equity_curve" in backtest_data and backtest_data["equity_curve"]:
        for i, point in enumerate(backtest_data["equity_curve"]):
            required_point_fields = ["date", "equity"]
            for field in required_point_fields:
                if field not in point:
                    errors.append(f"权益曲线点 #{i+1} 缺少必要字段: {field}")
    
    return errors