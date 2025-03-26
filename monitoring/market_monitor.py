#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 市场数据监控器

监控市场数据质量：
- 行情延迟
- 数据完整性
- 价格异常
- 流量统计
"""

import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import numpy as np
from collections import deque
from prometheus_client import Counter, Gauge, Histogram

# 市场数据指标
MARKET_LATENCY = Histogram('market_data_latency_seconds', '行情延迟')
DATA_QUALITY = Gauge('market_data_quality', '数据质量分数', ['symbol'])
PRICE_ANOMALY = Counter('market_data_price_anomaly', '价格异常次数', ['symbol'])
DATA_FLOW = Counter('market_data_flow_bytes', '数据流量', ['direction'])

class MarketMonitor:
    """市场数据监控器"""
    
    def __init__(self, config: Dict):
        """
        初始化市场数据监控器
        
        Args:
            config: 监控配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 监控配置
        self.latency_threshold = config.get('latency', {}).get('threshold', 0.05)  # 50ms
        self.sample_window = config.get('latency', {}).get('sample_window', 10)    # 10s
        self.jitter_threshold = config.get('quality', {}).get('jitter_threshold', 0.1)  # 100ms
        self.packet_loss_threshold = config.get('quality', {}).get('packet_loss_rate', 0.001)  # 0.1%
        
        # 状态变量
        self.latency_samples = {}
        self.price_history = {}
        self.packet_stats = {
            'received': 0,
            'lost': 0,
            'total_bytes': 0
        }
        
        # 缓存设置
        self.cache_size = config.get('cache_size', 1000)
        self.symbol_metrics = {}
        
    async def start(self):
        """启动市场数据监控"""
        self.logger.info("市场数据监控已启动")
        asyncio.create_task(self._run_quality_check())
        
    async def _run_quality_check(self):
        """运行数据质量检查"""
        while True:
            try:
                await self._check_data_quality()
                await asyncio.sleep(1)
            except Exception as e:
                self.logger.error(f"数据质量检查失败: {str(e)}")
                await asyncio.sleep(5)
                
    async def _check_data_quality(self):
        """检查数据质量"""
        try:
            for symbol in self.price_history:
                # 计算价格波动
                prices = self.price_history[symbol]
                if len(prices) < 2:
                    continue
                    
                # 检查价格异常
                mean_price = np.mean(prices)
                std_price = np.std(prices)
                latest_price = prices[-1]
                
                if abs(latest_price - mean_price) > 3 * std_price:  # 3σ原则
                    PRICE_ANOMALY.labels(symbol=symbol).inc()
                    await self._handle_price_anomaly(symbol, latest_price, mean_price, std_price)
                    
                # 计算数据质量分数
                quality_score = self._calculate_quality_score(symbol)
                DATA_QUALITY.labels(symbol=symbol).set(quality_score)
                
        except Exception as e:
            self.logger.error(f"检查数据质量失败: {str(e)}")
            
    def _calculate_quality_score(self, symbol: str) -> float:
        """计算数据质量分数"""
        try:
            metrics = self.symbol_metrics.get(symbol, {})
            
            # 延迟分数 (0-1)
            latency_samples = self.latency_samples.get(symbol, [])
            avg_latency = np.mean(latency_samples) if latency_samples else 0
            latency_score = max(0, 1 - (avg_latency / self.latency_threshold))
            
            # 抖动分数 (0-1)
            jitter = np.std(latency_samples) if len(latency_samples) > 1 else 0
            jitter_score = max(0, 1 - (jitter / self.jitter_threshold))
            
            # 丢包分数 (0-1)
            packet_loss_rate = metrics.get('packet_loss_rate', 0)
            loss_score = max(0, 1 - (packet_loss_rate / self.packet_loss_threshold))
            
            # 价格连续性分数 (0-1)
            price_gaps = metrics.get('price_gaps', 0)
            continuity_score = max(0, 1 - (price_gaps / 100))
            
            # 综合评分 (0-100)
            weights = [0.4, 0.2, 0.2, 0.2]  # 权重
            total_score = 100 * np.average([
                latency_score,
                jitter_score,
                loss_score,
                continuity_score
            ], weights=weights)
            
            return total_score
            
        except Exception as e:
            self.logger.error(f"计算数据质量分数失败: {str(e)}")
            return 0
            
    async def _handle_price_anomaly(self, symbol: str, price: float, mean: float, std: float):
        """处理价格异常"""
        try:
            anomaly_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'price': price,
                'mean': mean,
                'std': std,
                'deviation': abs(price - mean) / std
            }
            
            self.logger.warning(f"检测到价格异常: {anomaly_data}")
            
            # 这里可以添加告警逻辑
            
        except Exception as e:
            self.logger.error(f"处理价格异常失败: {str(e)}")
            
    # 数据更新接口
    def update_market_data(self, symbol: str, data: Dict):
        """更新市场数据"""
        try:
            # 更新价格历史
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.cache_size)
            self.price_history[symbol].append(data['price'])
            
            # 计算延迟
            latency = (datetime.now() - datetime.fromisoformat(data['timestamp'])).total_seconds()
            MARKET_LATENCY.observe(latency)
            
            if symbol not in self.latency_samples:
                self.latency_samples[symbol] = deque(maxlen=int(self.sample_window))
            self.latency_samples[symbol].append(latency)
            
            # 更新数据流量统计
            data_size = len(str(data))
            self.packet_stats['total_bytes'] += data_size
            DATA_FLOW.labels(direction='received').inc(data_size)
            
            # 更新符号指标
            if symbol not in self.symbol_metrics:
                self.symbol_metrics[symbol] = {
                    'packet_loss_rate': 0,
                    'price_gaps': 0,
                    'last_update': None
                }
                
            # 检查数据连续性
            last_update = self.symbol_metrics[symbol]['last_update']
            if last_update:
                time_gap = (datetime.fromisoformat(data['timestamp']) - last_update).total_seconds()
                if time_gap > self.config.get('max_gap', 1):
                    self.symbol_metrics[symbol]['price_gaps'] += 1
                    
            self.symbol_metrics[symbol]['last_update'] = datetime.fromisoformat(data['timestamp'])
            
        except Exception as e:
            self.logger.error(f"更新市场数据失败: {str(e)}")
            
    def record_packet_loss(self, symbol: str):
        """记录数据包丢失"""
        try:
            self.packet_stats['lost'] += 1
            
            if symbol in self.symbol_metrics:
                total_packets = self.packet_stats['received'] + self.packet_stats['lost']
                self.symbol_metrics[symbol]['packet_loss_rate'] = \
                    self.packet_stats['lost'] / total_packets if total_packets > 0 else 0
                    
        except Exception as e:
            self.logger.error(f"记录数据包丢失失败: {str(e)}")
            
    # 查询接口
    def get_market_metrics(self, symbol: str = None) -> Dict:
        """获取市场数据指标"""
        try:
            if symbol:
                return {
                    'latency': {
                        'current': np.mean(self.latency_samples.get(symbol, [])),
                        'threshold': self.latency_threshold
                    },
                    'quality': {
                        'score': self._calculate_quality_score(symbol),
                        'packet_loss_rate': self.symbol_metrics.get(symbol, {}).get('packet_loss_rate', 0),
                        'price_gaps': self.symbol_metrics.get(symbol, {}).get('price_gaps', 0)
                    },
                    'flow': {
                        'total_bytes': self.packet_stats['total_bytes']
                    }
                }
            else:
                return {
                    'total_symbols': len(self.price_history),
                    'total_packets': self.packet_stats['received'] + self.packet_stats['lost'],
                    'lost_packets': self.packet_stats['lost'],
                    'total_bytes': self.packet_stats['total_bytes']
                }
                
        except Exception as e:
            self.logger.error(f"获取市场数据指标失败: {str(e)}")
            return {}
            
    def get_symbol_status(self, symbol: str) -> str:
        """获取符号状态"""
        try:
            if symbol not in self.symbol_metrics:
                return 'unknown'
                
            quality_score = self._calculate_quality_score(symbol)
            
            if quality_score >= 90:
                return 'excellent'
            elif quality_score >= 80:
                return 'good'
            elif quality_score >= 60:
                return 'fair'
            else:
                return 'poor'
                
        except Exception as e:
            self.logger.error(f"获取符号状态失败: {str(e)}")
            return 'unknown'
            
    def get_data_quality_stats(self) -> Dict:
        """获取数据质量统计"""
        try:
            stats = {
                'symbols': len(self.symbol_metrics),
                'quality_distribution': {
                    'excellent': 0,
                    'good': 0,
                    'fair': 0,
                    'poor': 0
                },
                'avg_latency': 0,
                'total_anomalies': sum(
                    PRICE_ANOMALY.labels(symbol=symbol)._value.get()
                    for symbol in self.price_history
                )
            }
            
            # 计算质量分布
            for symbol in self.symbol_metrics:
                status = self.get_symbol_status(symbol)
                stats['quality_distribution'][status] += 1
                
            # 计算平均延迟
            all_latencies = []
            for samples in self.latency_samples.values():
                all_latencies.extend(samples)
            stats['avg_latency'] = np.mean(all_latencies) if all_latencies else 0
            
            return stats
            
        except Exception as e:
            self.logger.error(f"获取数据质量统计失败: {str(e)}")
            return {}