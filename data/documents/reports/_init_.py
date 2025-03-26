"""
报告文档存储目录

该目录用于存储报告类型的文档数据，包括:
- 交易报告
- 绩效报告
- 风险报告
- 策略报告
- 自定义报告

当使用文件系统存储（FileDocumentStore）时，
报告文档及其索引、版本历史等将物理存储在此目录中。
"""

# 报告类型常量
REPORT_TYPE_TRADING = "trading"          # 交易报告
REPORT_TYPE_PERFORMANCE = "performance"  # 绩效报告
REPORT_TYPE_RISK = "risk"                # 风险报告
REPORT_TYPE_STRATEGY = "strategy"        # 策略报告
REPORT_TYPE_CUSTOM = "custom"            # 自定义报告

# 导出公共接口
__all__ = [
    'REPORT_TYPE_TRADING',
    'REPORT_TYPE_PERFORMANCE',
    'REPORT_TYPE_RISK',
    'REPORT_TYPE_STRATEGY',
    'REPORT_TYPE_CUSTOM',
]