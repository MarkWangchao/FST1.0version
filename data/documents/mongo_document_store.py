"""
基于MongoDB的文档存储实现
"""

import logging
import json
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime
import uuid

from .document_item import DocumentItem, DocumentStatus, DocumentMetadata, DocumentVersion

# 尝试导入pymongo
try:
    import pymongo
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    from bson.objectid import ObjectId
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    # 创建模拟类，以便在没有pymongo时可以编译
    class MongoClient:
        def __init__(self, *args, **kwargs):
            pass
    class ObjectId:
        def __init__(self, *args, **kwargs):
            pass
    class PyMongoError(Exception):
        pass

logger = logging.getLogger(__name__)


class MongoConfig:
    """MongoDB配置类"""
    
    def __init__(self, 
                uri: str = "mongodb://localhost:27017/", 
                database: str = "document_store",
                documents_collection: str = "documents",
                versions_collection: str = "versions",
                metadata_collection: str = "metadata",
                connect_timeout: int = 5000,
                auth_mechanism: Optional[str] = None):
        self.uri = uri
        self.database = database
        self.documents_collection = documents_collection
        self.versions_collection = versions_collection
        self.metadata_collection = metadata_collection
        self.connect_timeout = connect_timeout
        self.auth_mechanism = auth_mechanism


