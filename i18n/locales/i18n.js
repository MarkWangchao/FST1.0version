/**
 * FST Trading Platform - 国际化支持配置
 * 
 * 提供多语言支持，包括英语、中文和日语
 * 支持动态语言切换和语言检测
 */

 // 导入语言包
 import enTranslations from './en.json';
 import zhTranslations from './zh.json';
 import jaTranslations from './ja.json';
 
 // 默认语言
 const DEFAULT_LOCALE = 'zh';
 
 // 支持的语言
 const SUPPORTED_LOCALES = ['en', 'zh', 'ja'];
 
 // 语言名称映射
 const LOCALE_NAMES = {
   'en': 'English',
   'zh': '中文',
   'ja': '日本語'
 };
 
 // 翻译资源
 const resources = {
   en: enTranslations,
   zh: zhTranslations,
   ja: jaTranslations
 };
 
 /**
  * I18n类 - 提供国际化功能
  */
 class I18n {
   constructor() {
     // 当前语言
     this.currentLocale = this._getDefaultLocale();
     
     // 事件监听器
     this.listeners = [];
     
     // 尝试从存储中加载语言设置
     this._loadFromStorage();
   }
   
   /**
    * 获取默认语言
    * @returns {string} 默认语言代码
    * @private
    */
   _getDefaultLocale() {
     // 尝试从浏览器获取语言
     if (typeof navigator !== 'undefined') {
       const browserLang = navigator.language || navigator.userLanguage;
       const lang = browserLang.split('-')[0];
       
       if (SUPPORTED_LOCALES.includes(lang)) {
         return lang;
       }
     }
     
     return DEFAULT_LOCALE;
   }
   
   /**
    * 从本地存储加载语言设置
    * @private
    */
   _loadFromStorage() {
     try {
       const storedLocale = localStorage.getItem('fst_locale');
       if (storedLocale && SUPPORTED_LOCALES.includes(storedLocale)) {
         this.currentLocale = storedLocale;
       }
     } catch (error) {
       console.warn('Failed to load locale from storage:', error);
     }
   }
   
   /**
    * 保存语言设置到本地存储
    * @private
    */
   _saveToStorage() {
     try {
       localStorage.setItem('fst_locale', this.currentLocale);
     } catch (error) {
       console.warn('Failed to save locale to storage:', error);
     }
   }
   
   /**
    * 翻译字符串
    * @param {string} key 翻译键名
    * @param {Object} [params={}] 参数替换对象
    * @returns {string} 翻译后的字符串
    */
   t(key, params = {}) {
     const translations = resources[this.currentLocale] || resources[DEFAULT_LOCALE];
     
     // 按照.分割路径获取嵌套翻译
     const keys = key.split('.');
     let value = translations;
     
     for (const k of keys) {
       value = value?.[k];
       if (value === undefined) break;
     }
     
     // 如果找不到翻译，尝试使用默认语言
     if (value === undefined && this.currentLocale !== DEFAULT_LOCALE) {
       let defaultValue = resources[DEFAULT_LOCALE];
       for (const k of keys) {
         defaultValue = defaultValue?.[k];
         if (defaultValue === undefined) break;
       }
       value = defaultValue;
     }
     
     // 如果仍找不到翻译，返回键名
     if (value === undefined) {
       console.warn(`Translation not found for key: ${key}`);
       return key;
     }
     
     // 替换参数
     if (typeof value === 'string' && Object.keys(params).length > 0) {
       return value.replace(/\{\{(\w+)\}\}/g, (_, paramKey) => {
         return params[paramKey] !== undefined ? params[paramKey] : `{{${paramKey}}}`;
       });
     }
     
     return value;
   }
   
   /**
    * 设置当前语言
    * @param {string} locale 语言代码
    * @returns {boolean} 是否设置成功
    */
   setLocale(locale) {
     if (!SUPPORTED_LOCALES.includes(locale)) {
       console.warn(`Unsupported locale: ${locale}`);
       return false;
     }
     
     const prevLocale = this.currentLocale;
     this.currentLocale = locale;
     this._saveToStorage();
     
     // 触发语言变更事件
     if (prevLocale !== locale) {
       this._notifyListeners(locale);
     }
     
     return true;
   }
   
   /**
    * 获取当前语言
    * @returns {string} 当前语言代码
    */
   getLocale() {
     return this.currentLocale;
   }
   
   /**
    * 获取当前语言名称
    * @returns {string} 当前语言名称
    */
   getLocaleName() {
     return LOCALE_NAMES[this.currentLocale] || LOCALE_NAMES[DEFAULT_LOCALE];
   }
   
   /**
    * 获取所有支持的语言
    * @returns {Array<{code: string, name: string}>} 语言列表
    */
   getSupportedLocales() {
     return SUPPORTED_LOCALES.map(code => ({
       code,
       name: LOCALE_NAMES[code]
     }));
   }
   
   /**
    * 添加语言变更监听器
    * @param {Function} listener 监听器函数，接收新语言代码作为参数
    * @returns {Function} 用于移除监听器的函数
    */
   onLocaleChange(listener) {
     this.listeners.push(listener);
     
     // 返回一个清理函数，用于移除监听器
     return () => {
       this.listeners = this.listeners.filter(l => l !== listener);
     };
   }
   
   /**
    * 通知所有监听器语言已变更
    * @param {string} newLocale 新语言代码
    * @private
    */
   _notifyListeners(newLocale) {
     this.listeners.forEach(listener => {
       try {
         listener(newLocale);
       } catch (error) {
         console.error('Error in locale change listener:', error);
       }
     });
     
     // 触发自定义事件
     if (typeof window !== 'undefined') {
       const event = new CustomEvent('localeChange', { detail: { locale: newLocale } });
       window.dispatchEvent(event);
     }
   }
   
   /**
    * 格式化日期
    * @param {Date|string|number} date 日期对象或时间戳
    * @param {Object} [options={}] Intl.DateTimeFormat 选项
    * @returns {string} 格式化后的日期字符串
    */
   formatDate(date, options = {}) {
     if (!date) return '';
     
     const dateObj = date instanceof Date ? date : new Date(date);
     
     try {
       const formatter = new Intl.DateTimeFormat(this.currentLocale, options);
       return formatter.format(dateObj);
     } catch (error) {
       console.error('Error formatting date:', error);
       return String(date);
     }
   }
   
   /**
    * 格式化数字
    * @param {number} number 数字
    * @param {Object} [options={}] Intl.NumberFormat 选项
    * @returns {string} 格式化后的数字字符串
    */
   formatNumber(number, options = {}) {
     if (number === null || number === undefined) return '';
     
     try {
       const formatter = new Intl.NumberFormat(this.currentLocale, options);
       return formatter.format(number);
     } catch (error) {
       console.error('Error formatting number:', error);
       return String(number);
     }
   }
   
   /**
    * 格式化货币
    * @param {number} amount 金额
    * @param {string} [currency='USD'] 货币代码
    * @returns {string} 格式化后的货币字符串
    */
   formatCurrency(amount, currency = 'USD') {
     return this.formatNumber(amount, {
       style: 'currency',
       currency
     });
   }
 }
 
 // 创建单例实例
 const i18n = new I18n();
 
 // 为方便使用，创建 t 函数别名
 export const t = (key, params) => i18n.t(key, params);
 
 // 导出实例和类
 export { i18n, I18n };
 export default i18n;