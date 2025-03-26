/**
 * FST Trading Platform - 语言选择器组件
 * 
 * 提供界面语言切换功能，支持下拉菜单和按钮组两种显示模式
 */

import { i18n, t } from '../locales/i18n';

/**
 * 语言选择器选项定义
 */
const localeOptions = [
  { value: 'zh', label: '中文', icon: '🇨🇳' },
  { value: 'en', label: 'English', icon: '🇺🇸' },
  { value: 'ja', label: '日本語', icon: '🇯🇵' }
];

/**
 * 语言选择器类，提供两种风格：下拉菜单和按钮组
 */
class LanguageSelector {
  /**
   * 构造函数
   * @param {Object} options 选择器选项
   */
  constructor(options = {}) {
    this.options = Object.assign({
      container: null,              // 容器元素或选择器
      type: 'dropdown',             // 类型：'dropdown' 或 'buttons'
      showIcons: true,              // 是否显示国旗图标
      showLabels: true,             // 是否显示文字标签
      onChange: null,               // 语言变更回调
      className: '',                // 自定义CSS类
      position: 'right',            // 下拉菜单位置：'left', 'right', 'center'
      dropdownWidth: '180px',       // 下拉菜单宽度
      autoClose: true               // 选择后是否自动关闭下拉菜单
    }, options);
    
    // 初始化元素引用
    this.container = null;
    this.dropdown = null;
    this.buttonGroup = null;
    this.selectedElement = null;
    this.menuItems = [];
    
    // 绑定方法
    this._onDocumentClick = this._onDocumentClick.bind(this);
    
    // 初始化
    this._init();
  }
  
