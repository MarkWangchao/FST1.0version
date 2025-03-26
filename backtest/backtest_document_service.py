"""
回测文档服务 - 回测模块专用的文档服务接口

该服务作为回测模块的一部分，提供了便捷的接口来存储和管理回测结果，
同时封装了底层存储细节，并提供回测特定的功能增强。
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime

# 导入基础设施层的回测文档服务
from infrastructure.storage.document.backtest_document_service import BacktestDocumentService as InfraBacktestDocumentService
from data.document.document_item import DocumentStatus
from backtest.performance_analyzer import PerformanceAnalyzer

logger = logging.getLogger(__name__)

class BacktestDocumentService:
    """
    回测文档服务 - 回测模块专用接口
    
    在底层存储服务的基础上提供额外功能:
    - 自动从回测引擎结果创建文档
    - 比较多个回测结果
    - 回测结果可视化导出
    - 回测结果批量管理
    - 与性能分析器集成
    """
    
    def __init__(self):
        """初始化回测文档服务"""
        # 使用基础设施层的回测文档服务
        self.infra_service = InfraBacktestDocumentService()
        self.performance_analyzer = PerformanceAnalyzer()
        logger.info("Backtest Document Service initialized")
    
    def save_backtest_result(self, 
                          backtest_result: Dict[str, Any],
                          backtest_id: Optional[str] = None) -> Optional[str]:
        """
        保存回测结果
        
        Args:
            backtest_result: 回测结果字典，包含回测引擎的完整输出
            backtest_id: 回测ID，如为None则自动生成
            
        Returns:
            Optional[str]: 回测ID，如果失败则返回None
        """
        # 提取关键信息
        strategy_id = backtest_result.get("strategy_id")
        strategy_name = backtest_result.get("strategy_name")
        
        if not strategy_id or not strategy_name:
            logger.error("Cannot save backtest result: missing strategy_id or strategy_name")
            return None
        
        # 提取核心回测数据
        parameters = backtest_result.get("parameters", {})
        trades = backtest_result.get("trades", [])
        equity_curve = backtest_result.get("equity_curve", [])
        start_date = backtest_result.get("start_date", "")
        end_date = backtest_result.get("end_date", "")
        
        # 计算或使用现有性能指标
        performance_metrics = backtest_result.get("performance_metrics")
        if not performance_metrics and trades and equity_curve:
            # 如果没有提供性能指标，但有交易和权益曲线数据，则计算性能指标
            try:
                performance_metrics = self.performance_analyzer.calculate_metrics(
                    trades=trades,
                    equity_curve=equity_curve
                )
            except Exception as e:
                logger.warning(f"Failed to calculate performance metrics: {str(e)}")
                performance_metrics = {}
        elif not performance_metrics:
            performance_metrics = {}
            
        # 提取其他元数据
        author = backtest_result.get("author")
        tags = backtest_result.get("tags", [])
        
        # 移除核心字段后的额外数据
        core_fields = {"strategy_id", "strategy_name", "parameters", "trades", 
                       "equity_curve", "performance_metrics", "start_date", 
                       "end_date", "author", "tags"}
        additional_data = {k: v for k, v in backtest_result.items() if k not in core_fields}
        
        # 调用底层服务保存
        return self.infra_service.save_backtest_result(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            parameters=parameters,
            performance_metrics=performance_metrics,
            start_date=start_date,
            end_date=end_date,
            trades=trades,
            equity_curve=equity_curve,
            author=author,
            tags=tags,
            backtest_id=backtest_id,
            additional_data=additional_data
        )
    
    def get_backtest(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        获取回测结果
        
        Args:
            backtest_id: 回测ID
            
        Returns:
            Optional[Dict[str, Any]]: 回测结果，如不存在则返回None
        """
        return self.infra_service.get_backtest(backtest_id)
    
    def delete_backtest(self, backtest_id: str) -> bool:
        """
        删除回测结果
        
        Args:
            backtest_id: 回测ID
            
        Returns:
            bool: 是否删除成功
        """
        return self.infra_service.update_backtest_status(
            backtest_id=backtest_id,
            status=DocumentStatus.DELETED
        )
    
    def archive_backtest(self, backtest_id: str) -> bool:
        """
        归档回测结果
        
        Args:
            backtest_id: 回测ID
            
        Returns:
            bool: 是否归档成功
        """
        return self.infra_service.update_backtest_status(
            backtest_id=backtest_id,
            status=DocumentStatus.ARCHIVED
        )
    
    def get_backtests_by_strategy(self, strategy_id: str) -> List[Dict[str, Any]]:
        """
        获取策略的所有回测结果
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            List[Dict[str, Any]]: 回测结果列表
        """
        # 构建查询标签
        strategy_tag = f"strategy:{strategy_id}"
        
        # 查询文档
        documents = self.infra_service.document_manager.query_documents(
            store_name=self.infra_service.store_name,
            tags=[strategy_tag],
            status=None  # 查询所有状态（除了已删除）
        )
        
        results = []
        for doc in documents:
            if not doc.content:
                continue
                
            # 创建基本结果
            result = {
                "id": doc.id,
                "strategy_id": doc.content.get("strategy_id", ""),
                "strategy_name": doc.content.get("strategy_name", ""),
                "start_date": doc.content.get("start_date", ""),
                "end_date": doc.content.get("end_date", ""),
                "status": doc.metadata.status.value,
                "created_at": doc.metadata.created_at.isoformat() if doc.metadata.created_at else "",
                "performance_summary": {}
            }
            
            # 添加性能摘要
            metrics = doc.content.get("performance_metrics", {})
            result["performance_summary"] = {
                "total_return": metrics.get("total_return", 0),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                "max_drawdown": metrics.get("max_drawdown", 0),
                "win_rate": metrics.get("win_rate", 0),
                "trade_count": len(doc.content.get("trades", []))
            }
            
            results.append(result)
            
        return results
    
    def compare_backtests(self, backtest_ids: List[str]) -> Dict[str, Any]:
        """
        比较多个回测结果
        
        Args:
            backtest_ids: 回测ID列表
            
        Returns:
            Dict[str, Any]: 比较结果
        """
        if not backtest_ids:
            return {}
            
        comparison = {
            "backtests": [],
            "metrics_comparison": {},
            "parameters_comparison": {},
            "summary": {}
        }
        
        key_metrics = ["total_return", "sharpe_ratio", "max_drawdown", 
                      "win_rate", "profit_factor", "expectancy"]
                      
        # 收集所有回测数据
        for backtest_id in backtest_ids:
            backtest = self.get_backtest(backtest_id)
            if not backtest:
                continue
                
            # 提取基本信息
            backtest_summary = {
                "id": backtest_id,
                "strategy_name": backtest.get("strategy_name", ""),
                "start_date": backtest.get("start_date", ""),
                "end_date": backtest.get("end_date", "")
            }
            
            # 提取性能指标
            metrics = backtest.get("performance_metrics", {})
            backtest_summary["metrics"] = {metric: metrics.get(metric, 0) for metric in key_metrics}
            
            # 提取参数
            backtest_summary["parameters"] = backtest.get("parameters", {})
            
            comparison["backtests"].append(backtest_summary)
        
        # 如果没有有效回测，返回空结果
        if not comparison["backtests"]:
            return comparison
            
        # 比较性能指标
        for metric in key_metrics:
            metric_values = [b["metrics"].get(metric, 0) for b in comparison["backtests"]]
            
            if not metric_values or all(v == 0 for v in metric_values):
                continue
                
            comparison["metrics_comparison"][metric] = {
                "values": {b["id"]: b["metrics"].get(metric, 0) for b in comparison["backtests"]},
                "best": max(comparison["backtests"], key=lambda b: b["metrics"].get(metric, 0))["id"],
                "worst": min(comparison["backtests"], key=lambda b: b["metrics"].get(metric, 0))["id"],
                "average": sum(metric_values) / len(metric_values)
            }
        
        # 比较参数
        all_params = set()
        for backtest in comparison["backtests"]:
            all_params.update(backtest["parameters"].keys())
            
        for param in all_params:
            param_values = {b["id"]: b["parameters"].get(param, None) for b in comparison["backtests"]}
            unique_values = set(str(v) for v in param_values.values() if v is not None)
            
            # 只比较有变化的参数
            if len(unique_values) > 1:
                comparison["parameters_comparison"][param] = param_values
        
        # 生成总结
        # 找出综合表现最好的回测（使用Sharpe比率或总回报）
        if "sharpe_ratio" in comparison["metrics_comparison"]:
            best_metric = "sharpe_ratio"
        elif "total_return" in comparison["metrics_comparison"]:
            best_metric = "total_return"
        else:
            best_metric = next(iter(comparison["metrics_comparison"].keys()), None)
            
        if best_metric:
            best_id = comparison["metrics_comparison"][best_metric]["best"]
            best_backtest = next((b for b in comparison["backtests"] if b["id"] == best_id), None)
            
            if best_backtest:
                comparison["summary"]["best_overall"] = {
                    "id": best_id,
                    "strategy_name": best_backtest["strategy_name"],
                    "metrics": best_backtest["metrics"],
                    "parameters": best_backtest["parameters"]
                }
        
        return comparison
    
    def export_backtest_report(self, backtest_id: str, format: str = "json") -> Optional[Dict[str, Any]]:
        """
        导出回测报告
        
        Args:
            backtest_id: 回测ID
            format: 导出格式，支持"json"、"csv"、"html"
            
        Returns:
            Optional[Dict[str, Any]]: 导出结果，包含导出数据或文件路径
        """
        # 获取回测数据
        backtest = self.get_backtest(backtest_id)
        if not backtest:
            logger.error(f"Cannot export backtest report: backtest {backtest_id} not found")
            return None
            
        if format.lower() == "json":
            # 直接返回JSON格式
            return {
                "format": "json",
                "data": backtest
            }
        elif format.lower() == "csv":
            # 导出CSV格式
            try:
                import pandas as pd
                import io
                
                # 创建交易记录DataFrame
                trades_df = pd.DataFrame(backtest.get("trades", []))
                
                # 创建权益曲线DataFrame
                equity_df = pd.DataFrame(backtest.get("equity_curve", []))
                
                # 创建性能指标DataFrame
                metrics = backtest.get("performance_metrics", {})
                metrics_df = pd.DataFrame([metrics])
                
                # 创建CSV字符串
                csv_output = {
                    "format": "csv",
                    "data": {
                        "summary": backtest.get("strategy_name", "") + " Backtest Report",
                        "metrics": metrics_df.to_csv(index=False),
                        "trades": trades_df.to_csv(index=False) if not trades_df.empty else "",
                        "equity_curve": equity_df.to_csv(index=False) if not equity_df.empty else ""
                    }
                }
                
                return csv_output
            except ImportError:
                logger.error("Cannot export CSV: pandas library not available")
                return None
            except Exception as e:
                logger.error(f"Error exporting CSV: {str(e)}")
                return None
        elif format.lower() == "html":
            # 导出HTML格式
            try:
                # 基本HTML模板
                html = f"""
                <html>
                <head>
                    <title>Backtest Report: {backtest.get("strategy_name", "")}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 20px; }}
                        h1, h2 {{ color: #333; }}
                        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                        th {{ background-color: #f2f2f2; }}
                        .metrics {{ display: flex; flex-wrap: wrap; }}
                        .metric-box {{ border: 1px solid #ddd; padding: 10px; margin: 5px; flex: 1; min-width: 200px; }}
                    </style>
                </head>
                <body>
                    <h1>Backtest Report: {backtest.get("strategy_name", "")}</h1>
                    <p>Period: {backtest.get("start_date", "")} to {backtest.get("end_date", "")}</p>
                """
                
                # 添加性能指标
                metrics = backtest.get("performance_metrics", {})
                html += "<h2>Performance Metrics</h2>"
                html += "<div class='metrics'>"
                for key, value in metrics.items():
                    html += f"<div class='metric-box'><h3>{key}</h3><p>{value}</p></div>"
                html += "</div>"
                
                # 添加参数
                parameters = backtest.get("parameters", {})
                if parameters:
                    html += "<h2>Strategy Parameters</h2>"
                    html += "<table><tr><th>Parameter</th><th>Value</th></tr>"
                    for key, value in parameters.items():
                        html += f"<tr><td>{key}</td><td>{value}</td></tr>"
                    html += "</table>"
                
                # 添加交易记录表格
                trades = backtest.get("trades", [])
                if trades:
                    html += "<h2>Trades</h2>"
                    html += "<table><tr>"
                    # 表头
                    for key in trades[0].keys():
                        html += f"<th>{key}</th>"
                    html += "</tr>"
                    
                    # 行数据
                    for trade in trades:
                        html += "<tr>"
                        for value in trade.values():
                            html += f"<td>{value}</td>"
                        html += "</tr>"
                    html += "</table>"
                
                html += "</body></html>"
                
                return {
                    "format": "html",
                    "data": html
                }
            except Exception as e:
                logger.error(f"Error exporting HTML: {str(e)}")
                return None
        else:
            logger.error(f"Unsupported export format: {format}")
            return None
    
    def batch_delete_backtests(self, backtest_ids: List[str]) -> Dict[str, bool]:
        """
        批量删除回测结果
        
        Args:
            backtest_ids: 回测ID列表
            
        Returns:
            Dict[str, bool]: 每个ID的删除结果
        """
        results = {}
        for backtest_id in backtest_ids:
            results[backtest_id] = self.delete_backtest(backtest_id)
        return results
    
    def batch_archive_backtests(self, backtest_ids: List[str]) -> Dict[str, bool]:
        """
        批量归档回测结果
        
        Args:
            backtest_ids: 回测ID列表
            
        Returns:
            Dict[str, bool]: 每个ID的归档结果
        """
        results = {}
        for backtest_id in backtest_ids:
            results[backtest_id] = self.archive_backtest(backtest_id)
        return results