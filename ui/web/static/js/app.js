// 创建Vue应用实例
const app = Vue.createApp({
    data() {
        return {
            // 用户信息
            user: {
                id: null,
                username: '',
                email: '',
                avatar: ''
            },
            
            // 市场数据
            marketData: {
                symbols: [],
                prices: {},
                lastUpdate: null
            },
            
            // 账户信息
            account: {
                balance: 0,
                positions: [],
                orders: [],
                trades: []
            },
            
            // UI状态
            ui: {
                loading: false,
                theme: 'light',
                notifications: [],
                currentView: 'dashboard'
            }
        }
    },
    
    methods: {
        // WebSocket连接管理
        initWebSocket() {
            this.socket = io('/trading', {
                transports: ['websocket']
            });
            
            this.socket.on('connect', () => {
                console.log('WebSocket connected');
                this.subscribeToMarketData();
            });
            
            this.socket.on('disconnect', () => {
                console.log('WebSocket disconnected');
            });
            
            this.socket.on('market_data', this.handleMarketData);
            this.socket.on('account_update', this.handleAccountUpdate);
            this.socket.on('order_update', this.handleOrderUpdate);
            this.socket.on('trade_update', this.handleTradeUpdate);
            this.socket.on('error', this.handleError);
        },
        
        // 订阅市场数据
        subscribeToMarketData() {
            if (this.marketData.symbols.length > 0) {
                this.socket.emit('subscribe', {
                    symbols: this.marketData.symbols
                });
            }
        },
        
        // 处理市场数据更新
        handleMarketData(data) {
            this.marketData.prices = {
                ...this.marketData.prices,
                ...data.prices
            };
            this.marketData.lastUpdate = new Date();
        },
        
        // 处理账户更新
        handleAccountUpdate(data) {
            this.account = {
                ...this.account,
                ...data
            };
        },
        
        // 处理订单更新
        handleOrderUpdate(data) {
            const index = this.account.orders.findIndex(order => order.id === data.id);
            if (index !== -1) {
                this.account.orders.splice(index, 1, data);
            } else {
                this.account.orders.push(data);
            }
        },
        
        // 处理成交更新
        handleTradeUpdate(data) {
            this.account.trades.unshift(data);
        },
        
        // 错误处理
        handleError(error) {
            this.showNotification({
                type: 'error',
                message: error.message
            });
        },
        
        // 显示通知
        showNotification(notification) {
            this.ui.notifications.push({
                id: Date.now(),
                ...notification
            });
            
            // 3秒后自动移除通知
            setTimeout(() => {
                this.removeNotification(notification.id);
            }, 3000);
        },
        
        // 移除通知
        removeNotification(id) {
            const index = this.ui.notifications.findIndex(n => n.id === id);
            if (index !== -1) {
                this.ui.notifications.splice(index, 1);
            }
        },
        
        // 切换主题
        toggleTheme() {
            this.ui.theme = this.ui.theme === 'light' ? 'dark' : 'light';
            document.documentElement.classList.toggle('dark');
            localStorage.setItem('theme', this.ui.theme);
        },
        
        // 加载用户信息
        async loadUserInfo() {
            try {
                const response = await fetch('/api/user/info');
                const data = await response.json();
                this.user = data;
            } catch (error) {
                this.handleError({
                    message: '加载用户信息失败'
                });
            }
        },
        
        // 加载初始数据
        async loadInitialData() {
            this.ui.loading = true;
            try {
                await Promise.all([
                    this.loadUserInfo(),
                    this.loadMarketSymbols(),
                    this.loadAccountInfo()
                ]);
            } catch (error) {
                this.handleError({
                    message: '加载初始数据失败'
                });
            } finally {
                this.ui.loading = false;
            }
        },
        
        // 加载市场符号列表
        async loadMarketSymbols() {
            try {
                const response = await fetch('/api/market/symbols');
                const data = await response.json();
                this.marketData.symbols = data;
            } catch (error) {
                this.handleError({
                    message: '加载市场符号失败'
                });
            }
        },
        
        // 加载账户信息
        async loadAccountInfo() {
            try {
                const response = await fetch('/api/account/info');
                const data = await response.json();
                this.account = data;
            } catch (error) {
                this.handleError({
                    message: '加载账户信息失败'
                });
            }
        }
    },
    
    mounted() {
        // 初始化主题
        const savedTheme = localStorage.getItem('theme') || 'light';
        this.ui.theme = savedTheme;
        if (savedTheme === 'dark') {
            document.documentElement.classList.add('dark');
        }
        
        // 初始化WebSocket连接
        this.initWebSocket();
        
        // 加载初始数据
        this.loadInitialData();
    }
});

// 注册全局组件
app.component('loading-spinner', {
    template: `
        <div class="loading">
            <div class="loading-spinner"></div>
        </div>
    `
});

// 挂载应用
app.mount('#app');