  /**
   * 初始化选择器
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
    
    // 清空容器
    this.container.innerHTML = '';
    this.container.classList.add('fst-language-selector');
    
    if (this.options.className) {
      this.container.classList.add(this.options.className);
    }
    
    // 创建选择器
    if (this.options.type === 'dropdown') {
      this._createDropdown();
    } else if (this.options.type === 'buttons') {
      this._createButtonGroup();
    } else {
      throw new Error(`不支持的选择器类型：${this.options.type}`);
    }
    
    // 添加全局事件监听器
    document.addEventListener('click', this._onDocumentClick);
  }
  
  /**
   * 创建下拉菜单
   * @private
   */
  _createDropdown() {
    // 创建下拉按钮
    const dropdown = document.createElement('div');
    dropdown.className = 'language-dropdown';
    
    // 当前选择的语言按钮
    const currentLocale = i18n.getLocale();
    const currentOption = localeOptions.find(opt => opt.value === currentLocale) || localeOptions[0];
    
    // 创建按钮
    const button = document.createElement('button');
    button.className = 'dropdown-toggle';
    button.setAttribute('aria-haspopup', 'true');
    button.setAttribute('aria-expanded', 'false');
    
    // 添加内容
    this._addOptionContent(button, currentOption);
    
    // 添加箭头图标
    const arrow = document.createElement('span');
    arrow.className = 'dropdown-arrow';
    arrow.innerHTML = '▼';
    button.appendChild(arrow);
    
    // 创建下拉菜单
    const menu = document.createElement('ul');
    menu.className = 'dropdown-menu';
    menu.style.width = this.options.dropdownWidth;
    menu.style.display = 'none';
    
    // 根据位置设置样式
    switch (this.options.position) {
      case 'left':
        menu.classList.add('dropdown-menu-left');
        break;
      case 'right':
        menu.classList.add('dropdown-menu-right');
        break;
      case 'center':
        menu.classList.add('dropdown-menu-center');
        break;
    }
    
    // 添加选项
    localeOptions.forEach(option => {
      const item = document.createElement('li');
      
      const link = document.createElement('a');
      link.href = '#';
      link.dataset.locale = option.value;
      
      this._addOptionContent(link, option);
      
      // 高亮当前选中的语言
      if (option.value === currentLocale) {
        link.classList.add('active');
        this.selectedElement = link;
      }
      
      // 添加点击事件
      link.addEventListener('click', (e) => {
        e.preventDefault();
        this._handleLocaleChange(option.value);
        
        // 更新选中状态
        this.menuItems.forEach(menuItem => menuItem.classList.remove('active'));
        link.classList.add('active');
        this.selectedElement = link;
        
        // 更新按钮显示
        button.innerHTML = '';
        this._addOptionContent(button, option);
        button.appendChild(arrow);
        
        // 自动关闭下拉菜单
        if (this.options.autoClose) {
          menu.style.display = 'none';
          button.setAttribute('aria-expanded', 'false');
        }
      });
      
      item.appendChild(link);
      menu.appendChild(item);
      this.menuItems.push(link);
    });
    
    // 切换下拉菜单显示/隐藏
    button.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      const isExpanded = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', (!isExpanded).toString());
      menu.style.display = isExpanded ? 'none' : 'block';
    });
    
    // 组装下拉菜单
    dropdown.appendChild(button);
    dropdown.appendChild(menu);
    this.container.appendChild(dropdown);
    
    // 保存引用
    this.dropdown = dropdown;
  }
  
  /**
   * 创建按钮组
   * @private
   */
  _createButtonGroup() {
    const buttonGroup = document.createElement('div');
    buttonGroup.className = 'language-button-group';
    
    const currentLocale = i18n.getLocale();
    
    // 为每个语言创建按钮
    localeOptions.forEach(option => {
      const button = document.createElement('button');
      button.className = 'language-button';
      button.dataset.locale = option.value;
      
      this._addOptionContent(button, option);
      
      // 高亮当前选中的语言
      if (option.value === currentLocale) {
        button.classList.add('active');
        this.selectedElement = button;
      }
      
      // 添加点击事件
      button.addEventListener('click', (e) => {
        e.preventDefault();
        
        if (option.value !== i18n.getLocale()) {
          this._handleLocaleChange(option.value);
          
          // 更新选中状态
          const buttons = buttonGroup.querySelectorAll('.language-button');
          buttons.forEach(btn => btn.classList.remove('active'));
          button.classList.add('active');
          this.selectedElement = button;
        }
      });
      
      buttonGroup.appendChild(button);
    });
    
    this.container.appendChild(buttonGroup);
    this.buttonGroup = buttonGroup;
  }
  
  /**
   * 向选项元素添加内容（图标和标签）
   * @param {HTMLElement} element 要添加内容的元素
   * @param {Object} option 选项数据
   * @private
   */
  _addOptionContent(element, option) {
    // 添加图标（如果启用）
    if (this.options.showIcons && option.icon) {
      const icon = document.createElement('span');
      icon.className = 'language-icon';
      icon.textContent = option.icon;
      element.appendChild(icon);
    }
    
    // 添加标签（如果启用）
    if (this.options.showLabels && option.label) {
      const label = document.createElement('span');
      label.className = 'language-label';
      label.textContent = option.label;
      element.appendChild(label);
    }
  }
  
  /**
   * 处理语言变更
   * @param {string} locale 新语言代码
   * @private
   */
  _handleLocaleChange(locale) {
    // 设置新语言
    i18n.setLocale(locale);
    
    // 触发变更回调
    if (typeof this.options.onChange === 'function') {
      this.options.onChange(locale);
    }
    
    // 触发自定义事件
    const event = new CustomEvent('languageChange', {
      detail: { locale }
    });
    this.container.dispatchEvent(event);
  }
  
  /**
   * 处理文档点击事件（用于关闭下拉菜单）
   * @param {Event} event 点击事件
   * @private
   */
  _onDocumentClick(event) {
    if (this.dropdown && !this.dropdown.contains(event.target)) {
      const menu = this.dropdown.querySelector('.dropdown-menu');
      const button = this.dropdown.querySelector('.dropdown-toggle');
      
      if (menu && menu.style.display === 'block') {
        menu.style.display = 'none';
        button.setAttribute('aria-expanded', 'false');
      }
    }
  }
  
  /**
   * 设置语言
   * @param {string} locale 语言代码
   * @returns {boolean} 是否设置成功
   */
  setLocale(locale) {
    if (!localeOptions.some(option => option.value === locale)) {
      console.warn(`不支持的语言：${locale}`);
      return false;
    }
    
    // 设置语言
    i18n.setLocale(locale);
    
    // 更新UI
    this._updateUI();
    
    return true;
  }
  
  /**
   * 获取当前语言
   * @returns {string} 当前语言代码
   */
  getLocale() {
    return i18n.getLocale();
  }
  
  /**
   * 更新UI显示
   * @private
   */
  _updateUI() {
    const currentLocale = i18n.getLocale();
    const currentOption = localeOptions.find(opt => opt.value === currentLocale);
    
    if (this.options.type === 'dropdown') {
      // 更新下拉按钮
      const button = this.dropdown.querySelector('.dropdown-toggle');
      const arrow = button.querySelector('.dropdown-arrow');
      
      button.innerHTML = '';
      this._addOptionContent(button, currentOption);
      button.appendChild(arrow);
      
      // 更新菜单项选中状态
      this.menuItems.forEach(item => {
        if (item.dataset.locale === currentLocale) {
          item.classList.add('active');
          this.selectedElement = item;
        } else {
          item.classList.remove('active');
        }
      });
    } else if (this.options.type === 'buttons') {
      // 更新按钮选中状态
      const buttons = this.buttonGroup.querySelectorAll('.language-button');
      buttons.forEach(button => {
        if (button.dataset.locale === currentLocale) {
          button.classList.add('active');
          this.selectedElement = button;
        } else {
          button.classList.remove('active');
        }
      });
    }
  }
  
  /**
   * 销毁选择器，移除事件监听器
   */
  destroy() {
    // 移除文档点击事件监听器
    document.removeEventListener('click', this._onDocumentClick);
    
    // 清空容器
    if (this.container) {
      this.container.innerHTML = '';
      this.container.classList.remove('fst-language-selector');
      
      if (this.options.className) {
        this.container.classList.remove(this.options.className);
      }
    }
    
    // 清除引用
    this.container = null;
    this.dropdown = null;
    this.buttonGroup = null;
    this.selectedElement = null;
    this.menuItems = [];
  }
}

