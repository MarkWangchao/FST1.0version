/**
 * FST Trading Platform - 图表组件
 * 提供交易平台图表功能：
 * - K线图表
 * - 深度图表
 * - 技术指标
 */

class FSTChart {
    /**
     * 创建图表实例
     * @param {String} container 容器元素ID
     * @param {String} type 图表类型: 'kline' | 'depth'
     * @param {Object} options 配置选项
     */
    constructor(container, type = 'kline', options = {}) {
        this.container = document.getElementById(container);
        this.type = type;
        this.options = this._mergeOptions(options);
        this.chart = null;
        
        this._init();
    }
    
    /**
     * 初始化图表
     * @private
     */
    _init() {
        // 检查容器
        if (!this.container) {
            console.error('图表容器不存在');
            return;
        }
        
        // 设置容器样式
        this.container.style.height = this.options.height || '400px';
        this.container.style.width = this.options.width || '100%';
        
        // 创建ECharts实例
        // 注意：实际应用中应引入ECharts或TradingView等库
        this.chart = {
            setOption: function(option) {
                console.log('图表设置选项', option);
            },
            resize: function() {
                console.log('图表调整大小');
            },
            dispose: function() {
                console.log('图表销毁');
            }
        };
        
        // 初始化图表选项
        this._initChartOption();
        
        // 添加窗口调整大小事件
        window.addEventListener('resize', this._handleResize.bind(this));
    }
    
    /**
     * 合并默认选项和用户选项
     * @param {Object} options 用户选项
     * @returns {Object} 合并后的选项
     * @private
     */
    _mergeOptions(options) {
        const defaultOptions = {
            // 基本设置
            height: '400px',
            width: '100%',
            theme: 'dark', // 'light' | 'dark'
            
            // K线图设置
            kline: {
                interval: '1h',
                candlestick: {
                    upColor: '#53c41a',
                    upBorderColor: '#53c41a',
                    downColor: '#f5222d',
                    downBorderColor: '#f5222d'
                },
                indicators: {
                    MA: true,
                    BOLL: false,
                    MACD: false,
                    RSI: false,
                    KDJ: false
                },
                ma: [5, 10, 30, 60]
            },
            
            // 深度图设置
            depth: {
                bidColor: 'rgba(83, 196, 26, 0.8)',
                askColor: 'rgba(245, 34, 45, 0.8)',
                bidAreaColor: 'rgba(83, 196, 26, 0.2)',
                askAreaColor: 'rgba(245, 34, 45, 0.2)'
            },
            
            // 交互设置
            interaction: {
                zoomable: true,
                draggable: true,
                tooltip: true
            }
        };
        
        // 深度合并选项
        const merged = { ...defaultOptions };
        
        for (const key in options) {
            if (typeof options[key] === 'object' && options[key] !== null && !Array.isArray(options[key])) {
                merged[key] = { ...defaultOptions[key], ...options[key] };
            } else {
                merged[key] = options[key];
            }
        }
        
        return merged;
    }
    
    /**
     * 初始化图表选项
     * @private
     */
    _initChartOption() {
        // 根据图表类型设置不同的初始选项
        if (this.type === 'kline') {
            this._initKlineOptions();
        } else if (this.type === 'depth') {
            this._initDepthOptions();
        }
    }
    
