/**
 * FST Trading Platform - 设置页面脚本
 * 实现功能：
 * - 用户偏好设置
 * - 交易参数设置
 * - 风控规则配置
 * - 通知设置
 * - API设置
 */

// 设置视图应用
const settingsApp = new Vue({
    el: '#settings-app',
    delimiters: ['${', '}'],
    data() {
        return {
            // 基础数据
            loading: false,
            error: null,
            
            // 当前选中的设置选项卡
            activeTab: 'basic',
            
            // 设置数据
            settings: {
                // 基本设置
                basic: {
                    theme: 'auto',          // 主题：light 浅色, dark 深色, auto 自动
                    language: 'zh_CN',      // 语言
                    timezone: 'Asia/Shanghai', // 时区
                    dateFormat: 'YYYY-MM-DD', // 日期格式
                    timeFormat: 'HH:mm:ss',  // 时间格式
                    decimalPrecision: 8      // 价格精度
                },
                
                // 交易设置
                trading: {
                    defaultExchange: 'binance', // 默认交易所
                    defaultPair: 'BTC/USDT',   // 默认交易对
                    defaultOrderType: 'LIMIT',  // 默认订单类型
                    defaultTimeInForce: 'GTC',  // 默认有效期
                    priceIncrement: 0.1,        // 价格递增/递减比例
                    quantityIncrement: 0.1,     // 数量递增/递减比例
                    confirmOrder: true,          // 下单前确认
                    showOrderResult: true,       // 显示下单结果
                    keepOrderHistory: 30         // 保留订单历史天数
                },
                
                // 风控设置
                riskManagement: {
                    enabled: true,              // 启用风控
                    maxOrderAmount: 1000,       // 单笔订单最大金额
                    dailyLimit: 10000,          // 日交易限额
                    tradeFrequencyLimit: 100,   // 交易频率限制(次/分钟)
                    priceDeviationLimit: 5,     // 价格偏离限制(%)
                    stopLossPercent: 10,        // 默认止损比例(%)
                    takeProfitPercent: 20,      // 默认止盈比例(%)
                    maxLeverage: 5              // 最大杠杆倍数
                },
                
                // 通知设置
                notifications: {
                    orderCreated: true,         // 订单创建通知
                    orderFilled: true,          // 订单成交通知
                    orderCancelled: true,       // 订单取消通知
                    tradeExecuted: true,        // 交易执行通知
                    priceAlert: true,           // 价格提醒
                    emailNotifications: false,  // 邮件通知
                    emailAddress: '',           // 邮箱地址
                    pushNotifications: false,   // 推送通知
                    desktopNotifications: true, // 桌面通知
                    soundAlerts: true           // 声音提醒
                },
                
                // API设置
                api: {
                    exchanges: [
                        {
                            name: 'binance',
                            apiKey: '',
                            secretKey: '',
                            enabled: false
                        },
                        {
                            name: 'huobi',
                            apiKey: '',
                            secretKey: '',
                            enabled: false
                        },
                        {
                            name: 'okex',
                            apiKey: '',
                            secretKey: '',
                            passphrase: '',
                            enabled: false
                        }
                    ]
                }
            },
            
            // 原始设置（用于检测变更）
            originalSettings: null,
            
            // 已保存的设置（用于重置）
            savedSettings: null,
            
            // 表单验证错误
            validationErrors: {},
            
            // 可用选项
            options: {
                themes: [
                    { value: 'light', label: '浅色主题' },
                    { value: 'dark', label: '深色主题' },
                    { value: 'auto', label: '自动（跟随系统）' }
                ],
                languages: [
                    { value: 'zh_CN', label: '简体中文' },
                    { value: 'en_US', label: 'English' }
                ],
                timezones: [
                    { value: 'Asia/Shanghai', label: '中国标准时间 (UTC+8)' },
                    { value: 'America/New_York', label: '美国东部时间' },
                    { value: 'Europe/London', label: '伦敦时间' },
                    { value: 'UTC', label: '协调世界时 (UTC)' }
                ],
                exchanges: [
                    { value: 'binance', label: 'Binance' },
                    { value: 'huobi', label: 'Huobi' },
                    { value: 'okex', label: 'OKEx' }
                ],
                orderTypes: [
                    { value: 'LIMIT', label: '限价单' },
                    { value: 'MARKET', label: '市价单' },
                    { value: 'STOP', label: '止损单' }
                ],
                timeInForce: [
                    { value: 'GTC', label: '成交为止 (GTC)' },
                    { value: 'IOC', label: '立即成交否则取消 (IOC)' },
                    { value: 'FOK', label: '全部成交否则取消 (FOK)' }
                ]
            }
        };
    },
    
    computed: {
        // 设置是否有变更
        hasChanges() {
            return JSON.stringify(this.settings) !== JSON.stringify(this.originalSettings);
        },
        
        // 检查当前选项卡是否有错误
        hasErrors() {
            return Object.keys(this.validationErrors).some(key => {
                return key.startsWith(this.activeTab + '.');
            });
        },
        
        // 获取基本设置选项卡的错误
        basicErrors() {
            return this.getTabErrors('basic');
        },
        
        // 获取交易设置选项卡的错误
        tradingErrors() {
            return this.getTabErrors('trading');
        },
        
        // 获取风控设置选项卡的错误
        riskErrors() {
            return this.getTabErrors('riskManagement');
        },
        
        // 获取通知设置选项卡的错误
        notificationErrors() {
            return this.getTabErrors('notifications');
        },
        
        // 获取API设置选项卡的错误
        apiErrors() {
            return this.getTabErrors('api');
        }
    },
    
    methods: {
        // 获取指定选项卡的错误
        getTabErrors(tab) {
            const errors = {};
            Object.keys(this.validationErrors).forEach(key => {
                if (key.startsWith(tab + '.')) {
                    errors[key.substring(tab.length + 1)] = this.validationErrors[key];
                }
            });
            return errors;
        },
        
        // 切换设置选项卡
        switchTab(tab) {
            // 检查当前选项卡是否有未保存变更
            if (this.hasChanges) {
                if (confirm('您有未保存的更改。是否确定离开当前页面？')) {
                    this.activeTab = tab;
                }
            } else {
                this.activeTab = tab;
            }
        },
        
        // 加载设置
        async loadSettings() {
            try {
                this.loading = true;
                
                const response = await fetch('/api/account/settings');
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 合并默认设置和用户设置
                    for (const section in result.data) {
                        if (this.settings[section]) {
                            this.settings[section] = {
                                ...this.settings[section],
                                ...result.data[section]
                            };
                        }
                    }
                    
                    // 保存原始设置，用于比较变更
                    this.originalSettings = JSON.parse(JSON.stringify(this.settings));
                    this.savedSettings = JSON.parse(JSON.stringify(this.settings));
                    
                    // 应用主题设置
                    this.applyTheme(this.settings.basic.theme);
                } else {
                    this.showError('加载设置失败: ' + result.message);
                }
            } catch (error) {
                this.showError('加载设置失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 应用主题设置
        applyTheme(theme) {
            if (theme === 'dark') {
                document.documentElement.classList.add('dark');
            } else if (theme === 'light') {
                document.documentElement.classList.remove('dark');
            } else if (theme === 'auto') {
                // 根据系统偏好设置主题
                if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                    document.documentElement.classList.add('dark');
                } else {
                    document.documentElement.classList.remove('dark');
                }
                
                // 监听系统主题变化
                window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', event => {
                    if (this.settings.basic.theme === 'auto') {
                        if (event.matches) {
                            document.documentElement.classList.add('dark');
                        } else {
                            document.documentElement.classList.remove('dark');
                        }
                    }
                });
            }
        },
        
        // 验证设置
        validateSettings() {
            this.validationErrors = {};
            
            // 验证基本设置
            if (!this.settings.basic.language) {
                this.validationErrors['basic.language'] = '请选择语言';
            }
            
            if (!this.settings.basic.timezone) {
                this.validationErrors['basic.timezone'] = '请选择时区';
            }
            
            // 验证交易设置
            if (this.settings.trading.maxOrderAmount <= 0) {
                this.validationErrors['trading.maxOrderAmount'] = '单笔订单最大金额必须大于0';
            }
            
            // 验证风控设置
            if (this.settings.riskManagement.enabled) {
                if (this.settings.riskManagement.maxOrderAmount <= 0) {
                    this.validationErrors['riskManagement.maxOrderAmount'] = '单笔订单最大金额必须大于0';
                }
                
                if (this.settings.riskManagement.dailyLimit <= 0) {
                    this.validationErrors['riskManagement.dailyLimit'] = '日交易限额必须大于0';
                }
                
                if (this.settings.riskManagement.stopLossPercent <= 0 || this.settings.riskManagement.stopLossPercent >= 100) {
                    this.validationErrors['riskManagement.stopLossPercent'] = '止损比例必须在0-100%之间';
                }
                
                if (this.settings.riskManagement.takeProfitPercent <= 0 || this.settings.riskManagement.takeProfitPercent >= 100) {
                    this.validationErrors['riskManagement.takeProfitPercent'] = '止盈比例必须在0-100%之间';
                }
            }
            
            // 验证通知设置
            if (this.settings.notifications.emailNotifications && !this.validateEmail(this.settings.notifications.emailAddress)) {
                this.validationErrors['notifications.emailAddress'] = '请输入有效的邮箱地址';
            }
            
            // 返回验证结果
            return Object.keys(this.validationErrors).length === 0;
        },
        
        // 验证邮箱
        validateEmail(email) {
            const re = /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
            return re.test(String(email).toLowerCase());
        },
        
        // 保存设置
        async saveSettings() {
            // 验证设置
            if (!this.validateSettings()) {
                // 如果有错误，切换到错误所在的标签页
                for (const key in this.validationErrors) {
                    const tab = key.split('.')[0];
                    this.activeTab = tab;
                    break;
                }
                
                this.showError('设置验证失败，请检查输入');
                return;
            }
            
            try {
                this.loading = true;
                
                const response = await fetch('/api/account/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(this.settings)
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    // 更新原始设置
                    this.originalSettings = JSON.parse(JSON.stringify(this.settings));
                    this.savedSettings = JSON.parse(JSON.stringify(this.settings));
                    
                    // 应用主题设置
                    this.applyTheme(this.settings.basic.theme);
                    
                    // 显示成功消息
                    window.showSuccess('设置已保存');
                } else {
                    this.showError('保存设置失败: ' + result.message);
                }
            } catch (error) {
                this.showError('保存设置失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 重置设置
        resetSettings() {
            if (confirm('确定要重置所有设置吗？')) {
                this.settings = JSON.parse(JSON.stringify(this.savedSettings));
                
                // 清除验证错误
                this.validationErrors = {};
            }
        },
        
        // 重置为默认设置
        resetToDefaults() {
            if (confirm('确定要恢复默认设置吗？这将覆盖所有自定义设置。')) {
                // 重新加载页面以恢复默认设置
                location.reload();
            }
        },
        
        // 添加交易所设置
        addExchange() {
            this.settings.api.exchanges.push({
                name: '',
                apiKey: '',
                secretKey: '',
                enabled: false
            });
        },
        
        // 移除交易所设置
        removeExchange(index) {
            this.settings.api.exchanges.splice(index, 1);
        },
        
        // 测试API连接
        async testApiConnection(exchange) {
            if (!exchange.apiKey || !exchange.secretKey) {
                this.showError('请填写API密钥');
                return;
            }
            
            try {
                this.loading = true;
                
                const response = await fetch('/api/account/testConnection', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        exchange: exchange.name,
                        apiKey: exchange.apiKey,
                        secretKey: exchange.secretKey,
                        passphrase: exchange.passphrase
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    window.showSuccess(`${exchange.name} API连接测试成功`);
                } else {
                    this.showError(`${exchange.name} API连接测试失败: ${result.message}`);
                }
            } catch (error) {
                this.showError(`${exchange.name} API连接测试失败: ${error.message}`);
            } finally {
                this.loading = false;
            }
        },
        
        // 发送测试邮件
        async sendTestEmail() {
            if (!this.validateEmail(this.settings.notifications.emailAddress)) {
                this.showError('请输入有效的邮箱地址');
                return;
            }
            
            try {
                this.loading = true;
                
                const response = await fetch('/api/account/sendTestEmail', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: this.settings.notifications.emailAddress
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    window.showSuccess('测试邮件已发送');
                } else {
                    this.showError('发送测试邮件失败: ' + result.message);
                }
            } catch (error) {
                this.showError('发送测试邮件失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 测试桌面通知
        testDesktopNotification() {
            if (Notification.permission === 'granted') {
                new Notification('FST Trading Platform', {
                    body: '这是一条测试通知',
                    icon: '/static/images/logo.png'
                });
            } else if (Notification.permission !== 'denied') {
                Notification.requestPermission().then(permission => {
                    if (permission === 'granted') {
                        new Notification('FST Trading Platform', {
                            body: '这是一条测试通知',
                            icon: '/static/images/logo.png'
                        });
                    }
                });
            } else {
                this.showError('桌面通知被浏览器禁用');
            }
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
        }
    },
    
    watch: {
        // 监听主题设置变更
        'settings.basic.theme': function(newValue) {
            this.applyTheme(newValue);
        }
    },
    
    // 生命周期钩子
    mounted() {
        // 加载设置
        this.loadSettings();
        
        // 请求桌面通知权限
        if (this.settings.notifications.desktopNotifications && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }
});