/**
 * FST Trading Platform - 通知组件
 * 提供全局通知功能，支持不同类型的消息：
 * - success: 成功消息
 * - error: 错误消息
 * - warning: 警告消息
 * - info: 信息提示
 */

// 通知组件
const NotificationComponent = {
    // 组件模板
    template: `
        <div class="notification-container">
            <transition-group name="notification-fade">
                <div v-for="notification in notifications" 
                     :key="notification.id"
                     :class="['notification', notification.type]"
                     @click="removeNotification(notification.id)">
                    <div class="notification-icon">
                        <i :class="getIconClass(notification.type)"></i>
                    </div>
                    <div class="notification-content">
                        <div v-if="notification.title" class="notification-title">{{ notification.title }}</div>
                        <div class="notification-message">{{ notification.message }}</div>
                    </div>
                    <button class="notification-close" @click.stop="removeNotification(notification.id)">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </transition-group>
        </div>
    `,

    // 组件数据
    data() {
        return {
            notifications: [],
            nextId: 1
        };
    },

    // 组件方法
    methods: {
        // 添加通知
        addNotification(notification) {
            // 默认值设置
            const defaultNotification = {
                id: this.nextId++,
                type: 'info',
                message: '',
                title: '',
                duration: 3000 // 默认显示3秒
            };

            // 合并通知配置
            const newNotification = { ...defaultNotification, ...notification };
            
            // 添加到列表
            this.notifications.push(newNotification);
            
            // 如果设置了持续时间，则自动移除
            if (newNotification.duration > 0) {
                setTimeout(() => {
                    this.removeNotification(newNotification.id);
                }, newNotification.duration);
            }
            
            return newNotification.id;
        },
        
        // 移除通知
        removeNotification(id) {
            const index = this.notifications.findIndex(notification => notification.id === id);
            if (index !== -1) {
                this.notifications.splice(index, 1);
            }
        },
        
        // 清除所有通知
        clearAll() {
            this.notifications = [];
        },
        
        // 获取图标类名
        getIconClass(type) {
            switch (type) {
                case 'success':
                    return 'fas fa-check-circle';
                case 'error':
                    return 'fas fa-times-circle';
                case 'warning':
                    return 'fas fa-exclamation-triangle';
                case 'info':
                default:
                    return 'fas fa-info-circle';
            }
        },
        
        // 快捷方法：显示成功通知
        success(message, options = {}) {
            return this.addNotification({
                type: 'success',
                message,
                ...options
            });
        },
        
        // 快捷方法：显示错误通知
        error(message, options = {}) {
            return this.addNotification({
                type: 'error',
                message,
                ...options
            });
        },
        
        // 快捷方法：显示警告通知
        warning(message, options = {}) {
            return this.addNotification({
                type: 'warning',
                message,
                ...options
            });
        },
        
        // 快捷方法：显示信息通知
        info(message, options = {}) {
            return this.addNotification({
                type: 'info',
                message,
                ...options
            });
        }
    }
};

// 创建通知组件实例
document.addEventListener('DOMContentLoaded', () => {
    // 创建通知容器
    const notificationContainer = document.createElement('div');
    notificationContainer.id = 'notification-container';
    document.body.appendChild(notificationContainer);
    
    // 创建Vue组件
    const NotificationInstance = new Vue({
        render: h => h(NotificationComponent)
    }).$mount('#notification-container');
    
    // 全局通知方法
    window.showNotification = (params) => {
        return NotificationInstance.$children[0].addNotification(params);
    };
    
    // 全局快捷通知方法
    window.showSuccess = (message, options) => {
        return NotificationInstance.$children[0].success(message, options);
    };
    
    window.showError = (message, options) => {
        return NotificationInstance.$children[0].error(message, options);
    };
    
    window.showWarning = (message, options) => {
        return NotificationInstance.$children[0].warning(message, options);
    };
    
    window.showInfo = (message, options) => {
        return NotificationInstance.$children[0].info(message, options);
    };
    
    // 清除所有通知
    window.clearAllNotifications = () => {
        NotificationInstance.$children[0].clearAll();
    };
});