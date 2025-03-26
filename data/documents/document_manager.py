"""
文档管理器模块 - 统一管理不同类型的文档存储

该模块提供了DocumentManager类，用于创建和管理不同类型的文档存储，
包括文件系统存储和MongoDB存储。通过统一接口简化文档操作。
"""

import os
import logging
import json
import yaml
from typing import Any, Dict, List, Optional, Union, Type
from pathlib import Path
import threading
from datetime import datetime

from .document_item import DocumentItem, DocumentStatus, DocumentMetadata
from .file_document_store import FileDocumentStore

# 尝试导入MongoDB文档存储
try:
    from .mongo_document_store import MongoDocumentStore, MongoConfig, MONGO_AVAILABLE
except ImportError:
    MONGO_AVAILABLE = False
    # 创建模拟类，以便在没有MongoDB时可以编译
    class MongoDocumentStore:
        def __init__(self, *args, **kwargs):
            pass
    
    class MongoConfig:
        def __init__(self, *args, **kwargs):
            pass

logger = logging.getLogger(__name__)


class DocumentManager:
    """
    文档管理器 - 统一接口管理不同类型的文档存储
    
    提供功能:
    - 管理多种文档存储后端(文件系统、MongoDB)
    - 统一的文档访问接口
    - 支持不同业务领域的文档分类
    - 处理文档路由和查询
    """
    
    # 文档类型常量定义
    STRATEGY_DOCS = "strategies"
    BACKTEST_DOCS = "backtests"
    REPORT_DOCS = "reports"
    
    # 存储类型常量定义
    FILE_STORE = "file"
    MONGO_STORE = "mongo"
    
    def __init__(self, config_path: Optional[str] = None, base_dir: Optional[str] = None):
        """
        初始化文档管理器
        
        Args:
            config_path: 配置文件路径，如不提供则使用默认配置
            base_dir: 文档基础目录，覆盖配置文件中的设置
        """
        self.config = self._load_config(config_path)
        self.base_dir = base_dir or self.config.get("base_dir", os.path.join(os.getcwd(), "data", "documents"))
        
        # 存储不同类型的文档存储
        self.stores = {}
        
        # 存储实例类型映射
        self.store_types = {}
        
        # 创建默认存储
        self._create_default_stores()
        
        # 全局锁，用于线程安全
        self._lock = threading.RLock()
        
        logger.info(f"Document Manager initialized with base_dir: {self.base_dir}")
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        加载配置
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Dict[str, Any]: 配置字典
        """
        default_config = {
            "base_dir": os.path.join(os.getcwd(), "data", "documents"),
            "default_store_type": self.FILE_STORE,
            "stores": {
                self.STRATEGY_DOCS: {"type": self.FILE_STORE, "subdirectory": "strategies"},
                self.BACKTEST_DOCS: {"type": self.FILE_STORE, "subdirectory": "backtests"},
                self.REPORT_DOCS: {"type": self.FILE_STORE, "subdirectory": "reports"}
            },
            "mongodb": {
                "uri": "mongodb://localhost:27017/",
                "database": "document_store"
            }
        }
        
        if not config_path:
            return default_config
            
        try:
            with open(config_path, 'r') as f:
                # 根据文件类型加载
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
                
                # 合并默认配置和用户配置
                return {**default_config, **config}
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {str(e)}")
            return default_config
    
    def _create_default_stores(self) -> None:
        """创建默认的文档存储"""
        for doc_type, store_config in self.config.get("stores", {}).items():
            store_type = store_config.get("type", self.config.get("default_store_type", self.FILE_STORE))
            
            if store_type == self.FILE_STORE:
                subdirectory = store_config.get("subdirectory", doc_type)
                self.create_file_store(doc_type, os.path.join(self.base_dir, subdirectory))
            elif store_type == self.MONGO_STORE and MONGO_AVAILABLE:
                collection = store_config.get("collection", doc_type)
                self.create_mongo_store(doc_type, collection=collection)
    
    def create_file_store(self, name: str, base_dir: Optional[str] = None) -> FileDocumentStore:
        """
        创建文件系统文档存储
        
        Args:
            name: 存储名称
            base_dir: 文档基础目录，如不提供则使用默认目录
            
        Returns:
            FileDocumentStore: 文件系统文档存储实例
        """
        with self._lock:
            if name in self.stores:
                return self.stores[name]
                
            # 确定目录
            if base_dir is None:
                doc_type = name
                store_config = self.config.get("stores", {}).get(doc_type, {})
                subdirectory = store_config.get("subdirectory", doc_type)
                base_dir = os.path.join(self.base_dir, subdirectory)
            
            # 创建文档存储
            store = FileDocumentStore(base_dir=base_dir, create_if_missing=True)
            self.stores[name] = store
            self.store_types[name] = self.FILE_STORE
            
            logger.info(f"Created file document store '{name}' at {base_dir}")
            return store
    
    def create_mongo_store(self, name: str, 
                          mongo_config: Optional[MongoConfig] = None,
                          uri: Optional[str] = None,
                          database: Optional[str] = None,
                          collection: Optional[str] = None) -> Optional[MongoDocumentStore]:
        """
        创建MongoDB文档存储
        
        Args:
            name: 存储名称
            mongo_config: MongoDB配置对象
            uri: MongoDB连接URI
            database: 数据库名称
            collection: 集合名称
            
        Returns:
            Optional[MongoDocumentStore]: MongoDB文档存储实例，如不支持则返回None
        """
        if not MONGO_AVAILABLE:
            logger.warning("MongoDB not available. Please install pymongo.")
            return None
            
        with self._lock:
            if name in self.stores and self.store_types[name] == self.MONGO_STORE:
                return self.stores[name]
                
            # 使用提供的配置或配置文件中的设置
            if mongo_config is None:
                mongo_conf = self.config.get("mongodb", {})
                mongo_config = MongoConfig(
                    uri=uri or mongo_conf.get("uri", "mongodb://localhost:27017/"),
                    database=database or mongo_conf.get("database", "document_store"),
                    documents_collection=collection or name
                )
            
            try:
                # 创建MongoDB存储
                store = MongoDocumentStore(config=mongo_config)
                self.stores[name] = store
                self.store_types[name] = self.MONGO_STORE
                
                logger.info(f"Created MongoDB document store '{name}' using database "
                           f"'{mongo_config.database}', collection '{mongo_config.documents_collection}'")
                return store
            except Exception as e:
                logger.error(f"Failed to create MongoDB store '{name}': {str(e)}")
                return None
    
    def get_store(self, name: str) -> Optional[Union[FileDocumentStore, MongoDocumentStore]]:
        """
        获取指定名称的文档存储
        
        Args:
            name: 存储名称
            
        Returns:
            Optional[Union[FileDocumentStore, MongoDocumentStore]]: 文档存储实例，不存在则返回None
        """
        return self.stores.get(name)
    
    def list_stores(self) -> List[str]:
        """
        列出所有可用的存储名称
        
        Returns:
            List[str]: 存储名称列表
        """
        return list(self.stores.keys())
    
    def get_store_info(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取存储信息
        
        Args:
            name: 存储名称，如为None则返回所有存储信息
            
        Returns:
            Dict[str, Any]: 存储信息字典
        """
        if name is not None:
            if name not in self.stores:
                return {}
                
            store = self.stores[name]
            return {
                "name": name,
                "type": self.store_types[name],
                "document_count": store.count_documents() if hasattr(store, "count_documents") else None
            }
        
        # 返回所有存储的信息
        result = {}
        for store_name in self.stores:
            result[store_name] = self.get_store_info(store_name)
        
        return result
    
    # 以下是代理方法，将操作转发到相应的文档存储
    
    def save_document(self, document: DocumentItem, store_name: str) -> bool:
        """
        保存文档到指定存储
        
        Args:
            document: 文档对象
            store_name: 存储名称
            
        Returns:
            bool: 是否成功
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return False
            
        return store.save_document(document)
    
    def load_document(self, doc_id: str, store_name: str) -> Optional[DocumentItem]:
        """
        从指定存储加载文档
        
        Args:
            doc_id: 文档ID
            store_name: 存储名称
            
        Returns:
            Optional[DocumentItem]: 文档对象，如不存在则返回None
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return None
            
        return store.load_document(doc_id)
    
    def delete_document(self, doc_id: str, store_name: str) -> bool:
        """
        从指定存储删除文档
        
        Args:
            doc_id: 文档ID
            store_name: 存储名称
            
        Returns:
            bool: 是否成功
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return False
            
        return store.delete_document(doc_id)
    
    def search_documents(self, 
                       query: Optional[Dict[str, Any]] = None, 
                       tags: Optional[List[str]] = None, 
                       author: Optional[str] = None,
                       status: Optional[DocumentStatus] = None,
                       store_name: str = None,
                       limit: int = 100,
                       offset: int = 0) -> List[Dict[str, Any]]:
        """
        搜索文档
        
        Args:
            query: 查询条件
            tags: 标签列表
            author: 作者
            status: 文档状态
            store_name: 存储名称，如为None则搜索所有存储
            limit: 结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 匹配的文档列表
        """
        results = []
        
        # 确定要搜索的存储
        stores_to_search = [store_name] if store_name else self.stores.keys()
        
        for name in stores_to_search:
            store = self.get_store(name)
            if not store:
                continue
                
            try:
                # 调用存储的搜索方法
                if hasattr(store, "search_documents"):
                    store_results = store.search_documents(
                        query=query,
                        tags=tags,
                        author=author,
                        status=status,
                        limit=limit,
                        offset=offset
                    )
                    
                    # 添加存储信息到结果
                    for doc in store_results:
                        if isinstance(doc, dict):
                            doc["store_name"] = name
                        results.append(doc)
            except Exception as e:
                logger.error(f"Error searching documents in store '{name}': {str(e)}")
        
        return results[:limit]
    
    def create_document(self, 
                      content: Any,
                      store_name: str,
                      author: Optional[str] = None,
                      doc_id: Optional[str] = None,
                      content_type: str = "application/json",
                      tags: Optional[List[str]] = None,
                      custom_metadata: Optional[Dict[str, Any]] = None,
                      schema: Optional[str] = None) -> Optional[str]:
        """
        创建新文档
        
        Args:
            content: 文档内容
            store_name: 存储名称
            author: 作者
            doc_id: 文档ID，如果为None则自动生成
            content_type: 内容类型
            tags: 标签列表
            custom_metadata: 自定义元数据
            schema: 文档模式
            
        Returns:
            Optional[str]: 文档ID，如果失败则返回None
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return None
            
        # 创建文档
        document = DocumentItem.create_new(
            content=content,
            author=author,
            doc_id=doc_id,
            content_type=content_type,
            tags=tags,
            custom_metadata=custom_metadata,
            schema=schema
        )
        
        # 保存文档
        success = store.save_document(document)
        if success:
            return document.id
        return None
    
    def update_document(self, 
                      doc_id: str,
                      store_name: str,
                      content: Optional[Any] = None,
                      author: Optional[str] = None,
                      comment: Optional[str] = None,
                      tags_to_add: Optional[List[str]] = None,
                      tags_to_remove: Optional[List[str]] = None,
                      status: Optional[DocumentStatus] = None,
                      custom_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        更新文档
        
        Args:
            doc_id: 文档ID
            store_name: 存储名称
            content: 新内容，如为None则不更新内容
            author: 更新作者
            comment: 更新注释
            tags_to_add: 要添加的标签
            tags_to_remove: 要移除的标签
            status: 新状态，如为None则不更新状态
            custom_metadata: 自定义元数据，如为None则不更新
            
        Returns:
            bool: 是否成功更新
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return False
            
        # 加载文档
        document = store.load_document(doc_id)
        if not document:
            logger.error(f"Document '{doc_id}' not found in store '{store_name}'")
            return False
            
        # 更新内容
        if content is not None:
            document.update_content(content, author=author, comment=comment)
            
        # 更新标签
        if tags_to_add:
            document.add_tags(tags_to_add)
            
        if tags_to_remove:
            document.remove_tags(tags_to_remove)
            
        # 更新状态
        if status is not None:
            document.change_status(status, author=author)
            
        # 更新自定义元数据
        if custom_metadata is not None:
            document.metadata.custom.update(custom_metadata)
            document.metadata.update()
            
        # 保存更新后的文档
        return store.save_document(document)
    
    def get_document_versions(self, doc_id: str, store_name: str) -> List[Dict[str, Any]]:
        """
        获取文档版本历史
        
        Args:
            doc_id: 文档ID
            store_name: 存储名称
            
        Returns:
            List[Dict[str, Any]]: 版本历史列表
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return []
            
        # 加载文档
        document = store.load_document(doc_id)
        if not document:
            logger.error(f"Document '{doc_id}' not found in store '{store_name}'")
            return []
            
        # 返回版本历史
        return [version.to_dict() for version in document.versions]
    
    def get_document_by_version(self, doc_id: str, version_id: str, store_name: str) -> Optional[DocumentItem]:
        """
        获取指定版本的文档
        
        Args:
            doc_id: 文档ID
            version_id: 版本ID
            store_name: 存储名称
            
        Returns:
            Optional[DocumentItem]: 文档对象
        """
        # 对于MongoDB存储，直接调用专门的方法
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return None
            
        # 检查是否有专门的版本获取方法
        if hasattr(store, "get_document_by_version"):
            return store.get_document_by_version(doc_id, version_id)
            
        # 通用方法：加载文档然后找到版本
        document = store.load_document(doc_id)
        if not document:
            logger.error(f"Document '{doc_id}' not found in store '{store_name}'")
            return None
            
        # 查找指定版本
        for version in document.versions:
            if version.version_id == version_id:
                # 这里只是找到了版本信息，但没有实际恢复该版本的内容
                # 实际应用中可能需要更复杂的版本恢复逻辑
                logger.info(f"Found version {version_id} for document {doc_id}")
                return document
                
        logger.error(f"Version '{version_id}' not found for document '{doc_id}'")
        return None
    
    def get_all_tags(self, store_name: Optional[str] = None) -> Dict[str, int]:
        """
        获取所有标签及其使用次数
        
        Args:
            store_name: 存储名称，如为None则获取所有存储的标签
            
        Returns:
            Dict[str, int]: 标签及其使用次数的字典
        """
        tags_count = {}
        
        # 确定要查询的存储
        stores_to_query = [store_name] if store_name else self.stores.keys()
        
        for name in stores_to_query:
            store = self.get_store(name)
            if not store:
                continue
                
            # MongoDB存储有聚合方法
            if self.store_types.get(name) == self.MONGO_STORE and hasattr(store, "aggregate_tags"):
                store_tags = store.aggregate_tags()
                for tag, count in store_tags.items():
                    tags_count[tag] = tags_count.get(tag, 0) + count
                continue
                
            # 文件存储需要列出所有标签
            if hasattr(store, "get_all_tags"):
                store_tags = store.get_all_tags()
                for tag in store_tags:
                    tags_count[tag] = tags_count.get(tag, 0) + 1
        
        return tags_count
    
    def get_documents_by_tag(self, tag: str, store_name: Optional[str] = None, 
                         limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取带有指定标签的文档
        
        Args:
            tag: 标签
            store_name: 存储名称，如为None则搜索所有存储
            limit: 结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 文档列表
        """
        return self.search_documents(tags=[tag], store_name=store_name, limit=limit, offset=offset)
    
    def backup_document_store(self, store_name: str, backup_dir: str) -> bool:
        """
        备份文档存储
        
        Args:
            store_name: 存储名称
            backup_dir: 备份目录
            
        Returns:
            bool: 是否成功
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return False
            
        # 检查备份目录
        os.makedirs(backup_dir, exist_ok=True)
        
        try:
            # 检查是否有专门的备份方法
            if hasattr(store, "backup_collection"):
                # MongoDB备份
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(backup_dir, f"{store_name}_documents_{timestamp}.json")
                return store.backup_collection("documents", backup_file)
            elif isinstance(store, FileDocumentStore):
                # 文件存储备份
                import shutil
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(backup_dir, f"{store_name}_{timestamp}")
                
                # 获取文件存储的基础目录
                source_dir = store.base_dir
                
                # 复制目录
                shutil.copytree(source_dir, backup_path)
                logger.info(f"Backed up file store '{store_name}' to {backup_path}")
                return True
            else:
                logger.error(f"Backup not supported for store type: {self.store_types.get(store_name)}")
                return False
        except Exception as e:
            logger.error(f"Error backing up store '{store_name}': {str(e)}")
            return False
    
    def restore_document_store(self, store_name: str, backup_path: str, 
                           clear_existing: bool = False) -> bool:
        """
        从备份恢复文档存储
        
        Args:
            store_name: 存储名称
            backup_path: 备份路径(文件或目录)
            clear_existing: 是否清除现有数据
            
        Returns:
            bool: 是否成功
        """
        store = self.get_store(store_name)
        if not store:
            logger.error(f"Store '{store_name}' not found")
            return False
            
        try:
            # 检查是否有专门的恢复方法
            if hasattr(store, "restore_collection"):
                # MongoDB恢复
                return store.restore_collection("documents", backup_path, clear_existing)
            elif isinstance(store, FileDocumentStore) and os.path.isdir(backup_path):
                # 文件存储恢复
                import shutil
                
                # 获取文件存储的基础目录
                target_dir = store.base_dir
                
                # 如果清除现有数据
                if clear_existing and os.path.exists(target_dir):
                    shutil.rmtree(target_dir)
                    
                # 恢复目录
                if not os.path.exists(target_dir):
                    shutil.copytree(backup_path, target_dir)
                else:
                    # 合并目录
                    for item in os.listdir(backup_path):
                        source_item = os.path.join(backup_path, item)
                        target_item = os.path.join(target_dir, item)
                        
                        if os.path.isdir(source_item):
                            if not os.path.exists(target_item):
                                shutil.copytree(source_item, target_item)
                            else:
                                # 递归合并子目录
                                for subitem in os.listdir(source_item):
                                    shutil.copy2(
                                        os.path.join(source_item, subitem),
                                        os.path.join(target_item, subitem)
                                    )
                        else:
                            shutil.copy2(source_item, target_item)
                
                logger.info(f"Restored file store '{store_name}' from {backup_path}")
                return True
            else:
                logger.error(f"Restore not supported for store type or invalid backup path")
                return False
        except Exception as e:
            logger.error(f"Error restoring store '{store_name}': {str(e)}")
            return False
    
    def close(self) -> None:
        """关闭所有文档存储"""
        for name, store in self.stores.items():
            try:
                if hasattr(store, "close") and callable(store.close):
                    store.close()
                    logger.info(f"Closed document store '{name}'")
            except Exception as e:
                logger.error(f"Error closing document store '{name}': {str(e)}")
    
    def __del__(self) -> None:
        """析构函数，确保正确关闭"""
        self.close()