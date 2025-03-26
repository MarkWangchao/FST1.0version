#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 异常覆盖率分析

分析异常处理的覆盖率，包括：
- 异常处理器覆盖率
- 异常类型覆盖率
- 异常恢复覆盖率
- 错误处理路径覆盖率
"""

import os
import sys
import ast
import inspect
import traceback
from typing import Dict, List, Set, Optional, Type
from collections import defaultdict

from . import CoverageBase, logger
from infrastructure.event_bus.event_manager import Event, EventType

class ExceptionVisitor(ast.NodeVisitor):
    """异常处理代码访问器"""
    
    def __init__(self):
        self.handlers = []
        self.raises = []
        self.recoveries = []
        self.error_paths = []
    
    def visit_Try(self, node):
        """访问try块"""
        for handler in node.handlers:
            handler_info = {
                'lineno': handler.lineno,
                'col_offset': handler.col_offset,
                'type': ast.unparse(handler.type) if handler.type else 'BaseException',
                'name': handler.name,
                'body': [ast.unparse(stmt) for stmt in handler.body]
            }
            self.handlers.append(handler_info)
            
            # 检查是否包含恢复逻辑
            if any(isinstance(stmt, (ast.Return, ast.Continue, ast.Break)) for stmt in handler.body):
                self.recoveries.append(handler_info)
        
        self.generic_visit(node)
    
    def visit_Raise(self, node):
        """访问raise语句"""
        self.raises.append({
            'lineno': node.lineno,
            'col_offset': node.col_offset,
            'exc': ast.unparse(node.exc) if node.exc else None,
            'cause': ast.unparse(node.cause) if node.cause else None
        })
        self.generic_visit(node)
    
    def visit_If(self, node):
        """访问if语句，检查错误处理路径"""
        # 检查是否是错误处理相关的条件
        cond_str = ast.unparse(node.test).lower()
        if any(kw in cond_str for kw in ['error', 'exception', 'failed', 'invalid']):
            self.error_paths.append({
                'lineno': node.lineno,
                'col_offset': node.col_offset,
                'condition': ast.unparse(node.test),
                'body': [ast.unparse(stmt) for stmt in node.body]
            })
        self.generic_visit(node)

class ExceptionCoverage(CoverageBase):
    """异常覆盖率分析器"""
    
    def __init__(self, target_dir: str):
        super().__init__("Exception Coverage")
        self.target_dir = target_dir
        self.executed_handlers = set()
        self.executed_raises = set()
        self.executed_recoveries = set()
        self.executed_error_paths = set()
        self.exception_stats = defaultdict(int)
        
        # 解析代码
        self._parse_code()
    
    def _parse_code(self):
        """解析代码"""
        self.target_files = []
        for root, _, files in os.walk(self.target_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    if self.should_include_path(filepath):
                        self.target_files.append(filepath)
        
        # 分析每个文件
        self.code_info = defaultdict(dict)
        for filepath in self.target_files:
            with open(filepath, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=filepath)
                
                visitor = ExceptionVisitor()
                visitor.visit(tree)
                
                self.code_info[filepath] = {
                    'handlers': visitor.handlers,
                    'raises': visitor.raises,
                    'recoveries': visitor.recoveries,
                    'error_paths': visitor.error_paths
                }
    
    def start(self):
        """开始收集覆盖率"""
        super().start()
        sys.excepthook = self._exception_hook
        
        # 注册事件处理器
        # TODO: 实现事件总线的订阅机制
    
    def stop(self):
        """停止收集覆盖率"""
        sys.excepthook = sys.__excepthook__
        super().stop()
        
        # 取消注册事件处理器
        # TODO: 实现事件总线的取消订阅机制
    
    def _exception_hook(self, exc_type: Type[BaseException], exc_value: BaseException, exc_traceback):
        """异常钩子"""
        # 记录异常统计
        self.exception_stats[exc_type.__name__] += 1
        
        # 分析异常堆栈
        for filename, lineno, _, _ in traceback.extract_tb(exc_traceback):
            if not self.should_include_path(filename):
                continue
            
            # 记录执行的异常处理器
            for handler in self.code_info.get(filename, {}).get('handlers', []):
                if handler['lineno'] == lineno:
                    self.executed_handlers.add((filename, lineno))
            
            # 记录执行的raise语句
            for raise_info in self.code_info.get(filename, {}).get('raises', []):
                if raise_info['lineno'] == lineno:
                    self.executed_raises.add((filename, lineno))
        
        # 调用原始的异常处理器
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    async def on_event(self, event: Event):
        """事件处理"""
        if event.event_type == EventType.EXCEPTION:
            # 记录异常恢复
            if 'recovery' in event.data:
                recovery_info = event.data['recovery']
                self.executed_recoveries.add(
                    (recovery_info.get('file'), recovery_info.get('line'))
                )
            
            # 记录错误处理路径
            if 'error_path' in event.data:
                error_path = event.data['error_path']
                self.executed_error_paths.add(
                    (error_path.get('file'), error_path.get('line'))
                )
    
    def collect(self) -> Dict:
        """收集覆盖率数据"""
        results = {}
        for filepath in self.target_files:
            info = self.code_info[filepath]
            
            # 统计异常处理器覆盖率
            total_handlers = len(info['handlers'])
            executed_handlers = len([h for h in info['handlers'] 
                                  if (filepath, h['lineno']) in self.executed_handlers])
            
            # 统计raise语句覆盖率
            total_raises = len(info['raises'])
            executed_raises = len([r for r in info['raises']
                                if (filepath, r['lineno']) in self.executed_raises])
            
            # 统计恢复逻辑覆盖率
            total_recoveries = len(info['recoveries'])
            executed_recoveries = len([r for r in info['recoveries']
                                    if (filepath, r['lineno']) in self.executed_recoveries])
            
            # 统计错误处理路径覆盖率
            total_error_paths = len(info['error_paths'])
            executed_error_paths = len([p for p in info['error_paths']
                                     if (filepath, p['lineno']) in self.executed_error_paths])
            
            results[filepath] = {
                'handlers': {
                    'total': total_handlers,
                    'executed': executed_handlers,
                    'items': info['handlers']
                },
                'raises': {
                    'total': total_raises,
                    'executed': executed_raises,
                    'items': info['raises']
                },
                'recoveries': {
                    'total': total_recoveries,
                    'executed': executed_recoveries,
                    'items': info['recoveries']
                },
                'error_paths': {
                    'total': total_error_paths,
                    'executed': executed_error_paths,
                    'items': info['error_paths']
                }
            }
        
        return results
    
    def report(self) -> Dict:
        """生成覆盖率报告"""
        coverage_data = self.collect()
        
        # 计算总体统计信息
        total_handlers = sum(data['handlers']['total'] for data in coverage_data.values())
        executed_handlers = sum(data['handlers']['executed'] for data in coverage_data.values())
        
        total_raises = sum(data['raises']['total'] for data in coverage_data.values())
        executed_raises = sum(data['raises']['executed'] for data in coverage_data.values())
        
        total_recoveries = sum(data['recoveries']['total'] for data in coverage_data.values())
        executed_recoveries = sum(data['recoveries']['executed'] for data in coverage_data.values())
        
        total_error_paths = sum(data['error_paths']['total'] for data in coverage_data.values())
        executed_error_paths = sum(data['error_paths']['executed'] for data in coverage_data.values())
        
        return {
            'summary': {
                'handler_rate': executed_handlers / total_handlers if total_handlers > 0 else 0,
                'raise_rate': executed_raises / total_raises if total_raises > 0 else 0,
                'recovery_rate': executed_recoveries / total_recoveries if total_recoveries > 0 else 0,
                'error_path_rate': executed_error_paths / total_error_paths if total_error_paths > 0 else 0
            },
            'files': coverage_data,
            'exception_stats': dict(self.exception_stats),
            'metadata': {
                'start_time': self.start_time,
                'end_time': self.end_time,
                'duration': self.end_time - self.start_time if self.end_time else 0
            }
        }