"""
报告服务模块 - 提供报告生成和管理功能

该模块提供了完整的报告服务功能，包括:
- 报告文档管理：创建、更新、查询和删除报告
- 报告生成：基于模板和数据生成各类报告
- 报告格式化：支持多种输出格式(JSON、HTML、PDF、Excel等)
- 报告调度：定时生成和更新报告
- 报告通知：通过邮件、短信等渠道发送报告通知

主要组件:
- ReportDocumentService: 报告文档服务，提供文档管理功能
- ReportGenerator: 报告生成器，负责报告内容的生成和格式化
"""

from .report_document_service import ReportDocumentService
from .report_generator import ReportGenerator

# 导出公共接口
__all__ = [
    "ReportDocumentService",
    "ReportGenerator"
]

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