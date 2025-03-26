"""
回测文档服务 - 专门处理与回测结果相关的文档操作

该服务基于通用文档管理器，提供针对回测特性的功能：
- 回测结果存储和管理
- 回测性能指标查询
- 回测结果比较
- 回测历史跟踪
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime
import uuid

from data.document.document_item import DocumentItem, DocumentStatus, DocumentMetadata
from data.document.document_manager import DocumentManager

logger = logging.getLogger(__name__)


class BacktestDocumentService:
    """
    回测文档服务 - 专门处理回测结果相关的文档操作
    
    提供功能:
    - 回测结果的创建、读取、更新和删除
    - 回测性能指标查询
    - 回测结果比较
    - 回测结果导出
    """
    
    # 回测状态常量
    STATUS_DRAFT = DocumentStatus.DRAFT
    STATUS_COMPLETED = DocumentStatus.PUBLISHED
    STATUS_ARCHIVED = DocumentStatus.ARCHIVED
    STATUS_DELETED = DocumentStatus.DELETED
    
    # 回测内容类型
    CONTENT_TYPE = "application/json"
    
    # 默认标签
    DEFAULT_TAGS = ["backtest"]
    
    # 回测文档模式
    SCHEMA = "backtest/v1"
    
    def __init__(self, document_manager: Optional[DocumentManager] = None):
        """
        初始化回测文档服务
        
        Args:
            document_manager: 文档管理器实例，如不提供则创建默认实例
        """
        self.document_manager = document_manager or DocumentManager()
        # 使用固定的存储名称
        self.store_name = DocumentManager.BACKTEST_DOCS
        logger.info(f"Backtest Document Service initialized using store: {self.store_name}")
    
    def save_backtest_result(self,
                          strategy_id: str,
                          strategy_name: str,
                          parameters: Dict[str, Any],
                          performance_metrics: Dict[str, Any],
                          start_date: str,
                          end_date: str,
                          trades: List[Dict[str, Any]],
                          equity_curve: List[Dict[str, Any]],
                          author: Optional[str] = None,
                          tags: Optional[List[str]] = None,
                          backtest_id: Optional[str] = None,
                          additional_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        保存回测结果
        
        Args:
            strategy_id: 策略ID
            strategy_name: 策略名称
            parameters: 策略参数
            performance_metrics: 性能指标
            start_date: 回测开始日期
            end_date: 回测结束日期
            trades: 交易记录
            equity_curve: 权益曲线
            author: 作者
            tags: 标签列表
            backtest_id: 回测ID，如为None则自动生成
            additional_data: 额外数据
            
        Returns:
            Optional[str]: 回测ID，如果失败则返回None
        """
        # 构建回测内容
        content = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "parameters": parameters,
            "performance_metrics": performance_metrics,
            "start_date": start_date,
            "end_date": end_date,
            "trades": trades,
            "equity_curve": equity_curve,
            "created_by": author,
            "created_at": datetime.now().isoformat()
        }
        
        # 添加额外数据
        if additional_data:
            content.update(additional_data)
            
        # 合并标签
        backtest_tags = list(self.DEFAULT_TAGS)
        if tags:
            backtest_tags.extend([tag for tag in tags if tag not in backtest_tags])
            
        # 添加策略ID标签，便于查找特定策略的所有回测
        strategy_tag = f"strategy:{strategy_id}"
        if strategy_tag not in backtest_tags:
            backtest_tags.append(strategy_tag)
            
        # 创建自定义元数据
        custom_metadata = {
            "title": f"Backtest: {strategy_name} ({start_date} to {end_date})",
            "strategy_id": strategy_id,
            "performance": {
                "sharpe_ratio": performance_metrics.get("sharpe_ratio"),
                "total_return": performance_metrics.get("total_return"),
                "max_drawdown": performance_metrics.get("max_drawdown")
            }
        }
        
        try:
            # 创建回测文档
            backtest_id = self.document_manager.create_document(
                content=content,
                store_name=self.store_name,
                author=author,
                doc_id=backtest_id,
                content_type=self.CONTENT_TYPE,
                tags=backtest_tags,
                custom_metadata=custom_metadata,
                schema=self.SCHEMA
            )
            
            # 设置状态为已完成
            if backtest_id:
                success = self.document_manager.update_document(
                    doc_id=backtest_id,
                    store_name=self.store_name,
                    status=self.STATUS_COMPLETED
                )
                
                if not success:
                    logger.warning(f"Created backtest {backtest_id} but failed to set status to COMPLETED")
            
            logger.info(f"Saved backtest result for strategy '{strategy_name}' with ID: {backtest_id}")
            return backtest_id
            
        except Exception as e:
            logger.error(f"Error saving backtest result for strategy '{strategy_name}': {str(e)}")
            return None
    
    def get_backtest(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        获取回测结果
        
        Args:
            backtest_id: 回测ID
            
        Returns:
            Optional[Dict[str, Any]]: 回测结果，如不存在则返回None
        """
        try:
            document = self.document_manager.load_document(backtest_id, self.store_name)
            if not document:
                return None
                
            # 创建结果字典
            result = document.content.copy() if isinstance(document.content, dict) else {"content": document.content}
            
            # 添加元数据
            result.update({
                "id": document.id,
                "status": document.metadata.status.value,
                "version": document.metadata.version,
                "tags": document.metadata.tags,
                "author": document.metadata.author,
                "created_at": document.metadata.created_at.isoformat(),
                "updated_at": document.metadata.updated_at.isoformat()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting backtest {backtest_id}: {str(e)}")
            return None
    
    def get_backtest_performance(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        获取回测性能指标
        
        Args:
            backtest_id: 回测ID
            
        Returns:
            Optional[Dict[str, Any]]: 性能指标，如不存在则返回None
        """
        try:
            # 获取完整回测
            backtest = self.get_backtest(backtest_id)
            if not backtest:
                return None
                
            # 提取性能指标
            return backtest.get("performance_metrics", {})
            
        except Exception as e:
            logger.error(f"Error getting backtest performance for {backtest_id}: {str(e)}")
            return None
    
    def update_backtest_status(self, 
                            backtest_id: str, 
                            status: DocumentStatus,
                            author: Optional[str] = None) -> bool:
        """
        更新回测状态
        
        Args:
            backtest_id: 回测ID
            status: 新状态
            author: 更新作者
            
        Returns:
            bool: 是否更新成功
        """
        try:
            success = self.document_manager.update_document(
                doc_id=backtest_id,
                store_name=self.store_name,
                author=author,
                status=status
            )
            
            if success:
                logger.info(f"Updated backtest {backtest_id} status to {status.value}")
            else:
                logger.error(f"Failed to update backtest {backtest_id} status")
                
            return success
            
        except Exception as e:
            logger.error(f"Error updating backtest {backtest_id} status: {str(e)}")
            return False
    
    def delete_backtest(self, backtest_id: str, permanent: bool = False) -> bool:
        """
        删除回测
        
        Args:
            backtest_id: 回测ID
            permanent: 是否永久删除，True为物理删除，False为标记为已删除状态
            
        Returns:
            bool: 是否删除成功
        """
        try:
            if permanent:
                # 物理删除
                success = self.document_manager.delete_document(backtest_id, self.store_name)
                if success:
                    logger.info(f"Permanently deleted backtest {backtest_id}")
                else:
                    logger.error(f"Failed to permanently delete backtest {backtest_id}")
            else:
                # 标记为已删除状态
                success = self.update_backtest_status(backtest_id, self.STATUS_DELETED)
                if success:
                    logger.info(f"Marked backtest {backtest_id} as deleted")
                else:
                    logger.error(f"Failed to mark backtest {backtest_id} as deleted")
                    
            return success
            
        except Exception as e:
            logger.error(f"Error deleting backtest {backtest_id}: {str(e)}")
            return False
    
    def list_backtests(self, 
                     strategy_id: Optional[str] = None,
                     status: Optional[DocumentStatus] = None,
                     author: Optional[str] = None,
                     tags: Optional[List[str]] = None,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     min_sharpe: Optional[float] = None,
                     max_drawdown: Optional[float] = None,
                     limit: int = 100,
                     offset: int = 0) -> List[Dict[str, Any]]:
        """
        列出回测
        
        Args:
            strategy_id: 策略ID过滤
            status: 回测状态过滤
            author: 作者过滤
            tags: 标签过滤
            start_date: 回测开始日期过滤
            end_date: 回测结束日期过滤
            min_sharpe: 最小夏普比率过滤
            max_drawdown: 最大回撤过滤
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 回测列表
        """
        try:
            # 构建查询条件
            query = {}
            search_tags = tags or []
            
            # 策略ID过滤
            if strategy_id:
                strategy_tag = f"strategy:{strategy_id}"
                search_tags.append(strategy_tag)
            
            # 日期过滤
            if start_date:
                query["content.start_date"] = {"$gte": start_date}
            if end_date:
                query["content.end_date"] = {"$lte": end_date}
            
            # 性能指标过滤
            if min_sharpe is not None:
                query["content.performance_metrics.sharpe_ratio"] = {"$gte": min_sharpe}
            if max_drawdown is not None:
                query["content.performance_metrics.max_drawdown"] = {"$lte": max_drawdown}
            
            # 使用文档管理器搜索
            results = self.document_manager.search_documents(
                query=query,
                tags=search_tags if search_tags else None,
                author=author,
                status=status,
                store_name=self.store_name,
                limit=limit,
                offset=offset
            )
            
            # 处理结果
            backtests = []
            for doc in results:
                if isinstance(doc, dict):
                    # 直接使用搜索返回的字典
                    backtests.append(doc)
                else:
                    # 如果是DocumentItem实例，转换为字典
                    try:
                        # 基础信息
                        backtest = {
                            "id": doc.id,
                            "status": doc.metadata.status.value,
                            "tags": doc.metadata.tags,
                            "author": doc.metadata.author,
                            "created_at": doc.metadata.created_at.isoformat(),
                            "updated_at": doc.metadata.updated_at.isoformat()
                        }
                        
                        # 添加内容摘要
                        if isinstance(doc.content, dict):
                            # 提取关键信息
                            backtest.update({
                                "strategy_id": doc.content.get("strategy_id"),
                                "strategy_name": doc.content.get("strategy_name"),
                                "start_date": doc.content.get("start_date"),
                                "end_date": doc.content.get("end_date"),
                                "performance_metrics": doc.content.get("performance_metrics", {}),
                                "parameters": doc.content.get("parameters", {})
                            })
                        else:
                            backtest["content"] = doc.content
                            
                        backtests.append(backtest)
                    except Exception as e:
                        logger.error(f"Error processing backtest document: {str(e)}")
            
            return backtests
            
        except Exception as e:
            logger.error(f"Error listing backtests: {str(e)}")
            return []
    
    def get_strategy_backtests(self, 
                            strategy_id: str,
                            status: Optional[DocumentStatus] = None,
                            limit: int = 100,
                            offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取策略的所有回测
        
        Args:
            strategy_id: 策略ID
            status: 回测状态过滤
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 回测列表
        """
        # 使用策略ID标签过滤
        strategy_tag = f"strategy:{strategy_id}"
        return self.list_backtests(
            tags=[strategy_tag],
            status=status,
            limit=limit,
            offset=offset
        )
    
    def get_latest_strategy_backtest(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        获取策略的最新回测
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            Optional[Dict[str, Any]]: 最新回测，如不存在则返回None
        """
        # 获取策略的所有回测，按更新时间倒序
        backtest_list = self.get_strategy_backtests(strategy_id, limit=1)
        if not backtest_list:
            return None
            
        return backtest_list[0]
    
    def compare_backtests(self, backtest_ids: List[str]) -> Dict[str, Any]:
        """
        比较多个回测结果
        
        Args:
            backtest_ids: 回测ID列表
            
        Returns:
            Dict[str, Any]: 比较结果
        """
        result = {
            "backtests": [],
            "performance_comparison": {},
            "parameter_differences": {}
        }
        
        try:
            # 加载所有回测
            backtests = []
            for backtest_id in backtest_ids:
                backtest = self.get_backtest(backtest_id)
                if backtest:
                    backtests.append(backtest)
                    
            if not backtests:
                return result
                
            # 添加基本信息
            for backtest in backtests:
                result["backtests"].append({
                    "id": backtest.get("id"),
                    "strategy_id": backtest.get("strategy_id"),
                    "strategy_name": backtest.get("strategy_name"),
                    "start_date": backtest.get("start_date"),
                    "end_date": backtest.get("end_date")
                })
            
            # 比较性能指标
            metrics_to_compare = [
                "total_return", "sharpe_ratio", "max_drawdown", "win_rate",
                "profit_factor", "average_trade"
            ]
            
            for metric in metrics_to_compare:
                metric_values = []
                for backtest in backtests:
                    performance = backtest.get("performance_metrics", {})
                    if metric in performance:
                        metric_values.append((backtest.get("id"), performance[metric]))
                
                if metric_values:
                    # 按指标排序
                    if metric in ["max_drawdown"]:
                        # 小值优先
                        sorted_values = sorted(metric_values, key=lambda x: x[1])
                    else:
                        # 大值优先
                        sorted_values = sorted(metric_values, key=lambda x: x[1], reverse=True)
                        
                    result["performance_comparison"][metric] = {
                        "values": dict(metric_values),
                        "best": {"backtest_id": sorted_values[0][0], "value": sorted_values[0][1]},
                        "worst": {"backtest_id": sorted_values[-1][0], "value": sorted_values[-1][1]},
                        "average": sum(v for _, v in metric_values) / len(metric_values)
                    }
            
            # 比较参数差异
            if len(backtests) > 1:
                all_params = set()
                for backtest in backtests:
                    params = backtest.get("parameters", {})
                    all_params.update(params.keys())
                
                # 找出有差异的参数
                for param in all_params:
                    values = {}
                    for backtest in backtests:
                        params = backtest.get("parameters", {})
                        if param in params:
                            values[backtest.get("id")] = params[param]
                    
                    # 如果至少有一个回测有这个参数，且值不全相同
                    if values and len(set(values.values())) > 1:
                        result["parameter_differences"][param] = values
            
            return result
            
        except Exception as e:
            logger.error(f"Error comparing backtests: {str(e)}")
            return result
    
    def find_best_backtest(self, 
                        strategy_id: Optional[str] = None,
                        metric: str = "sharpe_ratio",
                        min_trades: int = 10,
                        tags: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        找出最佳回测结果
        
        Args:
            strategy_id: 策略ID，如为None则在所有回测中查找
            metric: 性能指标，用于排序
            min_trades: 最小交易次数
            tags: 标签过滤
            
        Returns:
            Optional[Dict[str, Any]]: 最佳回测，如不存在则返回None
        """
        try:
            # 构建查询条件
            query = {
                "content.trades": {"$exists": True},
                "$expr": {"$gte": [{"$size": "$content.trades"}, min_trades]}
            }
            
            search_tags = tags or []
            
            # 策略ID过滤
            if strategy_id:
                strategy_tag = f"strategy:{strategy_id}"
                search_tags.append(strategy_tag)
            
            # 获取所有符合条件的回测
            backtests = self.list_backtests(
                tags=search_tags if search_tags else None,
                status=self.STATUS_COMPLETED,
                limit=100,
                offset=0
            )
            
            if not backtests:
                return None
                
            # 按指标排序
            reverse = True  # 默认大值优先
            if metric in ["max_drawdown"]:
                reverse = False  # 小值优先
                
            sorted_backtests = sorted(
                backtests,
                key=lambda x: x.get("performance_metrics", {}).get(metric, float('-inf' if reverse else 'inf')),
                reverse=reverse
            )
            
            # 返回最佳回测
            if sorted_backtests:
                best_backtest = sorted_backtests[0]
                logger.info(f"Found best backtest {best_backtest.get('id')} with {metric} = "
                           f"{best_backtest.get('performance_metrics', {}).get(metric)}")
                return best_backtest
                
            return None
            
        except Exception as e:
            logger.error(f"Error finding best backtest: {str(e)}")
            return None
    
    def export_backtest(self, backtest_id: str, export_path: str) -> bool:
        """
        导出回测结果到文件
        
        Args:
            backtest_id: 回测ID
            export_path: 导出文件路径
            
        Returns:
            bool: 是否导出成功
        """
        try:
            # 加载回测
            backtest = self.get_backtest(backtest_id)
            if not backtest:
                logger.error(f"Backtest {backtest_id} not found")
                return False
                
            # 导出到文件
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(backtest, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Exported backtest {backtest_id} to {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting backtest {backtest_id}: {str(e)}")
            return False
    
    def export_equity_curve(self, backtest_id: str, export_path: str, format: str = "json") -> bool:
        """
        导出权益曲线数据
        
        Args:
            backtest_id: 回测ID
            export_path: 导出文件路径
            format: 导出格式，支持json或csv
            
        Returns:
            bool: 是否导出成功
        """
        try:
            # 加载回测
            backtest = self.get_backtest(backtest_id)
            if not backtest:
                logger.error(f"Backtest {backtest_id} not found")
                return False
                
            # 提取权益曲线
            equity_curve = backtest.get("equity_curve", [])
            if not equity_curve:
                logger.error(f"Backtest {backtest_id} has no equity curve data")
                return False
                
            # 导出到文件
            if format.lower() == "json":
                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(equity_curve, f, ensure_ascii=False, indent=2)
            elif format.lower() == "csv":
                import csv
                with open(export_path, 'w', newline='', encoding='utf-8') as f:
                    # 确定列名
                    if equity_curve:
                        fieldnames = equity_curve[0].keys()
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(equity_curve)
            else:
                logger.error(f"Unsupported format: {format}")
                return False
                
            logger.info(f"Exported equity curve from backtest {backtest_id} to {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting equity curve from backtest {backtest_id}: {str(e)}")
            return False
    
    def export_trades(self, backtest_id: str, export_path: str, format: str = "json") -> bool:
        """
        导出交易记录
        
        Args:
            backtest_id: 回测ID
            export_path: 导出文件路径
            format: 导出格式，支持json或csv
            
        Returns:
            bool: 是否导出成功
        """
        try:
            # 加载回测
            backtest = self.get_backtest(backtest_id)
            if not backtest:
                logger.error(f"Backtest {backtest_id} not found")
                return False
                
            # 提取交易记录
            trades = backtest.get("trades", [])
            if not trades:
                logger.error(f"Backtest {backtest_id} has no trade data")
                return False
                
            # 导出到文件
            if format.lower() == "json":
                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(trades, f, ensure_ascii=False, indent=2)
            elif format.lower() == "csv":
                import csv
                with open(export_path, 'w', newline='', encoding='utf-8') as f:
                    # 确定列名
                    if trades:
                        fieldnames = trades[0].keys()
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(trades)
            else:
                logger.error(f"Unsupported format: {format}")
                return False
                
            logger.info(f"Exported trades from backtest {backtest_id} to {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting trades from backtest {backtest_id}: {str(e)}")
            return False