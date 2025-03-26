/**
 * FST Trading Platform - 订单簿组件
 * 实现功能：
 * - 买卖盘深度数据展示
 * - 价格和数量格式化
 * - 累计数量计算
 * - 实时数据更新
 * - 深度量可视化
 * - 价格点击交互
 */

class OrderBook {
    /**
     * 订单簿构造函数
     * @param {Object} options 配置选项
     */
    constructor(options = {}) {
        this.options = Object.assign({
            container: null,              // 容器元素或选择器
            maxRows: 15,                  // 最大行数
            pricePrecision: 8,            // 价格精度
            quantityPrecision: 8,         // 数量精度
            totalPrecision: 8,            // 累计数量精度
            percentPrecision: 2,          // 百分比精度
            baseAsset: '',                // 基础资产名称
            quoteAsset: '',               // 计价资产名称
            showChart: true,              // 是否显示深度图表
            showHeader: true,             // 是否显示头部
            priceChangeColors: true,      // 价格变化是否显示颜色
            theme: 'light',               // 主题：light 或 dark
            clickHandler: null            // 价格点击回调函数
        }, options);

        // 数据
        this.bids = [];          // 买单数据
        this.asks = [];          // 卖单数据
        this.lastUpdateId = 0;   // 最后更新ID
        
        // 统计信息
        this.spreadValue = 0;    // 买卖价差值
        this.spreadPercent = 0;  // 买卖价差百分比
        this.totalBidVolume = 0; // 总买单量
        this.totalAskVolume = 0; // 总卖单量
        
        // 元素引用
        this.container = null;
        this.bidsTable = null;
        this.asksTable = null;
        this.spreadElement = null;
        this.depthChart = null;
        
        // 初始化
        this._init();
    }
    
    /**
     * 初始化订单簿
     * @private
     */
    _init() {
        // 获取容器元素
        if (typeof this.options.container === 'string') {
            this.container = document.querySelector(this.options.container);
        } else if (this.options.container instanceof HTMLElement) {
            this.container = this.options.container;
        } else {
            throw new Error('必须提供有效的容器元素或选择器');
        }
        
        if (!this.container) {
            throw new Error('找不到容器元素');
        }
        
        // 设置容器样式
        this.container.classList.add('fst-orderbook');
        if (this.options.theme === 'dark') {
            this.container.classList.add('dark');
        }
        
        // 构建DOM结构
        this._buildDOM();
        
        // 应用初始数据
        this._render();
    }
    
