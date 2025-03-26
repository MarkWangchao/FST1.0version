/**
 * FST Trading Platform - 交易历史组件
 * 实现功能：
 * - 近期交易记录展示
 * - 交易记录过滤和排序
 * - 分页和记录数量控制
 * - 实时数据更新
 * - 买卖方向和价格变化可视化
 */

class TradeHistory {
    /**
     * 交易历史构造函数
     * @param {Object} options 配置选项
     */
    constructor(options = {}) {
        this.options = Object.assign({
            container: null,              // 容器元素或选择器
            maxRows: 50,                  // 最大显示行数
            pageSize: 15,                 // 每页显示数量
            pricePrecision: 8,            // 价格精度
            quantityPrecision: 8,         // 数量精度
            amountPrecision: 2,           // 交易额精度
            baseAsset: '',                // 基础资产名称
            quoteAsset: '',               // 计价资产名称
            showHeader: true,             // 是否显示头部
            showPagination: true,         // 是否显示分页
            showFilters: true,            // 是否显示过滤器
            autoUpdate: true,             // 是否自动更新滚动
            priceChangeColors: true,      // 价格变化是否显示颜色
            theme: 'light',               // 主题：light 或 dark
            onRowClick: null,             // 行点击回调函数
            dateTimeFormat: 'YYYY-MM-DD HH:mm:ss'  // 日期时间格式
        }, options);

        // 交易历史数据
        this.trades = [];          // 所有交易记录
        this.filteredTrades = [];  // 过滤后的交易记录
        this.lastPrice = null;     // 上一次价格，用于判断价格变化方向
        
        // 状态
        this.currentPage = 1;      // 当前页码
        this.filter = {
            side: 'all',           // 交易方向过滤：'all', 'buy', 'sell'
            minAmount: null,       // 最小交易额
            maxAmount: null,       // 最大交易额
            timeRange: 'all'       // 时间范围：'all', 'today', 'yesterday', 'week', 'month'
        };
        this.sort = {
            field: 'time',         // 排序字段：'time', 'price', 'quantity', 'amount'
            direction: 'desc'      // 排序方向：'asc', 'desc'
        };
        
        // 元素引用
        this.container = null;
        this.tableBody = null;
        this.paginationElement = null;
        this.filterElement = null;
        
        // 初始化
        this._init();
    }
    
