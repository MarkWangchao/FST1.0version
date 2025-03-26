/**
 * FST Trading Platform - 表单组件
 * 实现功能：
 * - 封装常用表单控件
 * - 表单验证功能
 * - 表单提交处理
 */

// 表单组件
class FSTForm {
    /**
     * 构造函数
     * @param {Object} options 表单选项
     */
    constructor(options = {}) {
        this.options = Object.assign({
            formId: null,               // 表单ID
            formElement: null,          // 表单元素
            fields: [],                 // 字段定义
            validationRules: {},        // 验证规则
            submitHandler: null,        // 提交处理函数
            resetHandler: null,         // 重置处理函数
            autoValidate: true,         // 是否自动验证
            validateOnChange: true,     // 是否在字段变更时验证
            validateOnBlur: true,       // 是否在字段失去焦点时验证
            showValidationMessages: true // 是否显示验证消息
        }, options);
        
        // 表单元素
        this.form = this.options.formElement || 
                   (this.options.formId ? document.getElementById(this.options.formId) : null);
                   
        if (!this.form) {
            throw new Error('表单元素未找到');
        }
        
        // 表单字段元素映射
        this.fieldElements = {};
        
        // 错误消息元素映射
        this.errorElements = {};
        
        // 表单数据
        this.formData = {};
        
        // 验证错误
        this.errors = {};
        
        // 初始化
        this.init();
    }
    
    /**
     * 初始化表单
     */
    init() {
        // 初始化字段元素映射
        this.initFieldElements();
        
        // 初始化表单数据
        this.updateFormData();
        
        // 绑定事件
        this.bindEvents();
    }
    
    /**
     * 初始化字段元素映射
     */
    initFieldElements() {
        if (this.options.fields && this.options.fields.length > 0) {
            // 通过字段定义初始化
            this.options.fields.forEach(field => {
                const element = this.form.querySelector(`[name="${field.name}"]`);
                if (element) {
                    this.fieldElements[field.name] = element;
                    
                    // 创建错误消息元素
                    if (this.options.showValidationMessages) {
                        this.createErrorElement(field.name);
                    }
                }
            });
        } else {
            // 通过表单元素初始化
            const inputs = this.form.querySelectorAll('input, select, textarea');
            inputs.forEach(input => {
                if (input.name) {
                    this.fieldElements[input.name] = input;
                    
                    // 创建错误消息元素
                    if (this.options.showValidationMessages) {
                        this.createErrorElement(input.name);
                    }
                }
            });
        }
    }
    
    /**
     * 创建错误消息元素
     * @param {string} fieldName 字段名
     */
    createErrorElement(fieldName) {
        // 检查是否已存在错误元素
        const existingErrorElement = this.form.querySelector(`.error-message[data-field="${fieldName}"]`);
        if (existingErrorElement) {
            this.errorElements[fieldName] = existingErrorElement;
            return;
        }
        
        // 获取字段元素
        const fieldElement = this.fieldElements[fieldName];
        if (!fieldElement) return;
        
        // 创建错误消息元素
        const errorElement = document.createElement('div');
        errorElement.className = 'error-message';
        errorElement.dataset.field = fieldName;
        errorElement.style.color = 'red';
        errorElement.style.fontSize = '12px';
        errorElement.style.marginTop = '5px';
        errorElement.style.display = 'none';
        
        // 插入到字段元素后面
        const parentElement = fieldElement.parentElement;
        if (parentElement) {
            parentElement.appendChild(errorElement);
            this.errorElements[fieldName] = errorElement;
        }
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 提交事件
        this.form.addEventListener('submit', (event) => {
            event.preventDefault();
            
            this.updateFormData();
            
            if (this.options.autoValidate) {
                const isValid = this.validate();
                if (!isValid) {
                    this.showValidationErrors();
                    return;
                }
            }
            
            if (typeof this.options.submitHandler === 'function') {
                this.options.submitHandler(this.formData, this);
            }
        });
        
        // 重置事件
        this.form.addEventListener('reset', (event) => {
            this.resetValidation();
            
            if (typeof this.options.resetHandler === 'function') {
                this.options.resetHandler(this);
            }
        });
        
        // 字段变更和失去焦点事件
        for (const fieldName in this.fieldElements) {
            const element = this.fieldElements[fieldName];
            
            if (this.options.validateOnChange) {
                element.addEventListener('input', () => {
                    this.updateFormData();
                    this.validateField(fieldName);
                });
                
                // 对于下拉框，监听change事件
                if (element.tagName === 'SELECT') {
                    element.addEventListener('change', () => {
                        this.updateFormData();
                        this.validateField(fieldName);
                    });
                }
            }
            
            if (this.options.validateOnBlur) {
                element.addEventListener('blur', () => {
                    this.updateFormData();
                    this.validateField(fieldName);
                });
            }
        }
    }
    
