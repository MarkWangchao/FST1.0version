"""
文档项定义，包含文档数据结构和元数据
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import uuid
import json


class DocumentStatus(Enum):
    """文档状态枚举"""
    DRAFT = "draft"             # 草稿状态
    PUBLISHED = "published"     # 已发布
    ARCHIVED = "archived"       # 已归档
    DELETED = "deleted"         # 已删除


@dataclass
class DocumentVersion:
    """文档版本信息"""
    version_id: str                          # 版本ID
    created_at: datetime                     # 创建时间
    created_by: Optional[str] = None         # 创建者
    comment: Optional[str] = None            # 版本注释
    changes: Optional[Dict[str, Any]] = None # 变更内容
    
    @classmethod
    def create_new(cls, created_by: Optional[str] = None, comment: Optional[str] = None) -> 'DocumentVersion':
        """
        创建新版本
        
        Args:
            created_by: 创建者
            comment: 版本注释
            
        Returns:
            DocumentVersion: 新版本对象
        """
        return cls(
            version_id=str(uuid.uuid4()),
            created_at=datetime.now(),
            created_by=created_by,
            comment=comment,
            changes={}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            'version_id': self.version_id,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
            'comment': self.comment,
            'changes': self.changes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentVersion':
        """
        从字典创建版本对象
        
        Args:
            data: 字典数据
            
        Returns:
            DocumentVersion: 版本对象
        """
        created_at = datetime.fromisoformat(data['created_at']) if isinstance(data['created_at'], str) else data['created_at']
        
        return cls(
            version_id=data['version_id'],
            created_at=created_at,
            created_by=data.get('created_by'),
            comment=data.get('comment'),
            changes=data.get('changes')
        )


@dataclass
class DocumentMetadata:
    """文档元数据"""
    created_at: datetime                         # 创建时间
    updated_at: datetime                         # 最后更新时间
    author: Optional[str] = None                 # 作者
    tags: List[str] = field(default_factory=list)# 标签
    status: DocumentStatus = DocumentStatus.DRAFT # 状态
    version: str = "1.0"                         # 版本
    content_type: str = "application/json"       # 内容类型
    size: int = 0                                # 内容大小(字节)
    schema: Optional[str] = None                 # 文档模式
    custom: Dict[str, Any] = field(default_factory=dict) # 自定义元数据
    
    def update(self):
        """更新最后修改时间"""
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'author': self.author,
            'tags': self.tags,
            'status': self.status.value,
            'version': self.version,
            'content_type': self.content_type,
            'size': self.size,
            'schema': self.schema,
            'custom': self.custom
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentMetadata':
        """
        从字典创建元数据对象
        
        Args:
            data: 字典数据
            
        Returns:
            DocumentMetadata: 元数据对象
        """
        created_at = datetime.fromisoformat(data['created_at']) if isinstance(data['created_at'], str) else data['created_at']
        updated_at = datetime.fromisoformat(data['updated_at']) if isinstance(data['updated_at'], str) else data['updated_at']
        
        return cls(
            created_at=created_at,
            updated_at=updated_at,
            author=data.get('author'),
            tags=data.get('tags', []),
            status=DocumentStatus(data['status']) if 'status' in data else DocumentStatus.DRAFT,
            version=data.get('version', "1.0"),
            content_type=data.get('content_type', "application/json"),
            size=data.get('size', 0),
            schema=data.get('schema'),
            custom=data.get('custom', {})
        )


@dataclass
class DocumentItem:
    """
    文档项，包含内容和元数据
    """
    id: str                              # 文档ID
    content: Any                         # 文档内容
    metadata: DocumentMetadata           # 元数据
    versions: List[DocumentVersion] = field(default_factory=list) # 版本历史
    
    @classmethod
    def create_new(cls, content: Any, author: Optional[str] = None, 
                 doc_id: Optional[str] = None, content_type: str = "application/json",
                 tags: Optional[List[str]] = None, custom_metadata: Optional[Dict[str, Any]] = None,
                 schema: Optional[str] = None) -> 'DocumentItem':
        """
        创建新文档
        
        Args:
            content: 文档内容
            author: 作者
            doc_id: 文档ID，如果为None则自动生成
            content_type: 内容类型
            tags: 标签列表
            custom_metadata: 自定义元数据
            schema: 文档模式
            
        Returns:
            DocumentItem: 新文档对象
        """
        # 计算内容大小
        size = len(json.dumps(content)) if content is not None else 0
        
        # 创建时间
        now = datetime.now()
        
        # 元数据
        metadata = DocumentMetadata(
            created_at=now,
            updated_at=now,
            author=author,
            tags=tags or [],
            status=DocumentStatus.DRAFT,
            content_type=content_type,
            size=size,
            schema=schema,
            custom=custom_metadata or {}
        )
        
        # 初始版本
        initial_version = DocumentVersion.create_new(
            created_by=author,
            comment="Initial version"
        )
        
        return cls(
            id=doc_id or str(uuid.uuid4()),
            content=content,
            metadata=metadata,
            versions=[initial_version]
        )
    
    def update_content(self, content: Any, author: Optional[str] = None, 
                     comment: Optional[str] = None) -> str:
        """
        更新文档内容并创建新版本
        
        Args:
            content: 新内容
            author: 作者
            comment: 版本注释
            
        Returns:
            str: 新版本ID
        """
        # 计算差异(简化实现，实际可能需要更复杂的差异计算)
        changes = {"new_size": len(json.dumps(content)) if content is not None else 0,
                  "old_size": self.metadata.size}
        
        # 创建新版本
        new_version = DocumentVersion(
            version_id=str(uuid.uuid4()),
            created_at=datetime.now(),
            created_by=author,
            comment=comment,
            changes=changes
        )
        
        # 添加到版本历史
        self.versions.append(new_version)
        
        # 更新内容和元数据
        self.content = content
        self.metadata.size = changes["new_size"]
        self.metadata.update()
        
        # 更新版本号
        version_parts = self.metadata.version.split('.')
        if len(version_parts) >= 2:
            major, minor = int(version_parts[0]), int(version_parts[1])
            minor += 1
            self.metadata.version = f"{major}.{minor}"
        
        return new_version.version_id
    
    def change_status(self, status: DocumentStatus, author: Optional[str] = None) -> None:
        """
        更改文档状态
        
        Args:
            status: 新状态
            author: 操作者
        """
        old_status = self.metadata.status
        self.metadata.status = status
        self.metadata.update()
        
        # 记录状态变更
        new_version = DocumentVersion(
            version_id=str(uuid.uuid4()),
            created_at=datetime.now(),
            created_by=author,
            comment=f"Status changed from {old_status.value} to {status.value}",
            changes={"status_change": {"from": old_status.value, "to": status.value}}
        )
        
        self.versions.append(new_version)
    
    def add_tags(self, tags: List[str]) -> None:
        """
        添加标签
        
        Args:
            tags: 要添加的标签列表
        """
        new_tags = [tag for tag in tags if tag not in self.metadata.tags]
        if new_tags:
            self.metadata.tags.extend(new_tags)
            self.metadata.update()
    
    def remove_tags(self, tags: List[str]) -> None:
        """
        移除标签
        
        Args:
            tags: 要移除的标签列表
        """
        original_count = len(self.metadata.tags)
        self.metadata.tags = [tag for tag in self.metadata.tags if tag not in tags]
        
        if len(self.metadata.tags) != original_count:
            self.metadata.update()
    
    def get_version(self, version_id: str) -> Optional[DocumentVersion]:
        """
        获取指定版本
        
        Args:
            version_id: 版本ID
            
        Returns:
            Optional[DocumentVersion]: 版本对象，如不存在则返回None
        """
        for version in self.versions:
            if version.version_id == version_id:
                return version
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            'id': self.id,
            'content': self.content,
            'metadata': self.metadata.to_dict(),
            'versions': [v.to_dict() for v in self.versions]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentItem':
        """
        从字典创建文档对象
        
        Args:
            data: 字典数据
            
        Returns:
            DocumentItem: 文档对象
        """
        metadata = DocumentMetadata.from_dict(data['metadata'])
        
        versions = []
        for v_data in data.get('versions', []):
            versions.append(DocumentVersion.from_dict(v_data))
        
        return cls(
            id=data['id'],
            content=data['content'],
            metadata=metadata,
            versions=versions
        )