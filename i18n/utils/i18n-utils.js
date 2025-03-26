/**
 * FST Trading Platform - 国际化辅助工具
 * 
 * 提供与i18n相关的辅助功能，包括格式化、混入和组件绑定
 */

import { i18n, t } from '../locales/i18n';

/**
 * 创建Vue i18n 混入对象
 * 在Vue组件中使用，提供 $t 方法和 $i18n 对象
 * @returns {Object} Vue混入对象
 */
export function createI18nMixin() {
  return {
    created() {
      // 将 t 函数绑定到组件实例
      this.$t = t;
      this.$i18n = i18n;
      
      // 添加语言变更监听器，刷新组件
      this._localeChangeUnsubscribe = i18n.onLocaleChange(() => {
        this.$forceUpdate();
      });
    },
    
    beforeDestroy() {
      // 清理语言变更监听器
      if (this._localeChangeUnsubscribe) {
        this._localeChangeUnsubscribe();
      }
    }
  };
}

/**
 * 检测文本方向
 * 判断给定语言的文本方向是从左到右还是从右到左
 * @param {string} [locale] 语言代码，默认为当前语言
 * @returns {string} 'ltr' 或 'rtl'
 */
export function getTextDirection(locale = null) {
  const lang = locale || i18n.getLocale();
  const rtlLanguages = ['ar', 'he', 'fa', 'ur'];
  
  return rtlLanguages.includes(lang) ? 'rtl' : 'ltr';
}

/**
 * 根据数量选择正确的单复数形式
 * @param {string} key 翻译键前缀（会自动添加 .zero、.one、.other 等后缀）
 * @param {number} count 数量
 * @param {Object} [params={}] 附加参数
 * @returns {string} 翻译后的字符串
 */
export function plural(key, count, params = {}) {
  // 获取正确的复数形式后缀
  let suffix = 'other';
  
  if (count === 0) {
    suffix = 'zero';
  } else if (count === 1) {
    suffix = 'one';
  } else if (count === 2) {
    suffix = 'two';
  }
  
  // 构建翻译键 (key.zero, key.one, key.other)
  const translationKey = `${key}.${suffix}`;
  
  // 传递数量和其他参数
  return t(translationKey, { count, ...params });
}

/**
 * 格式化日期差异为人类可读的文本
 * @param {Date|number|string} date 日期或时间戳
 * @param {Object} [options={}] 选项
 * @returns {string} 人类可读的时间差异
 */
export function timeAgo(date, options = {}) {
  if (!date) return '';
  
  const dateObj = date instanceof Date ? date : new Date(date);
  const now = new Date();
  const diffSeconds = Math.floor((now - dateObj) / 1000);
  
  // 将秒数转换为适合的时间单位
  if (diffSeconds < 60) {
    return t('timeAgo.justNow');
  } else if (diffSeconds < 3600) {
    const minutes = Math.floor(diffSeconds / 60);
    return plural('timeAgo.minutes', minutes, { minutes });
  } else if (diffSeconds < 86400) {
    const hours = Math.floor(diffSeconds / 3600);
    return plural('timeAgo.hours', hours, { hours });
  } else if (diffSeconds < 2592000) {
    const days = Math.floor(diffSeconds / 86400);
    return plural('timeAgo.days', days, { days });
  } else if (diffSeconds < 31536000) {
    const months = Math.floor(diffSeconds / 2592000);
    return plural('timeAgo.months', months, { months });
  } else {
    const years = Math.floor(diffSeconds / 31536000);
    return plural('timeAgo.years', years, { years });
  }
}

/**
 * 创建翻译器函数和语言选择器
 * @param {Object} [options={}] 选项
 * @returns {Object} { translate, selectLocale, currentLocale }
 */
export function createTranslator(options = {}) {
  const translate = (key, params) => t(key, params);
  
  const selectLocale = (locale) => {
    return i18n.setLocale(locale);
  };
  
  const currentLocale = () => i18n.getLocale();
  
  // 添加国际化的辅助格式化函数
  const formatDate = (date, formatOptions = {}) => {
    return i18n.formatDate(date, formatOptions);
  };
  
  const formatNumber = (number, formatOptions = {}) => {
    return i18n.formatNumber(number, formatOptions);
  };
  
  const formatCurrency = (amount, currency = 'USD') => {
    return i18n.formatCurrency(amount, currency);
  };
  
  return {
    translate,
    t: translate,
    selectLocale,
    currentLocale,
    formatDate,
    formatNumber,
    formatCurrency,
    getTextDirection: () => getTextDirection(),
    timeAgo,
    plural,
    getSupportedLocales: () => i18n.getSupportedLocales()
  };
}

/**
 * 带有多语言支持的日期格式化函数
 * @param {Date|string|number} date 日期对象或时间戳
 * @param {string} [format='medium'] 预定义格式或自定义格式
 * @returns {string} 格式化后的日期字符串
 */
export function formatDate(date, format = 'medium') {
  if (!date) return '';
  
  const dateObj = date instanceof Date ? date : new Date(date);
  
  // 预定义格式
  const formats = {
    short: { year: 'numeric', month: 'numeric', day: 'numeric' },
    medium: { year: 'numeric', month: 'short', day: 'numeric' },
    long: { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' },
    time: { hour: 'numeric', minute: 'numeric' },
    datetime: { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric' }
  };
  
  const options = formats[format] || {};
  return i18n.formatDate(dateObj, options);
}

/**
 * 基于语言的本地化文本排序
 * @param {Array<string>} texts 要排序的文本数组
 * @param {string} [locale] 语言代码，默认为当前语言
 * @returns {Array<string>} 排序后的文本数组
 */
export function sortLocalizedTexts(texts, locale = null) {
  const lang = locale || i18n.getLocale();
  
  try {
    return [...texts].sort((a, b) => {
      return String(a).localeCompare(String(b), lang);
    });
  } catch (error) {
    console.error('Error sorting localized texts:', error);
    return [...texts].sort();
  }
}

/**
 * 翻译React组件的工具钩子
 * 用于在React组件中使用i18n功能
 * @returns {Object} i18n工具对象
 */
export function useI18n() {
  // 创建工具集合
  const tools = createTranslator();
  
  // 返回工具对象
  return {
    t: tools.translate,
    locale: tools.currentLocale(),
    setLocale: tools.selectLocale,
    formatDate: tools.formatDate,
    formatNumber: tools.formatNumber,
    formatCurrency: tools.formatCurrency,
    timeAgo: tools.timeAgo,
    plural: tools.plural,
    supportedLocales: tools.getSupportedLocales(),
    textDirection: tools.getTextDirection()
  };
}

// 导出默认函数
export default {
  createI18nMixin,
  getTextDirection,
  plural,
  timeAgo,
  createTranslator,
  formatDate,
  sortLocalizedTexts,
  useI18n
};