    /**
     * 更新表单数据
     */
    updateFormData() {
        for (const fieldName in this.fieldElements) {
            const element = this.fieldElements[fieldName];
            
            if (element.type === 'checkbox') {
                this.formData[fieldName] = element.checked;
            } else if (element.type === 'radio') {
                if (element.checked) {
                    this.formData[fieldName] = element.value;
                }
            } else if (element.type === 'file') {
                this.formData[fieldName] = element.files;
            } else {
                this.formData[fieldName] = element.value;
            }
        }
    }
    
    /**
     * 设置表单数据
     * @param {Object} data 表单数据
     */
    setFormData(data) {
        for (const fieldName in data) {
            if (this.fieldElements[fieldName]) {
                const element = this.fieldElements[fieldName];
                const value = data[fieldName];
                
                if (element.type === 'checkbox') {
                    element.checked = Boolean(value);
                } else if (element.type === 'radio') {
                    element.checked = element.value === String(value);
                } else if (element.tagName === 'SELECT') {
                    for (let i = 0; i < element.options.length; i++) {
                        if (element.options[i].value === String(value)) {
                            element.selectedIndex = i;
                            break;
                        }
                    }
                } else {
                    element.value = value;
                }
            }
        }
        
        this.updateFormData();
    }
    
    /**
     * 验证表单
     * @returns {boolean} 验证结果
     */
    validate() {
        this.errors = {};
        
        for (const fieldName in this.fieldElements) {
            this.validateField(fieldName, false);
        }
        
        return Object.keys(this.errors).length === 0;
    }
    
    /**
     * 验证字段
     * @param {string} fieldName 字段名
     * @param {boolean} showError 是否显示错误
     * @returns {boolean} 验证结果
     */
    validateField(fieldName, showError = this.options.showValidationMessages) {
        // 获取字段值
        const value = this.formData[fieldName];
        
        // 获取验证规则
        const rules = this.options.validationRules[fieldName];
        if (!rules) return true;
        
        // 验证字段
        const errors = [];
        
        for (const rule of rules) {
            const { type, message, params } = rule;
            
            let isValid = true;
            
            switch (type) {
                case 'required':
                    isValid = value !== undefined && value !== null && value !== '';
                    break;
                    
                case 'email':
                    isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
                    break;
                    
                case 'number':
                    isValid = !isNaN(parseFloat(value)) && isFinite(value);
                    break;
                    
                case 'integer':
                    isValid = Number.isInteger(Number(value));
                    break;
                    
                case 'min':
                    isValid = parseFloat(value) >= params.min;
                    break;
                    
                case 'max':
                    isValid = parseFloat(value) <= params.max;
                    break;
                    
                case 'minLength':
                    isValid = String(value).length >= params.min;
                    break;
                    
                case 'maxLength':
                    isValid = String(value).length <= params.max;
                    break;
                    
                case 'pattern':
                    isValid = new RegExp(params.pattern).test(value);
                    break;
                    
                case 'custom':
                    if (typeof params.validator === 'function') {
                        isValid = params.validator(value, this.formData);
                    }
                    break;
            }
            
            if (!isValid) {
                errors.push(message);
                break;
            }
        }
        
        if (errors.length > 0) {
            this.errors[fieldName] = errors;
            
            if (showError) {
                this.showFieldError(fieldName, errors[0]);
            }
            
            return false;
        } else {
            delete this.errors[fieldName];
            
            if (showError && this.errorElements[fieldName]) {
                this.hideFieldError(fieldName);
            }
            
            return true;
        }
    }
    
    /**
     * 显示字段错误
     * @param {string} fieldName 字段名
     * @param {string} errorMessage 错误信息
     */
    showFieldError(fieldName, errorMessage) {
        const errorElement = this.errorElements[fieldName];
        if (!errorElement) return;
        
        errorElement.textContent = errorMessage;
        errorElement.style.display = 'block';
        
        const fieldElement = this.fieldElements[fieldName];
        if (fieldElement) {
            fieldElement.classList.add('is-invalid');
        }
    }
    