    /**
     * 构建DOM结构
     * @private
     */
    _buildDOM() {
        // 清空容器
        this.container.innerHTML = '';
        
        // 创建主布局
        const layout = document.createElement('div');
        layout.className = 'orderbook-layout';
        
        // 创建头部（如果需要）
        if (this.options.showHeader) {
            const header = document.createElement('div');
            header.className = 'orderbook-header';
            
            const title = document.createElement('div');
            title.className = 'orderbook-title';
            title.textContent = '订单簿';
            
            const spreadInfo = document.createElement('div');
            spreadInfo.className = 'orderbook-spread';
            this.spreadElement = spreadInfo;
            
            header.appendChild(title);
            header.appendChild(spreadInfo);
            layout.appendChild(header);
        }
        
        // 创建卖单区域（倒序显示）
        const asksContainer = document.createElement('div');
        asksContainer.className = 'orderbook-asks-container';
        
        const asksTable = document.createElement('table');
        asksTable.className = 'orderbook-table asks';
        
        // 卖单表头
        const asksHeader = document.createElement('thead');
        const asksHeaderRow = document.createElement('tr');
        
        const asksTotalHeader = document.createElement('th');
        asksTotalHeader.className = 'total';
        asksTotalHeader.textContent = '累计(' + (this.options.baseAsset || '数量') + ')';
        
        const asksQuantityHeader = document.createElement('th');
        asksQuantityHeader.className = 'quantity';
        asksQuantityHeader.textContent = this.options.baseAsset || '数量';
        
        const asksPriceHeader = document.createElement('th');
        asksPriceHeader.className = 'price';
        asksPriceHeader.textContent = '价格(' + (this.options.quoteAsset || '') + ')';
        
        asksHeaderRow.appendChild(asksTotalHeader);
        asksHeaderRow.appendChild(asksQuantityHeader);
        asksHeaderRow.appendChild(asksPriceHeader);
        asksHeader.appendChild(asksHeaderRow);
        asksTable.appendChild(asksHeader);
        
        // 卖单表主体
        const asksBody = document.createElement('tbody');
        asksTable.appendChild(asksBody);
        asksContainer.appendChild(asksTable);
        layout.appendChild(asksContainer);
        
        this.asksTable = asksBody;
        
        // 中间分隔显示区域（显示最新价格等信息）
        const middleBar = document.createElement('div');
        middleBar.className = 'orderbook-middle';
        
        const lastPrice = document.createElement('div');
        lastPrice.className = 'last-price';
        lastPrice.innerHTML = '<span>最新价格: </span><span class="value">--</span>';
        this.lastPriceElement = lastPrice.querySelector('.value');
        
        middleBar.appendChild(lastPrice);
        layout.appendChild(middleBar);
        
        // 创建买单区域
        const bidsContainer = document.createElement('div');
        bidsContainer.className = 'orderbook-bids-container';
        
        const bidsTable = document.createElement('table');
        bidsTable.className = 'orderbook-table bids';
        
        // 买单表头
        const bidsHeader = document.createElement('thead');
        const bidsHeaderRow = document.createElement('tr');
        
        const bidsPriceHeader = document.createElement('th');
        bidsPriceHeader.className = 'price';
        bidsPriceHeader.textContent = '价格(' + (this.options.quoteAsset || '') + ')';
        
        const bidsQuantityHeader = document.createElement('th');
        bidsQuantityHeader.className = 'quantity';
        bidsQuantityHeader.textContent = this.options.baseAsset || '数量';
        
        const bidsTotalHeader = document.createElement('th');
        bidsTotalHeader.className = 'total';
        bidsTotalHeader.textContent = '累计(' + (this.options.baseAsset || '数量') + ')';
        
        bidsHeaderRow.appendChild(bidsPriceHeader);
        bidsHeaderRow.appendChild(bidsQuantityHeader);
        bidsHeaderRow.appendChild(bidsTotalHeader);
        bidsHeader.appendChild(bidsHeaderRow);
        bidsTable.appendChild(bidsHeader);
        
        // 买单表主体
        const bidsBody = document.createElement('tbody');
        bidsTable.appendChild(bidsBody);
        bidsContainer.appendChild(bidsTable);
        layout.appendChild(bidsContainer);
        
        this.bidsTable = bidsBody;
        
        // 如果启用了深度图表
        if (this.options.showChart) {
            const chartContainer = document.createElement('div');
            chartContainer.className = 'orderbook-depth-chart';
            chartContainer.id = 'orderbook-depth-chart';
            layout.appendChild(chartContainer);
            
            // 保存图表容器引用，后续用于初始化图表
            this.chartContainer = chartContainer;
        }
        
        // 将布局添加到容器
        this.container.appendChild(layout);
        
        // 添加事件处理
        this._attachEvents();
    }
    
    /**
     * 附加事件处理函数
     * @private
     */
    _attachEvents() {
        // 为价格单元格添加点击事件
        this.container.addEventListener('click', (event) => {
            const priceCell = event.target.closest('.price');
            if (priceCell && this.options.clickHandler) {
                const price = parseFloat(priceCell.dataset.price);
                const side = priceCell.closest('.bids') ? 'buy' : 'sell';
                this.options.clickHandler(price, side);
            }
        });
    }
    
