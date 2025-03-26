"""
认证服务模块 - 提供用户认证和授权功能

该模块提供完整的认证和授权功能，包括:
- 用户认证（用户名密码、令牌等）
- 权限管理和访问控制
- 会话管理
- 多因素认证支持
- 认证日志和审计
- 密码策略管理
"""

from .auth_service import (
    AuthService, 
    AuthToken, 
    AuthCredentials,
    AuthResult,
    AuthError,
    PermissionDenied
)

# 导出公共接口
__all__ = [
    "AuthService",
    "AuthToken",
    "AuthCredentials",
    "AuthResult",
    "AuthError",
    "PermissionDenied"
]

# 认证类型常量
AUTH_TYPE_PASSWORD = "password"          # 密码认证
AUTH_TYPE_TOKEN = "token"                # 令牌认证
AUTH_TYPE_API_KEY = "api_key"           # API密钥认证
AUTH_TYPE_OAUTH = "oauth"                # OAuth认证
AUTH_TYPE_JWT = "jwt"                    # JWT认证
AUTH_TYPE_MFA = "mfa"                    # 多因素认证

# 权限级别常量
PERMISSION_NONE = 0                      # 无权限
PERMISSION_READ = 1                      # 只读权限
PERMISSION_WRITE = 2                     # 写入权限
PERMISSION_ADMIN = 3                     # 管理员权限
PERMISSION_SUPER_ADMIN = 4               # 超级管理员权限

# 认证状态常量
STATUS_AUTHENTICATED = "authenticated"    # 已认证
STATUS_UNAUTHORIZED = "unauthorized"      # 未认证
STATUS_EXPIRED = "expired"               # 已过期
STATUS_INVALID = "invalid"               # 无效
STATUS_LOCKED = "locked"                 # 已锁定
STATUS_PENDING = "pending"               # 待验证