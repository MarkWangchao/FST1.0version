"""
报告服务模块 - 负责生成、管理和分发交易和绩效报告的微服务

该模块提供以下功能:
- 交易绩效报告生成
- 资产组合分析
- 风险指标计算
- 报告定时生成和分发
- 报告格式化和导出（PDF、Excel、HTML等）
- 报告存储和检索
"""

from .service import ReportingService

__all__ = ['ReportingService']