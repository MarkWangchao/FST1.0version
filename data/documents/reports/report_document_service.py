"""
报告文档服务 - 专门处理报告相关的文档操作

该服务基于通用文档管理器，提供针对报告特性的功能：
- 报告的创建、读取、更新和删除
- 报告版本控制
- 报告模板管理
- 报告导出功能
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


class ReportDocumentService:
    """
    报告文档服务 - 专门处理报告相关的文档操作
    
    提供功能:
    - 报告的创建、读取、更新和删除
    - 报告版本控制
    - 报告模板管理
    - 报告导出功能
    """
    
    # 报告状态常量
    STATUS_DRAFT = DocumentStatus.DRAFT
    STATUS_PUBLISHED = DocumentStatus.PUBLISHED
    STATUS_ARCHIVED = DocumentStatus.ARCHIVED
    STATUS_DELETED = DocumentStatus.DELETED
    
    # 报告内容类型
    CONTENT_TYPE = "application/json"
    
    # 默认标签
    DEFAULT_TAGS = ["report"]
    
    # 报告文档模式
    SCHEMA = "report/v1"
    
    # 报告类型
    REPORT_TYPE_TRADING = "trading"      # 交易报告
    REPORT_TYPE_PERFORMANCE = "performance"  # 绩效报告
    REPORT_TYPE_RISK = "risk"           # 风险报告
    REPORT_TYPE_STRATEGY = "strategy"    # 策略报告
    REPORT_TYPE_CUSTOM = "custom"       # 自定义报告
    
    def __init__(self, document_manager: Optional[DocumentManager] = None):
        """
        初始化报告文档服务
        
        Args:
            document_manager: 文档管理器实例，如不提供则创建默认实例
        """
        self.document_manager = document_manager or DocumentManager()
        # 使用固定的存储名称
        self.store_name = DocumentManager.REPORT_DOCS
        logger.info(f"Report Document Service initialized using store: {self.store_name}")
    
    def create_report(self,
                   title: str,
                   report_type: str,
                   content: Dict[str, Any],
                   author: Optional[str] = None,
                   description: Optional[str] = None,
                   related_ids: Optional[Dict[str, str]] = None,
                   tags: Optional[List[str]] = None,
                   template_id: Optional[str] = None,
                   status: DocumentStatus = STATUS_DRAFT) -> Optional[str]:
        """
        创建新报告
        
        Args:
            title: 报告标题
            report_type: 报告类型
            content: 报告内容
            author: 作者
            description: 报告描述
            related_ids: 相关ID(如策略ID、回测ID等)
            tags: 标签列表
            template_id: 模板ID(如果基于模板创建)
            status: 报告状态
            
        Returns:
            Optional[str]: 报告ID，如果失败则返回None
        """
        try:
            # 构建报告内容
            report_content = {
                "title": title,
                "type": report_type,
                "description": description,
                "content": content,
                "related_ids": related_ids or {},
                "template_id": template_id,
                "created_by": author,
                "created_at": datetime.now().isoformat()
            }
            
            # 合并标签
            report_tags = list(self.DEFAULT_TAGS)
            if tags:
                report_tags.extend([tag for tag in tags if tag not in report_tags])
            
            # 添加类型标签
            type_tag = f"type:{report_type}"
            if type_tag not in report_tags:
                report_tags.append(type_tag)
            
            # 添加相关ID标签
            if related_ids:
                for key, value in related_ids.items():
                    relation_tag = f"{key}:{value}"
                    if relation_tag not in report_tags:
                        report_tags.append(relation_tag)
            
            # 创建自定义元数据
            custom_metadata = {
                "title": title,
                "type": report_type,
                "description": description,
                "related_ids": related_ids
            }
            
            # 创建报告文档
            report_id = self.document_manager.create_document(
                content=report_content,
                store_name=self.store_name,
                author=author,
                content_type=self.CONTENT_TYPE,
                tags=report_tags,
                custom_metadata=custom_metadata,
                schema=self.SCHEMA
            )
            
            if report_id:
                # 设置初始状态
                success = self.document_manager.update_document(
                    doc_id=report_id,
                    store_name=self.store_name,
                    status=status
                )
                
                if not success:
                    logger.warning(f"Created report {report_id} but failed to set status to {status.value}")
            
            logger.info(f"Created report '{title}' with ID: {report_id}")
            return report_id
            
        except Exception as e:
            logger.error(f"Error creating report '{title}': {str(e)}")
            return None
    
    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        获取报告
        
        Args:
            report_id: 报告ID
            
        Returns:
            Optional[Dict[str, Any]]: 报告内容，如不存在则返回None
        """
        try:
            document = self.document_manager.load_document(report_id, self.store_name)
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
            logger.error(f"Error getting report {report_id}: {str(e)}")
            return None
    
    def update_report(self,
                   report_id: str,
                   title: Optional[str] = None,
                   description: Optional[str] = None,
                   content: Optional[Dict[str, Any]] = None,
                   author: Optional[str] = None,
                   comment: Optional[str] = None,
                   tags_to_add: Optional[List[str]] = None,
                   tags_to_remove: Optional[List[str]] = None,
                   related_ids: Optional[Dict[str, str]] = None) -> bool:
        """
        更新报告
        
        Args:
            report_id: 报告ID
            title: 新标题
            description: 新描述
            content: 新内容
            author: 更新作者
            comment: 更新注释
            tags_to_add: 要添加的标签
            tags_to_remove: 要移除的标签
            related_ids: 更新相关ID
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 获取当前报告
            document = self.document_manager.load_document(report_id, self.store_name)
            if not document:
                logger.error(f"Report {report_id} not found")
                return False
            
            # 更新内容
            if isinstance(document.content, dict):
                updated_content = document.content.copy()
                if title:
                    updated_content["title"] = title
                if description:
                    updated_content["description"] = description
                if content:
                    updated_content["content"] = content
                if related_ids:
                    updated_content["related_ids"] = related_ids
            else:
                updated_content = content if content is not None else document.content
            
            # 更新文档
            success = self.document_manager.update_document(
                doc_id=report_id,
                store_name=self.store_name,
                content=updated_content,
                author=author,
                comment=comment,
                tags_to_add=tags_to_add,
                tags_to_remove=tags_to_remove
            )
            
            if success:
                logger.info(f"Updated report {report_id}")
            else:
                logger.error(f"Failed to update report {report_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error updating report {report_id}: {str(e)}")
            return False
    
    def update_report_status(self,
                         report_id: str,
                         status: DocumentStatus,
                         author: Optional[str] = None) -> bool:
        """
        更新报告状态
        
        Args:
            report_id: 报告ID
            status: 新状态
            author: 更新作者
            
        Returns:
            bool: 是否更新成功
        """
        try:
            success = self.document_manager.update_document(
                doc_id=report_id,
                store_name=self.store_name,
                status=status,
                author=author
            )
            
            if success:
                logger.info(f"Updated report {report_id} status to {status.value}")
            else:
                logger.error(f"Failed to update report {report_id} status")
                
            return success
            
        except Exception as e:
            logger.error(f"Error updating report {report_id} status: {str(e)}")
            return False
    
    def delete_report(self, report_id: str, permanent: bool = False) -> bool:
        """
        删除报告
        
        Args:
            report_id: 报告ID
            permanent: 是否永久删除，True为物理删除，False为标记为已删除状态
            
        Returns:
            bool: 是否删除成功
        """
        try:
            if permanent:
                # 物理删除
                success = self.document_manager.delete_document(report_id, self.store_name)
                if success:
                    logger.info(f"Permanently deleted report {report_id}")
                else:
                    logger.error(f"Failed to permanently delete report {report_id}")
            else:
                # 标记为已删除状态
                success = self.update_report_status(report_id, self.STATUS_DELETED)
                if success:
                    logger.info(f"Marked report {report_id} as deleted")
                else:
                    logger.error(f"Failed to mark report {report_id} as deleted")
                    
            return success
            
        except Exception as e:
            logger.error(f"Error deleting report {report_id}: {str(e)}")
            return False
    
    def list_reports(self,
                  report_type: Optional[str] = None,
                  status: Optional[DocumentStatus] = None,
                  author: Optional[str] = None,
                  tags: Optional[List[str]] = None,
                  related_id: Optional[str] = None,
                  start_date: Optional[str] = None,
                  end_date: Optional[str] = None,
                  limit: int = 100,
                  offset: int = 0) -> List[Dict[str, Any]]:
        """
        列出报告
        
        Args:
            report_type: 报告类型过滤
            status: 状态过滤
            author: 作者过滤
            tags: 标签过滤
            related_id: 相关ID过滤
            start_date: 开始日期过滤
            end_date: 结束日期过滤
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 报告列表
        """
        try:
            # 构建查询条件
            query = {}
            search_tags = tags or []
            
            # 报告类型过滤
            if report_type:
                type_tag = f"type:{report_type}"
                search_tags.append(type_tag)
            
            # 相关ID过滤
            if related_id:
                # 搜索所有可能包含此ID的标签
                id_tags = [tag for tag in search_tags if related_id in tag]
                search_tags.extend(id_tags)
            
            # 日期过滤
            if start_date:
                query["content.created_at"] = {"$gte": start_date}
            if end_date:
                query["content.created_at"] = {"$lte": end_date}
            
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
            reports = []
            for doc in results:
                if isinstance(doc, dict):
                    # 直接使用搜索返回的字典
                    reports.append(doc)
                else:
                    # 如果是DocumentItem实例，转换为字典
                    try:
                        # 基础信息
                        report = {
                            "id": doc.id,
                            "status": doc.metadata.status.value,
                            "tags": doc.metadata.tags,
                            "author": doc.metadata.author,
                            "created_at": doc.metadata.created_at.isoformat(),
                            "updated_at": doc.metadata.updated_at.isoformat()
                        }
                        
                        # 添加内容摘要
                        if isinstance(doc.content, dict):
                            report.update({
                                "title": doc.content.get("title"),
                                "type": doc.content.get("type"),
                                "description": doc.content.get("description"),
                                "related_ids": doc.content.get("related_ids", {})
                            })
                        else:
                            report["content"] = doc.content
                            
                        reports.append(report)
                    except Exception as e:
                        logger.error(f"Error processing report document: {str(e)}")
            
            return reports
            
        except Exception as e:
            logger.error(f"Error listing reports: {str(e)}")
            return []
    
    def get_report_versions(self, report_id: str) -> List[Dict[str, Any]]:
        """
        获取报告版本历史
        
        Args:
            report_id: 报告ID
            
        Returns:
            List[Dict[str, Any]]: 版本列表
        """
        try:
            return self.document_manager.get_document_versions(report_id, self.store_name)
        except Exception as e:
            logger.error(f"Error getting versions for report {report_id}: {str(e)}")
            return []
    
    def get_report_by_version(self, report_id: str, version_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定版本的报告
        
        Args:
            report_id: 报告ID
            version_id: 版本ID
            
        Returns:
            Optional[Dict[str, Any]]: 报告内容，如不存在则返回None
        """
        try:
            document = self.document_manager.get_document_by_version(
                report_id, version_id, self.store_name)
            
            if not document:
                return None
                
            # 转换为字典格式
            result = document.content.copy() if isinstance(document.content, dict) else {"content": document.content}
            result.update({
                "id": document.id,
                "version_id": version_id,
                "status": document.metadata.status.value,
                "author": document.metadata.author,
                "created_at": document.metadata.created_at.isoformat(),
                "updated_at": document.metadata.updated_at.isoformat()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting version {version_id} of report {report_id}: {str(e)}")
            return None
    
    def create_report_template(self,
                          title: str,
                          report_type: str,
                          template_content: Dict[str, Any],
                          author: Optional[str] = None,
                          description: Optional[str] = None,
                          tags: Optional[List[str]] = None) -> Optional[str]:
        """
        创建报告模板
        
        Args:
            title: 模板标题
            report_type: 报告类型
            template_content: 模板内容
            author: 作者
            description: 描述
            tags: 标签列表
            
        Returns:
            Optional[str]: 模板ID，如果失败则返回None
        """
        try:
            # 构建模板内容
            template = {
                "title": title,
                "type": report_type,
                "description": description,
                "template_content": template_content,
                "created_by": author,
                "created_at": datetime.now().isoformat()
            }
            
            # 添加模板标签
            template_tags = ["report_template", f"type:{report_type}"]
            if tags:
                template_tags.extend(tags)
            
            # 创建模板文档
            template_id = self.create_report(
                title=title,
                report_type=report_type,
                content=template,
                author=author,
                description=description,
                tags=template_tags,
                status=self.STATUS_PUBLISHED
            )
            
            if template_id:
                logger.info(f"Created report template '{title}' with ID: {template_id}")
            else:
                logger.error(f"Failed to create report template '{title}'")
                
            return template_id
            
        except Exception as e:
            logger.error(f"Error creating report template '{title}': {str(e)}")
            return None
    
    def get_report_templates(self,
                         report_type: Optional[str] = None,
                         limit: int = 100,
                         offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取报告模板列表
        
        Args:
            report_type: 报告类型过滤
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 模板列表
        """
        try:
            # 构建查询标签
            search_tags = ["report_template"]
            if report_type:
                search_tags.append(f"type:{report_type}")
            
            # 搜索模板
            return self.list_reports(
                tags=search_tags,
                status=self.STATUS_PUBLISHED,
                limit=limit,
                offset=offset
            )
            
        except Exception as e:
            logger.error(f"Error getting report templates: {str(e)}")
            return []
    
    def create_report_from_template(self,
                               template_id: str,
                               title: str,
                               content: Dict[str, Any],
                               author: Optional[str] = None,
                               description: Optional[str] = None,
                               related_ids: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        基于模板创建报告
        
        Args:
            template_id: 模板ID
            title: 报告标题
            content: 报告内容
            author: 作者
            description: 描述
            related_ids: 相关ID
            
        Returns:
            Optional[str]: 报告ID，如果失败则返回None
        """
        try:
            # 获取模板
            template = self.get_report(template_id)
            if not template:
                logger.error(f"Template {template_id} not found")
                return None
            
            # 创建报告
            report_id = self.create_report(
                title=title,
                report_type=template["type"],
                content=content,
                author=author,
                description=description,
                related_ids=related_ids,
                template_id=template_id,
                status=self.STATUS_DRAFT
            )
            
            if report_id:
                logger.info(f"Created report '{title}' from template {template_id}")
            else:
                logger.error(f"Failed to create report from template {template_id}")
                
            return report_id
            
        except Exception as e:
            logger.error(f"Error creating report from template {template_id}: {str(e)}")
            return None
    
    def export_report(self, report_id: str, export_path: str, format: str = "json") -> bool:
        """
        导出报告
        
        Args:
            report_id: 报告ID
            export_path: 导出文件路径
            format: 导出格式，支持json或html
            
        Returns:
            bool: 是否导出成功
        """
        try:
            # 获取报告
            report = self.get_report(report_id)
            if not report:
                logger.error(f"Report {report_id} not found")
                return False
            
            # 导出到文件
            if format.lower() == "json":
                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            elif format.lower() == "html":
                # 这里可以添加HTML导出逻辑
                # 例如使用模板引擎生成HTML报告
                logger.error("HTML export not implemented yet")
                return False
            else:
                logger.error(f"Unsupported format: {format}")
                return False
            
            logger.info(f"Exported report {report_id} to {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting report {report_id}: {str(e)}")
            return False
    
    def get_related_reports(self, related_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取与指定ID相关的报告
        
        Args:
            related_id: 相关ID
            limit: 返回结果数量限制
            
        Returns:
            List[Dict[str, Any]]: 相关报告列表
        """
        try:
            return self.list_reports(
                related_id=related_id,
                status=self.STATUS_PUBLISHED,
                limit=limit
            )
            
        except Exception as e:
            logger.error(f"Error getting related reports for ID {related_id}: {str(e)}")
            return []