    /**
     * 隐藏字段错误
     * @param {string} fieldName 字段名
     */
    hideFieldError(fieldName) {
        const errorElement = this.errorElements[fieldName];
        if (!errorElement) return;
        
        errorElement.textContent = '';
        errorElement.style.display = 'none';
        
        const fieldElement = this.fieldElements[fieldName];
        if (fieldElement) {
            fieldElement.classList.remove('is-invalid');
        }
    }
    
    /**
     * 显示所有验证错误
     */
    showValidationErrors() {
        for (const fieldName in this.errors) {
            const errors = this.errors[fieldName];
            if (errors.length > 0) {
                this.showFieldError(fieldName, errors[0]);
            }
        }
    }
    
    /**
     * 重置验证
     */
    resetValidation() {
        this.errors = {};
        
        for (const fieldName in this.errorElements) {
            this.hideFieldError(fieldName);
        }
    }
    
    /**
     * 提交表单
     */
    submit() {
        this.form.dispatchEvent(new Event('submit'));
    }
    
    /**
     * 重置表单
     */
    reset() {
        this.form.reset();
        this.updateFormData();
        this.resetValidation();
    }
    
    /**
     * 添加验证规则
     * @param {string} fieldName 字段名
     * @param {Array} rules 验证规则
     */
    addValidationRules(fieldName, rules) {
        if (!this.options.validationRules[fieldName]) {
            this.options.validationRules[fieldName] = [];
        }
        
        this.options.validationRules[fieldName] = [
            ...this.options.validationRules[fieldName],
            ...rules
        ];
    }
    
    /**
     * 移除验证规则
     * @param {string} fieldName 字段名
     */
    removeValidationRules(fieldName) {
        delete this.options.validationRules[fieldName];
    }
    
    /**
     * 动态添加字段
     * @param {string} fieldName 字段名
     * @param {HTMLElement} element 字段元素
     */
    addField(fieldName, element) {
        this.fieldElements[fieldName] = element;
        
        // 创建错误消息元素
        if (this.options.showValidationMessages) {
            this.createErrorElement(fieldName);
        }
        
        // 绑定事件
        if (this.options.validateOnChange) {
            element.addEventListener('input', () => {
                this.updateFormData();
                this.validateField(fieldName);
            });
            
            if (element.tagName === 'SELECT') {
                element.addEventListener('change', () => {
                    this.updateFormData();
                    this.validateField(fieldName);
                });
            }
        }
        
        if (this.options.validateOnBlur) {
            element.addEventListener('blur', () => {
                this.updateFormData();
                this.validateField(fieldName);
            });
        }
        
        this.updateFormData();
    }
    
    /**
     * 动态移除字段
     * @param {string} fieldName 字段名
     */
    removeField(fieldName) {
        delete this.fieldElements[fieldName];
        
        if (this.errorElements[fieldName]) {
            const errorElement = this.errorElements[fieldName];
            if (errorElement.parentElement) {
                errorElement.parentElement.removeChild(errorElement);
            }
            delete this.errorElements[fieldName];
        }
        
        delete this.formData[fieldName];
        delete this.errors[fieldName];
    }
}

// FormBuilder构建器类
class FormBuilder {
    /**
     * 构造函数
     * @param {string} formId 表单ID
     */
    constructor(formId) {
        this.formId = formId;
        this.fields = [];
        this.validationRules = {};
        this.submitHandler = null;
        this.resetHandler = null;
        this.options = {
            autoValidate: true,
            validateOnChange: true,
            validateOnBlur: true,
            showValidationMessages: true
        };
    }
    
