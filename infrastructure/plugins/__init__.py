#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 插件系统

提供可扩展的插件系统，允许通过钩子机制扩展系统功能，
而无需修改核心代码。主要功能包括：
- 插件的发现、加载和生命周期管理
- 基于钩子的扩展点机制
- 插件依赖管理和版本控制
- 插件配置管理

Created on 2025-03-07
"""

from infrastructure.plugins.hooks import (
    HookType,
    HookContext,
    HookSpecification,
    HookRegistry,
    get_hook_registry
)

from infrastructure.plugins.plugin_manager import (
    PluginStatus,
    PluginMetadata,
    Plugin,
    PluginManager,
    get_plugin_manager
)

__all__ = [
    # 钩子相关
    'HookType',
    'HookContext',
    'HookSpecification',
    'HookRegistry',
    'get_hook_registry',
    
    # 插件相关
    'PluginStatus',
    'PluginMetadata',
    'Plugin',
    'PluginManager',
    'get_plugin_manager',
]