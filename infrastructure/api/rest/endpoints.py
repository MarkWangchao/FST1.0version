#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import logging
import inspect
from typing import Any, Dict, List, Optional, Callable, Union, Type
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from aiohttp import web
from . import (
    STATUS_OK,
    STATUS_BAD_REQUEST,
    STATUS_INTERNAL_ERROR,
    CONTENT_TYPE_JSON,
    DEFAULT_API_VERSION
)

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class APIResponse:
    """API响应数据结构"""
    success: bool = True                    # 是否成功
    data: Any = None                        # 响应数据
    message: Optional[str] = None           # 响应消息
    error_code: Optional[str] = None        # 错误代码
    status_code: int = STATUS_OK            # HTTP状态码
    headers: Dict[str, str] = field(default_factory=dict)  # 自定义响应头
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error_code": self.error_code,
            "timestamp": datetime.now().isoformat()
        }

class APIError(Exception):
    """API错误异常"""
    def __init__(self, 
                message: str,
                error_code: Optional[str] = None,
                status_code: int = STATUS_BAD_REQUEST,
                data: Any = None):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.data = data
        super().__init__(message)

class APIEndpoint:
    """API端点基类"""
    def __init__(self, method: str, path: str, handler: Callable,
                auth_required: bool = True,
                rate_limit: Optional[int] = None,
                version: str = DEFAULT_API_VERSION):
        self.method = method
        self.path = path
        self.handler = handler
        self.auth_required = auth_required
        self.rate_limit = rate_limit
        self.version = version
        
        # 解析处理函数的参数
        self.params = inspect.signature(handler).parameters
        
    async def __call__(self, request: web.Request) -> web.Response:
        """处理请求"""
        try:
            # 解析请求参数
            kwargs = await self._parse_request_params(request)
            
            # 调用处理函数
            result = await self.handler(**kwargs)
            
            # 处理响应
            if isinstance(result, APIResponse):
                response = result
            else:
                response = APIResponse(data=result)
            
            # 返回JSON响应
            return web.json_response(
                response.to_dict(),
                status=response.status_code,
                headers=response.headers
            )
            
        except APIError as e:
            # 处理API错误
            response = APIResponse(
                success=False,
                message=e.message,
                error_code=e.error_code,
                status_code=e.status_code,
                data=e.data
            )
            return web.json_response(response.to_dict(), status=e.status_code)
            
        except Exception as e:
            # 处理未预期的错误
            logger.exception("Unexpected error in API endpoint")
            response = APIResponse(
                success=False,
                message=str(e),
                error_code="internal_error",
                status_code=STATUS_INTERNAL_ERROR
            )
            return web.json_response(response.to_dict(), status=STATUS_INTERNAL_ERROR)
    
    async def _parse_request_params(self, request: web.Request) -> Dict[str, Any]:
        """解析请求参数"""
        params = {}
        
        # 添加请求对象
        if "request" in self.params:
            params["request"] = request
        
        # 解析查询参数
        for name, param in self.params.items():
            if name in request.query:
                params[name] = request.query[name]
        
        # 解析请求体
        if request.body_exists:
            if request.content_type == CONTENT_TYPE_JSON:
                body = await request.json()
                for name, param in self.params.items():
                    if name in body:
                        params[name] = body[name]
        
        return params

class APIRouter:
    """API路由管理器"""
    def __init__(self, prefix: str = "", version: str = DEFAULT_API_VERSION):
        self.prefix = prefix
        self.version = version
        self.routes: List[APIEndpoint] = []
    
    def route(self, path: str, method: str = "GET", auth_required: bool = True,
             rate_limit: Optional[int] = None, version: Optional[str] = None):
        """路由装饰器"""
        def decorator(handler: Callable) -> Callable:
            endpoint = APIEndpoint(
                method=method,
                path=f"{self.prefix}{path}",
                handler=handler,
                auth_required=auth_required,
                rate_limit=rate_limit,
                version=version or self.version
            )
            self.routes.append(endpoint)
            return handler
        return decorator
    
    def get(self, path: str, **kwargs):
        """GET请求路由装饰器"""
        return self.route(path, method="GET", **kwargs)
    
    def post(self, path: str, **kwargs):
        """POST请求路由装饰器"""
        return self.route(path, method="POST", **kwargs)
    
    def put(self, path: str, **kwargs):
        """PUT请求路由装饰器"""
        return self.route(path, method="PUT", **kwargs)
    
    def delete(self, path: str, **kwargs):
        """DELETE请求路由装饰器"""
        return self.route(path, method="DELETE", **kwargs)
    
    def patch(self, path: str, **kwargs):
        """PATCH请求路由装饰器"""
        return self.route(path, method="PATCH", **kwargs)

def create_api_app(routers: List[APIRouter], 
                  middlewares: Optional[List[Callable]] = None) -> web.Application:
    """
    创建API应用
    
    Args:
        routers: 路由列表
        middlewares: 中间件列表
        
    Returns:
        web.Application: aiohttp应用实例
    """
    app = web.Application(middlewares=middlewares or [])
    
    # 注册路由
    for router in routers:
        for endpoint in router.routes:
            app.router.add_route(
                method=endpoint.method,
                path=endpoint.path,
                handler=endpoint
            )
    
    return app

# 辅助函数装饰器
def require_auth(handler: Callable) -> Callable:
    """要求认证装饰器"""
    @wraps(handler)
    async def wrapper(request: web.Request, *args, **kwargs):
        # 检查认证信息
        if not request.get("user", None):
            raise APIError(
                message="Authentication required",
                error_code="unauthorized",
                status_code=401
            )
        return await handler(request, *args, **kwargs)
    return wrapper

def rate_limit(limit: int) -> Callable:
    """速率限制装饰器"""
    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(request: web.Request, *args, **kwargs):
            # TODO: 实现速率限制逻辑
            return await handler(request, *args, **kwargs)
        return wrapper
    return decorator

def validate_params(*validators: Callable) -> Callable:
    """参数验证装饰器"""
    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(request: web.Request, *args, **kwargs):
            # 执行验证
            for validator in validators:
                await validator(request, *args, **kwargs)
            return await handler(request, *args, **kwargs)
        return wrapper
    return decorator