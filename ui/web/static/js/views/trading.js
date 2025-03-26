/**
 * FST Trading Platform - 交易页面脚本
 * 实现功能：
 * - 交易对选择
 * - 下单表单管理
 * - 订单提交和撤销
 * - 当前委托订单管理
 * - 成交记录展示
 * - 风控提示
 */

// 交易视图应用
const tradingApp = new Vue({
    el: '#trading-app',
    delimiters: ['${', '}'],
    data() {
        return {
            // 基础数据
            loading: false,
            error: null,
            
            // 交易所和交易对
            selectedExchange: 'binance',
            selectedSymbol: '',
            symbols: [],
            
            // 交易规则
            symbolInfo: null,  // 当前交易对信息
            
            // 账户信息
            account: {
                balance: 0,
                available: 0,
                positions: []
            },
            
            // 订单表单
            orderForm: {
                type: 'LIMIT',    // LIMIT 限价单, MARKET 市价单
                side: 'BUY',      // BUY 买入, SELL 卖出
                price: '',        // 价格
                quantity: '',     // 数量
                amount: '',       // 金额 (仅用于显示)
                stopPrice: '',    // 触发价 (用于止损止盈单)
                timeInForce: 'GTC' // GTC 成交为止, IOC 立即成交否则取消, FOK 全部成交否则取消
            },
            
            // 市场行情数据
            ticker: null,
            orderBook: {
                bids: [],  // 买单
                asks: []   // 卖单
            },
            recentTrades: [],
            
            // 用户订单
            activeOrders: [],  // 当前活跃订单
            orderHistory: [],  // 历史订单
            tradeHistory: [],  // 成交记录
            
            // UI状态
            tabs: {
                orderType: 'limit',  // limit 限价单, market 市价单, stop 止损单
                orderList: 'active'  // active 活跃订单, history 历史订单
            },
            
            // WebSocket连接
            socket: null
        };
    },
    
    computed: {
        // 当前余额展示
        currentBalance() {
            const coin = this.selectedSymbol ? this.selectedSymbol.split('/')[1] : '';
            const balance = this.account.available || 0;
            return `${this.formatNumber(balance)} ${coin}`;
        },
        
        // 价格变化样式
        priceChangeClass() {
            if (!this.ticker) return '';
            return this.ticker.priceChangePercent > 0 ? 'text-green-500' : 'text-red-500';
        },
        
        // 计算交易金额
        orderAmount() {
            if (this.orderForm.type === 'MARKET' && this.orderForm.side === 'BUY') {
                return this.orderForm.amount;
            }
            
            const price = parseFloat(this.orderForm.price) || 0;
            const quantity = parseFloat(this.orderForm.quantity) || 0;
            return (price * quantity).toFixed(8);
        },
        
        // 订单是否有效
        isOrderValid() {
            // 检查交易对是否选择
            if (!this.selectedSymbol) return false;
            
            // 限价单必须填写价格
            if (this.orderForm.type === 'LIMIT' && !this.orderForm.price) return false;
            
            // 必须填写数量
            if (!this.orderForm.quantity) return false;
            
            // 止损止盈单必须填写触发价
            if (this.orderForm.type === 'STOP' && !this.orderForm.stopPrice) return false;
            
            return true;
        },
        
        // 获取买卖方向文本
        sideText() {
            return this.orderForm.side === 'BUY' ? '买入' : '卖出';
        },
        
        // 获取订单类型文本
        typeText() {
            switch(this.orderForm.type) {
                case 'LIMIT': return '限价单';
                case 'MARKET': return '市价单';
                case 'STOP': return '止损单';
                default: return this.orderForm.type;
            }
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
                    this.loadSymbolInfo(),
                    this.loadTicker(),
                    this.loadOrderBook(),
                    this.loadRecentTrades(),
                    this.loadActiveOrders()
                ]);
                
                // 更新URL
                const url = new URL(window.location);
                url.searchParams.set('symbol', this.selectedSymbol);
                window.history.pushState({}, '', url);
                
                // 重置订单表单
                this.resetOrderForm();
                
            } catch (error) {
                this.showError('加载交易对数据失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 加载交易对信息
        async loadSymbolInfo() {
            const response = await fetch(`/api/trading/exchangeInformation?exchange=${this.selectedExchange}&symbol=${this.selectedSymbol}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.symbolInfo = result.data;
            } else {
                throw new Error(result.message || '加载交易对信息失败');
            }
        },
        
        // 加载行情数据
        async loadTicker() {
            const response = await fetch(`/api/market/ticker?symbol=${this.selectedSymbol}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.ticker = result.data;
                
                // 如果是限价单并且价格为空，使用当前价格
                if (this.orderForm.type === 'LIMIT' && !this.orderForm.price && this.ticker.price) {
                    this.orderForm.price = this.ticker.price.toString();
                }
            } else {
                throw new Error(result.message || '加载行情数据失败');
            }
        },
        
        // 加载订单簿
        async loadOrderBook() {
            const response = await fetch(`/api/market/depth?symbol=${this.selectedSymbol}&limit=20`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.orderBook = result.data;
                
                // 初始化订单簿组件
                if (window.FSTOrderBook && document.getElementById('order-book')) {
                    const orderBookComponent = new FSTOrderBook('order-book', {
                        bids: this.orderBook.bids,
                        asks: this.orderBook.asks,
                        precision: this.symbolInfo ? this.symbolInfo.pricePrecision : 8,
                        theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light'
                    });
                    
                    // 设置点击处理函数
                    orderBookComponent.onPriceClick = (price) => {
                        this.orderForm.price = price.toString();
                    };
                }
            } else {
                throw new Error(result.message || '加载订单簿失败');
            }
        },
        
        // 加载最近成交
        async loadRecentTrades() {
            const response = await fetch(`/api/market/trades?symbol=${this.selectedSymbol}&limit=20`);
            const result = await response.json();
            
            if (result.status === 'success') {
                this.recentTrades = result.data;
                
                // 初始化交易历史组件
                if (window.FSTTradeHistory && document.getElementById('market-trades')) {
                    new FSTTradeHistory('market-trades', {
                        trades: this.recentTrades,
                        precision: this.symbolInfo ? this.symbolInfo.pricePrecision : 8
                    });
                }
            } else {
                throw new Error(result.message || '加载成交记录失败');
            }
        },
        
        // 加载账户信息
        async loadAccountInfo() {
            try {
                const response = await fetch('/api/account/info');
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.account = result.data;
                } else {
                    this.showError('加载账户信息失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载账户信息失败: ' + error.message);
            }
        },
        
        // 加载活跃订单
        async loadActiveOrders() {
            try {
                const response = await fetch(`/api/trading/openOrders?symbol=${this.selectedSymbol}`);
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.activeOrders = result.data;
                } else {
                    this.showError('加载活跃订单失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载活跃订单失败: ' + error.message);
            }
        },
        
        // 加载历史订单
        async loadOrderHistory() {
            try {
                this.loading = true;
                const response = await fetch(`/api/trading/allOrders?symbol=${this.selectedSymbol}&limit=50`);
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.orderHistory = result.data;
                } else {
                    this.showError('加载历史订单失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载历史订单失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 加载成交历史
        async loadTradeHistory() {
            try {
                this.loading = true;
                const response = await fetch(`/api/account/trades?symbol=${this.selectedSymbol}&limit=50`);
                const result = await response.json();
                
                if (result.status === 'success') {
                    this.tradeHistory = result.data;
                } else {
                    this.showError('加载成交历史失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载成交历史失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 设置交易方向
        setSide(side) {
            this.orderForm.side = side;
        },
        
        // 设置订单类型
        setOrderType(type) {
            this.tabs.orderType = type.toLowerCase();
            
            switch(type.toLowerCase()) {
                case 'limit':
                    this.orderForm.type = 'LIMIT';
                    break;
                case 'market':
                    this.orderForm.type = 'MARKET';
                    // 市价单不需要填写价格
                    this.orderForm.price = '';
                    break;
                case 'stop':
                    this.orderForm.type = 'STOP';
                    break;
            }
        },
        
        // 设置快速数量百分比
        setQuantityPercent(percent) {
            if (!this.account.available || !this.ticker) return;
            
            const available = parseFloat(this.account.available);
            const price = parseFloat(this.ticker.price);
            
            if (available <= 0 || price <= 0) return;
            
            let quantity = 0;
            if (this.orderForm.side === 'BUY') {
                // 买入: 可用资金 / 当前价格 * 百分比
                quantity = (available / price) * (percent / 100);
            } else {
                // 卖出: 直接用可用资产数量 * 百分比
                // 这里假设account.available已经是对应交易对的基础货币数量
                quantity = available * (percent / 100);
            }
            
            // 按照交易对精度处理数量
            const precision = this.symbolInfo ? this.symbolInfo.quantityPrecision : 8;
            this.orderForm.quantity = quantity.toFixed(precision);
            
            // 更新金额
            this.updateOrderAmount();
        },
        
        // 使用最优价格
        useMarketPrice() {
            if (!this.ticker) return;
            this.orderForm.price = this.ticker.price.toString();
            this.updateOrderAmount();
        },
        
        // 更新订单金额
        updateOrderAmount() {
            const price = parseFloat(this.orderForm.price) || 0;
            const quantity = parseFloat(this.orderForm.quantity) || 0;
            this.orderForm.amount = (price * quantity).toFixed(8);
        },
        
        // 重置订单表单
        resetOrderForm() {
            this.orderForm = {
                type: 'LIMIT',
                side: 'BUY',
                price: this.ticker ? this.ticker.price.toString() : '',
                quantity: '',
                amount: '',
                stopPrice: '',
                timeInForce: 'GTC'
            };
        },
        
        // 提交订单
        async submitOrder() {
            if (!this.isOrderValid) {
                this.showError('订单参数无效，请检查输入');
                return;
            }
            
            try {
                this.loading = true;
                
                // 构建订单数据
                const orderData = {
                    symbol: this.selectedSymbol,
                    type: this.orderForm.type,
                    side: this.orderForm.side,
                    quantity: this.orderForm.quantity
                };
                
                // 如果是限价单，添加价格
                if (this.orderForm.type === 'LIMIT') {
                    orderData.price = this.orderForm.price;
                    orderData.timeInForce = this.orderForm.timeInForce;
                }
                
                // 如果是止损单，添加触发价
                if (this.orderForm.type === 'STOP') {
                    orderData.stopPrice = this.orderForm.stopPrice;
                }
                
                // 发送风控检查请求
                const riskCheckResponse = await fetch('/api/trading/riskCheck', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(orderData)
                });
                
                const riskResult = await riskCheckResponse.json();
                
                // 如果风控检查不通过
                if (riskResult.status !== 'success' || !riskResult.data.passed) {
                    this.showError(`风控检查失败: ${riskResult.message || riskResult.data.reason}`);
                    return;
                }
                
                // 发送创建订单请求
                const response = await fetch('/api/trading/order', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(orderData)
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 显示成功消息
                    window.showSuccess(`${this.sideText}${this.typeText}提交成功`);
                    
                    // 重新加载活跃订单
                    this.loadActiveOrders();
                    
                    // 重置订单表单
                    this.resetOrderForm();
                    
                    // 重新加载账户信息
                    this.loadAccountInfo();
                } else {
                    this.showError('提交订单失败: ' + result.message);
                }
            } catch (error) {
                this.showError('提交订单失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 取消订单
        async cancelOrder(orderId) {
            try {
                this.loading = true;
                
                const response = await fetch('/api/trading/order', {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        symbol: this.selectedSymbol,
                        orderId: orderId
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 显示成功消息
                    window.showSuccess('订单取消成功');
                    
                    // 从活跃订单列表中移除
                    const index = this.activeOrders.findIndex(order => order.orderId === orderId);
                    if (index > -1) {
                        this.activeOrders.splice(index, 1);
                    }
                    
                    // 重新加载账户信息
                    this.loadAccountInfo();
                } else {
                    this.showError('取消订单失败: ' + result.message);
                }
            } catch (error) {
                this.showError('取消订单失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 切换订单列表标签
        switchOrderListTab(tab) {
            this.tabs.orderList = tab;
            
            if (tab === 'history' && this.orderHistory.length === 0) {
                this.loadOrderHistory();
            }
        },
        
        // 格式化日期时间
        formatDateTime(timestamp) {
            const date = new Date(timestamp);
            return date.toLocaleString('zh-CN');
        },
        
        // 格式化价格
        formatPrice(price) {
            if (!price) return '0';
            const precision = this.symbolInfo ? this.symbolInfo.pricePrecision : 8;
            return parseFloat(price).toFixed(precision).replace(/\.?0+$/, '');
        },
        
        // 格式化数量
        formatQuantity(quantity) {
            if (!quantity) return '0';
            const precision = this.symbolInfo ? this.symbolInfo.quantityPrecision : 8;
            return parseFloat(quantity).toFixed(precision).replace(/\.?0+$/, '');
        },
        
        // 格式化数字通用方法
        formatNumber(num, precision = 8) {
            if (!num) return '0';
            return parseFloat(num).toFixed(precision).replace(/\.?0+$/, '');
        },
        
        // 获取订单状态文本
        getOrderStatusText(status) {
            const statusMap = {
                NEW: '新建',
                PARTIALLY_FILLED: '部分成交',
                FILLED: '全部成交',
                CANCELED: '已取消',
                PENDING_CANCEL: '取消中',
                REJECTED: '已拒绝',
                EXPIRED: '已过期'
            };
            return statusMap[status] || status;
        },
        
        // 获取订单状态样式
        getOrderStatusClass(status) {
            const classMap = {
                NEW: 'text-blue-500',
                PARTIALLY_FILLED: 'text-yellow-500',
                FILLED: 'text-green-500',
                CANCELED: 'text-gray-500',
                PENDING_CANCEL: 'text-gray-500',
                REJECTED: 'text-red-500',
                EXPIRED: 'text-gray-500'
            };
            return classMap[status] || '';
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
            const socket = io('/trading', {
                transports: ['websocket']
            });
            
            // 连接成功
            socket.on('connect', () => {
                console.log('交易WebSocket已连接');
                
                // 如果有选中的交易对，则订阅
                if (this.selectedSymbol) {
                    socket.emit('subscribe', {
                        symbol: this.selectedSymbol,
                        type: 'orderUpdate'
                    });
                }
            });
            
            // 断开连接
            socket.on('disconnect', () => {
                console.log('交易WebSocket已断开');
            });
            
            // 接收订单更新
            socket.on('orderUpdate', (data) => {
                // 更新活跃订单列表
                const index = this.activeOrders.findIndex(order => order.orderId === data.orderId);
                if (data.status === 'FILLED' || data.status === 'CANCELED' || data.status === 'REJECTED' || data.status === 'EXPIRED') {
                    // 订单完成，从活跃列表中移除
                    if (index > -1) {
                        this.activeOrders.splice(index, 1);
                    }
                    
                    // 添加到历史订单列表
                    if (this.orderHistory.findIndex(order => order.orderId === data.orderId) === -1) {
                        this.orderHistory.unshift(data);
                    }
                    
                    // 显示通知
                    const statusText = this.getOrderStatusText(data.status);
                    window.showInfo(`订单状态更新: ${statusText}`);
                } else if (index > -1) {
                    // 更新现有订单
                    this.$set(this.activeOrders, index, { ...this.activeOrders[index], ...data });
                } else {
                    // 添加新订单
                    this.activeOrders.unshift(data);
                }
            });
            
            // 接收行情更新
            socket.on('ticker', (data) => {
                if (data.symbol === this.selectedSymbol) {
                    this.ticker = data;
                }
            });
            
            // 接收订单簿更新
            socket.on('depth', (data) => {
                if (data.symbol === this.selectedSymbol) {
                    this.orderBook = data;
                    
                    // 更新订单簿组件
                    if (window.FSTOrderBook && document.getElementById('order-book')) {
                        window.FSTOrderBook.update(data.bids, data.asks);
                    }
                }
            });
            
            // 接收成交记录更新
            socket.on('trade', (data) => {
                if (data.symbol === this.selectedSymbol) {
                    // 将新成交记录添加到列表开头
                    this.recentTrades.unshift(data);
                    // 限制最多显示20条
                    if (this.recentTrades.length > 20) {
                        this.recentTrades.pop();
                    }
                    
                    // 更新交易历史组件
                    if (window.FSTTradeHistory && document.getElementById('market-trades')) {
                        window.FSTTradeHistory.addTrade(data);
                    }
                }
            });
            
            // 接收账户更新
            socket.on('accountUpdate', (data) => {
                // 更新账户信息
                this.account = { ...this.account, ...data };
            });
            
            // 保存socket实例
            this.socket = socket;
        }
    },
    
    // 生命周期钩子
    mounted() {
        // 从URL参数中获取symbol
        const urlParams = new URLSearchParams(window.location.search);
        const symbol = urlParams.get('symbol');
        if (symbol) {
            this.selectedSymbol = symbol;
        }
        
        // 初始化数据
        this.loadSymbols();
        this.loadAccountInfo();
        
        // 初始化WebSocket
        this.initWebSocket();
        
        // 设置表单输入事件监听
        this.$watch('orderForm.price', this.updateOrderAmount);
        this.$watch('orderForm.quantity', this.updateOrderAmount);
    },
    
    beforeDestroy() {
        // 断开WebSocket连接
        if (this.socket) {
            this.socket.disconnect();
        }
    }
});