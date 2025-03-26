"""
文档存储模块 - 提供结构化文档的存储和管理功能

该模块提供多种文档存储实现，包括文件系统存储和MongoDB存储，
以及统一的文档管理接口。

主要功能:
- 文档的存储、检索、更新和删除
- 支持文档版本控制
- 支持文档元数据管理
- 支持文档查询和过滤
- 支持文档索引
"""

from .document_item import DocumentItem, DocumentMetadata, DocumentVersion, DocumentStatus
from .document_manager import DocumentManager
from .file_document_store import FileDocumentStore

# 尝试导入MongoDB文档存储
try:
    from .mongo_document_store import MongoDocumentStore
    __mongo_available__ = True
except ImportError:
    __mongo_available__ = False

# 导出公共接口
__all__ = [
    "DocumentItem",
    "DocumentMetadata",
    "DocumentVersion",
    "DocumentStatus",
    "DocumentManager",
    "FileDocumentStore",
]

# 如果MongoDB可用，添加到导出列表
if __mongo_available__:
    __all__ += ["MongoDocumentStore"]