    /**
     * 初始化交易历史组件
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
        this.container.classList.add('fst-trade-history');
        if (this.options.theme === 'dark') {
            this.container.classList.add('dark');
        }
        
        // 构建DOM结构
        this._buildDOM();
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
        layout.className = 'trade-history-layout';
        
        // 创建头部（如果需要）
        if (this.options.showHeader) {
            const header = document.createElement('div');
            header.className = 'trade-history-header';
            
            const title = document.createElement('div');
            title.className = 'trade-history-title';
            title.textContent = '最近成交';
            
            header.appendChild(title);
            layout.appendChild(header);
        }
        
        // 创建过滤器（如果需要）
        if (this.options.showFilters) {
            const filters = document.createElement('div');
            filters.className = 'trade-history-filters';
            
            // 交易方向过滤
            const sideFilter = document.createElement('div');
            sideFilter.className = 'filter-group';
            
            const sideLabel = document.createElement('label');
            sideLabel.textContent = '方向:';
            
            const sideSelect = document.createElement('select');
            sideSelect.className = 'side-filter';
            
            const allOption = document.createElement('option');
            allOption.value = 'all';
            allOption.textContent = '全部';
            
            const buyOption = document.createElement('option');
            buyOption.value = 'buy';
            buyOption.textContent = '买入';
            
            const sellOption = document.createElement('option');
            sellOption.value = 'sell';
            sellOption.textContent = '卖出';
            
            sideSelect.appendChild(allOption);
            sideSelect.appendChild(buyOption);
            sideSelect.appendChild(sellOption);
            
            sideSelect.addEventListener('change', () => {
                this.filter.side = sideSelect.value;
                this._applyFilters();
            });
            
            sideFilter.appendChild(sideLabel);
            sideFilter.appendChild(sideSelect);
            
            // 时间范围过滤
            const timeFilter = document.createElement('div');
            timeFilter.className = 'filter-group';
            
            const timeLabel = document.createElement('label');
            timeLabel.textContent = '时间:';
            
            const timeSelect = document.createElement('select');
            timeSelect.className = 'time-filter';
            
            const timeAllOption = document.createElement('option');
            timeAllOption.value = 'all';
            timeAllOption.textContent = '全部';
            
            const todayOption = document.createElement('option');
            todayOption.value = 'today';
            todayOption.textContent = '今天';
            
            const yesterdayOption = document.createElement('option');
            yesterdayOption.value = 'yesterday';
            yesterdayOption.textContent = '昨天';
            
            const weekOption = document.createElement('option');
            weekOption.value = 'week';
            weekOption.textContent = '本周';
            
            const monthOption = document.createElement('option');
            monthOption.value = 'month';
            monthOption.textContent = '本月';
            
            timeSelect.appendChild(timeAllOption);
            timeSelect.appendChild(todayOption);
            timeSelect.appendChild(yesterdayOption);
            timeSelect.appendChild(weekOption);
            timeSelect.appendChild(monthOption);
            
            timeSelect.addEventListener('change', () => {
                this.filter.timeRange = timeSelect.value;
                this._applyFilters();
            });
            
            timeFilter.appendChild(timeLabel);
            timeFilter.appendChild(timeSelect);
            
            filters.appendChild(sideFilter);
            filters.appendChild(timeFilter);
            layout.appendChild(filters);
            
            this.filterElement = filters;
        }
        
        // 创建表格
        const tableContainer = document.createElement('div');
        tableContainer.className = 'trade-history-table-container';
        
        const table = document.createElement('table');
        table.className = 'trade-history-table';
        
        // 表头
        const tableHead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        
        const headers = [
            { name: '时间', field: 'time', className: 'time' },
            { name: '价格(' + (this.options.quoteAsset || '') + ')', field: 'price', className: 'price' },
            { name: '数量(' + (this.options.baseAsset || '') + ')', field: 'quantity', className: 'quantity' },
            { name: '交易额', field: 'amount', className: 'amount' }
        ];
        
        headers.forEach(header => {
            const th = document.createElement('th');
            th.className = header.className;
            th.textContent = header.name;
            th.dataset.field = header.field;
            
            // 添加排序事件
            th.addEventListener('click', () => {
                this._toggleSort(header.field);
            });
            
            // 添加排序指示器
            if (this.sort.field === header.field) {
                th.classList.add('sorted', this.sort.direction);
            }
            
            headerRow.appendChild(th);
        });
        
        tableHead.appendChild(headerRow);
        table.appendChild(tableHead);
        
        // 表体
        const tableBody = document.createElement('tbody');
        table.appendChild(tableBody);
        
        tableContainer.appendChild(table);
        layout.appendChild(tableContainer);
        
        this.tableBody = tableBody;
        
        // 创建分页（如果需要）
        if (this.options.showPagination) {
            const pagination = document.createElement('div');
            pagination.className = 'trade-history-pagination';
            
            const prevButton = document.createElement('button');
            prevButton.className = 'pagination-prev';
            prevButton.textContent = '上一页';
            prevButton.addEventListener('click', () => {
                if (this.currentPage > 1) {
                    this.currentPage--;
                    this._renderCurrentPage();
                }
            });
            
            const pageInfo = document.createElement('span');
            pageInfo.className = 'pagination-info';
            
            const nextButton = document.createElement('button');
            nextButton.className = 'pagination-next';
            nextButton.textContent = '下一页';
            nextButton.addEventListener('click', () => {
                const totalPages = Math.ceil(this.filteredTrades.length / this.options.pageSize);
                if (this.currentPage < totalPages) {
                    this.currentPage++;
                    this._renderCurrentPage();
                }
            });
            
            pagination.appendChild(prevButton);
            pagination.appendChild(pageInfo);
            pagination.appendChild(nextButton);
            
            layout.appendChild(pagination);
            
            this.paginationElement = {
                container: pagination,
                prevButton: prevButton,
                pageInfo: pageInfo,
                nextButton: nextButton
            };
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
        // 为表格行添加点击事件
        if (this.options.onRowClick) {
            this.tableBody.addEventListener('click', (event) => {
                const row = event.target.closest('tr');
                if (row) {
                    const index = parseInt(row.dataset.index, 10);
                    if (!isNaN(index) && index >= 0 && index < this.filteredTrades.length) {
                        const trade = this.filteredTrades[index];
                        this.options.onRowClick(trade);
                    }
                }
            });
        }
    }
    
    /**
     * 更新交易历史数据
     * @param {Array} trades 交易数据数组
     * @param {boolean} append 是否追加数据，默认为false（替换全部数据）
     */
    update(trades, append = false) {
        if (!Array.isArray(trades)) return;
        
        // 处理交易数据
        const processedTrades = trades.map(trade => {
            // 标准化交易对象格式
            const processed = {};
            
            // 时间
            processed.time = this._getTradeTime(trade);
            
            // 价格
            processed.price = this._getTradePrice(trade);
            
            // 数量
            processed.quantity = this._getTradeQuantity(trade);
            
            // 交易方向
            processed.side = this._getTradeSide(trade);
            
            // 交易额
            processed.amount = processed.price * processed.quantity;
            
            // 交易ID
            processed.id = trade.id || trade.tradeId || '';
            
            // 原始数据
            processed.raw = trade;
            
            return processed;
        });
        
        // 更新或追加数据
        if (append) {
            // 过滤掉已存在的交易记录（避免重复）
            const existingIds = new Set(this.trades.map(t => t.id));
            const newTrades = processedTrades.filter(trade => !existingIds.has(trade.id));
            
            // 将新交易添加到现有交易列表的前面（假设新交易是最近的）
            this.trades = [...newTrades, ...this.trades];
            
            // 限制记录数量
            if (this.trades.length > this.options.maxRows) {
                this.trades = this.trades.slice(0, this.options.maxRows);
            }
        } else {
            // 替换全部数据
            this.trades = processedTrades.slice(0, this.options.maxRows);
        }
        
        // 应用过滤和排序
        this._applyFilters();
    }
    
