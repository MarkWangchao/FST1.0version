"""
策略文档服务 - 专门处理与交易策略相关的文档操作

该服务基于通用文档管理器，提供针对策略特性的功能：
- 策略创建和管理
- 策略参数版本控制
- 策略模板和复制
- 策略分类和标签
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import uuid

from data.document.document_item import DocumentItem, DocumentStatus, DocumentMetadata
from data.document.document_manager import DocumentManager

logger = logging.getLogger(__name__)


class StrategyDocumentService:
    """
    策略文档服务 - 专门处理策略相关的文档操作
    
    提供功能:
    - 策略文档的创建、读取、更新和删除
    - 策略参数版本控制
    - 策略导入导出
    - 策略模板和克隆
    """
    
    # 策略状态常量
    STATUS_DRAFT = DocumentStatus.DRAFT
    STATUS_ACTIVE = DocumentStatus.PUBLISHED
    STATUS_ARCHIVED = DocumentStatus.ARCHIVED
    STATUS_DELETED = DocumentStatus.DELETED
    
    # 策略内容类型
    CONTENT_TYPE = "application/json"
    
    # 默认标签
    DEFAULT_TAGS = ["strategy"]
    
    # 策略文档模式
    SCHEMA = "strategy/v1"
    
    def __init__(self, document_manager: Optional[DocumentManager] = None):
        """
        初始化策略文档服务
        
        Args:
            document_manager: 文档管理器实例，如不提供则创建默认实例
        """
        self.document_manager = document_manager or DocumentManager()
        # 使用固定的存储名称
        self.store_name = DocumentManager.STRATEGY_DOCS
        logger.info(f"Strategy Document Service initialized using store: {self.store_name}")
    
    def create_strategy(self, 
                       name: str,
                       description: str,
                       strategy_type: str,
                       parameters: Dict[str, Any],
                       author: Optional[str] = None,
                       tags: Optional[List[str]] = None,
                       status: DocumentStatus = STATUS_DRAFT) -> Optional[str]:
        """
        创建新策略
        
        Args:
            name: 策略名称
            description: 策略描述
            strategy_type: 策略类型（例如："ma_cross", "mean_reversion"）
            parameters: 策略参数字典
            author: 作者
            tags: 标签列表，None则使用默认标签
            status: 策略状态
            
        Returns:
            Optional[str]: 策略ID，如果失败则返回None
        """
        # 构建策略内容
        content = {
            "name": name,
            "description": description,
            "strategy_type": strategy_type,
            "parameters": parameters,
            "created_by": author
        }
        
        # 合并标签
        strategy_tags = list(self.DEFAULT_TAGS)
        if tags:
            strategy_tags.extend([tag for tag in tags if tag not in strategy_tags])
        
        # 添加策略类型标签
        if strategy_type and strategy_type not in strategy_tags:
            strategy_tags.append(strategy_type)
        
        # 创建自定义元数据
        custom_metadata = {
            "title": name,
            "strategy_type": strategy_type
        }
        
        try:
            # 创建策略文档
            strategy_id = self.document_manager.create_document(
                content=content,
                store_name=self.store_name,
                author=author,
                content_type=self.CONTENT_TYPE,
                tags=strategy_tags,
                custom_metadata=custom_metadata,
                schema=self.SCHEMA
            )
            
            if strategy_id and status != self.STATUS_DRAFT:
                # 设置初始状态
                success = self.update_strategy_status(strategy_id, status, author)
                if not success:
                    logger.warning(f"Created strategy {strategy_id} but failed to set initial status to {status.value}")
            
            logger.info(f"Created strategy '{name}' with ID: {strategy_id}")
            return strategy_id
            
        except Exception as e:
            logger.error(f"Error creating strategy '{name}': {str(e)}")
            return None
    
    def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        获取策略文档
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            Optional[Dict[str, Any]]: 策略文档，如不存在则返回None
        """
        try:
            document = self.document_manager.load_document(strategy_id, self.store_name)
            if not document:
                return None
                
            # 创建结果字典，包含内容和元数据
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
            logger.error(f"Error getting strategy {strategy_id}: {str(e)}")
            return None
    
    def update_strategy(self, 
                      strategy_id: str,
                      name: Optional[str] = None,
                      description: Optional[str] = None,
                      parameters: Optional[Dict[str, Any]] = None,
                      author: Optional[str] = None,
                      comment: Optional[str] = None,
                      tags_to_add: Optional[List[str]] = None,
                      tags_to_remove: Optional[List[str]] = None) -> bool:
        """
        更新策略
        
        Args:
            strategy_id: 策略ID
            name: 新策略名称，None则不更新
            description: 新策略描述，None则不更新
            parameters: 新策略参数，None则不更新
            author: 更新作者
            comment: 更新注释
            tags_to_add: 要添加的标签
            tags_to_remove: 要移除的标签
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 加载原始文档
            document = self.document_manager.load_document(strategy_id, self.store_name)
            if not document:
                logger.error(f"Strategy {strategy_id} not found")
                return False
                
            # 更新内容
            content = None
            custom_metadata = None
            
            if name is not None or description is not None or parameters is not None:
                content = document.content.copy() if isinstance(document.content, dict) else {}
                
                if name is not None:
                    content["name"] = name
                    # 同时更新元数据中的标题
                    custom_metadata = {"title": name}
                
                if description is not None:
                    content["description"] = description
                
                if parameters is not None:
                    content["parameters"] = parameters
            
            # 更新文档
            success = self.document_manager.update_document(
                doc_id=strategy_id,
                store_name=self.store_name,
                content=content,
                author=author,
                comment=comment,
                tags_to_add=tags_to_add,
                tags_to_remove=tags_to_remove,
                custom_metadata=custom_metadata
            )
            
            if success:
                logger.info(f"Updated strategy {strategy_id}")
            else:
                logger.error(f"Failed to update strategy {strategy_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error updating strategy {strategy_id}: {str(e)}")
            return False
    
    def update_strategy_status(self, 
                             strategy_id: str, 
                             status: DocumentStatus,
                             author: Optional[str] = None) -> bool:
        """
        更新策略状态
        
        Args:
            strategy_id: 策略ID
            status: 新状态
            author: 更新作者
            
        Returns:
            bool: 是否更新成功
        """
        try:
            success = self.document_manager.update_document(
                doc_id=strategy_id,
                store_name=self.store_name,
                author=author,
                status=status
            )
            
            if success:
                logger.info(f"Updated strategy {strategy_id} status to {status.value}")
            else:
                logger.error(f"Failed to update strategy {strategy_id} status")
                
            return success
            
        except Exception as e:
            logger.error(f"Error updating strategy {strategy_id} status: {str(e)}")
            return False
    
    def delete_strategy(self, strategy_id: str, permanent: bool = False) -> bool:
        """
        删除策略
        
        Args:
            strategy_id: 策略ID
            permanent: 是否永久删除，True为物理删除，False为标记为已删除状态
            
        Returns:
            bool: 是否删除成功
        """
        try:
            if permanent:
                # 物理删除
                success = self.document_manager.delete_document(strategy_id, self.store_name)
                if success:
                    logger.info(f"Permanently deleted strategy {strategy_id}")
                else:
                    logger.error(f"Failed to permanently delete strategy {strategy_id}")
            else:
                # 标记为已删除状态
                success = self.update_strategy_status(strategy_id, self.STATUS_DELETED)
                if success:
                    logger.info(f"Marked strategy {strategy_id} as deleted")
                else:
                    logger.error(f"Failed to mark strategy {strategy_id} as deleted")
                    
            return success
            
        except Exception as e:
            logger.error(f"Error deleting strategy {strategy_id}: {str(e)}")
            return False
    
    def list_strategies(self, 
                      status: Optional[DocumentStatus] = None,
                      strategy_type: Optional[str] = None,
                      author: Optional[str] = None,
                      tags: Optional[List[str]] = None,
                      limit: int = 100,
                      offset: int = 0) -> List[Dict[str, Any]]:
        """
        列出策略
        
        Args:
            status: 策略状态过滤
            strategy_type: 策略类型过滤
            author: 作者过滤
            tags: 标签过滤
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 策略列表
        """
        try:
            # 构建查询条件
            query = {}
            if strategy_type:
                query["content.strategy_type"] = strategy_type
            
            # 使用文档管理器搜索
            results = self.document_manager.search_documents(
                query=query,
                tags=tags,
                author=author,
                status=status,
                store_name=self.store_name,
                limit=limit,
                offset=offset
            )
            
            # 处理结果
            strategies = []
            for doc in results:
                if isinstance(doc, dict):
                    # 直接使用搜索返回的字典
                    strategies.append(doc)
                else:
                    # 如果是DocumentItem实例，转换为字典
                    try:
                        strategy = doc.content.copy() if isinstance(doc.content, dict) else {"content": doc.content}
                        strategy.update({
                            "id": doc.id,
                            "status": doc.metadata.status.value,
                            "tags": doc.metadata.tags,
                            "author": doc.metadata.author,
                            "created_at": doc.metadata.created_at.isoformat(),
                            "updated_at": doc.metadata.updated_at.isoformat()
                        })
                        strategies.append(strategy)
                    except Exception as e:
                        logger.error(f"Error processing strategy document: {str(e)}")
            
            return strategies
            
        except Exception as e:
            logger.error(f"Error listing strategies: {str(e)}")
            return []
    
    def get_strategy_versions(self, strategy_id: str) -> List[Dict[str, Any]]:
        """
        获取策略版本历史
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            List[Dict[str, Any]]: 版本历史列表
        """
        try:
            return self.document_manager.get_document_versions(strategy_id, self.store_name)
        except Exception as e:
            logger.error(f"Error getting strategy {strategy_id} versions: {str(e)}")
            return []
    
    def get_strategy_by_version(self, strategy_id: str, version_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定版本的策略
        
        Args:
            strategy_id: 策略ID
            version_id: 版本ID
            
        Returns:
            Optional[Dict[str, Any]]: 策略文档，如不存在则返回None
        """
        try:
            document = self.document_manager.get_document_by_version(
                doc_id=strategy_id,
                version_id=version_id,
                store_name=self.store_name
            )
            
            if not document:
                return None
                
            # 创建结果字典
            result = document.content.copy() if isinstance(document.content, dict) else {"content": document.content}
            
            # 添加元数据
            result.update({
                "id": document.id,
                "status": document.metadata.status.value,
                "version": document.metadata.version,
                "version_id": version_id,
                "tags": document.metadata.tags,
                "author": document.metadata.author,
                "created_at": document.metadata.created_at.isoformat(),
                "updated_at": document.metadata.updated_at.isoformat()
            })
            
            # 查找版本信息
            for version in document.versions:
                if version.version_id == version_id:
                    result["version_info"] = {
                        "created_at": version.created_at.isoformat(),
                        "created_by": version.created_by,
                        "comment": version.comment
                    }
                    break
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting strategy {strategy_id} version {version_id}: {str(e)}")
            return None
    
    def clone_strategy(self, 
                     strategy_id: str,
                     new_name: str,
                     author: Optional[str] = None,
                     description: Optional[str] = None,
                     parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        克隆策略
        
        Args:
            strategy_id: 源策略ID
            new_name: 新策略名称
            author: 新作者
            description: 新描述，如为None则使用源策略描述
            parameters: 新参数，如为None则使用源策略参数
            
        Returns:
            Optional[str]: 新策略ID，如果失败则返回None
        """
        try:
            # 加载源策略
            source = self.get_strategy(strategy_id)
            if not source:
                logger.error(f"Source strategy {strategy_id} not found")
                return None
                
            # 使用源策略值或提供的新值
            source_description = source.get("description", "")
            source_strategy_type = source.get("strategy_type", "unknown")
            source_parameters = source.get("parameters", {})
            source_tags = source.get("tags", [])
            
            # 创建新策略
            return self.create_strategy(
                name=new_name,
                description=description if description is not None else source_description,
                strategy_type=source_strategy_type,
                parameters=parameters if parameters is not None else source_parameters,
                author=author,
                tags=source_tags,
                status=self.STATUS_DRAFT  # 克隆的策略总是以草稿状态开始
            )
            
        except Exception as e:
            logger.error(f"Error cloning strategy {strategy_id}: {str(e)}")
            return None
    
    def export_strategy(self, strategy_id: str, export_path: str) -> bool:
        """
        导出策略到文件
        
        Args:
            strategy_id: 策略ID
            export_path: 导出文件路径
            
        Returns:
            bool: 是否导出成功
        """
        try:
            # 加载策略
            strategy = self.get_strategy(strategy_id)
            if not strategy:
                logger.error(f"Strategy {strategy_id} not found")
                return False
                
            # 导出到文件
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(strategy, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Exported strategy {strategy_id} to {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting strategy {strategy_id}: {str(e)}")
            return False
    
    def import_strategy(self, import_path: str, author: Optional[str] = None) -> Optional[str]:
        """
        从文件导入策略
        
        Args:
            import_path: 导入文件路径
            author: 导入作者，如为None则使用文件中的作者
            
        Returns:
            Optional[str]: 新策略ID，如果失败则返回None
        """
        try:
            # 读取文件
            with open(import_path, 'r', encoding='utf-8') as f:
                strategy_data = json.load(f)
                
            # 提取必要信息
            name = strategy_data.get("name")
            description = strategy_data.get("description")
            strategy_type = strategy_data.get("strategy_type")
            parameters = strategy_data.get("parameters")
            tags = strategy_data.get("tags", [])
            
            # 验证必要字段
            if not name or not strategy_type:
                logger.error(f"Invalid strategy file: missing required fields")
                return None
                
            # 创建新策略
            return self.create_strategy(
                name=name,
                description=description or "",
                strategy_type=strategy_type,
                parameters=parameters or {},
                author=author or strategy_data.get("author"),
                tags=tags,
                status=self.STATUS_DRAFT  # 导入的策略总是以草稿状态开始
            )
            
        except Exception as e:
            logger.error(f"Error importing strategy from {import_path}: {str(e)}")
            return None
    
    def create_strategy_template(self, 
                               name: str,
                               description: str,
                               strategy_type: str,
                               parameters: Dict[str, Any],
                               author: Optional[str] = None,
                               tags: Optional[List[str]] = None) -> Optional[str]:
        """
        创建策略模板
        
        Args:
            name: 模板名称
            description: 模板描述
            strategy_type: 策略类型
            parameters: 默认参数
            author: 作者
            tags: 标签列表
            
        Returns:
            Optional[str]: 模板ID，如果失败则返回None
        """
        # 添加模板标签
        template_tags = tags or []
        if "template" not in template_tags:
            template_tags.append("template")
            
        # 创建模板就是创建一个特殊标记的策略
        return self.create_strategy(
            name=name,
            description=description,
            strategy_type=strategy_type,
            parameters=parameters,
            author=author,
            tags=template_tags,
            status=self.STATUS_PUBLISHED  # 模板通常是已发布状态
        )
    
    def get_strategy_templates(self, 
                            strategy_type: Optional[str] = None,
                            limit: int = 100,
                            offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取策略模板列表
        
        Args:
            strategy_type: 策略类型过滤
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 模板列表
        """
        # 使用模板标签过滤
        return self.list_strategies(
            status=self.STATUS_PUBLISHED,
            strategy_type=strategy_type,
            tags=["template"],
            limit=limit,
            offset=offset
        )
    
    def create_strategy_from_template(self,
                                  template_id: str,
                                  new_name: str,
                                  author: Optional[str] = None,
                                  parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        从模板创建策略
        
        Args:
            template_id: 模板ID
            new_name: 新策略名称
            author: 作者
            parameters: 自定义参数，如为None则使用模板默认参数
            
        Returns:
            Optional[str]: 新策略ID，如果失败则返回None
        """
        # 基本上就是克隆，但去掉模板标签
        try:
            # 克隆策略
            new_strategy_id = self.clone_strategy(
                strategy_id=template_id,
                new_name=new_name,
                author=author,
                parameters=parameters
            )
            
            if new_strategy_id:
                # 移除模板标签
                self.document_manager.update_document(
                    doc_id=new_strategy_id,
                    store_name=self.store_name,
                    tags_to_remove=["template"]
                )
                
                logger.info(f"Created strategy {new_strategy_id} from template {template_id}")
                
            return new_strategy_id
            
        except Exception as e:
            logger.error(f"Error creating strategy from template {template_id}: {str(e)}")
            return None