    /**
     * 更新订单簿数据
     * @param {Object} data 包含bids和asks的数据对象
     */
    update(data) {
        if (!data) return;
        
        // 更新最后更新ID
        if (data.lastUpdateId && data.lastUpdateId > this.lastUpdateId) {
            this.lastUpdateId = data.lastUpdateId;
        }
        
        // 更新买单和卖单
        if (data.bids) {
            this.bids = this._processDepthData(data.bids, true);
        }
        
        if (data.asks) {
            this.asks = this._processDepthData(data.asks, false);
        }
        
        // 计算统计信息
        this._calculateStats();
        
        // 重新渲染
        this._render();
        
        // 更新深度图表
        if (this.options.showChart && this.chartContainer) {
            this._renderDepthChart();
        }
    }
    
    /**
     * 更新最新价格
     * @param {number} price 最新价格
     * @param {string} priceChangeType 价格变化类型 ('up', 'down', or null)
     */
    updateLastPrice(price, priceChangeType = null) {
        if (!this.lastPriceElement) return;
        
        const formattedPrice = this.formatPrice(price);
        this.lastPriceElement.textContent = formattedPrice;
        
        // 清除之前的类
        this.lastPriceElement.classList.remove('up', 'down');
        
        // 如果指定了价格变化类型，添加相应的类
        if (priceChangeType && this.options.priceChangeColors) {
            this.lastPriceElement.classList.add(priceChangeType);
        }
    }
    
    /**
     * 处理深度数据
     * @param {Array} data 深度数据数组
     * @param {boolean} isBids 是否为买单数据
     * @returns {Array} 处理后的数据
     * @private
     */
    _processDepthData(data, isBids) {
        if (!Array.isArray(data)) return [];
        
        // 转换为标准格式：[价格, 数量]
        const processed = data.map(item => {
            // 处理不同可能的数据格式
            let price, quantity;
            
            if (Array.isArray(item)) {
                [price, quantity] = item;
            } else if (typeof item === 'object') {
                price = item.price || item.p;
                quantity = item.quantity || item.q || item.amount || item.a;
            }
            
            return [parseFloat(price), parseFloat(quantity)];
        });
        
        // 过滤掉数量为0的条目
        const filtered = processed.filter(item => item[1] > 0);
        
        // 排序：买单降序，卖单升序
        const sorted = filtered.sort((a, b) => {
            return isBids ? b[0] - a[0] : a[0] - b[0];
        });
        
        // 限制行数
        return sorted.slice(0, this.options.maxRows);
    }
    
    /**
     * 计算统计信息
     * @private
     */
    _calculateStats() {
        // 计算买卖价差
        if (this.asks.length > 0 && this.bids.length > 0) {
            const lowestAsk = this.asks[0][0];
            const highestBid = this.bids[0][0];
            
            this.spreadValue = lowestAsk - highestBid;
            this.spreadPercent = (this.spreadValue / lowestAsk) * 100;
        } else {
            this.spreadValue = 0;
            this.spreadPercent = 0;
        }
        
        // 计算总买单量和总卖单量
        this.totalBidVolume = this.bids.reduce((sum, item) => sum + item[1], 0);
        this.totalAskVolume = this.asks.reduce((sum, item) => sum + item[1], 0);
        
        // 计算每行的累计数量
        let bidTotal = 0;
        this.bids = this.bids.map(item => {
            bidTotal += item[1];
            return [...item, bidTotal];
        });
        
        let askTotal = 0;
        this.asks = this.asks.map(item => {
            askTotal += item[1];
            return [...item, askTotal];
        });
    }
    
    /**
     * 渲染订单簿
     * @private
     */
    _render() {
        // 更新价差显示
        if (this.spreadElement) {
            this.spreadElement.textContent = `价差: ${this.formatPrice(this.spreadValue)} (${this.formatPercent(this.spreadPercent)})`;
        }
        
        // 渲染卖单（倒序）
        this._renderAsks();
        
        // 渲染买单
        this._renderBids();
    }
    
