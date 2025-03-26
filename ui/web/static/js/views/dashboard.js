/**
 * FST Trading Platform - 仪表盘页面脚本
 * 实现功能：
 * - 资产概览和资产分布
 * - 市场摘要和热门交易对
 * - 近期交易活动
 * - 未完成订单跟踪
 * - 系统状态和性能监控
 * - 实时提醒和通知
 */

// 仪表盘视图应用
const dashboardApp = new Vue({
    el: '#dashboard-app',
    delimiters: ['${', '}'],
    data() {
        return {
            // 基础数据
            loading: {
                assets: false,
                markets: false,
                orders: false,
                trades: false,
                system: false
            },
            error: null,
            
            // 账户资产数据
            assets: {
                totalBalanceUSD: 0,
                totalBalanceBTC: 0,
                totalProfit: 0,
                profitPercent: 0,
                distribution: [],
                spotAssets: [],
                marginAssets: [],
                futuresAssets: []
            },
            
            // 市场摘要数据
            markets: {
                trendingPairs: [],
                topGainers: [],
                topLosers: [],
                watchlist: [],
                btcPrice: 0,
                ethPrice: 0,
                marketTrend: 'neutral' // up, down, neutral
            },
            
            // 账户活动
            activity: {
                openOrders: [],
                recentTrades: [],
                todayTradeCount: 0,
                todayTradeVolume: 0,
                todayProfit: 0
            },
            
            // 系统状态
            system: {
                status: 'normal', // normal, warning, critical
                cpu: 0,
                memory: 0,
                disk: 0,
                uptime: 0,
                activeBots: 0,
                pausedBots: 0,
                alerts: []
            },
            
            // 图表实例
            charts: {
                assetsPie: null,
                profitHistory: null,
                tradesChart: null
            },
            
            // 设置和偏好
            preferences: {
                timeframe: '24h', // 24h, 7d, 30d, all
                exchangeFilter: 'all',
                assetType: 'all', // spot, margin, futures
                refreshInterval: 60 // 秒
            },
            
            // 刷新计时器
            refreshTimer: null,
            lastRefresh: null
        };
    },
    
    computed: {
        // 资产涨跌样式
        profitStyle() {
            return {
                'text-success': this.assets.totalProfit > 0,
                'text-danger': this.assets.totalProfit < 0
            };
        },
        
        // 计算资产分布百分比
        assetDistribution() {
            return this.assets.distribution.map(item => {
                return {
                    ...item,
                    percent: (item.value / this.assets.totalBalanceUSD) * 100
                };
            });
        },
        
        // 格式化的上次刷新时间
        formattedLastRefresh() {
            if (!this.lastRefresh) return '未刷新';
            
            const now = new Date();
            const diff = Math.floor((now - this.lastRefresh) / 1000);
            
            if (diff < 60) {
                return `${diff}秒前`;
            } else if (diff < 3600) {
                return `${Math.floor(diff / 60)}分钟前`;
            } else {
                return `${Math.floor(diff / 3600)}小时前`;
            }
        },
        
        // 系统状态样式
        systemStatusStyle() {
            return {
                'bg-success': this.system.status === 'normal',
                'bg-warning': this.system.status === 'warning',
                'bg-danger': this.system.status === 'critical'
            };
        },
        
        // 过滤后的交易对观察列表
        filteredWatchlist() {
            if (this.preferences.exchangeFilter === 'all') {
                return this.markets.watchlist;
            }
            
            return this.markets.watchlist.filter(item => 
                item.exchange === this.preferences.exchangeFilter
            );
        },
        
        // 计算在所选时间范围内的收益
        timeframeProfit() {
            // 此处应返回所选时间范围内的收益数据
            // 实际应用中通常需要从后端获取特定时间范围的数据
            return 0;
        },
        
        // 计算用于监控的系统状态指标
        systemMetrics() {
            return [
                { name: 'CPU使用率', value: this.system.cpu, unit: '%', alert: this.system.cpu > 80 },
                { name: '内存使用率', value: this.system.memory, unit: '%', alert: this.system.memory > 80 },
                { name: '磁盘使用率', value: this.system.disk, unit: '%', alert: this.system.disk > 80 },
                { name: '已运行时间', value: this.formatUptime(this.system.uptime), unit: '', alert: false },
                { name: '活跃机器人', value: this.system.activeBots, unit: '', alert: false }
            ];
        }
    },
    
    methods: {
        // 格式化数字为货币格式
        formatCurrency(value, currency = 'USD', maximumFractionDigits = 2) {
            if (typeof value !== 'number') return '0.00';
            
            return new Intl.NumberFormat('zh-CN', {
                style: 'currency',
                currency: currency,
                maximumFractionDigits: maximumFractionDigits
            }).format(value);
        },
        
        // 格式化数字为百分比
        formatPercent(value) {
            if (typeof value !== 'number') return '0.00%';
            
            return new Intl.NumberFormat('zh-CN', {
                style: 'percent',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value / 100);
        },
        
        // 格式化运行时间
        formatUptime(seconds) {
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor((seconds % 86400) / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            
            let result = '';
            if (days > 0) result += `${days}天 `;
            if (hours > 0) result += `${hours}小时 `;
            result += `${minutes}分钟`;
            
            return result;
        },
        
        // 格式化时间戳
        formatTimestamp(timestamp) {
            const date = new Date(timestamp);
            return date.toLocaleString('zh-CN');
        },
        
        // 加载资产数据
        async loadAssets() {
            try {
                this.loading.assets = true;
                
                const response = await fetch('/api/account/assets');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.assets = result.data;
                    this.renderAssetDistributionChart();
                } else {
                    this.showError('加载资产数据失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载资产数据失败: ' + error.message);
            } finally {
                this.loading.assets = false;
            }
        },
        
        // 加载市场数据
        async loadMarkets() {
            try {
                this.loading.markets = true;
                
                const response = await fetch('/api/market/summary');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.markets = result.data;
                } else {
                    this.showError('加载市场数据失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载市场数据失败: ' + error.message);
            } finally {
                this.loading.markets = false;
            }
        },
        
        // 加载订单数据
        async loadOrders() {
            try {
                this.loading.orders = true;
                
                const response = await fetch('/api/trading/openOrders');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.activity.openOrders = result.data;
                } else {
                    this.showError('加载订单数据失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载订单数据失败: ' + error.message);
            } finally {
                this.loading.orders = false;
            }
        },
        
        // 加载交易数据
        async loadTrades() {
            try {
                this.loading.trades = true;
                
                const response = await fetch('/api/trading/recentTrades');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.activity.recentTrades = result.data.trades;
                    this.activity.todayTradeCount = result.data.todayCount;
                    this.activity.todayTradeVolume = result.data.todayVolume;
                    this.activity.todayProfit = result.data.todayProfit;
                    
                    this.renderTradesChart();
                } else {
                    this.showError('加载交易数据失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载交易数据失败: ' + error.message);
            } finally {
                this.loading.trades = false;
            }
        },
        
        // 加载系统状态
        async loadSystemStatus() {
            try {
                this.loading.system = true;
                
                const response = await fetch('/api/system/status');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.system = result.data;
                } else {
                    this.showError('加载系统状态失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载系统状态失败: ' + error.message);
            } finally {
                this.loading.system = false;
            }
        },
        
        // 刷新所有数据
        async refreshAll() {
            await Promise.all([
                this.loadAssets(),
                this.loadMarkets(),
                this.loadOrders(),
                this.loadTrades(),
                this.loadSystemStatus()
            ]);
            
            this.lastRefresh = new Date();
        },
        
        // 添加交易对到观察列表
        async addToWatchlist(symbol, exchange) {
            try {
                const response = await fetch('/api/account/watchlist', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        symbol,
                        exchange
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 更新观察列表
                    this.markets.watchlist.push(result.data);
                    window.showSuccess(`已将 ${symbol} 添加到观察列表`);
                } else {
                    this.showError('添加到观察列表失败: ' + result.message);
                }
            } catch (error) {
                this.showError('添加到观察列表失败: ' + error.message);
            }
        },
        
        // 从观察列表移除交易对
        async removeFromWatchlist(id) {
            try {
                const response = await fetch(`/api/account/watchlist/${id}`, {
                    method: 'DELETE'
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 更新观察列表
                    this.markets.watchlist = this.markets.watchlist.filter(item => item.id !== id);
                    window.showSuccess('已从观察列表移除');
                } else {
                    this.showError('从观察列表移除失败: ' + result.message);
                }
            } catch (error) {
                this.showError('从观察列表移除失败: ' + error.message);
            }
        },
        
        // 取消订单
        async cancelOrder(orderId, symbol, exchange) {
            if (!confirm(`确定要取消此订单吗？\n订单号: ${orderId}\n交易对: ${symbol}`)) {
                return;
            }
            
            try {
                const response = await fetch('/api/trading/order', {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        orderId,
                        symbol,
                        exchange
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 更新订单列表
                    this.activity.openOrders = this.activity.openOrders.filter(order => order.orderId !== orderId);
                    window.showSuccess('订单已取消');
                } else {
                    this.showError('取消订单失败: ' + result.message);
                }
            } catch (error) {
                this.showError('取消订单失败: ' + error.message);
            }
        },
        
        // 取消所有订单
        async cancelAllOrders() {
            if (!confirm('确定要取消所有未完成的订单吗？')) {
                return;
            }
            
            try {
                const response = await fetch('/api/trading/cancelAllOrders', {
                    method: 'DELETE'
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 更新订单列表
                    this.activity.openOrders = [];
                    window.showSuccess('所有订单已取消');
                } else {
                    this.showError('取消所有订单失败: ' + result.message);
                }
            } catch (error) {
                this.showError('取消所有订单失败: ' + error.message);
            }
        },
        
        // 设置时间范围
        setTimeframe(timeframe) {
            this.preferences.timeframe = timeframe;
            this.loadAssets();
            this.loadTrades();
        },
        
        // 设置交易所过滤器
        setExchangeFilter(exchange) {
            this.preferences.exchangeFilter = exchange;
        },
        
        // 设置资产类型
        setAssetType(type) {
            this.preferences.assetType = type;
            this.loadAssets();
        },
        
        // 渲染资产分布饼图
        renderAssetDistributionChart() {
            if (!this.assets.distribution || this.assets.distribution.length === 0) {
                return;
            }
            
            if (!document.getElementById('asset-distribution-chart')) {
                return;
            }
            
            // 销毁旧图表实例
            if (this.charts.assetsPie) {
                this.charts.assetsPie.dispose();
            }
            
            // 准备图表数据
            const chartData = this.assets.distribution.map(item => {
                return {
                    name: item.asset,
                    value: item.value
                };
            });
            
            // 创建饼图实例
            this.charts.assetsPie = echarts.init(document.getElementById('asset-distribution-chart'));
            
            // 设置图表选项
            const option = {
                tooltip: {
                    trigger: 'item',
                    formatter: '{a} <br/>{b}: {c} ({d}%)'
                },
                legend: {
                    orient: 'vertical',
                    right: 10,
                    top: 'center',
                    data: chartData.map(item => item.name)
                },
                series: [
                    {
                        name: '资产分布',
                        type: 'pie',
                        radius: ['50%', '70%'],
                        avoidLabelOverlap: false,
                        label: {
                            show: false,
                            position: 'center'
                        },
                        emphasis: {
                            label: {
                                show: true,
                                fontSize: '16',
                                fontWeight: 'bold'
                            }
                        },
                        labelLine: {
                            show: false
                        },
                        data: chartData
                    }
                ]
            };
            
            // 应用图表选项
            this.charts.assetsPie.setOption(option);
            
            // 响应窗口大小变化
            window.addEventListener('resize', () => {
                if (this.charts.assetsPie) {
                    this.charts.assetsPie.resize();
                }
            });
        },
        
        // 渲染交易图表
        renderTradesChart() {
            if (!this.activity.recentTrades || this.activity.recentTrades.length === 0) {
                return;
            }
            
            if (!document.getElementById('trades-chart')) {
                return;
            }
            
            // 销毁旧图表实例
            if (this.charts.tradesChart) {
                this.charts.tradesChart.dispose();
            }
            
            // 准备图表数据
            const dates = [];
            const buyVolumes = [];
            const sellVolumes = [];
            
            // 按日期分组并计算交易量
            const tradesByDate = {};
            
            this.activity.recentTrades.forEach(trade => {
                const date = new Date(trade.time).toLocaleDateString();
                
                if (!tradesByDate[date]) {
                    tradesByDate[date] = {
                        buyVolume: 0,
                        sellVolume: 0
                    };
                }
                
                if (trade.side === 'BUY') {
                    tradesByDate[date].buyVolume += trade.quoteQty;
                } else {
                    tradesByDate[date].sellVolume += trade.quoteQty;
                }
            });
            
            // 构建图表数据数组
            Object.keys(tradesByDate).sort().forEach(date => {
                dates.push(date);
                buyVolumes.push(tradesByDate[date].buyVolume);
                sellVolumes.push(tradesByDate[date].sellVolume);
            });
            
            // 创建图表实例
            this.charts.tradesChart = echarts.init(document.getElementById('trades-chart'));
            
            // 设置图表选项
            const option = {
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'shadow'
                    }
                },
                legend: {
                    data: ['买入', '卖出']
                },
                grid: {
                    left: '3%',
                    right: '4%',
                    bottom: '3%',
                    containLabel: true
                },
                xAxis: {
                    type: 'category',
                    data: dates
                },
                yAxis: {
                    type: 'value'
                },
                series: [
                    {
                        name: '买入',
                        type: 'bar',
                        stack: 'total',
                        data: buyVolumes,
                        itemStyle: {
                            color: '#4caf50'
                        }
                    },
                    {
                        name: '卖出',
                        type: 'bar',
                        stack: 'total',
                        data: sellVolumes,
                        itemStyle: {
                            color: '#f44336'
                        }
                    }
                ]
            };
            
            // 应用图表选项
            this.charts.tradesChart.setOption(option);
            
            // 响应窗口大小变化
            window.addEventListener('resize', () => {
                if (this.charts.tradesChart) {
                    this.charts.tradesChart.resize();
                }
            });
        },
        
        // 显示错误信息
        showError(message) {
            this.error = message;
            console.error(message);
            
            // 使用通知组件显示错误
            if (window.showNotification) {
                window.showNotification({
                    type: 'error',
                    message: message,
                    duration: 5000
                });
            }
        },
        
        // 初始化自动刷新
        setupAutoRefresh() {
            this.stopAutoRefresh(); // 清除之前的计时器
            
            // 设置新的刷新计时器
            this.refreshTimer = setInterval(() => {
                this.refreshAll();
            }, this.preferences.refreshInterval * 1000);
        },
        
        // 停止自动刷新
        stopAutoRefresh() {
            if (this.refreshTimer) {
                clearInterval(this.refreshTimer);
                this.refreshTimer = null;
            }
        },
        
        // 更改刷新间隔
        setRefreshInterval(seconds) {
            this.preferences.refreshInterval = seconds;
            this.setupAutoRefresh();
            
            // 保存到本地存储
            localStorage.setItem('dashboard.refreshInterval', seconds);
        }
    },
    
    // 生命周期钩子
    mounted() {
        // 从本地存储加载用户偏好
        const savedRefreshInterval = localStorage.getItem('dashboard.refreshInterval');
        if (savedRefreshInterval) {
            this.preferences.refreshInterval = parseInt(savedRefreshInterval);
        }
        
        // 加载所有数据
        this.refreshAll();
        
        // 设置自动刷新
        this.setupAutoRefresh();
    },
    
    // 组件销毁前清理
    beforeDestroy() {
        // 停止自动刷新
        this.stopAutoRefresh();
        
        // 销毁图表实例
        if (this.charts.assetsPie) {
            this.charts.assetsPie.dispose();
        }
        
        if (this.charts.profitHistory) {
            this.charts.profitHistory.dispose();
        }
        
        if (this.charts.tradesChart) {
            this.charts.tradesChart.dispose();
        }
    }
});