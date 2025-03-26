#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 策略覆盖率分析

分析策略代码的覆盖率，包括：
- 策略函数覆盖率
- 条件分支覆盖率
- 信号生成覆盖率
- 风险控制覆盖率
"""

import os
import sys
import ast
import inspect
from typing import Dict, List, Set, Optional
from collections import defaultdict
import coverage

from . import CoverageBase, logger
from infrastructure.event_bus.event_manager import Event, EventType

class StrategyVisitor(ast.NodeVisitor):
    """策略代码访问器"""
    
    def __init__(self):
        self.functions = set()
        self.branches = []
        self.signals = set()
        self.risk_controls = set()
    
    def visit_FunctionDef(self, node):
        """访问函数定义"""
        self.functions.add(node.name)
        self.generic_visit(node)
    
    def visit_If(self, node):
        """访问条件分支"""
        self.branches.append({
            'lineno': node.lineno,
            'col_offset': node.col_offset,
            'condition': ast.unparse(node.test)
        })
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """访问函数调用"""
        if isinstance(node.func, ast.Name):
            # 检测信号生成
            if node.func.id.startswith('generate_') or \
               node.func.id.endswith('_signal'):
                self.signals.add(node.func.id)
            
            # 检测风险控制
            if node.func.id.startswith('check_risk') or \
               node.func.id.startswith('validate_'):
                self.risk_controls.add(node.func.id)
        
        self.generic_visit(node)

class StrategyCoverage(CoverageBase):
    """策略覆盖率分析器"""
    
    def __init__(self, strategy_dir: str):
        super().__init__("Strategy Coverage")
        self.strategy_dir = strategy_dir
        self.cov = coverage.Coverage()
        self.executed_functions = set()
        self.executed_branches = set()
        self.executed_signals = set()
        self.executed_risk_controls = set()
        
        # 解析策略代码
        self._parse_strategy_code()
    
    def _parse_strategy_code(self):
        """解析策略代码"""
        self.strategy_files = []
        for root, _, files in os.walk(self.strategy_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    if self.should_include_path(filepath):
                        self.strategy_files.append(filepath)
        
        # 分析每个策略文件
        self.code_info = defaultdict(dict)
        for filepath in self.strategy_files:
            with open(filepath, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=filepath)
                
                visitor = StrategyVisitor()
                visitor.visit(tree)
                
                self.code_info[filepath] = {
                    'functions': visitor.functions,
                    'branches': visitor.branches,
                    'signals': visitor.signals,
                    'risk_controls': visitor.risk_controls
                }
    
    def start(self):
        """开始收集覆盖率"""
        super().start()
        self.cov.start()
        
        # 注册事件处理器
        # TODO: 实现事件总线的订阅机制
    
    def stop(self):
        """停止收集覆盖率"""
        self.cov.stop()
        super().stop()
        
        # 取消注册事件处理器
        # TODO: 实现事件总线的取消订阅机制
    
    async def on_event(self, event: Event):
        """事件处理"""
        # 记录执行的函数和信号
        if event.event_type == EventType.STRATEGY:
            if 'function' in event.data:
                self.executed_functions.add(event.data['function'])
            if 'signal' in event.data:
                self.executed_signals.add(event.data['signal'])
        
        # 记录执行的风险控制
        elif event.event_type == EventType.RISK_CONTROL:
            if 'check' in event.data:
                self.executed_risk_controls.add(event.data['check'])
    
    def collect(self) -> Dict:
        """收集覆盖率数据"""
        # 获取代码覆盖率数据
        self.cov.save()
        coverage_data = self.cov.get_data()
        
        # 统计每个文件的覆盖率
        results = {}
        for filepath in self.strategy_files:
            file_lines = coverage_data.lines(filepath)
            if file_lines:
                total_lines = len(file_lines)
                executed_lines = len([l for l in file_lines if l in coverage_data.lines(filepath)])
                
                info = self.code_info[filepath]
                results[filepath] = {
                    'line_rate': executed_lines / total_lines if total_lines > 0 else 0,
                    'total_lines': total_lines,
                    'executed_lines': executed_lines,
                    'functions': {
                        'total': len(info['functions']),
                        'executed': len(self.executed_functions & info['functions']),
                        'items': sorted(info['functions'])
                    },
                    'branches': {
                        'total': len(info['branches']),
                        'executed': len(self.executed_branches & {b['lineno'] for b in info['branches']}),
                        'items': info['branches']
                    },
                    'signals': {
                        'total': len(info['signals']),
                        'executed': len(self.executed_signals & info['signals']),
                        'items': sorted(info['signals'])
                    },
                    'risk_controls': {
                        'total': len(info['risk_controls']),
                        'executed': len(self.executed_risk_controls & info['risk_controls']),
                        'items': sorted(info['risk_controls'])
                    }
                }
        
        return results
    
    def report(self) -> Dict:
        """生成覆盖率报告"""
        coverage_data = self.collect()
        
        # 计算总体统计信息
        total_lines = sum(data['total_lines'] for data in coverage_data.values())
        executed_lines = sum(data['executed_lines'] for data in coverage_data.values())
        
        total_functions = sum(data['functions']['total'] for data in coverage_data.values())
        executed_functions = sum(data['functions']['executed'] for data in coverage_data.values())
        
        total_signals = sum(data['signals']['total'] for data in coverage_data.values())
        executed_signals = sum(data['signals']['executed'] for data in coverage_data.values())
        
        total_risk_controls = sum(data['risk_controls']['total'] for data in coverage_data.values())
        executed_risk_controls = sum(data['risk_controls']['executed'] for data in coverage_data.values())
        
        return {
            'summary': {
                'line_rate': executed_lines / total_lines if total_lines > 0 else 0,
                'function_rate': executed_functions / total_functions if total_functions > 0 else 0,
                'signal_rate': executed_signals / total_signals if total_signals > 0 else 0,
                'risk_control_rate': executed_risk_controls / total_risk_controls if total_risk_controls > 0 else 0
            },
            'files': coverage_data,
            'metadata': {
                'start_time': self.start_time,
                'end_time': self.end_time,
                'duration': self.end_time - self.start_time if self.end_time else 0
            }
        }