    /**
     * 添加文本字段
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addTextField(options) {
        const field = Object.assign({
            type: 'text',
            name: '',
            label: '',
            placeholder: '',
            value: '',
            required: false,
            disabled: false,
            className: '',
            attributes: {}
        }, options);
        
        this.fields.push(field);
        
        // 添加必填验证规则
        if (field.required) {
            this.addValidationRule(field.name, {
                type: 'required',
                message: `${field.label || field.name}不能为空`
            });
        }
        
        return this;
    }
    
    /**
     * 添加密码字段
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addPasswordField(options) {
        return this.addTextField({
            ...options,
            type: 'password'
        });
    }
    
    /**
     * 添加邮箱字段
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addEmailField(options) {
        const builder = this.addTextField({
            ...options,
            type: 'email'
        });
        
        this.addValidationRule(options.name, {
            type: 'email',
            message: `请输入有效的邮箱地址`
        });
        
        return builder;
    }
    
    /**
     * 添加数字字段
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addNumberField(options) {
        const builder = this.addTextField({
            ...options,
            type: 'number'
        });
        
        this.addValidationRule(options.name, {
            type: 'number',
            message: `请输入有效的数字`
        });
        
        if (options.min !== undefined) {
            this.addValidationRule(options.name, {
                type: 'min',
                message: `不能小于${options.min}`,
                params: { min: options.min }
            });
        }
        
        if (options.max !== undefined) {
            this.addValidationRule(options.name, {
                type: 'max',
                message: `不能大于${options.max}`,
                params: { max: options.max }
            });
        }
        
        return builder;
    }
    
    /**
     * 添加复选框
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addCheckbox(options) {
        const field = Object.assign({
            type: 'checkbox',
            name: '',
            label: '',
            checked: false,
            disabled: false,
            className: '',
            attributes: {}
        }, options);
        
        this.fields.push(field);
        
        return this;
    }
    
    /**
     * 添加单选框组
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addRadioGroup(options) {
        const field = Object.assign({
            type: 'radio',
            name: '',
            label: '',
            options: [],
            value: '',
            disabled: false,
            className: '',
            attributes: {}
        }, options);
        
        this.fields.push(field);
        
        return this;
    }
    
    /**
     * 添加下拉选择框
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addSelectField(options) {
        const field = Object.assign({
            type: 'select',
            name: '',
            label: '',
            options: [],
            value: '',
            multiple: false,
            required: false,
            disabled: false,
            className: '',
            attributes: {}
        }, options);
        
        this.fields.push(field);
        
        // 添加必填验证规则
        if (field.required) {
            this.addValidationRule(field.name, {
                type: 'required',
                message: `请选择${field.label || field.name}`
            });
        }
        
        return this;
    }
    
    /**
     * 添加文本区域
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addTextareaField(options) {
        const field = Object.assign({
            type: 'textarea',
            name: '',
            label: '',
            placeholder: '',
            value: '',
            rows: 3,
            required: false,
            disabled: false,
            className: '',
            attributes: {}
        }, options);
        
        this.fields.push(field);
        
        // 添加必填验证规则
        if (field.required) {
            this.addValidationRule(field.name, {
                type: 'required',
                message: `${field.label || field.name}不能为空`
            });
        }
        
        return this;
    }
    
    /**
     * 添加隐藏字段
     * @param {Object} options 字段选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addHiddenField(options) {
        const field = Object.assign({
            type: 'hidden',
            name: '',
            value: ''
        }, options);
        
        this.fields.push(field);
        
        return this;
    }
    
    /**
     * 添加提交按钮
     * @param {Object} options 按钮选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addSubmitButton(options) {
        const field = Object.assign({
            type: 'submit',
            label: '提交',
            className: 'btn btn-primary',
            attributes: {}
        }, options);
        
        this.fields.push(field);
        
        return this;
    }
    
    /**
     * 添加重置按钮
     * @param {Object} options 按钮选项
     * @returns {FormBuilder} 当前构建器实例
     */
    addResetButton(options) {
        const field = Object.assign({
            type: 'reset',
            label: '重置',
            className: 'btn btn-secondary',
            attributes: {}
        }, options);
        
        this.fields.push(field);
        
        return this;
    }
    
    /**
     * 添加验证规则
     * @param {string} fieldName 字段名
     * @param {Object} rule 验证规则
     * @returns {FormBuilder} 当前构建器实例
     */
    addValidationRule(fieldName, rule) {
        if (!this.validationRules[fieldName]) {
            this.validationRules[fieldName] = [];
        }
        
        this.validationRules[fieldName].push(rule);
        
        return this;
    }
    
    /**
     * 设置提交处理函数
     * @param {Function} handler 处理函数
     * @returns {FormBuilder} 当前构建器实例
     */
    onSubmit(handler) {
        this.submitHandler = handler;
        return this;
    }
    
    /**
     * 设置重置处理函数
     * @param {Function} handler 处理函数
     * @returns {FormBuilder} 当前构建器实例
     */
    onReset(handler) {
        this.resetHandler = handler;
        return this;
    }
    
    /**
     * 设置选项
     * @param {Object} options 选项
     * @returns {FormBuilder} 当前构建器实例
     */
    setOptions(options) {
        this.options = Object.assign(this.options, options);
        return this;
    }
    