    /**
     * 渲染卖单
     * @private
     */
    _renderAsks() {
        if (!this.asksTable) return;
        
        // 清空当前内容
        this.asksTable.innerHTML = '';
        
        // 计算最大总量，用于背景宽度计算
        const maxTotal = this.asks.length > 0 ? this.asks[this.asks.length - 1][2] : 0;
        
        // 倒序渲染卖单（从高到低）
        const sortedAsks = [...this.asks].reverse();
        
        sortedAsks.forEach(ask => {
            const [price, quantity, total] = ask;
            
            const row = document.createElement('tr');
            
            // 累计列
            const totalCell = document.createElement('td');
            totalCell.className = 'total';
            totalCell.textContent = this.formatQuantity(total);
            
            // 背景条（可视化数量）
            const totalPercent = (total / maxTotal) * 100;
            const totalBg = document.createElement('div');
            totalBg.className = 'bg-bar';
            totalBg.style.width = `${totalPercent}%`;
            totalCell.appendChild(totalBg);
            
            // 数量列
            const quantityCell = document.createElement('td');
            quantityCell.className = 'quantity';
            quantityCell.textContent = this.formatQuantity(quantity);
            
            // 价格列
            const priceCell = document.createElement('td');
            priceCell.className = 'price';
            priceCell.textContent = this.formatPrice(price);
            priceCell.dataset.price = price;
            
            row.appendChild(totalCell);
            row.appendChild(quantityCell);
            row.appendChild(priceCell);
            
            this.asksTable.appendChild(row);
        });
    }
    
    /**
     * 渲染买单
     * @private
     */
    _renderBids() {
        if (!this.bidsTable) return;
        
        // 清空当前内容
        this.bidsTable.innerHTML = '';
        
        // 计算最大总量，用于背景宽度计算
        const maxTotal = this.bids.length > 0 ? this.bids[this.bids.length - 1][2] : 0;
        
        this.bids.forEach(bid => {
            const [price, quantity, total] = bid;
            
            const row = document.createElement('tr');
            
            // 价格列
            const priceCell = document.createElement('td');
            priceCell.className = 'price';
            priceCell.textContent = this.formatPrice(price);
            priceCell.dataset.price = price;
            
            // 数量列
            const quantityCell = document.createElement('td');
            quantityCell.className = 'quantity';
            quantityCell.textContent = this.formatQuantity(quantity);
            
            // 累计列
            const totalCell = document.createElement('td');
            totalCell.className = 'total';
            totalCell.textContent = this.formatQuantity(total);
            
            // 背景条（可视化数量）
            const totalPercent = (total / maxTotal) * 100;
            const totalBg = document.createElement('div');
            totalBg.className = 'bg-bar';
            totalBg.style.width = `${totalPercent}%`;
            totalCell.appendChild(totalBg);
            
            row.appendChild(priceCell);
            row.appendChild(quantityCell);
            row.appendChild(totalCell);
            
            this.bidsTable.appendChild(row);
        });
    }
    