    /**
     * 添加单个交易记录
     * @param {Object} trade 交易数据
     */
    addTrade(trade) {
        if (!trade) return;
        
        // 处理交易数据
        const processed = {
            time: this._getTradeTime(trade),
            price: this._getTradePrice(trade),
            quantity: this._getTradeQuantity(trade),
            side: this._getTradeSide(trade),
            id: trade.id || trade.tradeId || '',
            raw: trade
        };
        
        // 计算交易额
        processed.amount = processed.price * processed.quantity;
        
        // 保存上一次价格，用于确定价格变化方向
        this.lastPrice = this.trades.length > 0 ? this.trades[0].price : null;
        
        // 添加到交易列表的开头
        this.trades.unshift(processed);
        
        // 限制记录数量
        if (this.trades.length > this.options.maxRows) {
            this.trades.pop();
        }
        
        // 应用过滤和排序
        this._applyFilters();
        
        // 如果启用了自动更新，且当前在第一页，则直接渲染新交易
        if (this.options.autoUpdate && this.currentPage === 1) {
            this._renderNewTrade(processed);
        }
    }
    
    /**
     * 应用过滤器并重新渲染
     * @private
     */
    _applyFilters() {
        // 应用过滤条件
        this.filteredTrades = this.trades.filter(trade => {
            // 交易方向过滤
            if (this.filter.side !== 'all' && trade.side !== this.filter.side) {
                return false;
            }
            
            // 交易额过滤
            if (this.filter.minAmount !== null && trade.amount < this.filter.minAmount) {
                return false;
            }
            
            if (this.filter.maxAmount !== null && trade.amount > this.filter.maxAmount) {
                return false;
            }
            
            // 时间范围过滤
            if (this.filter.timeRange !== 'all') {
                const tradeDate = new Date(trade.time);
                const now = new Date();
                
                // 调整时区为本地时区
                const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                const yesterday = new Date(today);
                yesterday.setDate(today.getDate() - 1);
                
                // 本周第一天（周日或周一，取决于地区）
                const firstDayOfWeek = new Date(today);
                firstDayOfWeek.setDate(today.getDate() - today.getDay());
                
                // 本月第一天
                const firstDayOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
                
                switch (this.filter.timeRange) {
                    case 'today':
                        if (tradeDate < today) return false;
                        break;
                    case 'yesterday':
                        if (tradeDate < yesterday || tradeDate >= today) return false;
                        break;
                    case 'week':
                        if (tradeDate < firstDayOfWeek) return false;
                        break;
                    case 'month':
                        if (tradeDate < firstDayOfMonth) return false;
                        break;
                }
            }
            
            return true;
        });
        
        // 应用排序
        this._applySort();
        
        // 重置到第一页
        this.currentPage = 1;
        
        // 重新渲染
        this._renderCurrentPage();
    }
    
