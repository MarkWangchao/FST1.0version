"""
基于文件系统的文档存储实现
"""

import os
import json
import shutil
import glob
import threading
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from datetime import datetime

from .document_item import DocumentItem, DocumentStatus, DocumentMetadata

logger = logging.getLogger(__name__)


class FileDocumentStore:
    """
    基于文件系统的文档存储，提供:
    - 文档的增删改查操作
    - 索引维护
    - 元数据搜索
    - 版本管理
    """
    
    def __init__(self, base_dir: str, create_if_missing: bool = True):
        """
        初始化文件文档存储
        
        Args:
            base_dir: 基础存储目录
            create_if_missing: 若目录不存在是否创建
        
        Raises:
            ValueError: 目录不存在且不允许创建时
        """
        self.base_dir = Path(base_dir)
        self.docs_dir = self.base_dir / "documents"
        self.index_dir = self.base_dir / "indexes"
        self.backup_dir = self.base_dir / "backups"
        
        # 创建目录结构
        if not self.base_dir.exists():
            if create_if_missing:
                self._create_directory_structure()
            else:
                raise ValueError(f"Directory {base_dir} does not exist")
        else:
            self._ensure_directory_structure()
        
        # 线程锁，防止并发操作导致数据不一致
        self._locks = {}
        self._global_lock = threading.RLock()
        
        # 加载索引
        self._index = self._load_index()
        
        logger.info(f"FileDocumentStore initialized at {base_dir}")
    
    def _create_directory_structure(self):
        """创建必要的目录结构"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(exist_ok=True)
        self.index_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
        
        # 创建索引文件
        self._create_empty_index()
    
    def _ensure_directory_structure(self):
        """确保所有必要的目录都存在"""
        self.docs_dir.mkdir(exist_ok=True)
        self.index_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
        
        # 确保索引文件存在
        if not (self.index_dir / "main_index.json").exists():
            self._create_empty_index()
    
    def _create_empty_index(self):
        """创建空索引文件"""
        empty_index = {
            "documents": {},
            "tags": {},
            "authors": {},
            "last_updated": datetime.now().isoformat()
        }
        with open(self.index_dir / "main_index.json", 'w', encoding='utf-8') as f:
            json.dump(empty_index, f, ensure_ascii=False, indent=2)
    
    def _load_index(self) -> Dict[str, Any]:
        """
        加载主索引
        
        Returns:
            Dict[str, Any]: 索引数据
        """
        index_path = self.index_dir / "main_index.json"
        try:
            if index_path.exists():
                with open(index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 索引不存在，创建新索引
                self._create_empty_index()
                with open(index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading index: {str(e)}")
            # 索引损坏，创建新索引
            self._create_empty_index()
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    def _save_index(self):
        """保存主索引"""
        index_path = self.index_dir / "main_index.json"
        self._index["last_updated"] = datetime.now().isoformat()
        
        # 创建临时文件，以防写入过程中中断导致索引损坏
        temp_path = index_path.with_suffix(".tmp")
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)
        
        # 用临时文件替换原索引文件
        temp_path.replace(index_path)
    
    def _get_document_lock(self, doc_id: str) -> threading.RLock:
        """
        获取文档锁
        
        Args:
            doc_id: 文档ID
            
        Returns:
            threading.RLock: 文档锁
        """
        with self._global_lock:
            if doc_id not in self._locks:
                self._locks[doc_id] = threading.RLock()
            return self._locks[doc_id]
    
    def _get_document_path(self, doc_id: str) -> Path:
        """
        获取文档文件路径
        
        Args:
            doc_id: 文档ID
            
        Returns:
            Path: 文件路径
        """
        return self.docs_dir / f"{doc_id}.json"
    
    def _backup_document(self, doc_id: str) -> bool:
        """
        备份文档文件
        
        Args:
            doc_id: 文档ID
            
        Returns:
            bool: 是否成功备份
        """
        src_path = self._get_document_path(doc_id)
        if not src_path.exists():
            return False
            
        # 备份目录
        backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{doc_id}_{backup_time}.json"
        
        try:
            shutil.copy2(src_path, backup_path)
            return True
        except Exception as e:
            logger.error(f"Failed to backup document {doc_id}: {str(e)}")
            return False
    
    def _update_index_for_document(self, doc: DocumentItem, is_new: bool = False, is_delete: bool = False):
        """
        更新文档索引
        
        Args:
            doc: 文档对象
            is_new: 是否为新文档
            is_delete: 是否为删除操作
        """
        with self._global_lock:
            doc_id = doc.id
            
            if is_delete:
                # 删除文档索引
                if doc_id in self._index["documents"]:
                    # 移除标签索引
                    for tag in self._index["documents"][doc_id].get("tags", []):
                        if tag in self._index["tags"] and doc_id in self._index["tags"][tag]:
                            self._index["tags"][tag].remove(doc_id)
                            # 如果标签无引用，则移除该标签
                            if not self._index["tags"][tag]:
                                del self._index["tags"][tag]
                    
                    # 移除作者索引
                    author = self._index["documents"][doc_id].get("author")
                    if author and author in self._index["authors"]:
                        if doc_id in self._index["authors"][author]:
                            self._index["authors"][author].remove(doc_id)
                            # 如果作者无引用，则移除该作者
                            if not self._index["authors"][author]:
                                del self._index["authors"][author]
                    
                    # 移除文档索引
                    del self._index["documents"][doc_id]
                    
                    self._save_index()
                return
            
            # 更新或添加文档索引
            doc_index = {
                "id": doc.id,
                "title": doc.metadata.custom.get("title", "Untitled"),
                "author": doc.metadata.author,
                "tags": doc.metadata.tags,
                "status": doc.metadata.status.value,
                "content_type": doc.metadata.content_type,
                "created_at": doc.metadata.created_at.isoformat(),
                "updated_at": doc.metadata.updated_at.isoformat(),
                "version": doc.metadata.version,
                "size": doc.metadata.size
            }
            
            # 更新主文档索引
            self._index["documents"][doc_id] = doc_index
            
            # 更新标签索引
            for tag in doc.metadata.tags:
                if tag not in self._index["tags"]:
                    self._index["tags"][tag] = []
                if doc_id not in self._index["tags"][tag]:
                    self._index["tags"][tag].append(doc_id)
            
            # 如果是修改操作，需要处理可能已移除的标签
            if not is_new:
                old_tags = set(self._index["documents"][doc_id].get("tags", []))
                new_tags = set(doc.metadata.tags)
                removed_tags = old_tags - new_tags
                
                for tag in removed_tags:
                    if tag in self._index["tags"] and doc_id in self._index["tags"][tag]:
                        self._index["tags"][tag].remove(doc_id)
                        # 如果标签无引用，则移除该标签
                        if not self._index["tags"][tag]:
                            del self._index["tags"][tag]
            
            # 更新作者索引
            author = doc.metadata.author
            if author:
                if author not in self._index["authors"]:
                    self._index["authors"][author] = []
                if doc_id not in self._index["authors"][author]:
                    self._index["authors"][author].append(doc_id)
            
            self._save_index()
    
    def save_document(self, document: DocumentItem) -> bool:
        """
        保存文档
        
        Args:
            document: 文档对象
            
        Returns:
            bool: 是否成功保存
        """
        doc_id = document.id
        lock = self._get_document_lock(doc_id)
        
        with lock:
            try:
                is_new = not self._get_document_path(doc_id).exists()
                
                # 如果文件已存在，先备份
                if not is_new:
                    self._backup_document(doc_id)
                
                # 保存文档
                doc_path = self._get_document_path(doc_id)
                doc_dict = document.to_dict()
                
                # 使用临时文件防止写入中断
                temp_path = doc_path.with_suffix(".tmp")
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(doc_dict, f, ensure_ascii=False, indent=2)
                
                # 替换原文件
                temp_path.replace(doc_path)
                
                # 更新索引
                self._update_index_for_document(document, is_new=is_new)
                
                logger.info(f"Document {doc_id} saved successfully")
                return True
                
            except Exception as e:
                logger.error(f"Error saving document {doc_id}: {str(e)}")
                return False
    
    def load_document(self, doc_id: str) -> Optional[DocumentItem]:
        """
        加载文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            Optional[DocumentItem]: 文档对象，如不存在则返回None
        """
        lock = self._get_document_lock(doc_id)
        
        with lock:
            doc_path = self._get_document_path(doc_id)
            
            if not doc_path.exists():
                return None
                
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    doc_dict = json.load(f)
                
                return DocumentItem.from_dict(doc_dict)
                
            except Exception as e:
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
        lock = self._get_document_lock(doc_id)
        
        with lock:
            doc_path = self._get_document_path(doc_id)
            
            if not doc_path.exists():
                return False
                
            try:
                # 先备份
                self._backup_document(doc_id)
                
                # 加载文档以更新索引
                doc = self.load_document(doc_id)
                
                # 删除文件
                doc_path.unlink()
                
                # 更新索引
                if doc:
                    self._update_index_for_document(doc, is_delete=True)
                
                logger.info(f"Document {doc_id} deleted successfully")
                return True
                
            except Exception as e:
                logger.error(f"Error deleting document {doc_id}: {str(e)}")
                return False
    
    def search_documents(self, query: Dict[str, Any] = None, 
                        tags: List[str] = None, 
                        author: str = None,
                        status: DocumentStatus = None,
                        limit: int = 100,
                        offset: int = 0,
                        sort_by: str = "updated_at",
                        sort_desc: bool = True) -> List[Dict[str, Any]]:
        """
        搜索文档
        
        Args:
            query: 查询条件
            tags: 标签列表
            author: 作者
            status: 文档状态
            limit: 返回结果数量限制
            offset: 分页偏移量
            sort_by: 排序字段
            sort_desc: 是否降序排序
            
        Returns:
            List[Dict[str, Any]]: 匹配的文档索引列表
        """
        with self._global_lock:
            # 收集符合条件的文档ID
            doc_ids = set(self._index["documents"].keys())
            
            # 根据标签过滤
            if tags:
                tag_doc_ids = set()
                for tag in tags:
                    if tag in self._index["tags"]:
                        tag_doc_ids.update(self._index["tags"][tag])
                doc_ids = doc_ids.intersection(tag_doc_ids) if tag_doc_ids else set()
            
            # 根据作者过滤
            if author and author in self._index["authors"]:
                author_doc_ids = set(self._index["authors"][author])
                doc_ids = doc_ids.intersection(author_doc_ids)
            
            # 根据状态过滤
            if status:
                status_value = status.value
                status_doc_ids = {
                    doc_id for doc_id, doc_info in self._index["documents"].items()
                    if doc_info.get("status") == status_value
                }
                doc_ids = doc_ids.intersection(status_doc_ids)
            
            # 根据查询条件过滤
            if query:
                query_doc_ids = set()
                for doc_id, doc_info in self._index["documents"].items():
                    match = True
                    for key, value in query.items():
                        if key not in doc_info or doc_info[key] != value:
                            match = False
                            break
                    if match:
                        query_doc_ids.add(doc_id)
                doc_ids = doc_ids.intersection(query_doc_ids)
            
            # 转换为文档信息列表
            docs = [self._index["documents"][doc_id] for doc_id in doc_ids]
            
            # 排序
            if sort_by:
                docs.sort(key=lambda d: d.get(sort_by, ""), reverse=sort_desc)
            
            # 应用分页
            return docs[offset:offset+limit]
    
    def get_all_tags(self) -> List[str]:
        """
        获取所有标签
        
        Returns:
            List[str]: 标签列表
        """
        with self._global_lock:
            return list(self._index["tags"].keys())
    
    def get_all_authors(self) -> List[str]:
        """
        获取所有作者
        
        Returns:
            List[str]: 作者列表
        """
        with self._global_lock:
            return list(self._index["authors"].keys())
    
    def get_documents_by_tag(self, tag: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        根据标签获取文档
        
        Args:
            tag: 标签
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 文档索引列表
        """
        with self._global_lock:
            if tag not in self._index["tags"]:
                return []
                
            doc_ids = self._index["tags"][tag][offset:offset+limit]
            return [self._index["documents"][doc_id] for doc_id in doc_ids if doc_id in self._index["documents"]]
    
    def get_documents_by_author(self, author: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        根据作者获取文档
        
        Args:
            author: 作者
            limit: 返回结果数量限制
            offset: 分页偏移量
            
        Returns:
            List[Dict[str, Any]]: 文档索引列表
        """
        with self._global_lock:
            if author not in self._index["authors"]:
                return []
                
            doc_ids = self._index["authors"][author][offset:offset+limit]
            return [self._index["documents"][doc_id] for doc_id in doc_ids if doc_id in self._index["documents"]]
    
    def rebuild_index(self) -> bool:
        """
        重建索引
        
        Returns:
            bool: 是否成功
        """
        with self._global_lock:
            try:
                # 创建新的空索引
                new_index = {
                    "documents": {},
                    "tags": {},
                    "authors": {},
                    "last_updated": datetime.now().isoformat()
                }
                
                # 遍历文档目录
                for doc_path in self.docs_dir.glob("*.json"):
                    try:
                        # 加载文档
                        with open(doc_path, 'r', encoding='utf-8') as f:
                            doc_dict = json.load(f)
                        
                        doc = DocumentItem.from_dict(doc_dict)
                        doc_id = doc.id
                        
                        # 更新文档索引
                        doc_index = {
                            "id": doc.id,
                            "title": doc.metadata.custom.get("title", "Untitled"),
                            "author": doc.metadata.author,
                            "tags": doc.metadata.tags,
                            "status": doc.metadata.status.value,
                            "content_type": doc.metadata.content_type,
                            "created_at": doc.metadata.created_at.isoformat(),
                            "updated_at": doc.metadata.updated_at.isoformat(),
                            "version": doc.metadata.version,
                            "size": doc.metadata.size
                        }
                        
                        new_index["documents"][doc_id] = doc_index
                        
                        # 更新标签索引
                        for tag in doc.metadata.tags:
                            if tag not in new_index["tags"]:
                                new_index["tags"][tag] = []
                            if doc_id not in new_index["tags"][tag]:
                                new_index["tags"][tag].append(doc_id)
                        
                        # 更新作者索引
                        author = doc.metadata.author
                        if author:
                            if author not in new_index["authors"]:
                                new_index["authors"][author] = []
                            if doc_id not in new_index["authors"][author]:
                                new_index["authors"][author].append(doc_id)
                                
                    except Exception as e:
                        logger.error(f"Error processing document {doc_path}: {str(e)}")
                
                # 备份旧索引
                old_index_path = self.index_dir / "main_index.json"
                if old_index_path.exists():
                    backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = self.index_dir / f"main_index_backup_{backup_time}.json"
                    shutil.copy2(old_index_path, backup_path)
                
                # 使用新索引替换旧索引
                self._index = new_index
                self._save_index()
                
                logger.info("Index rebuilt successfully")
                return True
                
            except Exception as e:
                logger.error(f"Error rebuilding index: {str(e)}")
                return False
    
    def count_documents(self, status: Optional[DocumentStatus] = None) -> int:
        """
        统计文档数量
        
        Args:
            status: 可选的状态过滤条件
            
        Returns:
            int: 文档数量
        """
        with self._global_lock:
            if status is None:
                return len(self._index["documents"])
            
            status_value = status.value
            return sum(1 for doc_info in self._index["documents"].values() 
                      if doc_info.get("status") == status_value)
    
    def export_document(self, doc_id: str, export_path: str, 
                      include_versions: bool = True) -> bool:
        """
        导出文档
        
        Args:
            doc_id: 文档ID
            export_path: 导出路径
            include_versions: 是否包含版本历史
            
        Returns:
            bool: 是否成功
        """
        doc = self.load_document(doc_id)
        if not doc:
            return False
            
        try:
            export_data = doc.to_dict()
            
            # 如果不包含版本历史，则只保留最新版本
            if not include_versions:
                latest_version = export_data["versions"][-1] if export_data["versions"] else None
                export_data["versions"] = [latest_version] if latest_version else []
            
            # 导出文档
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
                
            return True
            
        except Exception as e:
            logger.error(f"Error exporting document {doc_id}: {str(e)}")
            return False
    
    def import_document(self, import_path: str, 
                      overwrite_existing: bool = False,
                      new_id: bool = False) -> Optional[str]:
        """
        导入文档
        
        Args:
            import_path: 导入路径
            overwrite_existing: 是否覆盖现有文档
            new_id: 是否使用新ID
            
        Returns:
            Optional[str]: 导入的文档ID，如失败则返回None
        """
        try:
            # 读取导入文件
            with open(import_path, 'r', encoding='utf-8') as f:
                doc_dict = json.load(f)
            
            # 创建文档对象
            doc = DocumentItem.from_dict(doc_dict)
            
            # 如果需要新ID
            if new_id:
                original_id = doc.id
                doc.id = str(uuid.uuid4())
                logger.info(f"Assigned new ID {doc.id} to imported document (original ID: {original_id})")
            
            # 检查是否存在
            if self._get_document_path(doc.id).exists() and not overwrite_existing:
                logger.warning(f"Document {doc.id} already exists and overwrite_existing=False")
                return None
            
            # 保存文档
            if self.save_document(doc):
                return doc.id
            
            return None
            
        except Exception as e:
            logger.error(f"Error importing document: {str(e)}")
            return None
    
    def cleanup(self):
        """清理资源"""
        # 这里可以添加清理资源的逻辑，如定期清理备份等
        # 对于文件存储，大多数资源不需要显式清理
        pass