    /**
     * 渲染深度图表
     * @private
     */
    _renderDepthChart() {
        // 如果存在全局图表对象并且有图表容器
        if (window.echarts && this.chartContainer) {
            // 如果图表实例不存在，创建新实例
            if (!this.depthChart) {
                this.depthChart = echarts.init(this.chartContainer);
            }
            
            // 准备数据
            const bidData = this.bids.map(item => [item[0], item[2]]);  // [价格, 累计量]
            const askData = this.asks.map(item => [item[0], item[2]]);  // [价格, 累计量]
            
            // 图表配置
            const option = {
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    formatter: (params) => {
                        const price = params[0].data[0];
                        const volume = params[0].data[1];
                        return `价格: ${this.formatPrice(price)}<br/>累计: ${this.formatQuantity(volume)}`;
                    }
                },
                grid: {
                    left: '3%',
                    right: '4%',
                    bottom: '3%',
                    top: '5%',
                    containLabel: true
                },
                xAxis: {
                    type: 'value',
                    scale: true,
                    splitLine: { show: false },
                    axisLine: { onZero: false },
                    axisLabel: {
                        formatter: (value) => this.formatPrice(value, 2)
                    }
                },
                yAxis: {
                    type: 'value',
                    scale: true,
                    splitLine: { show: false },
                    axisLabel: {
                        formatter: (value) => this.formatQuantity(value, 2)
                    }
                },
                series: [
                    {
                        name: '买单',
                        type: 'line',
                        step: 'end',
                        data: bidData.reverse(),  // 反转数据以正确排序
                        lineStyle: { color: '#4caf50' },
                        areaStyle: { 
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                { offset: 0, color: 'rgba(76, 175, 80, 0.5)' },
                                { offset: 1, color: 'rgba(76, 175, 80, 0.1)' }
                            ])
                        }
                    },
                    {
                        name: '卖单',
                        type: 'line',
                        step: 'start',
                        data: askData,
                        lineStyle: { color: '#f44336' },
                        areaStyle: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                { offset: 0, color: 'rgba(244, 67, 54, 0.5)' },
                                { offset: 1, color: 'rgba(244, 67, 54, 0.1)' }
                            ])
                        }
                    }
                ]
            };
            
            // 应用图表配置
            this.depthChart.setOption(option);
            
            // 响应窗口大小变化
            window.addEventListener('resize', () => {
                if (this.depthChart) {
                    this.depthChart.resize();
                }
            });
        }
    }
    
    /**
     * 格式化价格
     * @param {number} price 价格
     * @param {number} [precision] 精度（可选，默认使用配置）
     * @returns {string} 格式化的价格字符串
     */
    formatPrice(price, precision = this.options.pricePrecision) {
        if (typeof price !== 'number') return '0';
        return price.toFixed(precision);
    }
    
    /**
     * 格式化数量
     * @param {number} quantity 数量
     * @param {number} [precision] 精度（可选，默认使用配置）
     * @returns {string} 格式化的数量字符串
     */
    formatQuantity(quantity, precision = this.options.quantityPrecision) {
        if (typeof quantity !== 'number') return '0';
        return quantity.toFixed(precision);
    }
    
    /**
     * 格式化百分比
     * @param {number} percent 百分比值
     * @returns {string} 格式化的百分比字符串
     */
    formatPercent(percent) {
        if (typeof percent !== 'number') return '0%';
        return percent.toFixed(this.options.percentPrecision) + '%';
    }
    
    /**
     * 设置订单簿主题
     * @param {string} theme 主题名称 ('light' 或 'dark')
     */
    setTheme(theme) {
        if (theme === 'dark') {
            this.container.classList.add('dark');
        } else {
            this.container.classList.remove('dark');
        }
        
        this.options.theme = theme;
        
        // 如果有图表，也更新图表主题
        if (this.depthChart) {
            // 图表重新渲染
            this._renderDepthChart();
        }
    }
    
    /**
     * 更新配置选项
     * @param {Object} options 新配置
     */
    updateOptions(options) {
        this.options = Object.assign(this.options, options);
        
        // 重新构建DOM结构
        this._buildDOM();
        
        // 重新渲染数据
        this._render();
        
        // 如果启用图表，重新渲染图表
        if (this.options.showChart && this.chartContainer) {
            this._renderDepthChart();
        }
    }
    
    /**
     * 设置容器高度
     * @param {number|string} height 高度值（数字或CSS字符串）
     */
    setHeight(height) {
        if (typeof height === 'number') {
            this.container.style.height = `${height}px`;
        } else {
            this.container.style.height = height;
        }
        
        // 如果有图表，调整图表大小
        if (this.depthChart) {
            this.depthChart.resize();
        }
    }
    
    /**
     * 销毁订单簿组件
     */
    destroy() {
        // 移除事件监听器
        this.container.removeEventListener('click', this._clickHandler);
        
        // 销毁图表
        if (this.depthChart) {
            this.depthChart.dispose();
            this.depthChart = null;
        }
        
        // 清空容器
        this.container.innerHTML = '';
        
        // 移除类
        this.container.classList.remove('fst-orderbook', 'dark');
    }
}

// 导出订单簿组件
window.OrderBook = OrderBook;