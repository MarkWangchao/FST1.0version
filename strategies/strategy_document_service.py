"""
策略文档服务 - 策略模块专用的文档服务接口

该服务作为策略模块的一部分，提供了便捷的接口来存储和管理策略定义，
同时封装了底层存储细节，并提供策略特定的功能增强。
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime
import importlib
import inspect

# 导入基础设施层的策略文档服务
from infrastructure.storage.document.strategy_document_service import StrategyDocumentService as InfraStrategyDocumentService
from data.document.document_item import DocumentStatus
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class StrategyDocumentService:
    """
    策略文档服务 - 策略模块专用接口
    
    在底层存储服务的基础上提供额外功能:
    - 从策略类对象自动创建文档
    - 策略参数验证和默认值管理
    - 策略代码与文档的同步
    - 策略与回测结果的关联
    - 策略模板库
    """
    
    # 策略类型常量
    STRATEGY_TYPE_TREND = "trend_following"
    STRATEGY_TYPE_MEAN_REVERSION = "mean_reversion"
    STRATEGY_TYPE_BREAKOUT = "breakout"
    STRATEGY_TYPE_MOMENTUM = "momentum"
    STRATEGY_TYPE_ARBITRAGE = "arbitrage"
    STRATEGY_TYPE_MACHINE_LEARNING = "machine_learning"
    STRATEGY_TYPE_CUSTOM = "custom"
    
    # 风险级别常量
    RISK_LEVEL_LOW = "low"
    RISK_LEVEL_MEDIUM = "medium"
    RISK_LEVEL_HIGH = "high"
    
    def __init__(self):
        """初始化策略文档服务"""
        # 使用基础设施层的策略文档服务
        self.infra_service = InfraStrategyDocumentService()
        logger.info("Strategy Document Service initialized")
    
    def create_strategy_from_class(self, 
                                strategy_class: type,
                                name: Optional[str] = None,
                                description: Optional[str] = None,
                                custom_parameters: Optional[Dict[str, Any]] = None,
                                author: Optional[str] = None,
                                tags: Optional[List[str]] = None,
                                risk_level: Optional[str] = None) -> Optional[str]:
        """
        从策略类创建策略文档
        
        Args:
            strategy_class: 策略类（必须是BaseStrategy的子类）
            name: 策略名称，如果为None则使用类名
            description: 策略描述，如果为None则使用类文档字符串
            custom_parameters: 自定义参数，覆盖类默认参数
            author: 作者
            tags: 标签列表
            risk_level: 风险级别
            
        Returns:
            Optional[str]: 策略ID，如果失败则返回None
        """
        # 检查策略类是否有效
        if not inspect.isclass(strategy_class) or not issubclass(strategy_class, BaseStrategy):
            logger.error(f"Invalid strategy class: {strategy_class.__name__} is not a subclass of BaseStrategy")
            return None
        
        # 获取策略名称
        if name is None:
            name = strategy_class.__name__
        
        # 获取策略描述
        if description is None:
            description = inspect.getdoc(strategy_class) or f"{name} - Auto-generated from class"
        
        # 获取策略类型
        strategy_type = getattr(strategy_class, "STRATEGY_TYPE", self.STRATEGY_TYPE_CUSTOM)
        
        # 获取默认参数
        default_params = {}
        for param_name, param in inspect.signature(strategy_class.__init__).parameters.items():
            # 跳过self参数
            if param_name == "self":
                continue
            
            # 获取默认值
            if param.default is not inspect.Parameter.empty:
                default_params[param_name] = param.default
        
        # 合并自定义参数
        parameters = default_params.copy()
        if custom_parameters:
            parameters.update(custom_parameters)
        
        # 添加风险级别
        if risk_level:
            parameters["risk_level"] = risk_level
        
        # 添加策略类路径，便于后续实例化
        class_path = f"{strategy_class.__module__}.{strategy_class.__name__}"
        parameters["class_path"] = class_path
        
        # 添加标签
        strategy_tags = tags or []
        if risk_level and f"risk:{risk_level}" not in strategy_tags:
            strategy_tags.append(f"risk:{risk_level}")
        
        # 创建策略
        strategy_id = self.infra_service.create_strategy(
            name=name,
            description=description,
            strategy_type=strategy_type,
            parameters=parameters,
            author=author,
            tags=strategy_tags
        )
        
        return strategy_id
    
    def instantiate_strategy(self, strategy_id: str, **kwargs) -> Optional[BaseStrategy]:
        """
        从策略文档实例化策略对象
        
        Args:
            strategy_id: 策略ID
            **kwargs: 额外参数，会覆盖文档中的参数
            
        Returns:
            Optional[BaseStrategy]: 策略实例，如果失败则返回None
        """
        # 获取策略文档
        strategy_doc = self.get_strategy(strategy_id)
        if not strategy_doc:
            logger.error(f"Strategy {strategy_id} not found")
            return None
        
        # 获取参数
        parameters = strategy_doc.get("parameters", {}).copy()
        
        # 获取类路径
        class_path = parameters.pop("class_path", None)
        if not class_path:
            logger.error(f"Strategy {strategy_id} does not have a class_path parameter")
            return None
        
        # 移除非初始化参数
        parameters.pop("risk_level", None)
        
        # 合并额外参数
        parameters.update(kwargs)
        
        # 加载策略类
        try:
            module_path, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            strategy_class = getattr(module, class_name)
            
            # 创建实例
            strategy_instance = strategy_class(**parameters)
            
            # 设置策略ID
            strategy_instance.strategy_id = strategy_id
            
            return strategy_instance
            
        except (ImportError, AttributeError, ValueError) as e:
            logger.error(f"Error instantiating strategy {strategy_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error instantiating strategy {strategy_id}: {str(e)}")
            return None
    
    def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        获取策略文档
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            Optional[Dict[str, Any]]: 策略文档，如不存在则返回None
        """
        return self.infra_service.get_strategy(strategy_id)
    
    def get_strategy_parameters(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        获取策略参数
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            Optional[Dict[str, Any]]: 策略参数，如不存在则返回None
        """
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return None
        
        return strategy.get("parameters", {})
    
    def update_strategy_parameters(self, 
                                 strategy_id: str, 
                                 parameters: Dict[str, Any],
                                 author: Optional[str] = None,
                                 comment: Optional[str] = None) -> bool:
        """
        更新策略参数
        
        Args:
            strategy_id: 策略ID
            parameters: 新参数，会与现有参数合并
            author: 更新作者
            comment: 更新注释
            
        Returns:
            bool: 是否更新成功
        """
        # 获取当前参数
        current_params = self.get_strategy_parameters(strategy_id)
        if current_params is None:
            return False
        
        # 合并参数，保留class_path
        class_path = current_params.get("class_path")
        merged_params = current_params.copy()
        merged_params.update(parameters)
        
        # 确保class_path不变
        if class_path:
            merged_params["class_path"] = class_path
        
        # 更新策略
        return self.infra_service.update_strategy(
            strategy_id=strategy_id,
            parameters=merged_params,
            author=author,
            comment=comment
        )
    
    def activate_strategy(self, strategy_id: str, author: Optional[str] = None) -> bool:
        """
        激活策略
        
        Args:
            strategy_id: 策略ID
            author: 更新作者
            
        Returns:
            bool: 是否激活成功
        """
        return self.infra_service.update_strategy_status(
            strategy_id=strategy_id,
            status=self.infra_service.STATUS_ACTIVE,
            author=author
        )
    
    def archive_strategy(self, strategy_id: str, author: Optional[str] = None) -> bool:
        """
        归档策略
        
        Args:
            strategy_id: 策略ID
            author: 更新作者
            
        Returns:
            bool: 是否归档成功
        """
        return self.infra_service.update_strategy_status(
            strategy_id=strategy_id,
            status=self.infra_service.STATUS_ARCHIVED,
            author=author
        )
    
    def delete_strategy(self, strategy_id: str, author: Optional[str] = None) -> bool:
        """
        删除策略
        
        Args:
            strategy_id: 策略ID
            author: 更新作者
            
        Returns:
            bool: 是否删除成功
        """
        return self.infra_service.update_strategy_status(
            strategy_id=strategy_id,
            status=self.infra_service.STATUS_DELETED,
            author=author
        )
    
    def clone_strategy(self, 
                     source_id: str, 
                     new_name: str, 
                     author: Optional[str] = None,
                     parameter_updates: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        克隆策略
        
        Args:
            source_id: 源策略ID
            new_name: 新策略名称
            author: 作者
            parameter_updates: 参数更新
            
        Returns:
            Optional[str]: 新策略ID，如果失败则返回None
        """
        # 获取源策略
        source = self.get_strategy(source_id)
        if not source:
            logger.error(f"Source strategy {source_id} not found")
            return None
        
        # 准备参数
        parameters = source.get("parameters", {}).copy()
        if parameter_updates:
            parameters.update(parameter_updates)
        
        # 准备标签，添加clone标签
        tags = source.get("tags", []).copy()
        if "clone" not in tags:
            tags.append("clone")
        
        # 添加源策略标签
        source_tag = f"source:{source_id}"
        if source_tag not in tags:
            tags.append(source_tag)
        
        # 创建克隆
        description = f"Cloned from {source.get('name', 'unknown strategy')} ({source_id})\n\n{source.get('description', '')}"
        
        return self.infra_service.create_strategy(
            name=new_name,
            description=description,
            strategy_type=source.get("strategy_type", ""),
            parameters=parameters,
            author=author,
            tags=tags
        )
    
    def get_strategy_history(self, strategy_id: str) -> List[Dict[str, Any]]:
        """
        获取策略历史版本
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            List[Dict[str, Any]]: 策略历史版本列表
        """
        try:
            # 获取文档历史
            history = self.infra_service.document_manager.get_document_history(
                doc_id=strategy_id,
                store_name=self.infra_service.store_name
            )
            
            # 转换为简化格式
            result = []
            for version in history:
                # 提取参数差异
                params_diff = {}
                if version.diff and "parameters" in version.diff:
                    params_diff = version.diff["parameters"]
                
                # 创建版本摘要
                version_summary = {
                    "version": version.version,
                    "author": version.author,
                    "timestamp": version.timestamp.isoformat() if version.timestamp else "",
                    "comment": version.comment or "",
                    "parameter_changes": params_diff
                }
                
                result.append(version_summary)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting strategy history for {strategy_id}: {str(e)}")
            return []
    
    def get_strategy_backtest_results(self, strategy_id: str) -> List[Dict[str, Any]]:
        """
        获取策略的回测结果
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            List[Dict[str, Any]]: 回测结果列表
        """
        try:
            # 导入回测文档服务
            from backtest.backtest_document_service import BacktestDocumentService
            backtest_service = BacktestDocumentService()
            
            # 获取回测结果
            return backtest_service.get_backtests_by_strategy(strategy_id)
            
        except ImportError:
            logger.error("BacktestDocumentService not available")
            return []
        except Exception as e:
            logger.error(f"Error getting backtest results for strategy {strategy_id}: {str(e)}")
            return []
    
    def create_strategy_template(self, 
                               strategy_id: str, 
                               template_name: str,
                               description: Optional[str] = None,
                               author: Optional[str] = None) -> Optional[str]:
        """
        从现有策略创建模板
        
        Args:
            strategy_id: 源策略ID
            template_name: 模板名称
            description: 模板描述
            author: 作者
            
        Returns:
            Optional[str]: 模板ID，如果失败则返回None
        """
        # 获取源策略
        source = self.get_strategy(strategy_id)
        if not source:
            logger.error(f"Source strategy {strategy_id} not found")
            return None
        
        # 准备参数，移除特定实例相关的参数
        parameters = source.get("parameters", {}).copy()
        
        # 准备标签
        tags = source.get("tags", []).copy()
        if "template" not in tags:
            tags.append("template")
        
        # 生成描述
        if not description:
            description = f"Template created from {source.get('name', '')} ({strategy_id})\n\n{source.get('description', '')}"
        
        # 创建模板
        return self.infra_service.create_strategy(
            name=template_name,
            description=description,
            strategy_type=source.get("strategy_type", ""),
            parameters=parameters,
            author=author,
            tags=tags
        )
    
    def get_strategy_templates(self) -> List[Dict[str, Any]]:
        """
        获取所有策略模板
        
        Returns:
            List[Dict[str, Any]]: 模板列表
        """
        try:
            # 查询模板
            documents = self.infra_service.document_manager.query_documents(
                store_name=self.infra_service.store_name,
                tags=["template"],
                status=self.infra_service.STATUS_ACTIVE
            )
            
            # 转换为简化格式
            result = []
            for doc in documents:
                # 创建模板摘要
                template = {
                    "id": doc.id,
                    "name": doc.content.get("name", ""),
                    "description": doc.content.get("description", ""),
                    "strategy_type": doc.content.get("strategy_type", ""),
                    "parameters": doc.content.get("parameters", {}),
                    "created_at": doc.metadata.created_at.isoformat() if doc.metadata.created_at else "",
                    "author": doc.metadata.author
                }
                
                result.append(template)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting strategy templates: {str(e)}")
            return []