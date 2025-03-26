#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 文档数据存储实现

提供文档数据存储的具体实现:
- MongoDB存储
- 文档存储管理
"""

from .mongodb_store import MongoDBStore
from .document_store import DocumentStore

__all__ = ['MongoDBStore', 'DocumentStore']