    /**
     * 初始化K线图选项
     * @private
     */
    _initKlineOptions() {
        const option = {
            animation: false,
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                }
            },
            legend: {
                data: ['K线', '成交量']
            },
            grid: [
                {
                    left: '10%',
                    right: '10%',
                    top: '10%',
                    height: '60%'
                },
                {
                    left: '10%',
                    right: '10%',
                    top: '75%',
                    height: '15%'
                }
            ],
            xAxis: [
                {
                    type: 'category',
                    data: [],
                    boundaryGap: false,
                    axisLine: { onZero: false },
                    splitLine: { show: false },
                    min: 'dataMin',
                    max: 'dataMax'
                },
                {
                    type: 'category',
                    gridIndex: 1,
                    data: [],
                    boundaryGap: false,
                    axisLine: { onZero: false },
                    splitLine: { show: false },
                    min: 'dataMin',
                    max: 'dataMax'
                }
            ],
            yAxis: [
                {
                    scale: true,
                    splitArea: {
                        show: true
                    }
                },
                {
                    scale: true,
                    gridIndex: 1,
                    splitNumber: 2,
                    axisLabel: { show: false },
                    axisLine: { show: false },
                    axisTick: { show: false },
                    splitLine: { show: false }
                }
            ],
            dataZoom: [
                {
                    type: 'inside',
                    xAxisIndex: [0, 1],
                    start: 0,
                    end: 100
                },
                {
                    show: true,
                    xAxisIndex: [0, 1],
                    type: 'slider',
                    top: '92%',
                    start: 0,
                    end: 100
                }
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: [],
                    itemStyle: {
                        color: this.options.kline.candlestick.upColor,
                        color0: this.options.kline.candlestick.downColor,
                        borderColor: this.options.kline.candlestick.upBorderColor,
                        borderColor0: this.options.kline.candlestick.downBorderColor
                    }
                },
                {
                    name: '成交量',
                    type: 'bar',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: []
                }
            ]
        };
        
        // 设置图表选项
        this.chart.setOption(option);
    }
    
    /**
     * 初始化深度图选项
     * @private
     */
    _initDepthOptions() {
        const option = {
            animation: false,
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                },
                formatter: function(params) {
                    const price = params[0].data[0];
                    const bid = params[0].data[1] || 0;
                    const ask = params[1] ? params[1].data[1] || 0 : 0;
                    return `价格: ${price}<br>买盘: ${bid}<br>卖盘: ${ask}`;
                }
            },
            grid: {
                left: '10%',
                right: '10%',
                top: '10%',
                bottom: '15%'
            },
            xAxis: {
                type: 'value',
                scale: true,
                name: '价格',
                nameGap: 30,
                nameLocation: 'middle',
                min: 'dataMin',
                max: 'dataMax',
                axisLabel: {
                    formatter: function(value) {
                        return value.toFixed(8).replace(/\.?0+$/, '');
                    }
                }
            },
            yAxis: {
                type: 'value',
                scale: true,
                name: '数量',
                nameGap: 30
            },
            series: [
                {
                    name: '买盘',
                    type: 'line',
                    step: 'start',
                    data: [],
                    lineStyle: {
                        color: this.options.depth.bidColor
                    },
                    areaStyle: {
                        color: this.options.depth.bidAreaColor
                    },
                    symbol: 'none'
                },
                {
                    name: '卖盘',
                    type: 'line',
                    step: 'start',
                    data: [],
                    lineStyle: {
                        color: this.options.depth.askColor
                    },
                    areaStyle: {
                        color: this.options.depth.askAreaColor
                    },
                    symbol: 'none'
                }
            ]
        };
        
        // 设置图表选项
        this.chart.setOption(option);
    }
    
    /**
     * 处理窗口大小变化
     * @private
     */
    _handleResize() {
        if (this.chart) {
            this.chart.resize();
        }
    }
    
    /**
     * 更新K线数据
     * @param {Array} data K线数据数组，格式为 [[timestamp, open, high, low, close, volume], ...]
     */
    updateKlineData(data) {
        if (this.type !== 'kline' || !this.chart) {
            console.error('图表类型不是K线图或图表未初始化');
            return;
        }
        
        // 处理数据
        const klineData = [];
        const volumeData = [];
        const categoryData = [];
        
        data.forEach(item => {
            const date = new Date(item[0]);
            const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
            categoryData.push(dateStr);
            
            klineData.push([
                item[1], // open
                item[4], // close
                item[3], // low
                item[2]  // high
            ]);
            
            // 根据价格变化设置成交量颜色
            const color = item[4] >= item[1] ? this.options.kline.candlestick.upColor : this.options.kline.candlestick.downColor;
            
            volumeData.push({
                value: item[5],
                itemStyle: {
                    color: color
                }
            });
        });
        
        // 添加技术指标
        this._addIndicators(data);
        
        // 更新图表数据
        this.chart.setOption({
            xAxis: [
                {
                    data: categoryData
                },
                {
                    data: categoryData
                }
            ],
            series: [
                {
                    data: klineData
                },
                {
                    data: volumeData
                }
            ]
        });
    }
    
    /**
     * 添加技术指标
     * @param {Array} data K线数据
     * @private
     */
    _addIndicators(data) {
        const indicators = this.options.kline.indicators;
        
        // 添加MA
        if (indicators.MA) {
            this._addMA(data);
        }
        
        // 添加BOLL
        if (indicators.BOLL) {
            this._addBOLL(data);
        }
        
        // 添加MACD
        if (indicators.MACD) {
            this._addMACD(data);
        }
    }
    
    /**
     * 添加移动平均线指标
     * @param {Array} data K线数据
     * @private
     */
    _addMA(data) {
        // 此处仅为示例，需要根据实际情况计算MA值
        console.log('添加MA指标');
    }
    
    /**
     * 添加布林带指标
     * @param {Array} data K线数据
     * @private
     */
    _addBOLL(data) {
        // 此处仅为示例，需要根据实际情况计算BOLL值
        console.log('添加BOLL指标');
    }
    
    /**
     * 添加MACD指标
     * @param {Array} data K线数据
     * @private
     */
    _addMACD(data) {
        // 此处仅为示例，需要根据实际情况计算MACD值
        console.log('添加MACD指标');
    }
    
    /**
     * 更新深度数据
     * @param {Object} data 深度数据，格式为 {bids: [[price, amount], ...], asks: [[price, amount], ...]}
     */
    updateDepthData(data) {
        if (this.type !== 'depth' || !this.chart) {
            console.error('图表类型不是深度图或图表未初始化');
            return;
        }
        
        // 处理买卖盘数据
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
        
        // 更新图表数据
        this.chart.setOption({
            series: [
                {
                    data: bidsCumulative
                },
                {
                    data: asksCumulative
                }
            ]
        });
    }
    
    /**
     * 设置图表主题
     * @param {String} theme 主题: 'light' | 'dark'
     */
    setTheme(theme) {
        this.options.theme = theme;
        
        // 实际应用中需要根据主题切换图表样式
        console.log('切换图表主题:', theme);
    }
    
    /**
     * 切换技术指标
     * @param {String} indicator 指标名称
     * @param {Boolean} enable 是否启用
     */
    toggleIndicator(indicator, enable) {
        if (this.type !== 'kline') {
            console.error('只有K线图支持技术指标');
            return;
        }
        
        this.options.kline.indicators[indicator] = enable;
        
        // 触发图表更新
        console.log('切换技术指标:', indicator, enable);
    }
    
    /**
     * 销毁图表实例
     */
    dispose() {
        if (this.chart) {
            this.chart.dispose();
            this.chart = null;
        }
        
        // 移除事件监听
        window.removeEventListener('resize', this._handleResize.bind(this));
        
        console.log('图表已销毁');
    }
}

// 导出图表类
window.FSTChart = FSTChart;