"""
报告文档服务 - 报告模块专用的文档服务接口

该服务作为报告模块的一部分，提供了便捷的接口来创建和管理报告文档，
同时封装了底层存储细节，并提供报告特定的功能增强。
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime
import importlib
import uuid

# 导入基础设施层的报告文档服务
from infrastructure.storage.document.report_document_service import ReportDocumentService as InfraReportDocumentService
from data.document.document_item import DocumentStatus

logger = logging.getLogger(__name__)


class ReportDocumentService:
    """
    报告文档服务 - 报告模块专用接口
    
    在底层存储服务的基础上提供额外功能:
    - 报告生成与模板管理
    - 报告导出为多种格式
    - 定期报告调度
    - 报告通知
    - 报告批量处理
    """
    
    # 报告类型常量
    REPORT_TYPE_DAILY = "daily_trading"         # 每日交易报告
    REPORT_TYPE_WEEKLY = "weekly_trading"       # 每周交易报告
    REPORT_TYPE_MONTHLY = "monthly_trading"     # 每月交易报告
    REPORT_TYPE_PERFORMANCE = "performance"     # 绩效报告
    REPORT_TYPE_STRATEGY = "strategy"           # 策略报告
    REPORT_TYPE_RISK = "risk"                   # 风险报告
    REPORT_TYPE_BACKTEST = "backtest"           # 回测报告
    REPORT_TYPE_CUSTOM = "custom"               # 自定义报告
    
    # 报告格式常量
    FORMAT_JSON = "json"
    FORMAT_HTML = "html"
    FORMAT_PDF = "pdf"
    FORMAT_CSV = "csv"
    FORMAT_EXCEL = "excel"
    
    def __init__(self):
        """初始化报告文档服务"""
        # 使用基础设施层的报告文档服务
        self.infra_service = InfraReportDocumentService()
        logger.info("Report Document Service initialized")
    
    def create_report(self,
                    title: str,
                    report_type: str,
                    content: Dict[str, Any],
                    author: Optional[str] = None,
                    description: Optional[str] = None,
                    related_ids: Optional[Dict[str, str]] = None,
                    tags: Optional[List[str]] = None,
                    template_id: Optional[str] = None) -> Optional[str]:
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
            
        Returns:
            Optional[str]: 报告ID，如果失败则返回None
        """
        # 添加元数据
        report_content = content.copy()
        report_content["generated_at"] = datetime.now().isoformat()
        
        # 创建报告
        return self.infra_service.create_report(
            title=title,
            report_type=report_type,
            content=report_content,
            author=author,
            description=description,
            related_ids=related_ids,
            tags=tags,
            template_id=template_id,
            status=self.infra_service.STATUS_DRAFT
        )
    
    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        获取报告
        
        Args:
            report_id: 报告ID
            
        Returns:
            Optional[Dict[str, Any]]: 报告内容，如不存在则返回None
        """
        return self.infra_service.get_report(report_id)
    
    def publish_report(self, report_id: str, author: Optional[str] = None) -> bool:
        """
        发布报告
        
        Args:
            report_id: 报告ID
            author: 操作者
            
        Returns:
            bool: 是否发布成功
        """
        return self.infra_service.update_report_status(
            report_id=report_id,
            status=self.infra_service.STATUS_PUBLISHED,
            author=author
        )
    
    def archive_report(self, report_id: str, author: Optional[str] = None) -> bool:
        """
        归档报告
        
        Args:
            report_id: 报告ID
            author: 操作者
            
        Returns:
            bool: 是否归档成功
        """
        return self.infra_service.update_report_status(
            report_id=report_id,
            status=self.infra_service.STATUS_ARCHIVED,
            author=author
        )
    
    def delete_report(self, report_id: str, author: Optional[str] = None) -> bool:
        """
        删除报告
        
        Args:
            report_id: 报告ID
            author: 操作者
            
        Returns:
            bool: 是否删除成功
        """
        return self.infra_service.update_report_status(
            report_id=report_id,
            status=self.infra_service.STATUS_DELETED,
            author=author
        )
    
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
            description: 模板描述
            tags: 标签列表
            
        Returns:
            Optional[str]: 模板ID，如果失败则返回None
        """
        # 添加模板标签
        template_tags = tags or []
        if "template" not in template_tags:
            template_tags.append("template")
        
        # 创建模板内容
        content = {
            "is_template": True,
            "template_content": template_content,
            "template_variables": self._extract_template_variables(template_content)
        }
        
        # 创建报告
        return self.infra_service.create_report(
            title=f"Template: {title}",
            report_type=report_type,
            content=content,
            author=author,
            description=description,
            tags=template_tags,
            status=self.infra_service.STATUS_PUBLISHED
        )
    
    def _extract_template_variables(self, template_content: Dict[str, Any]) -> List[str]:
        """
        从模板内容中提取变量
        
        Args:
            template_content: 模板内容
            
        Returns:
            List[str]: 变量列表
        """
        variables = []
        content_str = json.dumps(template_content)
        
        # 简单的变量提取，假设变量格式为 {{variable_name}}
        import re
        var_matches = re.findall(r'{{([\w\d_]+)}}', content_str)
        variables.extend(var_matches)
        
        return list(set(variables))  # 去重
    
    def create_report_from_template(self,
                                  template_id: str,
                                  variable_values: Dict[str, Any],
                                  title: Optional[str] = None,
                                  author: Optional[str] = None,
                                  description: Optional[str] = None,
                                  related_ids: Optional[Dict[str, str]] = None,
                                  tags: Optional[List[str]] = None) -> Optional[str]:
        """
        从模板创建报告
        
        Args:
            template_id: 模板ID
            variable_values: 变量值
            title: 报告标题，如果为None则使用模板标题
            author: 作者
            description: 报告描述，如果为None则使用模板描述
            related_ids: 相关ID
            tags: 标签列表
            
        Returns:
            Optional[str]: 报告ID，如果失败则返回None
        """
        # 获取模板
        template = self.get_report(template_id)
        if not template or not template.get("content", {}).get("is_template"):
            logger.error(f"Template {template_id} not found or not a valid template")
            return None
        
        # 获取模板内容
        template_content = template.get("content", {}).get("template_content", {})
        
        # 替换变量
        report_content = self._replace_template_variables(template_content, variable_values)
        
        # 使用模板字段（如果未提供）
        if title is None:
            title = template.get("title", "").replace("Template: ", "")
        
        if description is None:
            description = template.get("description", "")
        
        # 创建报告
        return self.create_report(
            title=title,
            report_type=template.get("type", self.REPORT_TYPE_CUSTOM),
            content=report_content,
            author=author,
            description=description,
            related_ids=related_ids,
            tags=tags,
            template_id=template_id
        )
    
    def _replace_template_variables(self, 
                                   template_content: Dict[str, Any], 
                                   variable_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        替换模板变量
        
        Args:
            template_content: 模板内容
            variable_values: 变量值
            
        Returns:
            Dict[str, Any]: 替换变量后的内容
        """
        content_str = json.dumps(template_content)
        
        # 替换变量
        for var_name, var_value in variable_values.items():
            placeholder = f"{{{{{var_name}}}}}"
            
            # 转换值为字符串（如果需要）
            if isinstance(var_value, (dict, list)):
                value_str = json.dumps(var_value)
                # 移除引号，以便正确解析JSON
                content_str = content_str.replace(f'"{placeholder}"', value_str)
            else:
                value_str = str(var_value)
                # 字符串值保留引号
                if isinstance(var_value, str):
                    content_str = content_str.replace(placeholder, value_str)
                else:
                    content_str = content_str.replace(f'"{placeholder}"', value_str)
        
        # 解析回字典
        try:
            return json.loads(content_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error replacing template variables: {str(e)}")
            return {}
    
    def get_report_templates(self, report_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取报告模板
        
        Args:
            report_type: 报告类型，如果为None则获取所有模板
            
        Returns:
            List[Dict[str, Any]]: 模板列表
        """
        # 构建查询条件
        tags = ["template"]
        if report_type:
            tags.append(f"type:{report_type}")
        
        # 查询模板
        documents = self.infra_service.document_manager.query_documents(
            store_name=self.infra_service.store_name,
            tags=tags,
            status=self.infra_service.STATUS_PUBLISHED
        )
        
        # 处理结果
        templates = []
        for doc in documents:
            if not doc.content or not isinstance(doc.content, dict):
                continue
                
            template = {
                "id": doc.id,
                "title": doc.content.get("title", ""),
                "type": doc.content.get("type", ""),
                "description": doc.content.get("description", ""),
                "variables": doc.content.get("content", {}).get("template_variables", []),
                "created_at": doc.metadata.created_at.isoformat() if doc.metadata.created_at else "",
                "author": doc.metadata.author
            }
            
            templates.append(template)
        
        return templates
    
    def export_report(self, report_id: str, format: str = FORMAT_JSON) -> Optional[Dict[str, Any]]:
        """
        导出报告
        
        Args:
            report_id: 报告ID
            format: 导出格式，支持"json"、"html"、"pdf"、"csv"、"excel"
            
        Returns:
            Optional[Dict[str, Any]]: 导出结果，包含导出数据或文件路径
        """
        # 获取报告
        report = self.get_report(report_id)
        if not report:
            logger.error(f"Report {report_id} not found")
            return None
        
        # 根据格式导出
        format = format.lower()
        if format == self.FORMAT_JSON:
            return {
                "format": "json",
                "data": report
            }
        elif format == self.FORMAT_HTML:
            return self._export_as_html(report)
        elif format == self.FORMAT_PDF:
            return self._export_as_pdf(report)
        elif format == self.FORMAT_CSV:
            return self._export_as_csv(report)
        elif format == self.FORMAT_EXCEL:
            return self._export_as_excel(report)
        else:
            logger.error(f"Unsupported export format: {format}")
            return None
    
    def _export_as_html(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """导出为HTML格式"""
        try:
            # 基本HTML模板
            html = f"""
            <html>
            <head>
                <title>{report.get("title", "Report")}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1, h2 {{ color: #333; }}
                    .report-info {{ margin-bottom: 20px; }}
                    .report-content {{ margin-top: 20px; }}
                    table {{ border-collapse: collapse; width: 100%; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; }}
                    th {{ background-color: #f2f2f2; }}
                </style>
            </head>
            <body>
                <h1>{report.get("title", "Report")}</h1>
                
                <div class="report-info">
                    <p><strong>Type:</strong> {report.get("type", "")}</p>
                    <p><strong>Description:</strong> {report.get("description", "")}</p>
                    <p><strong>Created:</strong> {report.get("created_at", "")}</p>
                    <p><strong>Author:</strong> {report.get("author", "")}</p>
                </div>
                
                <div class="report-content">
                    <h2>Report Content</h2>
            """
            
            # 添加报告内容
            content = report.get("content", {})
            if isinstance(content, dict):
                # 按部分添加内容
                for section, section_data in content.items():
                    if section == "is_template" or section == "template_variables" or section == "template_content":
                        continue
                        
                    html += f"<h3>{section}</h3>"
                    
                    if isinstance(section_data, list):
                        # 表格形式展示列表
                        if section_data and isinstance(section_data[0], dict):
                            html += "<table><tr>"
                            # 表头
                            for key in section_data[0].keys():
                                html += f"<th>{key}</th>"
                            html += "</tr>"
                            
                            # 数据行
                            for item in section_data:
                                html += "<tr>"
                                for value in item.values():
                                    html += f"<td>{value}</td>"
                                html += "</tr>"
                            html += "</table>"
                        else:
                            # 普通列表
                            html += "<ul>"
                            for item in section_data:
                                html += f"<li>{item}</li>"
                            html += "</ul>"
                    elif isinstance(section_data, dict):
                        # 键值对形式展示字典
                        html += "<table>"
                        for key, value in section_data.items():
                            html += f"<tr><td><strong>{key}</strong></td><td>{value}</td></tr>"
                        html += "</table>"
                    else:
                        # 直接显示其他类型
                        html += f"<p>{section_data}</p>"
            
            html += """
                </div>
            </body>
            </html>
            """
            
            return {
                "format": "html",
                "data": html
            }
        except Exception as e:
            logger.error(f"Error exporting report as HTML: {str(e)}")
            return {
                "format": "html",
                "error": str(e)
            }
    
    def _export_as_pdf(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """导出为PDF格式"""
        try:
            # 尝试导入PDF库
            try:
                from weasyprint import HTML
                import tempfile
            except ImportError:
                logger.error("weasyprint library not available for PDF export")
                return {
                    "format": "pdf",
                    "error": "PDF export requires weasyprint library"
                }
            
            # 先转换为HTML
            html_export = self._export_as_html(report)
            if "error" in html_export:
                return {
                    "format": "pdf",
                    "error": html_export["error"]
                }
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                pdf_path = tmp.name
            
            # 转换为PDF
            HTML(string=html_export["data"]).write_pdf(pdf_path)
            
            return {
                "format": "pdf",
                "file_path": pdf_path
            }
        except Exception as e:
            logger.error(f"Error exporting report as PDF: {str(e)}")
            return {
                "format": "pdf",
                "error": str(e)
            }
    
    def _export_as_csv(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """导出为CSV格式"""
        try:
            # 尝试导入pandas
            try:
                import pandas as pd
            except ImportError:
                logger.error("pandas library not available for CSV export")
                return {
                    "format": "csv",
                    "error": "CSV export requires pandas library"
                }
            
            # 获取内容
            content = report.get("content", {})
            result = {}
            
            # 处理报告内容
            if isinstance(content, dict):
                for section, section_data in content.items():
                    if isinstance(section_data, list) and section_data and isinstance(section_data[0], dict):
                        # 可以转换为DataFrame的列表数据
                        df = pd.DataFrame(section_data)
                        result[section] = df.to_csv(index=False)
            
            # 如果没有表格数据，创建一个简单的摘要
            if not result:
                summary = {
                    "Title": [report.get("title", "")],
                    "Type": [report.get("type", "")],
                    "Description": [report.get("description", "")],
                    "Created At": [report.get("created_at", "")],
                    "Author": [report.get("author", "")]
                }
                df = pd.DataFrame(summary)
                result["summary"] = df.to_csv(index=False)
            
            return {
                "format": "csv",
                "data": result
            }
        except Exception as e:
            logger.error(f"Error exporting report as CSV: {str(e)}")
            return {
                "format": "csv",
                "error": str(e)
            }
    
    def _export_as_excel(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """导出为Excel格式"""
        try:
            # 尝试导入pandas
            try:
                import pandas as pd
                import tempfile
            except ImportError:
                logger.error("pandas library not available for Excel export")
                return {
                    "format": "excel",
                    "error": "Excel export requires pandas library"
                }
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                excel_path = tmp.name
            
            # 创建Excel写入器
            with pd.ExcelWriter(excel_path) as writer:
                # 写入概览
                summary = {
                    "Title": [report.get("title", "")],
                    "Type": [report.get("type", "")],
                    "Description": [report.get("description", "")],
                    "Created At": [report.get("created_at", "")],
                    "Author": [report.get("author", "")]
                }
                pd.DataFrame(summary).to_excel(writer, sheet_name="Overview", index=False)
                
                # 写入内容
                content = report.get("content", {})
                if isinstance(content, dict):
                    for section, section_data in content.items():
                        if isinstance(section_data, list) and section_data and isinstance(section_data[0], dict):
                            # 可以转换为DataFrame的列表数据
                            sheet_name = section[:31]  # Excel工作表名称最长31字符
                            pd.DataFrame(section_data).to_excel(writer, sheet_name=sheet_name, index=False)
            
            return {
                "format": "excel",
                "file_path": excel_path
            }
        except Exception as e:
            logger.error(f"Error exporting report as Excel: {str(e)}")
            return {
                "format": "excel",
                "error": str(e)
            }
    
    def schedule_recurring_report(self,
                                template_id: str,
                                schedule: str,
                                variable_provider: Optional[str] = None,
                                author: Optional[str] = None,
                                tags: Optional[List[str]] = None) -> Optional[str]:
        """
        调度定期报告
        
        Args:
            template_id: 模板ID
            schedule: 调度表达式（cron格式）
            variable_provider: 变量提供者（函数或类路径）
            author: 作者
            tags: 标签
            
        Returns:
            Optional[str]: 调度ID
        """
        # 获取模板
        template = self.get_report(template_id)
        if not template or not template.get("content", {}).get("is_template"):
            logger.error(f"Template {template_id} not found or not a valid template")
            return None
        
        # 创建调度记录
        schedule_id = str(uuid.uuid4())
        
        try:
            # 导入调度服务
            # 注意：此处需要实际的调度服务实现
            # from services.scheduling import SchedulingService
            # scheduling_service = SchedulingService()
            
            # 创建调度任务
            # 调度服务负责在指定时间调用此服务的create_scheduled_report方法
            # scheduling_service.create_schedule(
            #     task_id=schedule_id,
            #     schedule=schedule,
            #     task_type="report_generation",
            #     task_params={
            #         "template_id": template_id,
            #         "variable_provider": variable_provider,
            #         "author": author,
            #         "tags": tags
            #     }
            # )
            
            # 记录调度信息
            schedule_record = {
                "id": schedule_id,
                "template_id": template_id,
                "schedule": schedule,
                "variable_provider": variable_provider,
                "author": author,
                "status": "active",
                "created_at": datetime.now().isoformat()
            }
            
            # 这里可以保存调度记录到某个存储
            
            logger.info(f"Created recurring report schedule {schedule_id} for template {template_id}")
            
            return schedule_id
        except Exception as e:
            logger.error(f"Error scheduling recurring report: {str(e)}")
            return None
    
    def create_scheduled_report(self,
                              template_id: str,
                              variable_provider: Optional[str] = None,
                              author: Optional[str] = None,
                              tags: Optional[List[str]] = None) -> Optional[str]:
        """
        创建调度报告
        
        Args:
            template_id: 模板ID
            variable_provider: 变量提供者（函数或类路径）
            author: 作者
            tags: 标签
            
        Returns:
            Optional[str]: 报告ID
        """
        try:
            # 获取变量
            variables = {}
            
            if variable_provider:
                try:
                    # 尝试导入并调用变量提供者
                    module_path, func_name = variable_provider.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    provider_func = getattr(module, func_name)
                    
                    # 调用变量提供者
                    variables = provider_func()
                except (ImportError, AttributeError) as e:
                    logger.error(f"Error loading variable provider {variable_provider}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error getting variables from provider {variable_provider}: {str(e)}")
            
            # 创建报告
            report_id = self.create_report_from_template(
                template_id=template_id,
                variable_values=variables,
                author=author,
                tags=tags
            )
            
            # 发布报告
            if report_id:
                self.publish_report(report_id, author)
            
            return report_id
        except Exception as e:
            logger.error(f"Error creating scheduled report: {str(e)}")
            return None
    
    def send_report_notification(self,
                               report_id: str,
                               recipients: List[str],
                               channel: str = "email",
                               custom_message: Optional[str] = None) -> bool:
        """
        发送报告通知
        
        Args:
            report_id: 报告ID
            recipients: 接收者列表
            channel: 通知渠道（email, sms, etc）
            custom_message: 自定义消息
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 获取报告
            report = self.get_report(report_id)
            if not report:
                logger.error(f"Report {report_id} not found")
                return False
            
            # 构建通知消息
            title = report.get("title", "Trading System Report")
            report_type = report.get("type", "")
            created_at = report.get("created_at", "")
            
            message = custom_message or f"New report available: {title} (Type: {report_type}, Created: {created_at})"
            
            # 尝试发送通知
            # 注意：此处需要实际的通知服务实现
            if channel == "email":
                # from services.notification.email_service import EmailService
                # email_service = EmailService()
                # return email_service.send_email(
                #     recipients=recipients,
                #     subject=f"Trading System Report: {title}",
                #     body=message,
                #     attachments=[self.export_report(report_id, "pdf")]
                # )
                logger.info(f"Would send email notification for report {report_id} to {recipients}")
                return True
            elif channel == "sms":
                # from services.notification.sms_service import SmsService
                # sms_service = SmsService()
                # return sms_service.send_sms(
                #     recipients=recipients,
                #     message=message
                # )
                logger.info(f"Would send SMS notification for report {report_id} to {recipients}")
                return True
            else:
                logger.error(f"Unsupported notification channel: {channel}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending report notification: {str(e)}")
            return False
    
    def batch_delete_reports(self, report_ids: List[str], author: Optional[str] = None) -> Dict[str, bool]:
        """
        批量删除报告
        
        Args:
            report_ids: 报告ID列表
            author: 操作者
            
        Returns:
            Dict[str, bool]: 每个ID的删除结果
        """
        results = {}
        for report_id in report_ids:
            results[report_id] = self.delete_report(report_id, author)
        return results
    
    def batch_archive_reports(self, report_ids: List[str], author: Optional[str] = None) -> Dict[str, bool]:
        """
        批量归档报告
        
        Args:
            report_ids: 报告ID列表
            author: 操作者
            
        Returns:
            Dict[str, bool]: 每个ID的归档结果
        """
        results = {}
        for report_id in report_ids:
            results[report_id] = self.archive_report(report_id, author)
        return results