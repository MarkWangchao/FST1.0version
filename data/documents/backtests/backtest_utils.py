"""
回测数据工具模块

提供回测数据的导入导出和处理功能:
- 回测数据的导入和导出 (CSV, JSON)
- 回测数据的格式转换
- 回测结果的分析和比较
"""

import os
import json
import csv
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime

from .backtest_schema import standardize_backtest_result, validate_backtest_data

logger = logging.getLogger(__name__)


class BacktestDataConverter:
    """
    回测数据转换工具类
    
    提供不同格式回测数据之间的转换功能。
    """
    
    @staticmethod
    def backtest_to_json(backtest_data: Dict[str, Any], output_path: str) -> bool:
        """
        将回测数据导出为JSON格式
        
        Args:
            backtest_data: 回测数据
            output_path: 输出文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # 标准化数据
            standardized_data = standardize_backtest_result(backtest_data)
            
            # 导出为JSON
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(standardized_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"成功导出回测数据到 {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出回测数据到JSON失败: {str(e)}")
            return False
    
    @staticmethod
    def json_to_backtest(json_path: str) -> Optional[Dict[str, Any]]:
        """
        从JSON文件导入回测数据
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            Optional[Dict[str, Any]]: 回测数据，失败则返回None
        """
        try:
            # 读取JSON文件
            with open(json_path, 'r', encoding='utf-8') as f:
                backtest_data = json.load(f)
            
            # 验证数据
            errors = validate_backtest_data(backtest_data)
            if errors:
                error_msg = "\n".join(errors)
                logger.error(f"导入的回测数据无效:\n{error_msg}")
                return None
            
            logger.info(f"成功从 {json_path} 导入回测数据")
            return backtest_data
            
        except Exception as e:
            logger.error(f"从JSON导入回测数据失败: {str(e)}")
            return None
    
    @staticmethod
    def trades_to_csv(trades: List[Dict[str, Any]], output_path: str) -> bool:
        """
        将交易记录导出为CSV格式
        
        Args:
            trades: 交易记录列表
            output_path: 输出文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # 如果没有交易记录，创建一个空文件
            if not trades:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write("没有交易记录")
                return True
            
            # 确定CSV列
            fieldnames = set()
            for trade in trades:
                fieldnames.update(trade.keys())
            
            fieldnames = sorted(list(fieldnames))
            
            # 写入CSV
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(trades)
                
            logger.info(f"成功导出交易记录到 {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出交易记录到CSV失败: {str(e)}")
            return False
    
    @staticmethod
    def equity_curve_to_csv(equity_curve: List[Dict[str, Any]], output_path: str) -> bool:
        """
        将权益曲线导出为CSV格式
        
        Args:
            equity_curve: 权益曲线数据
            output_path: 输出文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # 如果没有权益曲线数据，创建一个空文件
            if not equity_curve:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write("没有权益曲线数据")
                return True
            
            # 确定CSV列
            fieldnames = set()
            for point in equity_curve:
                fieldnames.update(point.keys())
            
            fieldnames = sorted(list(fieldnames))
            
            # 写入CSV
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(equity_curve)
                
            logger.info(f"成功导出权益曲线到 {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出权益曲线到CSV失败: {str(e)}")
            return False
    
    @staticmethod
    def to_pandas(backtest_data: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        """
        将回测数据转换为pandas DataFrame
        
        Args:
            backtest_data: 回测数据
            
        Returns:
            Dict[str, pd.DataFrame]: 包含不同数据部分的DataFrame字典
        """
        try:
            result = {}
            
            # 交易记录转换为DataFrame
            if "trades" in backtest_data and backtest_data["trades"]:
                result["trades"] = pd.DataFrame(backtest_data["trades"])
                
                # 转换日期列
                date_columns = [col for col in result["trades"].columns if "time" in col or "date" in col]
                for col in date_columns:
                    result["trades"][col] = pd.to_datetime(result["trades"][col])
            
            # 权益曲线转换为DataFrame
            if "equity_curve" in backtest_data and backtest_data["equity_curve"]:
                result["equity_curve"] = pd.DataFrame(backtest_data["equity_curve"])
                
                # 转换日期列
                if "date" in result["equity_curve"].columns:
                    result["equity_curve"]["date"] = pd.to_datetime(result["equity_curve"]["date"])
                    result["equity_curve"].set_index("date", inplace=True)
            
            # 持仓历史转换为DataFrame
            if "position_history" in backtest_data and backtest_data["position_history"]:
                result["position_history"] = pd.DataFrame(backtest_data["position_history"])
                
                # 转换日期列
                if "date" in result["position_history"].columns:
                    result["position_history"]["date"] = pd.to_datetime(result["position_history"]["date"])
                    result["position_history"].set_index("date", inplace=True)
            
            # 性能指标转换为DataFrame
            if "performance_metrics" in backtest_data:
                metrics = backtest_data["performance_metrics"]
                if "custom_metrics" in metrics:
                    # 合并自定义指标
                    metrics_without_custom = {k: v for k, v in metrics.items() if k != "custom_metrics"}
                    all_metrics = {**metrics_without_custom, **(metrics.get("custom_metrics", {}))}
                else:
                    all_metrics = metrics
                
                result["metrics"] = pd.DataFrame([all_metrics])
            
            return result
            
        except Exception as e:
            logger.error(f"转换回测数据到pandas DataFrame失败: {str(e)}")
            return {}


class BacktestAnalyzer:
    """
    回测分析工具类
    
    提供回测结果的分析和比较功能。
    """
    
    @staticmethod
    def calculate_drawdowns(equity_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        计算回撤序列
        
        Args:
            equity_curve: 权益曲线数据
            
        Returns:
            List[Dict[str, Any]]: 回撤序列
        """
        try:
            if not equity_curve:
                return []
            
            # 转换为DataFrame
            df = pd.DataFrame(equity_curve)
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            
            # 计算滚动最大值
            df["peak"] = df["equity"].cummax()
            
            # 计算回撤
            df["drawdown"] = (df["equity"] - df["peak"]) / df["peak"] * 100
            
            # 计算回撤持续时间
            df["is_peak"] = df["equity"] == df["peak"]
            df["peak_group"] = df["is_peak"].cumsum()
            df["days_since_peak"] = df.groupby("peak_group").cumcount()
            
            # 转换回字典列表
            result = []
            for _, row in df.iterrows():
                result.append({
                    "date": row.name.isoformat(),
                    "equity": row["equity"],
                    "peak": row["peak"],
                    "drawdown": row["drawdown"],
                    "days_since_peak": row["days_since_peak"]
                })
            
            return result
            
        except Exception as e:
            logger.error(f"计算回撤序列失败: {str(e)}")
            return []
    
    @staticmethod
    def compare_backtests(backtests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        比较多个回测结果
        
        Args:
            backtests: 回测结果列表
            
        Returns:
            Dict[str, Any]: 比较结果
        """
        try:
            if not backtests:
                return {}
            
            # 提取基本信息和性能指标
            comparison = {
                "backtest_count": len(backtests),
                "backtests": [],
                "metrics_comparison": {},
                "best_backtest": {}
            }
            
            # 收集每个回测的基本信息和指标
            for i, backtest in enumerate(backtests):
                info = backtest.get("backtest_info", {})
                metrics = backtest.get("performance_metrics", {})
                
                backtest_summary = {
                    "id": info.get("id", f"backtest_{i+1}"),
                    "name": info.get("strategy_name", f"Strategy {i+1}"),
                    "period": f"{info.get('start_date', 'N/A')} - {info.get('end_date', 'N/A')}",
                    "metrics": {
                        "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                        "max_drawdown": metrics.get("max_drawdown", 0),
                        "annual_return": metrics.get("annual_return", 0),
                        "win_rate": metrics.get("win_rate", 0),
                        "total_trades": metrics.get("total_trades", 0)
                    }
                }
                
                comparison["backtests"].append(backtest_summary)
            
            # 按指标比较
            key_metrics = ["sharpe_ratio", "max_drawdown", "annual_return", "win_rate", "total_trades"]
            
            for metric in key_metrics:
                # 收集所有回测的该指标值
                values = [b["metrics"][metric] for b in comparison["backtests"]]
                
                # 计算统计信息
                comparison["metrics_comparison"][metric] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "std": np.std(values),
                    "best_backtest_id": comparison["backtests"][np.argmax(values)]["id"] if metric != "max_drawdown" else comparison["backtests"][np.argmin(values)]["id"]
                }
            
            # 确定综合最佳回测 (简单算法: 夏普比率最高)
            best_index = np.argmax([b["metrics"]["sharpe_ratio"] for b in comparison["backtests"]])
            comparison["best_backtest"] = {
                "id": comparison["backtests"][best_index]["id"],
                "name": comparison["backtests"][best_index]["name"],
                "metrics": comparison["backtests"][best_index]["metrics"]
            }
            
            return comparison
            
        except Exception as e:
            logger.error(f"比较回测结果失败: {str(e)}")
            return {"error": str(e)}