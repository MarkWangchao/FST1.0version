#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 合规监控器

提供合规监控功能：
- 交易合规检查
- 可疑行为检测
- 审计日志记录
- 合规报告生成
"""

import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from prometheus_client import Counter, Gauge
import json

# 合规指标
COMPLIANCE_VIOLATIONS = Counter('compliance_violations_total', '合规违规次数', ['type'])
SUSPICIOUS_ACTIVITIES = Counter('suspicious_activities_total', '可疑活动次数', ['type'])
AUDIT_RECORDS = Counter('audit_records_total', '审计记录数', ['category'])

class ComplianceMonitor:
    """合规监控器"""
    
    def __init__(self, config: Dict):
        """
        初始化合规监控器
        
        Args:
            config: 监控配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 合规配置
        self.pattern_config = config.get('pattern_detection', {})
        self.audit_config = config.get('audit_log', {})
        
        # 状态变量
        self.trade_history = []
        self.violation_history = []
        self.suspicious_history = []
        self.audit_logs = []
        
        # 缓存设置
        self.cache_size = config.get('cache_size', 10000)
        
    async def start(self):
        """启动合规监控"""
        self.logger.info("合规监控已启动")
        asyncio.create_task(self._run_compliance_check())
        
    async def _run_compliance_check(self):
        """运行合规检查"""
        while True:
            try:
                await self._check_compliance()
                await self._detect_suspicious_activities()
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                self.logger.error(f"合规检查失败: {str(e)}")
                await asyncio.sleep(5)
                
    async def _check_compliance(self):
        """检查交易合规性"""
        try:
            if not self.trade_history:
                return
                
            # 转换为DataFrame便于分析
            df = pd.DataFrame(self.trade_history)
            
            # 检查交易限额
            await self._check_trading_limits(df)
            
            # 检查持仓限制
            await self._check_position_limits(df)
            
            # 检查交易频率
            await self._check_trading_frequency(df)
            
            # 检查交易时间
            await self._check_trading_hours(df)
            
        except Exception as e:
            self.logger.error(f"检查交易合规性失败: {str(e)}")
            
    async def _detect_suspicious_activities(self):
        """检测可疑活动"""
        try:
            if not self.trade_history:
                return
                
            df = pd.DataFrame(self.trade_history)
            
            # 检测大额交易
            await self._detect_large_trades(df)
            
            # 检测频繁交易
            await self._detect_frequent_trading(df)
            
            # 检测价格操纵
            await self._detect_price_manipulation(df)
            
            # 检测洗盘交易
            await self._detect_wash_trades(df)
            
        except Exception as e:
            self.logger.error(f"检测可疑活动失败: {str(e)}")
            
    async def _check_trading_limits(self, df: pd.DataFrame):
        """检查交易限额"""
        try:
            # 计算每日交易量
            daily_volume = df.groupby(pd.Grouper(key='timestamp', freq='D'))['volume'].sum()
            
            # 检查是否超过限额
            limit = self.pattern_config.get('daily_limit', 1000000)
            violations = daily_volume[daily_volume > limit]
            
            for date, volume in violations.items():
                violation = {
                    'type': 'trading_limit',
                    'timestamp': date.isoformat(),
                    'details': {
                        'volume': volume,
                        'limit': limit
                    }
                }
                
                self.violation_history.append(violation)
                COMPLIANCE_VIOLATIONS.labels(type='trading_limit').inc()
                await self.log_audit_event('violation', violation)
                
        except Exception as e:
            self.logger.error(f"检查交易限额失败: {str(e)}")
            
    async def _check_position_limits(self, df: pd.DataFrame):
        """检查持仓限制"""
        try:
            # 计算当前持仓
            positions = df.groupby('symbol')['volume'].sum()
            
            # 检查是否超过限制
            for symbol, volume in positions.items():
                limit = self.pattern_config.get('position_limits', {}).get(symbol, 1000)
                
                if abs(volume) > limit:
                    violation = {
                        'type': 'position_limit',
                        'timestamp': datetime.now().isoformat(),
                        'details': {
                            'symbol': symbol,
                            'volume': volume,
                            'limit': limit
                        }
                    }
                    
                    self.violation_history.append(violation)
                    COMPLIANCE_VIOLATIONS.labels(type='position_limit').inc()
                    await self.log_audit_event('violation', violation)
                    
        except Exception as e:
            self.logger.error(f"检查持仓限制失败: {str(e)}")
            
    async def _check_trading_frequency(self, df: pd.DataFrame):
        """检查交易频率"""
        try:
            # 计算每分钟交易次数
            freq = df.groupby([pd.Grouper(key='timestamp', freq='T'), 'symbol']).size()
            
            # 检查是否超过限制
            limit = self.pattern_config.get('frequency_limit', 100)
            violations = freq[freq > limit]
            
            for (timestamp, symbol), count in violations.items():
                violation = {
                    'type': 'frequency_limit',
                    'timestamp': timestamp.isoformat(),
                    'details': {
                        'symbol': symbol,
                        'count': count,
                        'limit': limit
                    }
                }
                
                self.violation_history.append(violation)
                COMPLIANCE_VIOLATIONS.labels(type='frequency_limit').inc()
                await self.log_audit_event('violation', violation)
                
        except Exception as e:
            self.logger.error(f"检查交易频率失败: {str(e)}")
            
    async def _check_trading_hours(self, df: pd.DataFrame):
        """检查交易时间"""
        try:
            # 获取交易时间配置
            trading_hours = self.pattern_config.get('trading_hours', {
                'start': '09:30',
                'end': '15:00'
            })
            
            # 检查是否在交易时间外
            df['time'] = pd.to_datetime(df['timestamp']).dt.time
            outside_hours = df[
                (df['time'] < pd.to_datetime(trading_hours['start']).time()) |
                (df['time'] > pd.to_datetime(trading_hours['end']).time())
            ]
            
            for _, trade in outside_hours.iterrows():
                violation = {
                    'type': 'trading_hours',
                    'timestamp': trade['timestamp'],
                    'details': {
                        'symbol': trade['symbol'],
                        'time': trade['time'].strftime('%H:%M:%S')
                    }
                }
                
                self.violation_history.append(violation)
                COMPLIANCE_VIOLATIONS.labels(type='trading_hours').inc()
                await self.log_audit_event('violation', violation)
                
        except Exception as e:
            self.logger.error(f"检查交易时间失败: {str(e)}")
            
    async def _detect_large_trades(self, df: pd.DataFrame):
        """检测大额交易"""
        try:
            # 计算每笔交易的标准差
            std_volume = df.groupby('symbol')['volume'].transform('std')
            mean_volume = df.groupby('symbol')['volume'].transform('mean')
            
            # 检测超过3个标准差的交易
            large_trades = df[abs(df['volume'] - mean_volume) > 3 * std_volume]
            
            for _, trade in large_trades.iterrows():
                suspicious = {
                    'type': 'large_trade',
                    'timestamp': trade['timestamp'],
                    'details': {
                        'symbol': trade['symbol'],
                        'volume': trade['volume'],
                        'mean': mean_volume[trade.name],
                        'std': std_volume[trade.name]
                    }
                }
                
                self.suspicious_history.append(suspicious)
                SUSPICIOUS_ACTIVITIES.labels(type='large_trade').inc()
                await self.log_audit_event('suspicious', suspicious)
                
        except Exception as e:
            self.logger.error(f"检测大额交易失败: {str(e)}")
            
    async def _detect_frequent_trading(self, df: pd.DataFrame):
        """检测频繁交易"""
        try:
            # 计算交易间隔
            df = df.sort_values('timestamp')
            intervals = df.groupby('symbol')['timestamp'].diff()
            
            # 检测小于最小间隔的交易
            min_interval = pd.Timedelta(self.pattern_config.get('min_interval', '1s'))
            frequent_trades = df[intervals < min_interval]
            
            for _, trade in frequent_trades.iterrows():
                suspicious = {
                    'type': 'frequent_trading',
                    'timestamp': trade['timestamp'],
                    'details': {
                        'symbol': trade['symbol'],
                        'interval': intervals[trade.name].total_seconds()
                    }
                }
                
                self.suspicious_history.append(suspicious)
                SUSPICIOUS_ACTIVITIES.labels(type='frequent_trading').inc()
                await self.log_audit_event('suspicious', suspicious)
                
        except Exception as e:
            self.logger.error(f"检测频繁交易失败: {str(e)}")
            
    async def _detect_price_manipulation(self, df: pd.DataFrame):
        """检测价格操纵"""
        try:
            # 计算价格变动
            price_changes = df.groupby('symbol')['price'].pct_change()
            
            # 检测异常价格变动
            threshold = self.pattern_config.get('price_change_threshold', 0.01)
            manipulations = df[abs(price_changes) > threshold]
            
            for _, trade in manipulations.iterrows():
                suspicious = {
                    'type': 'price_manipulation',
                    'timestamp': trade['timestamp'],
                    'details': {
                        'symbol': trade['symbol'],
                        'price': trade['price'],
                        'change': price_changes[trade.name]
                    }
                }
                
                self.suspicious_history.append(suspicious)
                SUSPICIOUS_ACTIVITIES.labels(type='price_manipulation').inc()
                await self.log_audit_event('suspicious', suspicious)
                
        except Exception as e:
            self.logger.error(f"检测价格操纵失败: {str(e)}")
            
    async def _detect_wash_trades(self, df: pd.DataFrame):
        """检测洗盘交易"""
        try:
            # 查找相近时间、相近价格、方向相反的交易
            df = df.sort_values('timestamp')
            
            for symbol in df['symbol'].unique():
                symbol_trades = df[df['symbol'] == symbol]
                
                for i in range(len(symbol_trades) - 1):
                    trade1 = symbol_trades.iloc[i]
                    trade2 = symbol_trades.iloc[i + 1]
                    
                    # 检查时间间隔
                    time_diff = (pd.to_datetime(trade2['timestamp']) - 
                               pd.to_datetime(trade1['timestamp'])).total_seconds()
                    
                    # 检查价格差异
                    price_diff = abs(trade2['price'] - trade1['price']) / trade1['price']
                    
                    if (time_diff < 60 and  # 1分钟内
                        price_diff < 0.001 and  # 价差小于0.1%
                        trade1['direction'] != trade2['direction']):  # 方向相反
                        
                        suspicious = {
                            'type': 'wash_trade',
                            'timestamp': trade2['timestamp'],
                            'details': {
                                'symbol': symbol,
                                'trade1': trade1.to_dict(),
                                'trade2': trade2.to_dict(),
                                'time_diff': time_diff,
                                'price_diff': price_diff
                            }
                        }
                        
                        self.suspicious_history.append(suspicious)
                        SUSPICIOUS_ACTIVITIES.labels(type='wash_trade').inc()
                        await self.log_audit_event('suspicious', suspicious)
                        
        except Exception as e:
            self.logger.error(f"检测洗盘交易失败: {str(e)}")
            
    async def log_audit_event(self, category: str, details: Dict):
        """记录审计事件"""
        try:
            audit_data = {
                'timestamp': datetime.now().isoformat(),
                'category': category,
                'details': details
            }
            
            self.audit_logs.append(audit_data)
            AUDIT_RECORDS.labels(category=category).inc()
            
            # 保存审计日志
            if len(self.audit_logs) >= self.cache_size:
                await self._save_audit_logs()
                
        except Exception as e:
            self.logger.error(f"记录审计事件失败: {str(e)}")
            
    async def _save_audit_logs(self):
        """保存审计日志"""
        try:
            if not self.audit_logs:
                return
                
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"audit_log_{timestamp}.json"
            filepath = os.path.join(self.audit_config['path'], filename)
            
            # 保存日志
            with open(filepath, 'w') as f:
                json.dump(self.audit_logs, f, indent=2)
                
            self.audit_logs = []
            self.logger.info(f"审计日志已保存: {filepath}")
            
        except Exception as e:
            self.logger.error(f"保存审计日志失败: {str(e)}")
            
    # 数据更新接口
    def add_trade(self, trade_data: Dict):
        """添加交易记录"""
        try:
            self.trade_history.append(trade_data)
            
            # 限制历史记录大小
            if len(self.trade_history) > self.cache_size:
                self.trade_history = self.trade_history[-self.cache_size:]
                
        except Exception as e:
            self.logger.error(f"添加交易记录失败: {str(e)}")
            
    # 查询接口
    def get_violations(self,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      violation_type: Optional[str] = None) -> List[Dict]:
        """获取违规记录"""
        try:
            filtered = []
            for violation in self.violation_history:
                timestamp = datetime.fromisoformat(violation['timestamp'])
                
                if start_time and timestamp < start_time:
                    continue
                if end_time and timestamp > end_time:
                    continue
                if violation_type and violation['type'] != violation_type:
                    continue
                    
                filtered.append(violation)
                
            return filtered
            
        except Exception as e:
            self.logger.error(f"获取违规记录失败: {str(e)}")
            return []
            
    def get_suspicious_activities(self,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None,
                                activity_type: Optional[str] = None) -> List[Dict]:
        """获取可疑活动"""
        try:
            filtered = []
            for activity in self.suspicious_history:
                timestamp = datetime.fromisoformat(activity['timestamp'])
                
                if start_time and timestamp < start_time:
                    continue
                if end_time and timestamp > end_time:
                    continue
                if activity_type and activity['type'] != activity_type:
                    continue
                    
                filtered.append(activity)
                
            return filtered
            
        except Exception as e:
            self.logger.error(f"获取可疑活动失败: {str(e)}")
            return []
            
    def get_compliance_stats(self) -> Dict:
        """获取合规统计信息"""
        try:
            return {
                'violations': {
                    'total': len(self.violation_history),
                    'by_type': {
                        type: COMPLIANCE_VIOLATIONS.labels(type=type)._value.get()
                        for type in ['trading_limit', 'position_limit', 
                                   'frequency_limit', 'trading_hours']
                    }
                },
                'suspicious_activities': {
                    'total': len(self.suspicious_history),
                    'by_type': {
                        type: SUSPICIOUS_ACTIVITIES.labels(type=type)._value.get()
                        for type in ['large_trade', 'frequent_trading',
                                   'price_manipulation', 'wash_trade']
                    }
                },
                'audit_records': {
                    'total': len(self.audit_logs),
                    'by_category': {
                        category: AUDIT_RECORDS.labels(category=category)._value.get()
                        for category in ['violation', 'suspicious']
                    }
                }
            }
            
        except Exception as e:
            self.logger.error(f"获取合规统计信息失败: {str(e)}")
            return {}