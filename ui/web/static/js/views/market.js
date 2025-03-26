/**
 * FST Trading Platform - 市场行情页面脚本
 * 实现功能：
 * - 交易对列表加载
 * - 行情数据获取
 * - K线图表渲染
 * - 市场深度图渲染
 * - 最近成交记录展示
 * - 自选交易对管理
 */

// 市场视图应用
const marketApp = new Vue({
    el: '#market-app',
    delimiters: ['${', '}'],
    data() {
        return {
            // 基础数据
            loading: false,
            error: null,
            // 交易所和交易对
            selectedExchange: '',
            selectedSymbol: '',
            symbols: [],
            // 时间周期选择
            selectedInterval: '1h',
            intervals: [
                { label: '1m', value: '1m' },
                { label: '5m', value: '5m' },
                { label: '15m', value: '15m' },
                { label: '1h', value: '1h' },
                { label: '4h', value: '4h' },
                { label: '1d', value: '1d' },
                { label: '1w', value: '1w' },
            ],
            // 行情数据
            ticker: null,
            recentTrades: [],
            marketList: [],
            // 图表相关
            klineChart: null,
            depthChart: null,
            indicators: {
                MA: true,
                BOLL: false,
                MACD: false
            },
            // 市场分类
            activeCategory: 'usdt',
            favorites: []
        };
    },
    
    computed: {
        // 价格变化颜色样式
        priceChangeClass() {
            if (!this.ticker) return '';
            return this.ticker.priceChangePercent > 0 ? 'text-green-500' : 'text-red-500';
        },
        
        // 根据当前分类筛选市场列表
        filteredMarketList() {
            if (!this.marketList.length) return [];
            
            if (this.activeCategory === 'favorite') {
                return this.marketList.filter(item => this.isFavorite(item.symbol));
            }
            
            return this.marketList.filter(item => {
                const symbol = item.symbol.toLowerCase();
                return symbol.endsWith(this.activeCategory);
            });
        }
    },
    
    methods: {
        // 加载交易对列表
        async loadSymbols() {
            try {
                this.loading = true;
                
                const response = await fetch(`/api/market/symbols?exchange=${this.selectedExchange}`);
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.symbols = result.data;
                    
                    // 如果有交易对，但当前未选择，则选择第一个
                    if (this.symbols.length && !this.selectedSymbol) {
                        this.selectedSymbol = this.symbols[0];
                        this.changeSymbol();
                    }
                } else {
                    this.showError('加载交易对列表失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载交易对列表失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 切换交易对
        async changeSymbol() {
            if (!this.selectedSymbol) return;
            
            try {
                this.loading = true;
                
                // 并行加载多个数据
                await Promise.all([
                    this.loadTicker(),
                    this.loadKlines(),
                    this.loadDepth(),
                    this.loadRecentTrades()
                ]);
                
                // 更新URL
                const url = new URL(window.location);
                url.searchParams.set('symbol', this.selectedSymbol);
                window.history.pushState({}, '', url);
                
            } catch (error) {
                this.showError('加载交易对数据失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 加载行情数据
        async loadTicker() {
            const response = await fetch(`/api/market/ticker?symbol=${this.selectedSymbol}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.ticker = result.data;
            } else {
                throw new Error(result.message || '加载行情数据失败');
            }
        },
        
        // 加载K线数据并绘制图表
        async loadKlines() {
            const response = await fetch(`/api/market/klines?symbol=${this.selectedSymbol}&interval=${this.selectedInterval}&limit=200`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.renderKlineChart(result.data);
            } else {
                throw new Error(result.message || '加载K线数据失败');
            }
        },
        
        // 加载深度数据并绘制图表
        async loadDepth() {
            const response = await fetch(`/api/market/depth?symbol=${this.selectedSymbol}&limit=50`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.renderDepthChart(result.data);
            } else {
                throw new Error(result.message || '加载深度数据失败');
            }
        },
        
        // 加载最近成交记录
        async loadRecentTrades() {
            const response = await fetch(`/api/market/trades?symbol=${this.selectedSymbol}&limit=30`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.recentTrades = result.data;
            } else {
                throw new Error(result.message || '加载成交记录失败');
            }
        },
        
        // 加载市场列表
        async loadMarketList() {
            try {
                const response = await fetch(`/api/market/tickers?exchange=${this.selectedExchange}`);
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.marketList = result.data;
                } else {
                    this.showError('加载市场列表失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载市场列表失败: ' + error.message);
            }
        },
        
        // 设置时间周期
        setInterval(interval) {
            this.selectedInterval = interval;
            this.loadKlines();
        },
        
        // 设置市场分类
        setCategory(category) {
            this.activeCategory = category;
        },
        
        // 渲染K线图表
        renderKlineChart(data) {
            const chartDom = document.getElementById('kline-chart');
            
            // 如果使用echarts或其他图表库，这里是初始化逻辑
            if (!this.klineChart) {
                // 这里仅占位，实际应用中应使用echarts或tradingview等库
                this.klineChart = {
                    setOption: function(option) {
                        console.log('K线图表设置选项', option);
                    }
                };
            }
            
            // 准备数据
            const klineData = data.map(item => ({
                time: new Date(item[0]),
                open: parseFloat(item[1]),
                high: parseFloat(item[2]),
                low: parseFloat(item[3]),
                close: parseFloat(item[4]),
                volume: parseFloat(item[5])
            }));
            
            // 设置图表选项
            const option = {
                title: {
                    text: `${this.selectedSymbol} K线图 (${this.selectedInterval})`
                },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'cross'
                    }
                },
                legend: {
                    data: ['K线', '成交量']
                },
                grid: {
                    left: '10%',
                    right: '10%',
                    bottom: '15%'
                },
                xAxis: {
                    type: 'time',
                    boundaryGap: false
                },
                yAxis: [
                    {
                        type: 'value',
                        scale: true,
                        name: '价格',
                        splitArea: {
                            show: true
                        }
                    },
                    {
                        type: 'value',
                        scale: true,
                        name: '成交量',
                        splitArea: {
                            show: true
                        }
                    }
                ],
                series: [
                    {
                        name: 'K线',
                        type: 'candlestick',
                        data: klineData.map(item => [
                            item.time, 
                            item.open, 
                            item.close, 
                            item.low, 
                            item.high
                        ])
                    },
                    {
                        name: '成交量',
                        type: 'bar',
                        yAxisIndex: 1,
                        data: klineData.map(item => [
                            item.time,
                            item.volume
                        ])
                    }
                ]
            };
            
            // 如果启用了均线指标
            if (this.indicators.MA) {
                // 添加MA指标配置
            }
            
            // 如果启用了布林带指标
            if (this.indicators.BOLL) {
                // 添加BOLL指标配置
            }
            
            // 如果启用了MACD指标
            if (this.indicators.MACD) {
                // 添加MACD指标配置
            }
            
            this.klineChart.setOption(option);
        },
        
        // 渲染深度图表
        renderDepthChart(data) {
            const chartDom = document.getElementById('depth-chart');
            
            // 如果使用echarts或其他图表库，这里是初始化逻辑
            if (!this.depthChart) {
                // 这里仅占位，实际应用中应使用echarts或tradingview等库
                this.depthChart = {
                    setOption: function(option) {
                        console.log('深度图表设置选项', option);
                    }
                };
            }
            
            // 准备数据
            const bids = data.bids.map(item => [parseFloat(item[0]), parseFloat(item[1])]);
            const asks = data.asks.map(item => [parseFloat(item[0]), parseFloat(item[1])]);
            
            // 计算累计量
            const bidsCumulative = [];
            const asksCumulative = [];
            
            let bidTotal = 0;
            for (const bid of bids) {
                bidTotal += bid[1];
                bidsCumulative.push([bid[0], bidTotal]);
            }
            
            let askTotal = 0;
            for (const ask of asks) {
                askTotal += ask[1];
                asksCumulative.push([ask[0], askTotal]);
            }
            
            // 设置图表选项
            const option = {
                title: {
                    text: '市场深度'
                },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'cross'
                    },
                    formatter: function(params) {
                        const bid = params[0];
                        const ask = params[1];
                        return `价格: ${bid.data[0]}<br>数量: ${bid.data[1]}`;
                    }
                },
                legend: {
                    data: ['买单(Bid)', '卖单(Ask)']
                },
                grid: {
                    left: '10%',
                    right: '10%',
                    bottom: '15%'
                },
                xAxis: {
                    type: 'value',
                    scale: true,
                    name: '价格'
                },
                yAxis: {
                    type: 'value',
                    scale: true,
                    name: '累计数量'
                },
                series: [
                    {
                        name: '买单(Bid)',
                        type: 'line',
                        step: 'start',
                        data: bidsCumulative,
                        lineStyle: {
                            color: '#53c41a'
                        },
                        areaStyle: {
                            color: 'rgba(83, 196, 26, 0.2)'
                        }
                    },
                    {
                        name: '卖单(Ask)',
                        type: 'line',
                        step: 'start',
                        data: asksCumulative,
                        lineStyle: {
                            color: '#f5222d'
                        },
                        areaStyle: {
                            color: 'rgba(245, 34, 45, 0.2)'
                        }
                    }
                ]
            };
            
            this.depthChart.setOption(option);
        },
        
        // 切换指标
        toggleIndicator(indicator) {
            this.indicators[indicator] = !this.indicators[indicator];
            this.loadKlines();
        },
        
        // 添加/移除自选
        toggleFavorite(symbol) {
            const index = this.favorites.indexOf(symbol);
            if (index > -1) {
                this.favorites.splice(index, 1);
            } else {
                this.favorites.push(symbol);
            }
            
            // 保存到本地存储
            localStorage.setItem('fst-favorites', JSON.stringify(this.favorites));
        },
        
        // 检查是否在自选列表中
        isFavorite(symbol) {
            return this.favorites.includes(symbol);
        },
        
        // 跳转到交易页面
        goToTrade(symbol) {
            window.location.href = `/trading?symbol=${symbol}`;
        },
        
        // 获取价格变化样式
        getPriceChangeClass(item) {
            return parseFloat(item.priceChangePercent) > 0 ? 'text-green-500' : 'text-red-500';
        },
        
        // 格式化价格
        formatPrice(price) {
            return parseFloat(price).toFixed(8).replace(/\.?0+$/, '');
        },
        
        // 格式化价格变化
        formatPriceChange(change) {
            return parseFloat(change) >= 0 ? '+' + this.formatPrice(change) : this.formatPrice(change);
        },
        
        // 格式化百分比
        formatPercent(percent) {
            return parseFloat(percent).toFixed(2) + '%';
        },
        
        // 格式化成交量
        formatVolume(volume) {
            return parseFloat(volume).toLocaleString('zh-CN', { maximumFractionDigits: 6 });
        },
        
        // 格式化时间
        formatTime(timestamp) {
            const date = new Date(timestamp);
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
        
        // 初始化WebSocket连接
        initWebSocket() {
            // 连接WebSocket
            const socket = io('/market', {
                transports: ['websocket']
            });
            
            // 连接成功
            socket.on('connect', () => {
                console.log('行情WebSocket已连接');
                
                // 如果有选中的交易对，则订阅
                if (this.selectedSymbol) {
                    socket.emit('subscribe', {
                        symbol: this.selectedSymbol,
                        type: 'ticker',
                        interval: this.selectedInterval
                    });
                }
            });
            
            // 断开连接
            socket.on('disconnect', () => {
                console.log('行情WebSocket已断开');
            });
            
            // 接收行情更新
            socket.on('ticker', (data) => {
                if (data.symbol === this.selectedSymbol) {
                    this.ticker = data;
                }
                
                // 更新市场列表中的数据
                const index = this.marketList.findIndex(item => item.symbol === data.symbol);
                if (index > -1) {
                    this.$set(this.marketList, index, { ...this.marketList[index], ...data });
                }
            });
            
            // 接收K线数据更新
            socket.on('kline', (data) => {
                if (data.symbol === this.selectedSymbol && data.interval === this.selectedInterval) {
                    // 更新K线图表
                    this.loadKlines();
                }
            });
            
            // 接收深度数据更新
            socket.on('depth', (data) => {
                if (data.symbol === this.selectedSymbol) {
                    // 更新深度图表
                    this.renderDepthChart(data);
                }
            });
            
            // 接收成交记录更新
            socket.on('trade', (data) => {
                if (data.symbol === this.selectedSymbol) {
                    // 将新成交记录添加到列表开头
                    this.recentTrades.unshift(data);
                    // 限制最多显示30条
                    if (this.recentTrades.length > 30) {
                        this.recentTrades.pop();
                    }
                }
            });
            
            // 保存socket实例
            this.socket = socket;
        }
    },
    
    // 生命周期钩子
    mounted() {
        // 加载自选列表
        const storedFavorites = localStorage.getItem('fst-favorites');
        if (storedFavorites) {
            try {
                this.favorites = JSON.parse(storedFavorites);
            } catch (e) {
                console.error('解析自选列表失败', e);
                this.favorites = [];
            }
        }
        
        // 从URL参数中获取symbol
        const urlParams = new URLSearchParams(window.location.search);
        const symbol = urlParams.get('symbol');
        if (symbol) {
            this.selectedSymbol = symbol;
        }
        
        // 初始化数据
        this.loadSymbols();
        this.loadMarketList();
        
        // 初始化WebSocket
        this.initWebSocket();
        
        // 设置自动刷新
        this.refreshInterval = setInterval(() => {
            this.loadMarketList();
        }, 30000); // 每30秒刷新一次市场列表
    },
    
    beforeDestroy() {
        // 清除定时器
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        // 断开WebSocket连接
        if (this.socket) {
            this.socket.disconnect();
        }
    }
});