    /**
     * 应用排序
     * @private
     */
    _applySort() {
        const { field, direction } = this.sort;
        
        this.filteredTrades.sort((a, b) => {
            let result;
            
            // 根据字段类型进行排序
            if (field === 'time') {
                result = new Date(a.time) - new Date(b.time);
            } else {
                result = a[field] - b[field];
            }
            
            // 应用排序方向
            return direction === 'asc' ? result : -result;
        });
    }
    
    /**
     * 切换排序
     * @param {string} field 排序字段
     * @private
     */
    _toggleSort(field) {
        if (this.sort.field === field) {
            // 如果是同一个字段，切换排序方向
            this.sort.direction = this.sort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            // 如果是新字段，默认为降序
            this.sort.field = field;
            this.sort.direction = 'desc';
        }
        
        // 更新表头排序指示器
        const headers = this.tableBody.parentNode.querySelectorAll('th');
        headers.forEach(th => {
            th.classList.remove('sorted', 'asc', 'desc');
            if (th.dataset.field === field) {
                th.classList.add('sorted', this.sort.direction);
            }
        });
        
        // 应用排序并重新渲染
        this._applySort();
        this._renderCurrentPage();
    }
    
    /**
     * 渲染当前页面的交易记录
     * @private
     */
    _renderCurrentPage() {
        if (!this.tableBody) return;
        
        // 清空当前内容
        this.tableBody.innerHTML = '';
        
        // 计算当前页的数据范围
        const startIndex = (this.currentPage - 1) * this.options.pageSize;
        const endIndex = Math.min(startIndex + this.options.pageSize, this.filteredTrades.length);
        
        // 获取当前页的交易记录
        const currentPageTrades = this.filteredTrades.slice(startIndex, endIndex);
        
        // 渲染每一行
        currentPageTrades.forEach((trade, index) => {
            const row = document.createElement('tr');
            row.className = `side-${trade.side}`;
            row.dataset.index = startIndex + index;
            
            // 时间列
            const timeCell = document.createElement('td');
            timeCell.className = 'time';
            timeCell.textContent = this._formatDateTime(trade.time);
            
            // 价格列
            const priceCell = document.createElement('td');
            priceCell.className = `price ${trade.side}`;
            priceCell.textContent = this.formatPrice(trade.price);
            
            // 数量列
            const quantityCell = document.createElement('td');
            quantityCell.className = 'quantity';
            quantityCell.textContent = this.formatQuantity(trade.quantity);
            
            // 交易额列
            const amountCell = document.createElement('td');
            amountCell.className = 'amount';
            amountCell.textContent = this.formatAmount(trade.amount);
            
            row.appendChild(timeCell);
            row.appendChild(priceCell);
            row.appendChild(quantityCell);
            row.appendChild(amountCell);
            
            this.tableBody.appendChild(row);
        });
        
        // 如果没有数据，显示空状态
        if (currentPageTrades.length === 0) {
            const emptyRow = document.createElement('tr');
            emptyRow.className = 'empty-row';
            
            const emptyCell = document.createElement('td');
            emptyCell.colSpan = 4;
            emptyCell.textContent = '暂无交易记录';
            
            emptyRow.appendChild(emptyCell);
            this.tableBody.appendChild(emptyRow);
        }
        
        // 更新分页信息
        this._updatePagination();
    }
    