/**
 * 创建语言选择器实例
 * @param {Object} options 选择器选项
 * @returns {LanguageSelector} 语言选择器实例
 */
export function createLanguageSelector(options = {}) {
  return new LanguageSelector(options);
}

/**
 * 获取支持的语言选项
 * @returns {Array} 语言选项列表
 */
export function getSupportedLocales() {
  return localeOptions.map(option => ({
    value: option.value,
    label: option.label,
    icon: option.icon,
    name: i18n.t(`languages.${option.value}`)
  }));
}

/**
 * Vue语言选择器组件定义
 * 可用于Vue应用程序
 */
export const VueLanguageSelector = {
  name: 'LanguageSelector',
  
  props: {
    type: {
      type: String,
      default: 'dropdown',
      validator: value => ['dropdown', 'buttons'].includes(value)
    },
    showIcons: {
      type: Boolean,
      default: true
    },
    showLabels: {
      type: Boolean,
      default: true
    },
    position: {
      type: String,
      default: 'right',
      validator: value => ['left', 'right', 'center'].includes(value)
    },
    dropdownWidth: {
      type: String,
      default: '180px'
    },
    autoClose: {
      type: Boolean,
      default: true
    }
  },
  
  data() {
    return {
      currentLocale: i18n.getLocale(),
      isOpen: false,
      locales: localeOptions
    };
  },
  
  methods: {
    toggleDropdown() {
      this.isOpen = !this.isOpen;
    },
    
    changeLocale(locale) {
      i18n.setLocale(locale);
      this.currentLocale = locale;
      this.isOpen = false;
      
      this.$emit('change', locale);
    },
    
    closeDropdown() {
      this.isOpen = false;
    },
    
    getLocaleLabel(locale) {
      const option = this.locales.find(opt => opt.value === locale);
      return option ? option.label : locale;
    },
    
    getLocaleIcon(locale) {
      const option = this.locales.find(opt => opt.value === locale);
      return option ? option.icon : '';
    }
  },
  
  mounted() {
    // 添加点击外部关闭下拉菜单的事件监听器
    if (this.type === 'dropdown') {
      document.addEventListener('click', this.closeDropdown);
    }
    
    // 添加语言变更监听器
    this._localeChangeUnsubscribe = i18n.onLocaleChange(locale => {
      this.currentLocale = locale;
    });
  },
  
  beforeDestroy() {
    // 移除事件监听器
    if (this.type === 'dropdown') {
      document.removeEventListener('click', this.closeDropdown);
    }
    
    // 移除语言变更监听器
    if (this._localeChangeUnsubscribe) {
      this._localeChangeUnsubscribe();
    }
  },
  
  template: `
    <div class="vue-language-selector" :class="type">
      <div v-if="type === 'dropdown'" class="language-dropdown">
        <button @click.stop="toggleDropdown" class="dropdown-toggle" :aria-expanded="isOpen">
          <span v-if="showIcons" class="language-icon">{{ getLocaleIcon(currentLocale) }}</span>
          <span v-if="showLabels" class="language-label">{{ getLocaleLabel(currentLocale) }}</span>
          <span class="dropdown-arrow">▼</span>
        </button>
        
        <ul class="dropdown-menu" :style="{ width: dropdownWidth, display: isOpen ? 'block' : 'none' }" :class="'dropdown-menu-' + position">
          <li v-for="locale in locales" :key="locale.value">
            <a href="#" @click.prevent="changeLocale(locale.value)" :class="{ active: currentLocale === locale.value }">
              <span v-if="showIcons" class="language-icon">{{ locale.icon }}</span>
              <span v-if="showLabels" class="language-label">{{ locale.label }}</span>
            </a>
          </li>
        </ul>
      </div>
      
      <div v-else-if="type === 'buttons'" class="language-button-group">
        <button
          v-for="locale in locales"
          :key="locale.value"
          @click="changeLocale(locale.value)"
          class="language-button"
          :class="{ active: currentLocale === locale.value }"
        >
          <span v-if="showIcons" class="language-icon">{{ locale.icon }}</span>
          <span v-if="showLabels" class="language-label">{{ locale.label }}</span>
        </button>
      </div>
    </div>
  `
};

// 默认导出
export default {
  LanguageSelector,
  createLanguageSelector,
  getSupportedLocales,
  VueLanguageSelector
};