    /**
     * 构建表单
     * @returns {FSTForm} 表单实例
     */
    build() {
        // 创建表单实例
        const form = new FSTForm({
            formId: this.formId,
            fields: this.fields,
            validationRules: this.validationRules,
            submitHandler: this.submitHandler,
            resetHandler: this.resetHandler,
            ...this.options
        });
        
        return form;
    }
    
    /**
     * 渲染表单
     * @param {HTMLElement|string} container 容器元素或选择器
     * @returns {FSTForm} 表单实例
     */
    render(container) {
        // 获取容器元素
        let containerElement;
        if (typeof container === 'string') {
            containerElement = document.querySelector(container);
        } else if (container instanceof HTMLElement) {
            containerElement = container;
        } else {
            throw new Error('无效的容器元素');
        }
        
        if (!containerElement) {
            throw new Error('容器元素未找到');
        }
        
        // 创建表单元素
        const formElement = document.createElement('form');
        formElement.id = this.formId;
        formElement.className = 'fst-form';
        
        // 添加字段
        this.fields.forEach(field => {
            const fieldContainer = document.createElement('div');
            fieldContainer.className = 'form-group mb-3';
            
            // 添加标签
            if (field.label && field.type !== 'hidden' && field.type !== 'submit' && field.type !== 'reset') {
                const label = document.createElement('label');
                label.setAttribute('for', field.name);
                label.className = 'form-label';
                label.textContent = field.label;
                
                if (field.required) {
                    const requiredSpan = document.createElement('span');
                    requiredSpan.className = 'text-danger';
                    requiredSpan.textContent = ' *';
                    label.appendChild(requiredSpan);
                }
                
                fieldContainer.appendChild(label);
            }
            
            // 创建字段元素
            let fieldElement;
            
            switch(field.type) {
                case 'textarea':
                    fieldElement = document.createElement('textarea');
                    fieldElement.className = `form-control ${field.className || ''}`;
                    fieldElement.name = field.name;
                    fieldElement.id = field.name;
                    fieldElement.placeholder = field.placeholder || '';
                    fieldElement.value = field.value || '';
                    fieldElement.rows = field.rows || 3;
                    
                    if (field.disabled) {
                        fieldElement.disabled = true;
                    }
                    
                    // 添加自定义属性
                    for (const attr in field.attributes) {
                        fieldElement.setAttribute(attr, field.attributes[attr]);
                    }
                    break;
                    
                case 'select':
                    fieldElement = document.createElement('select');
                    fieldElement.className = `form-select ${field.className || ''}`;
                    fieldElement.name = field.name;
                    fieldElement.id = field.name;
                    
                    if (field.multiple) {
                        fieldElement.multiple = true;
                    }
                    
                    if (field.disabled) {
                        fieldElement.disabled = true;
                    }
                    
                    // 添加选项
                    if (field.options && field.options.length > 0) {
                        field.options.forEach(option => {
                            const optionElement = document.createElement('option');
                            optionElement.value = option.value;
                            optionElement.textContent = option.label;
                            
                            if (field.value === option.value) {
                                optionElement.selected = true;
                            }
                            
                            fieldElement.appendChild(optionElement);
                        });
                    }
                    
                    // 添加自定义属性
                    for (const attr in field.attributes) {
                        fieldElement.setAttribute(attr, field.attributes[attr]);
                    }
                    break;
                    
                case 'checkbox':
                    const checkboxWrapper = document.createElement('div');
                    checkboxWrapper.className = 'form-check';
                    
                    fieldElement = document.createElement('input');
                    fieldElement.className = `form-check-input ${field.className || ''}`;
                    fieldElement.type = field.type;
                    fieldElement.name = field.name;
                    fieldElement.id = field.name;
                    
                    if (field.checked) {
                        fieldElement.checked = true;
                    }
                    
                    if (field.disabled) {
                        fieldElement.disabled = true;
                    }
                    
                    // 添加自定义属性
                    for (const attr in field.attributes) {
                        fieldElement.setAttribute(attr, field.attributes[attr]);
                    }
                    
                    const checkboxLabel = document.createElement('label');
                    checkboxLabel.className = 'form-check-label';
                    checkboxLabel.setAttribute('for', field.name);
                    checkboxLabel.textContent = field.label;
                    
                    checkboxWrapper.appendChild(fieldElement);
                    checkboxWrapper.appendChild(checkboxLabel);
                    
                    fieldContainer.innerHTML = '';
                    fieldContainer.appendChild(checkboxWrapper);
                    break;
                    
                case 'radio':
                    fieldContainer.innerHTML = '';
                    
                    if (field.label) {
                        const groupLabel = document.createElement('div');
                        groupLabel.className = 'form-label';
                        groupLabel.textContent = field.label;
                        fieldContainer.appendChild(groupLabel);
                    }
                    
                    // 添加单选按钮
                    if (field.options && field.options.length > 0) {
                        field.options.forEach((option, index) => {
                            const radioWrapper = document.createElement('div');
                            radioWrapper.className = 'form-check';
                            
                            const radioElement = document.createElement('input');
                            radioElement.className = `form-check-input ${field.className || ''}`;
                            radioElement.type = 'radio';
                            radioElement.name = field.name;
                            radioElement.id = `${field.name}_${index}`;
                            radioElement.value = option.value;
                            
                            if (field.value === option.value) {
                                radioElement.checked = true;
                            }
                            
                            if (field.disabled) {
                                radioElement.disabled = true;
                            }
                            
                            // 添加自定义属性
                            for (const attr in field.attributes) {
                                radioElement.setAttribute(attr, field.attributes[attr]);
                            }
                            
                            const radioLabel = document.createElement('label');
                            radioLabel.className = 'form-check-label';
                            radioLabel.setAttribute('for', `${field.name}_${index}`);
                            radioLabel.textContent = option.label;
                            
                            radioWrapper.appendChild(radioElement);
                            radioWrapper.appendChild(radioLabel);
                            
                            fieldContainer.appendChild(radioWrapper);
                        });
                    }
                    
                    fieldElement = document.querySelector(`input[name="${field.name}"]`);
                    break;
                    
                case 'submit':
                case 'reset':
                    fieldElement = document.createElement('button');
                    fieldElement.className = field.className || '';
                    fieldElement.type = field.type;
                    fieldElement.textContent = field.label;
                    
                    // 添加自定义属性
                    for (const attr in field.attributes) {
                        fieldElement.setAttribute(attr, field.attributes[attr]);
                    }
                    
                    fieldContainer.className = 'form-group mt-3';
                    break;
                    
                default: // 文本、密码、邮箱、数字等输入框
                    fieldElement = document.createElement('input');
                    fieldElement.className = `form-control ${field.className || ''}`;
                    fieldElement.type = field.type;
                    fieldElement.name = field.name;
                    fieldElement.id = field.name;
                    fieldElement.placeholder = field.placeholder || '';
                    fieldElement.value = field.value || '';
                    
                    if (field.disabled) {
                        fieldElement.disabled = true;
                    }
                    
                    // 添加数字范围属性
                    if (field.type === 'number') {
                        if (field.min !== undefined) {
                            fieldElement.min = field.min;
                        }
                        
                        if (field.max !== undefined) {
                            fieldElement.max = field.max;
                        }
                        
                        if (field.step !== undefined) {
                            fieldElement.step = field.step;
                        }
                    }
                    
                    // 添加自定义属性
                    for (const attr in field.attributes) {
                        fieldElement.setAttribute(attr, field.attributes[attr]);
                    }
            }
            
            // 表单组类型不需要再添加字段元素
            if (field.type !== 'checkbox' && field.type !== 'radio') {
                fieldContainer.appendChild(fieldElement);
            }
            
            // 添加验证错误消息容器
            if (field.type !== 'submit' && field.type !== 'reset') {
                const errorElement = document.createElement('div');
                errorElement.className = 'error-message';
                errorElement.dataset.field = field.name;
                errorElement.style.color = 'red';
                errorElement.style.fontSize = '12px';
                errorElement.style.marginTop = '5px';
                errorElement.style.display = 'none';
                
                fieldContainer.appendChild(errorElement);
            }
            
            formElement.appendChild(fieldContainer);
        });
        
        // 将表单添加到容器
        containerElement.innerHTML = '';
        containerElement.appendChild(formElement);
        
        // 创建表单实例
        const form = new FSTForm({
            formElement: formElement,
            fields: this.fields,
            validationRules: this.validationRules,
            submitHandler: this.submitHandler,
            resetHandler: this.resetHandler,
            ...this.options
        });
        
        return form;
    }
}

// 导出表单组件和构建器
window.FSTForm = FSTForm;
window.FormBuilder = FormBuilder;