    /**
     * 渲染新的交易记录（添加到顶部）
     * @param {Object} trade 交易数据
     * @private
     */
    _renderNewTrade(trade) {
        if (!this.tableBody || this.currentPage !== 1) return;
        
        // 移除最后一行（如果已经达到每页显示的最大数量）
        if (this.tableBody.children.length >= this.options.pageSize) {
            this.tableBody.removeChild(this.tableBody.lastChild);
        }
        
        // 创建新行
        const row = document.createElement('tr');
        row.className = `side-${trade.side}`;
        row.dataset.index = 0;  // 新交易总是索引0
        
        // 时间列
        const timeCell = document.createElement('td');
        timeCell.className = 'time';
        timeCell.textContent = this._formatDateTime(trade.time);
        
        // 价格列
        const priceCell = document.createElement('td');
        
        // 判断价格变化方向
        let priceChangeClass = '';
        if (this.lastPrice !== null && this.options.priceChangeColors) {
            priceChangeClass = trade.price > this.lastPrice ? 'price-up' : 
                              (trade.price < this.lastPrice ? 'price-down' : '');
        }
        
        priceCell.className = `price ${trade.side} ${priceChangeClass}`;
        priceCell.textContent = this.formatPrice(trade.price);
        
        // 数量列
        const quantityCell = document.createElement('td');
        quantityCell.className = 'quantity';
        quantityCell.textContent = this.formatQuantity(trade.quantity);
        
        // 交易额列
        const amountCell = document.createElement('td');
        amountCell.className = 'amount';
        amountCell.textContent = this.formatAmount(trade.amount);
        
        row.appendChild(timeCell);
        row.appendChild(priceCell);
        row.appendChild(quantityCell);
        row.appendChild(amountCell);
        
        // 添加到表格顶部
        if (this.tableBody.firstChild) {
            this.tableBody.insertBefore(row, this.tableBody.firstChild);
        } else {
            this.tableBody.appendChild(row);
        }
        
        // 添加新行的闪烁效果
        setTimeout(() => {
            row.classList.add('new-trade');
            setTimeout(() => {
                row.classList.remove('new-trade');
            }, 1000);
        }, 0);
        
        // 更新其他行的索引
        Array.from(this.tableBody.children).forEach((row, index) => {
            if (index > 0) {
                row.dataset.index = index;
            }
        });
        
        // 更新分页信息
        this._updatePagination();
    }
    
    /**
     * 更新分页信息
     * @private
     */
    _updatePagination() {
        if (!this.paginationElement) return;
        
        const { container, prevButton, pageInfo, nextButton } = this.paginationElement;
        
        // 计算总页数
        const totalPages = Math.ceil(this.filteredTrades.length / this.options.pageSize);
        
        // 更新页码信息
        pageInfo.textContent = `${this.currentPage} / ${totalPages || 1}`;
        
        // 更新按钮状态
        prevButton.disabled = this.currentPage <= 1;
        nextButton.disabled = this.currentPage >= totalPages;
        
        // 显示或隐藏分页
        container.style.display = totalPages > 1 ? 'flex' : 'none';
    }
    
    /**
     * 获取交易时间
     * @param {Object} trade 交易数据
     * @returns {Date|string} 交易时间
     * @private
     */
    _getTradeTime(trade) {
        // 尝试不同的属性名
        const timeValue = trade.time || trade.timestamp || trade.tradeTime || trade.date || Date.now();
        
        // 如果是数字，假设是时间戳（毫秒或秒）
        if (typeof timeValue === 'number') {
            // 区分毫秒和秒时间戳
            return timeValue > 9999999999 ? new Date(timeValue) : new Date(timeValue * 1000);
        }
        
        // 如果是字符串，尝试解析
        if (typeof timeValue === 'string') {
            return new Date(timeValue);
        }
        
        // 如果是Date对象，直接返回
        if (timeValue instanceof Date) {
            return timeValue;
        }
        
        // 默认返回当前时间
        return new Date();
    }
    
    /**
     * 获取交易价格
     * @param {Object} trade 交易数据
     * @returns {number} 交易价格
     * @private
     */
    _getTradePrice(trade) {
        const price = trade.price || trade.p;
        return typeof price === 'number' ? price : parseFloat(price);
    }
    
    /**
     * 获取交易数量
     * @param {Object} trade 交易数据
     * @returns {number} 交易数量
     * @private
     */
    _getTradeQuantity(trade) {
        const quantity = trade.quantity || trade.amount || trade.q || trade.a;
        return typeof quantity === 'number' ? quantity : parseFloat(quantity);
    }
    
