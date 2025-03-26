"""
REST API模块 - 提供HTTP接口服务

该模块提供以下功能:
- RESTful API端点定义和路由
- 请求处理和响应格式化
- 中间件支持(认证、日志、限流等)
- API版本管理
- 错误处理和响应
- API文档生成
"""

from .endpoints import (
    APIRouter,
    APIEndpoint,
    APIResponse,
    APIError,
    create_api_app
)

from .middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    CORSMiddleware,
    ErrorHandlerMiddleware
)

__all__ = [
    # API路由和端点
    "APIRouter",
    "APIEndpoint",
    "APIResponse",
    "APIError",
    "create_api_app",
    
    # 中间件
    "AuthMiddleware",
    "LoggingMiddleware", 
    "RateLimitMiddleware",
    "CORSMiddleware",
    "ErrorHandlerMiddleware"
]

# HTTP方法常量
HTTP_GET = "GET"
HTTP_POST = "POST"
HTTP_PUT = "PUT"
HTTP_DELETE = "DELETE"
HTTP_PATCH = "PATCH"
HTTP_OPTIONS = "OPTIONS"
HTTP_HEAD = "HEAD"

# 响应状态码
STATUS_OK = 200
STATUS_CREATED = 201
STATUS_ACCEPTED = 202
STATUS_NO_CONTENT = 204
STATUS_BAD_REQUEST = 400
STATUS_UNAUTHORIZED = 401
STATUS_FORBIDDEN = 403
STATUS_NOT_FOUND = 404
STATUS_METHOD_NOT_ALLOWED = 405
STATUS_CONFLICT = 409
STATUS_INTERNAL_ERROR = 500

# 内容类型
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_FORM = "application/x-www-form-urlencoded"
CONTENT_TYPE_MULTIPART = "multipart/form-data"
CONTENT_TYPE_TEXT = "text/plain"
CONTENT_TYPE_HTML = "text/html"

# API版本
API_VERSION_V1 = "v1"
API_VERSION_V2 = "v2"
DEFAULT_API_VERSION = API_VERSION_V1

# 默认配置
DEFAULT_RATE_LIMIT = 100  # 每分钟请求数
DEFAULT_TIMEOUT = 30      # 请求超时时间(秒)
DEFAULT_MAX_PAGE_SIZE = 100  # 最大分页大小