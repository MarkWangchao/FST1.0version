#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 插件管理器

提供统一的插件管理功能，负责插件的加载、初始化、配置和调度。
插件系统允许通过钩子机制扩展系统功能，而无需修改核心代码。
"""

import importlib
import inspect
import logging
import os
import sys
import json
import pkgutil
import traceback
import yaml
from dataclasses import dataclass
from enum import Enum
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

# 导入钩子系统
from infrastructure.plugins.hooks import (
    HookContext, 
    HookRegistry, 
    HookSpecification, 
    HookType,
    get_hook_registry
)

# 日志配置
logger = logging.getLogger("fst.plugins.manager")


class PluginStatus(str, Enum):
    """插件状态枚举"""
    DISCOVERED = "discovered"  # 已发现但未加载
    LOADED = "loaded"          # 已加载但未初始化
    INITIALIZED = "initialized"  # 已初始化但未启用
    ENABLED = "enabled"        # 已启用并运行
    DISABLED = "disabled"      # 已禁用
    ERROR = "error"            # 错误状态


@dataclass
class PluginMetadata:
    """插件元数据"""
    
    id: str                    # 插件ID
    name: str                  # 插件名称
    version: str               # 插件版本
    description: str           # 插件描述
    author: str                # 作者
    requires: List[str]        # 依赖插件列表
    python_requires: str       # Python版本要求
    hooks: List[str]           # 使用的钩子列表
    provides: List[str]        # 提供的功能
    tags: List[str]            # 标签
    entry_point: str           # 入口点
    config_schema: Dict[str, Any] = None  # 配置模式
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginMetadata':
        """从字典创建元数据"""
        metadata = cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            requires=data.get("requires", []),
            python_requires=data.get("python_requires", ""),
            hooks=data.get("hooks", []),
            provides=data.get("provides", []),
            tags=data.get("tags", []),
            entry_point=data.get("entry_point", ""),
            config_schema=data.get("config_schema", {})
        )
        return metadata
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "requires": self.requires,
            "python_requires": self.python_requires,
            "hooks": self.hooks,
            "provides": self.provides,
            "tags": self.tags,
            "entry_point": self.entry_point,
            "config_schema": self.config_schema
        }


class Plugin:
    """
    插件对象
    
    封装单个插件的所有信息和操作接口。
    """
    
    def __init__(self, 
                metadata: PluginMetadata, 
                module: Optional[ModuleType] = None,
                path: Optional[str] = None):
        """
        初始化插件
        
        Args:
            metadata: 插件元数据
            module: 插件模块对象
            path: 插件路径
        """
        self.metadata = metadata
        self.module = module
        self.path = path
        self.status = PluginStatus.DISCOVERED
        self.config = {}
        self.error = None
        self.handlers = {}  # hook_name -> [handler]
        
        # 插件导出的接口
        self.exports = {}
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"Plugin({self.metadata.id}, {self.status.value})"
    
    def get_info(self) -> Dict[str, Any]:
        """获取插件信息"""
        return {
            "id": self.metadata.id,
            "name": self.metadata.name,
            "version": self.metadata.version,
            "description": self.metadata.description,
            "author": self.metadata.author,
            "status": self.status.value,
            "path": self.path,
            "hooks": list(self.handlers.keys()),
            "error": str(self.error) if self.error else None
        }


class PluginManager:
    """
    插件管理器
    
    管理系统中的所有插件，提供插件发现、加载和执行功能。
    """
    
    def __init__(self):
        """初始化插件管理器"""
        self.plugins = {}  # id -> Plugin
        self.plugin_dirs = []  # 插件目录列表
        self.hook_registry = get_hook_registry()
        self.loaded = False
        self._registered_handlers = {}  # (plugin_id, hook_name) -> [handler_id]
        self._plugin_graph = {}  # id -> [required_id]
        
        logger.info("插件管理器初始化")
    
    def add_plugin_dir(self, directory: str) -> bool:
        """
        添加插件目录
        
        Args:
            directory: 插件目录路径
            
        Returns:
            bool: 是否添加成功
        """
        if not os.path.isdir(directory):
            logger.warning(f"插件目录不存在: {directory}")
            return False
            
        if directory not in self.plugin_dirs:
            self.plugin_dirs.append(directory)
            logger.info(f"添加插件目录: {directory}")
            return True
            
        return False
    
    def discover_plugins(self) -> List[str]:
        """
        发现插件
        
        扫描所有插件目录，查找并加载插件元数据。
        
        Returns:
            List[str]: 已发现的插件ID列表
        """
        discovered_ids = []
        
        for plugin_dir in self.plugin_dirs:
            logger.info(f"扫描插件目录: {plugin_dir}")
            
            # 遍历目录中的所有子目录
            for item in os.listdir(plugin_dir):
                item_path = os.path.join(plugin_dir, item)
                
                # 检查是否为目录
                if not os.path.isdir(item_path):
                    continue
                    
                # 检查是否有元数据文件
                metadata_file = os.path.join(item_path, "plugin.json")
                if not os.path.isfile(metadata_file):
                    metadata_file = os.path.join(item_path, "plugin.yaml")
                    if not os.path.isfile(metadata_file):
                        continue
                
                # 加载元数据
                try:
                    metadata = self._load_metadata(metadata_file)
                    if not metadata or not metadata.id:
                        logger.warning(f"无效的插件元数据: {metadata_file}")
                        continue
                        
                    # 创建插件对象
                    plugin = Plugin(metadata, path=item_path)
                    self.plugins[metadata.id] = plugin
                    discovered_ids.append(metadata.id)
                    
                    logger.info(f"发现插件: {metadata.id} ({metadata.name} v{metadata.version})")
                except Exception as e:
                    logger.error(f"加载插件元数据失败: {metadata_file} - {str(e)}")
        
        # 构建依赖图
        self._build_dependency_graph()
        
        return discovered_ids
    
    def _load_metadata(self, metadata_file: str) -> Optional[PluginMetadata]:
        """
        加载元数据文件
        
        Args:
            metadata_file: 元数据文件路径
            
        Returns:
            Optional[PluginMetadata]: 元数据对象
        """
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                if metadata_file.endswith(".json"):
                    data = json.load(f)
                else:  # YAML
                    data = yaml.safe_load(f)
                    
            return PluginMetadata.from_dict(data)
        except Exception as e:
            logger.error(f"解析元数据文件失败: {metadata_file} - {str(e)}")
            return None
    
    def _build_dependency_graph(self):
        """构建插件依赖图"""
        self._plugin_graph = {}
        
        for plugin_id, plugin in self.plugins.items():
            self._plugin_graph[plugin_id] = plugin.metadata.requires
    
    def _check_circular_dependencies(self) -> List[str]:
        """
        检查循环依赖
        
        Returns:
            List[str]: 循环依赖链
        """
        visited = {}  # plugin_id -> (is_in_current_path, is_processed)
        path = []
        result = []
        
        def dfs(node):
            visited[node] = (True, False)
            path.append(node)
            
            for dependency in self._plugin_graph.get(node, []):
                if dependency not in visited:
                    if dfs(dependency):
                        return True
                elif visited[dependency][0] and not visited[dependency][1]:
                    # 循环依赖
                    cycle_start = path.index(dependency)
                    result.extend(path[cycle_start:] + [dependency])
                    return True
                    
            visited[node] = (False, True)
            path.pop()
            return False
        
        for plugin_id in self._plugin_graph:
            if plugin_id not in visited:
                if dfs(plugin_id):
                    return result
                    
        return []
    
    def _resolve_load_order(self) -> List[str]:
        """
        解析加载顺序
        
        使用拓扑排序确定插件加载顺序。
        
        Returns:
            List[str]: 插件ID列表，按加载顺序排序
        """
        # 检查循环依赖
        circular = self._check_circular_dependencies()
        if circular:
            logger.error(f"检测到循环依赖: {' -> '.join(circular)}")
            
        # 计算入度
        in_degree = {plugin_id: 0 for plugin_id in self._plugin_graph}
        for plugin_id, dependencies in self._plugin_graph.items():
            for dep in dependencies:
                if dep in in_degree:
                    in_degree[dep] += 1
        
        # 拓扑排序
        queue = [plugin_id for plugin_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            for plugin_id, dependencies in self._plugin_graph.items():
                if current in dependencies:
                    in_degree[plugin_id] -= 1
                    if in_degree[plugin_id] == 0:
                        queue.append(plugin_id)
        
        # 检查是否所有插件都已排序
        if len(result) != len(self._plugin_graph):
            logger.warning("无法解析所有依赖关系，部分插件将不会加载")
            
        return result
    
    def load_plugins(self, plugin_ids: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        加载插件
        
        按依赖顺序加载指定的插件或所有发现的插件。
        
        Args:
            plugin_ids: 要加载的插件ID列表，如果为None则加载所有插件
            
        Returns:
            Dict[str, bool]: 插件ID -> 是否加载成功
        """
        # 如果未指定，加载所有发现的插件
        if plugin_ids is None:
            plugin_ids = list(self.plugins.keys())
            
        # 解析加载顺序
        load_order = self._resolve_load_order()
        
        # 过滤不需要加载的插件
        load_order = [pid for pid in load_order if pid in plugin_ids]
        
        # 加载结果
        results = {}
        
        # 按顺序加载插件
        for plugin_id in load_order:
            plugin = self.plugins.get(plugin_id)
            if not plugin:
                logger.warning(f"插件不存在: {plugin_id}")
                results[plugin_id] = False
                continue
                
            # 检查依赖
            missing_deps = []
            for dep_id in plugin.metadata.requires:
                if dep_id not in self.plugins:
                    missing_deps.append(dep_id)
                elif self.plugins[dep_id].status != PluginStatus.LOADED:
                    # 依赖未加载或加载失败
                    if dep_id not in results or not results[dep_id]:
                        missing_deps.append(dep_id)
            
            if missing_deps:
                logger.error(f"插件 {plugin_id} 缺少依赖: {', '.join(missing_deps)}")
                plugin.status = PluginStatus.ERROR
                plugin.error = f"缺少依赖: {', '.join(missing_deps)}"
                results[plugin_id] = False
                continue
                
            # 加载插件模块
            try:
                # 将插件目录添加到系统路径
                sys.path.insert(0, plugin.path)
                
                # 加载模块
                entry_point = plugin.metadata.entry_point
                if not entry_point:
                    entry_point = f"{plugin_id}.plugin"
                    
                module = importlib.import_module(entry_point)
                plugin.module = module
                plugin.status = PluginStatus.LOADED
                results[plugin_id] = True
                
                logger.info(f"已加载插件: {plugin_id}")
            except Exception as e:
                logger.error(f"加载插件 {plugin_id} 失败: {str(e)}")
                plugin.status = PluginStatus.ERROR
                plugin.error = str(e)
                results[plugin_id] = False
            finally:
                # 从系统路径中移除插件目录
                if plugin.path in sys.path:
                    sys.path.remove(plugin.path)
        
        self.loaded = True
        return results
    
    def initialize_plugins(self, 
                         plugin_ids: Optional[List[str]] = None, 
                         config: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, bool]:
        """
        初始化插件
        
        调用插件的初始化方法，传入配置。
        
        Args:
            plugin_ids: 要初始化的插件ID列表，如果为None则初始化所有已加载的插件
            config: 插件配置，格式为 {plugin_id: config_dict}
            
        Returns:
            Dict[str, bool]: 插件ID -> 是否初始化成功
        """
        if not self.loaded:
            logger.warning("插件尚未加载，请先调用load_plugins")
            return {}
            
        # 如果未指定，初始化所有已加载的插件
        if plugin_ids is None:
            plugin_ids = [pid for pid, p in self.plugins.items() 
                         if p.status == PluginStatus.LOADED]
                         
        # 合并配置
        config = config or {}
        
        # 初始化结果
        results = {}
        
        # 按依赖顺序排序
        load_order = self._resolve_load_order()
        init_order = [pid for pid in load_order if pid in plugin_ids]
        
        # 按顺序初始化插件
        for plugin_id in init_order:
            plugin = self.plugins.get(plugin_id)
            if not plugin or plugin.status != PluginStatus.LOADED:
                continue
                
            # 获取插件配置
            plugin_config = config.get(plugin_id, {})
            plugin.config = plugin_config
            
            # 查找初始化方法
            init_func = getattr(plugin.module, "initialize", None)
            if not init_func or not callable(init_func):
                logger.warning(f"插件 {plugin_id} 没有定义initialize函数")
                plugin.status = PluginStatus.INITIALIZED
                results[plugin_id] = True
                continue
                
            # 调用初始化方法
            try:
                init_func(plugin_config)
                plugin.status = PluginStatus.INITIALIZED
                results[plugin_id] = True
                
                # 注册插件的钩子处理器
                self._register_plugin_hooks(plugin)
                
                # 记录插件导出的接口
                exports_func = getattr(plugin.module, "get_exports", None)
                if exports_func and callable(exports_func):
                    plugin.exports = exports_func() or {}
                
                logger.info(f"已初始化插件: {plugin_id}")
            except Exception as e:
                logger.error(f"初始化插件 {plugin_id} 失败: {str(e)}")
                logger.error(traceback.format_exc())
                plugin.status = PluginStatus.ERROR
                plugin.error = str(e)
                results[plugin_id] = False
        
        return results
    
    def _register_plugin_hooks(self, plugin: Plugin):
        """
        注册插件的钩子处理器
        
        Args:
            plugin: 插件对象
        """
        register_func = getattr(plugin.module, "register_hooks", None)
        if not register_func or not callable(register_func):
            logger.debug(f"插件 {plugin.metadata.id} 没有定义register_hooks函数")
            return
            
        # 注册插件的钩子
        try:
            hooks_dict = register_func(self.hook_registry)
            if not hooks_dict or not isinstance(hooks_dict, dict):
                return
                
            # 注册每个钩子处理器
            for hook_name, handler in hooks_dict.items():
                if not callable(handler):
                    logger.warning(f"插件 {plugin.metadata.id} 提供了无效的钩子处理器: {hook_name}")
                    continue
                    
                # 注册到钩子注册表
                success = self.hook_registry.register_handler(hook_name, handler)
                if success:
                    # 记录已注册的处理器，用于卸载插件时清理
                    key = (plugin.metadata.id, hook_name)
                    if key not in self._registered_handlers:
                        self._registered_handlers[key] = []
                    self._registered_handlers[key].append(handler)
                    
                    # 记录在插件对象中
                    if hook_name not in plugin.handlers:
                        plugin.handlers[hook_name] = []
                    plugin.handlers[hook_name].append(handler)
                    
                    logger.debug(f"插件 {plugin.metadata.id} 注册钩子处理器: {hook_name}")
                    
        except Exception as e:
            logger.error(f"注册插件 {plugin.metadata.id} 的钩子处理器失败: {str(e)}")
    
    def enable_plugins(self, plugin_ids: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        启用插件
        
        调用插件的启用方法，使插件开始工作。
        
        Args:
            plugin_ids: 要启用的插件ID列表，如果为None则启用所有已初始化的插件
            
        Returns:
            Dict[str, bool]: 插件ID -> 是否启用成功
        """
        # 如果未指定，启用所有已初始化的插件
        if plugin_ids is None:
            plugin_ids = [pid for pid, p in self.plugins.items() 
                         if p.status == PluginStatus.INITIALIZED]
                         
        # 启用结果
        results = {}
        
        # 按顺序启用插件
        for plugin_id in plugin_ids:
            plugin = self.plugins.get(plugin_id)
            if not plugin or plugin.status != PluginStatus.INITIALIZED:
                continue
                
            # 查找启用方法
            enable_func = getattr(plugin.module, "enable", None)
            if not enable_func or not callable(enable_func):
                # 没有定义enable函数，默认为已启用
                plugin.status = PluginStatus.ENABLED
                results[plugin_id] = True
                continue
                
            # 调用启用方法
            try:
                enable_func()
                plugin.status = PluginStatus.ENABLED
                results[plugin_id] = True
                logger.info(f"已启用插件: {plugin_id}")
            except Exception as e:
                logger.error(f"启用插件 {plugin_id} 失败: {str(e)}")
                plugin.status = PluginStatus.ERROR
                plugin.error = str(e)
                results[plugin_id] = False
        
        return results
    
    def disable_plugins(self, plugin_ids: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        禁用插件
        
        调用插件的禁用方法，使插件停止工作但不卸载。
        
        Args:
            plugin_ids: 要禁用的插件ID列表，如果为None则禁用所有已启用的插件
            
        Returns:
            Dict[str, bool]: 插件ID -> 是否禁用成功
        """
        # 如果未指定，禁用所有已启用的插件
        if plugin_ids is None:
            plugin_ids = [pid for pid, p in self.plugins.items() 
                         if p.status == PluginStatus.ENABLED]
                         
        # 按依赖顺序的逆序禁用
        load_order = self._resolve_load_order()
        disable_order = [pid for pid in reversed(load_order) if pid in plugin_ids]
        
        # 禁用结果
        results = {}
        
        # 按顺序禁用插件
        for plugin_id in disable_order:
            plugin = self.plugins.get(plugin_id)
            if not plugin or plugin.status != PluginStatus.ENABLED:
                continue
                
            # 查找禁用方法
            disable_func = getattr(plugin.module, "disable", None)
            if not disable_func or not callable(disable_func):
                # 没有定义disable函数，默认为已禁用
                plugin.status = PluginStatus.INITIALIZED
                results[plugin_id] = True
                continue
                
            # 调用禁用方法
            try:
                disable_func()
                plugin.status = PluginStatus.INITIALIZED
                results[plugin_id] = True
                logger.info(f"已禁用插件: {plugin_id}")
            except Exception as e:
                logger.error(f"禁用插件 {plugin_id} 失败: {str(e)}")
                plugin.error = str(e)
                results[plugin_id] = False
        
        return results
    
    def unload_plugins(self, plugin_ids: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        卸载插件
        
        卸载指定的插件，清理资源。
        
        Args:
            plugin_ids: 要卸载的插件ID列表，如果为None则卸载所有插件
            
        Returns:
            Dict[str, bool]: 插件ID -> 是否卸载成功
        """
        # 如果未指定，卸载所有插件
        if plugin_ids is None:
            plugin_ids = list(self.plugins.keys())
            
        # 首先禁用所有要卸载的插件
        enabled_ids = [pid for pid in plugin_ids if self.plugins.get(pid, None) and 
                      self.plugins[pid].status == PluginStatus.ENABLED]
        self.disable_plugins(enabled_ids)
        
        # 按依赖顺序的逆序卸载
        load_order = self._resolve_load_order()
        unload_order = [pid for pid in reversed(load_order) if pid in plugin_ids]
        
        # 卸载结果
        results = {}
        
        # 按顺序卸载插件
        for plugin_id in unload_order:
            plugin = self.plugins.get(plugin_id)
            if not plugin:
                continue
                
            # 查找卸载方法
            unload_func = getattr(plugin.module, "unload", None)
            
            # 移除钩子处理器
            self._unregister_plugin_hooks(plugin)
            
            # 调用卸载方法
            try:
                if unload_func and callable(unload_func):
                    unload_func()
                    
                # 从插件列表中移除
                #del self.plugins[plugin_id]
                plugin.status = PluginStatus.DISCOVERED
                plugin.module = None
                results[plugin_id] = True
                logger.info(f"已卸载插件: {plugin_id}")
            except Exception as e:
                logger.error(f"卸载插件 {plugin_id} 失败: {str(e)}")
                plugin.error = str(e)
                results[plugin_id] = False
        
        return results
    
    def _unregister_plugin_hooks(self, plugin: Plugin):
        """
        取消注册插件的钩子处理器
        
        Args:
            plugin: 插件对象
        """
        # 从钩子注册表中移除处理器
        for hook_name, handlers in plugin.handlers.items():
            for handler in handlers:
                self.hook_registry.unregister_handler(hook_name, handler)
                
        # 清理记录
        for key in list(self._registered_handlers.keys()):
            if key[0] == plugin.metadata.id:
                del self._registered_handlers[key]
                
        # 清理插件对象中的记录
        plugin.handlers.clear()
    
    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """
        获取插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[Plugin]: 插件对象，如果不存在则返回None
        """
        return self.plugins.get(plugin_id)
    
    def get_plugins(self, status: Optional[PluginStatus] = None) -> List[Plugin]:
        """
        获取插件列表
        
        Args:
            status: 过滤状态，如果为None则返回所有插件
            
        Returns:
            List[Plugin]: 插件列表
        """
        if status is None:
            return list(self.plugins.values())
        else:
            return [p for p in self.plugins.values() if p.status == status]
    
    def get_plugin_info(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        获取插件信息
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[Dict[str, Any]]: 插件信息，如果不存在则返回None
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return None
        return plugin.get_info()
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        列出所有插件
        
        Returns:
            List[Dict[str, Any]]: 插件信息列表
        """
        return [p.get_info() for p in self.plugins.values()]
    
    def get_plugin_export(self, plugin_id: str, export_name: str) -> Optional[Any]:
        """
        获取插件导出的接口
        
        Args:
            plugin_id: 插件ID
            export_name: 导出名称
            
        Returns:
            Optional[Any]: 导出的接口，如果不存在则返回None
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin or plugin.status not in (PluginStatus.INITIALIZED, PluginStatus.ENABLED):
            return None
        return plugin.exports.get(export_name)
    
    def execute_hook(self, 
                   hook_name: str, 
                   *args, 
                   **kwargs) -> HookContext:
        """
        执行钩子
        
        调用注册到指定钩子的所有处理器。
        
        Args:
            hook_name: 钩子名称
            *args, **kwargs: 传递给钩子处理器的参数
            
        Returns:
            HookContext: 钩子执行上下文
        """
        # 获取钩子规范
        hook_spec = self.hook_registry.get_spec(hook_name)
        if not hook_spec:
            logger.warning(f"未定义的钩子: {hook_name}")
            return HookContext(None, args, kwargs)
            
        # 创建钩子上下文
        context = HookContext(hook_spec, args, kwargs)
        
        # 获取处理器
        handlers = self.hook_registry.get_handlers(hook_name)
        if not handlers:
            logger.debug(f"钩子没有处理器: {hook_name}")
            return context
        
        # 按优先级排序的处理器列表
        sorted_handlers = sorted(handlers, key=lambda h: h['priority'])
        
        # 执行处理器
        try:
            for handler_info in sorted_handlers:
                handler = handler_info['handler']
                try:
                    # 调用处理器
                    result = handler(*args, **kwargs)
                    
                    # 记录结果
                    context.add_result(result)
                    
                    # 如果需要顺序执行并且返回False，则中止后续处理器
                    if hook_spec.sequential and result is False:
                        break
                except Exception as e:
                    logger.error(f"执行钩子处理器失败: {hook_name} -> {handler_info['name']} - {str(e)}")
                    context.set_error(e)
                    if hook_spec.sequential:
                        break
        except Exception as e:
            logger.error(f"执行钩子异常: {hook_name} - {str(e)}")
            context.set_error(e)
            
        return context
    
    def reload_plugin(self, plugin_id: str) -> bool:
        """
        重新加载插件
        
        卸载并重新加载指定的插件。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否重新加载成功
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            logger.warning(f"插件不存在: {plugin_id}")
            return False
            
        # 保存状态和配置
        status = plugin.status
        config = plugin.config.copy()
        
        # 卸载插件
        self.unload_plugins([plugin_id])
        
        # 加载插件
        load_result = self.load_plugins([plugin_id])
        if not load_result.get(plugin_id, False):
            return False
            
        # 初始化插件
        init_result = self.initialize_plugins([plugin_id], {plugin_id: config})
        if not init_result.get(plugin_id, False):
            return False
            
        # 如果原来是启用状态，则重新启用
        if status == PluginStatus.ENABLED:
            enable_result = self.enable_plugins([plugin_id])
            return enable_result.get(plugin_id, False)
            
        return True
    
    def shutdown(self):
        """
        关闭插件系统
        
        禁用并卸载所有插件。
        """
        logger.info("关闭插件系统")
        
        # 禁用所有插件
        self.disable_plugins()
        
        # 卸载所有插件
        self.unload_plugins()


# 全局插件管理器
_plugin_manager = None

def get_plugin_manager() -> PluginManager:
    """
    获取全局插件管理器
    
    Returns:
        PluginManager: 插件管理器实例
    """
    global _plugin_manager
    
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
        
    return _plugin_manager