    /**
     * 获取交易方向
     * @param {Object} trade 交易数据
     * @returns {string} 交易方向 ('buy' 或 'sell')
     * @private
     */
    _getTradeSide(trade) {
        // 尝试从不同属性名中获取交易方向
        const side = trade.side || trade.type || trade.direction || '';
        
        // 标准化交易方向
        const sideStr = String(side).toLowerCase();
        if (sideStr === 'buy' || sideStr === 'bid' || sideStr === 'b') {
            return 'buy';
        } else if (sideStr === 'sell' || sideStr === 'ask' || sideStr === 's') {
            return 'sell';
        }
        
        // 尝试从其他指标推断交易方向
        if (trade.isBuyerMaker === false || trade.isBuyer === true) {
            return 'buy';
        } else if (trade.isBuyerMaker === true || trade.isBuyer === false) {
            return 'sell';
        }
        
        // 如果无法确定，默认为买入
        return 'buy';
    }
    
    /**
     * 格式化日期时间
     * @param {Date|string|number} datetime 日期时间
     * @returns {string} 格式化的日期时间字符串
     * @private
     */
    _formatDateTime(datetime) {
        // 确保是Date对象
        const date = datetime instanceof Date ? datetime : new Date(datetime);
        
        // 根据指定格式渲染
        // 这里简化了实现，实际项目中可以使用dayjs或其他日期库
        const format = this.options.dateTimeFormat || 'YYYY-MM-DD HH:mm:ss';
        
        // 提取年月日时分秒
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        
        // 应用格式
        let formatted = format
            .replace('YYYY', year)
            .replace('MM', month)
            .replace('DD', day)
            .replace('HH', hours)
            .replace('mm', minutes)
            .replace('ss', seconds);
        
        return formatted;
    }
    
    /**
     * 格式化价格
     * @param {number} price 价格
     * @returns {string} 格式化的价格字符串
     */
    formatPrice(price) {
        if (typeof price !== 'number') return '0';
        return price.toFixed(this.options.pricePrecision);
    }
    
    /**
     * 格式化数量
     * @param {number} quantity 数量
     * @returns {string} 格式化的数量字符串
     */
    formatQuantity(quantity) {
        if (typeof quantity !== 'number') return '0';
        return quantity.toFixed(this.options.quantityPrecision);
    }
    
    /**
     * 格式化交易额
     * @param {number} amount 交易额
     * @returns {string} 格式化的交易额字符串
     */
    formatAmount(amount) {
        if (typeof amount !== 'number') return '0';
        return amount.toFixed(this.options.amountPrecision);
    }
    
    /**
     * 设置主题
     * @param {string} theme 主题名称 ('light' 或 'dark')
     */
    setTheme(theme) {
        if (theme === 'dark') {
            this.container.classList.add('dark');
        } else {
            this.container.classList.remove('dark');
        }
        
        this.options.theme = theme;
    }
    
    /**
     * 更新配置选项
     * @param {Object} options 新配置
     */
    updateOptions(options) {
        this.options = Object.assign(this.options, options);
        
        // 重新构建DOM结构
        this._buildDOM();
        
        // 重新应用过滤和排序
        this._applyFilters();
    }
    
    /**
     * 清空交易历史
     */
    clear() {
        this.trades = [];
        this.filteredTrades = [];
        this.currentPage = 1;
        
        if (this.tableBody) {
            this.tableBody.innerHTML = '';
            
            // 显示空状态
            const emptyRow = document.createElement('tr');
            emptyRow.className = 'empty-row';
            
            const emptyCell = document.createElement('td');
            emptyCell.colSpan = 4;
            emptyCell.textContent = '暂无交易记录';
            
            emptyRow.appendChild(emptyCell);
            this.tableBody.appendChild(emptyRow);
        }
        
        if (this.paginationElement) {
            this.paginationElement.container.style.display = 'none';
        }
    }
    
    /**
     * 销毁交易历史组件
     */
    destroy() {
        // 移除事件监听器
        if (this.tableBody) {
            this.tableBody.removeEventListener('click', this._handleRowClick);
        }
        
        // 清空容器
        if (this.container) {
            this.container.innerHTML = '';
            this.container.classList.remove('fst-trade-history', 'dark');
        }
        
        // 清空数据
        this.trades = [];
        this.filteredTrades = [];
    }
}

// 导出交易历史组件
window.TradeHistory = TradeHistory;