class MongoDocumentStore:
    """
    基于MongoDB的文档存储实现
    
    提供功能:
    - 文档的增删改查操作
    - 版本管理
    - 高级查询和聚合
    - 索引优化
    """
    
    def __init__(self, config: Optional[MongoConfig] = None):
        """
        初始化MongoDB文档存储
        
        Args:
            config: MongoDB配置对象
        
        Raises:
            ImportError: 如果pymongo不可用
            ConnectionError: 如果无法连接到MongoDB
        """
        if not MONGO_AVAILABLE:
            raise ImportError("pymongo is not installed. Please install it with 'pip install pymongo'")
            
        self.config = config or MongoConfig()
        
        # 连接到MongoDB
        try:
            client_kwargs = {
                'serverSelectionTimeoutMS': self.config.connect_timeout
            }
            
            if self.config.auth_mechanism:
                client_kwargs['authMechanism'] = self.config.auth_mechanism
                
            self.client = MongoClient(self.config.uri, **client_kwargs)
            
            # 验证连接
            self.client.server_info()
            
            # 获取数据库和集合
            self.db = self.client[self.config.database]
            self.documents = self.db[self.config.documents_collection]
            self.versions = self.db[self.config.versions_collection]
            self.metadata = self.db[self.config.metadata_collection]
            
            # 确保索引
            self._ensure_indexes()
            
            logger.info(f"Connected to MongoDB at {self.config.uri}, database: {self.config.database}")
            
        except PyMongoError as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise ConnectionError(f"Could not connect to MongoDB: {str(e)}")
    
    def _ensure_indexes(self):
        """创建和确保必要的索引"""
        # 文档集合索引
        self.documents.create_index("id", unique=True)
        self.documents.create_index([
            ("metadata.status", pymongo.ASCENDING),
            ("metadata.updated_at", pymongo.DESCENDING)
        ])
        self.documents.create_index("metadata.tags")
        self.documents.create_index("metadata.author")
        self.documents.create_index("metadata.content_type")
        
        # 版本集合索引
        self.versions.create_index([
            ("document_id", pymongo.ASCENDING),
            ("version_id", pymongo.ASCENDING)
        ], unique=True)
        self.versions.create_index("created_at")
        
        # 元数据集合索引
        self.metadata.create_index("type")
        self.metadata.create_index("name", unique=True)
        
        logger.info("MongoDB indexes ensured")
    
    def _document_to_mongo(self, document: DocumentItem) -> Dict[str, Any]:
        """
        转换DocumentItem到MongoDB文档格式
        
        Args:
            document: 文档对象
            
        Returns:
            Dict[str, Any]: MongoDB文档
        """
        # 由于MongoDB已经是JSON格式存储，所以我们可以直接使用to_dict
        doc_dict = document.to_dict()
        
        # MongoDB _id字段特殊处理
        doc_dict['_id'] = doc_dict['id']
        
        return doc_dict
    
    def _mongo_to_document(self, mongo_doc: Dict[str, Any]) -> DocumentItem:
        """
        转换MongoDB文档到DocumentItem
        
        Args:
            mongo_doc: MongoDB文档
            
        Returns:
            DocumentItem: 文档对象
        """
        # 移除MongoDB特有的_id字段
        if '_id' in mongo_doc and mongo_doc['_id'] != mongo_doc.get('id'):
            mongo_doc['id'] = mongo_doc['_id']
        
        if '_id' in mongo_doc:
            del mongo_doc['_id']
            
        return DocumentItem.from_dict(mongo_doc)
    
    def save_document(self, document: DocumentItem) -> bool:
        """
        保存文档
        
        Args:
            document: 文档对象
            
        Returns:
            bool: 是否成功保存
        """
        try:
            # 检查是否为更新操作
            existing_doc = self.documents.find_one({"id": document.id})
            is_update = existing_doc is not None
            
            # 转换为MongoDB文档
            mongo_doc = self._document_to_mongo(document)
            
            # 保存文档
            if is_update:
                # 更新操作
                result = self.documents.replace_one({"id": document.id}, mongo_doc)
                success = result.modified_count > 0
            else:
                # 新增操作
                result = self.documents.insert_one(mongo_doc)
                success = result.acknowledged
            
            # 同步保存最新版本到版本集合
            if document.versions:
                latest_version = document.versions[-1]
                version_doc = {
                    "document_id": document.id,
                    "version_id": latest_version.version_id,
                    "created_at": latest_version.created_at,
                    "created_by": latest_version.created_by,
                    "comment": latest_version.comment,
                    "changes": latest_version.changes
                }
                
                # 检查版本是否已存在
                existing_version = self.versions.find_one({
                    "document_id": document.id,
                    "version_id": latest_version.version_id
                })
                
                if not existing_version:
                    self.versions.insert_one(version_doc)
            
            logger.info(f"{'Updated' if is_update else 'Saved'} document {document.id}")
            return success
            
        except PyMongoError as e:
            logger.error(f"Error saving document {document.id}: {str(e)}")
            return False
    
    def load_document(self, doc_id: str) -> Optional[DocumentItem]:
        """
        加载文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            Optional[DocumentItem]: 文档对象，如不存在则返回None
        """
        try:
            # 查询文档
            mongo_doc = self.documents.find_one({"id": doc_id})
            
            if not mongo_doc:
                return None
                
            # 转换为DocumentItem
            return self._mongo_to_document(mongo_doc)
            
        except PyMongoError as e:
            logger.error(f"Error loading document {doc_id}: {str(e)}")
            return None
    
    def delete_document(self, doc_id: str) -> bool:
        """
        删除文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            bool: 是否成功删除
        """
        try:
            # 查询文档是否存在
            existing_doc = self.documents.find_one({"id": doc_id})
            if not existing_doc:
                return False
                
            # 删除文档
            result = self.documents.delete_one({"id": doc_id})
            
            # 删除相关版本记录
            self.versions.delete_many({"document_id": doc_id})
            
            success = result.deleted_count > 0
            
            if success:
                logger.info(f"Document {doc_id} deleted successfully")
            
            return success
            
        except PyMongoError as e:
            logger.error(f"Error deleting document {doc_id}: {str(e)}")
            return False
    
    def search_documents(self, query: Dict[str, Any] = None, 
                        tags: List[str] = None, 
                        author: str = None,
                        status: DocumentStatus = None,
                        full_text: str = None,
                        limit: int = 100,
                        offset: int = 0,
                        sort_by: str = "metadata.updated_at",
                        sort_desc: bool = True) -> List[DocumentItem]:
        """
        搜索文档
        
        Args:
            query: 自定义查询条件
            tags: 标签列表
            author: 作者
            status: 文档状态
            full_text: 全文搜索
            limit: 返回结果数量限制
            offset: 分页偏移量
            sort_by: 排序字段
            sort_desc: 是否降序排序
            
        Returns:
            List[DocumentItem]: 匹配的文档对象列表
        """
        try:
            # 构建查询条件
            mongo_query = {}
            
            # 自定义查询条件
            if query:
                mongo_query.update(query)
            
            # 标签查询
            if tags:
                mongo_query["metadata.tags"] = {"$all": tags}
            
            # 作者查询
            if author:
                mongo_query["metadata.author"] = author
            
            # 状态查询
            if status:
                mongo_query["metadata.status"] = status.value
            
            # 全文搜索
            if full_text:
                # 注意：这需要MongoDB配置了全文搜索索引
                mongo_query["$text"] = {"$search": full_text}
            
            # 排序条件
            sort_dict = [(sort_by, pymongo.DESCENDING if sort_desc else pymongo.ASCENDING)]
            
            # 执行查询
            cursor = self.documents.find(mongo_query).sort(sort_dict).skip(offset).limit(limit)
            
            # 转换为DocumentItem列表
            result = [self._mongo_to_document(doc) for doc in cursor]
            
            logger.debug(f"Search found {len(result)} documents")
            return result
            
        except PyMongoError as e:
            logger.error(f"Error searching documents: {str(e)}")
            return []
    
    def count_documents(self, status: Optional[DocumentStatus] = None) -> int:
        """
        统计文档数量
        
        Args:
            status: 可选的状态过滤条件
            
        Returns:
            int: 文档数量
        """
        try:
            query = {}
            if status:
                query["metadata.status"] = status.value
                
            return self.documents.count_documents(query)
            
        except PyMongoError as e:
            logger.error(f"Error counting documents: {str(e)}")
            return 0
    
    def get_document_versions(self, doc_id: str) -> List[DocumentVersion]:
        """
        获取文档的所有版本
        
        Args:
            doc_id: 文档ID
            
        Returns:
            List[DocumentVersion]: 版本列表
        """
        try:
            # 查询版本记录
            cursor = self.versions.find({"document_id": doc_id}).sort("created_at", pymongo.ASCENDING)
            
            # 转换为DocumentVersion列表
            versions = []
            for version_doc in cursor:
                version = DocumentVersion(
                    version_id=version_doc["version_id"],
                    created_at=version_doc["created_at"],
                    created_by=version_doc.get("created_by"),
                    comment=version_doc.get("comment"),
                    changes=version_doc.get("changes")
                )
                versions.append(version)
                
            return versions
            
        except PyMongoError as e:
            logger.error(f"Error getting versions for document {doc_id}: {str(e)}")
            return []
    
    def get_document_by_version(self, doc_id: str, version_id: str) -> Optional[DocumentItem]:
        """
        获取文档的特定版本
        
        Note: 目前的实现只返回最新的文档，但标记了请求的版本
              完整实现需要维护每个版本的完整文档副本
        
        Args:
            doc_id: 文档ID
            version_id: 版本ID
            
        Returns:
            Optional[DocumentItem]: 文档对象，如不存在则返回None
        """
        try:
            # 查询版本是否存在
            version_doc = self.versions.find_one({
                "document_id": doc_id,
                "version_id": version_id
            })
            
            if not version_doc:
                logger.warning(f"Version {version_id} not found for document {doc_id}")
                return None
            
            # 加载文档
            document = self.load_document(doc_id)
            if not document:
                return None
                
            # 标记请求的版本
            logger.info(f"Loaded document {doc_id} (requested version: {version_id})")
            
            # 注意: 这里只返回最新的文档
            # 为了完整实现版本控制，需要为每个版本存储完整的文档副本
            return document
            
        except PyMongoError as e:
            logger.error(f"Error getting version {version_id} of document {doc_id}: {str(e)}")
            return None
    
    def aggregate_tags(self) -> Dict[str, int]:
        """
        聚合所有标签并统计数量
        
        Returns:
            Dict[str, int]: 标签计数字典
        """
        try:
            pipeline = [
                {"$unwind": "$metadata.tags"},
                {"$group": {"_id": "$metadata.tags", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            
            result = self.documents.aggregate(pipeline)
            
            # 转换为字典
            tags_count = {doc["_id"]: doc["count"] for doc in result}
            
            return tags_count
            
        except PyMongoError as e:
            logger.error(f"Error aggregating tags: {str(e)}")
            return {}
    
    def aggregate_authors(self) -> Dict[str, int]:
        """
        聚合所有作者并统计数量
        
        Returns:
            Dict[str, int]: 作者计数字典
        """
        try:
            pipeline = [
                {"$match": {"metadata.author": {"$ne": None}}},
                {"$group": {"_id": "$metadata.author", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            
            result = self.documents.aggregate(pipeline)
            
            # 转换为字典
            authors_count = {doc["_id"]: doc["count"] for doc in result}
            
            return authors_count
            
        except PyMongoError as e:
            logger.error(f"Error aggregating authors: {str(e)}")
            return {}
    
    def aggregate_by_status(self) -> Dict[str, int]:
        """
        聚合所有状态并统计数量
        
        Returns:
            Dict[str, int]: 状态计数字典
        """
        try:
            pipeline = [
                {"$group": {"_id": "$metadata.status", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            
            result = self.documents.aggregate(pipeline)
            
            # 转换为字典
            status_count = {doc["_id"]: doc["count"] for doc in result}
            
            return status_count
            
        except PyMongoError as e:
            logger.error(f"Error aggregating status: {str(e)}")
            return {}
    
    def find_related_documents(self, doc_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        查找与指定文档相关的文档
        
        Args:
            doc_id: 文档ID
            max_results: 最大结果数
            
        Returns:
            List[Dict[str, Any]]: 相关文档索引列表
        """
        try:
            # 加载源文档
            document = self.load_document(doc_id)
            if not document:
                return []
                
            # 根据标签查找相关文档
            tags = document.metadata.tags
            if not tags:
                return []
                
            # 查询具有相同标签的文档
            query = {
                "metadata.tags": {"$in": tags},
                "id": {"$ne": doc_id}  # 排除自身
            }
            
            # 执行聚合查询，计算标签匹配数
            pipeline = [
                {"$match": query},
                {"$project": {
                    "id": 1,
                    "metadata": 1,
                    "match_count": {
                        "$size": {
                            "$setIntersection": ["$metadata.tags", tags]
                        }
                    }
                }},
                {"$sort": {"match_count": -1}},
                {"$limit": max_results}
            ]
            
            result = self.documents.aggregate(pipeline)
            
            # 转换为简化的文档信息
            related_docs = []
            for doc in result:
                related_docs.append({
                    "id": doc["id"],
                    "title": doc["metadata"].get("custom", {}).get("title", "Untitled"),
                    "author": doc["metadata"].get("author"),
                    "tags": doc["metadata"].get("tags", []),
                    "match_count": doc["match_count"]
                })
                
            return related_docs
            
        except PyMongoError as e:
            logger.error(f"Error finding related documents for {doc_id}: {str(e)}")
            return []
    
    def backup_collection(self, collection_name: str, output_file: str) -> bool:
        """
        备份集合到JSON文件
        
        Args:
            collection_name: 集合名称
            output_file: 输出文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            # 获取集合
            if collection_name == "documents":
                collection = self.documents
            elif collection_name == "versions":
                collection = self.versions
            elif collection_name == "metadata":
                collection = self.metadata
            else:
                logger.error(f"Unknown collection: {collection_name}")
                return False
                
            # 导出所有文档
            docs = list(collection.find({}))
            
            # 转换ObjectId为字符串
            for doc in docs:
                if '_id' in doc and isinstance(doc['_id'], ObjectId):
                    doc['_id'] = str(doc['_id'])
            
            # 保存到文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(docs, f, ensure_ascii=False, indent=2, default=str)
                
            logger.info(f"Backed up {len(docs)} documents from {collection_name} to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error backing up collection {collection_name}: {str(e)}")
            return False
    
    def restore_collection(self, collection_name: str, input_file: str, 
                         clear_existing: bool = False) -> bool:
        """
        从JSON文件恢复集合
        
        Args:
            collection_name: 集合名称
            input_file: 输入文件路径
            clear_existing: 是否清除现有数据
            
        Returns:
            bool: 是否成功
        """
        try:
            # 获取集合
            if collection_name == "documents":
                collection = self.documents
            elif collection_name == "versions":
                collection = self.versions
            elif collection_name == "metadata":
                collection = self.metadata
            else:
                logger.error(f"Unknown collection: {collection_name}")
                return False
                
            # 读取文件
            with open(input_file, 'r', encoding='utf-8') as f:
                docs = json.load(f)
                
            # 清除现有数据
            if clear_existing:
                collection.delete_many({})
                
            # 恢复数据
            if docs:
                result = collection.insert_many(docs)
                success = len(result.inserted_ids) == len(docs)
                
                logger.info(f"Restored {len(result.inserted_ids)} documents to {collection_name}")
                return success
            
            return True
            
        except Exception as e:
            logger.error(f"Error restoring collection {collection_name}: {str(e)}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if hasattr(self, 'client') and self.client:
            self.client.close()
            logger.info("MongoDB connection closed")