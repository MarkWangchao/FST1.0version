#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import json
import logging
import asyncio
from typing import Callable, Dict, Optional, Set
from datetime import datetime, timedelta
from aiohttp import web
from dataclasses import dataclass, field
from . import (
    STATUS_UNAUTHORIZED,
    STATUS_FORBIDDEN,
    STATUS_TOO_MANY_REQUESTS,
    CONTENT_TYPE_JSON
)

# 配置日志
logger = logging.getLogger(__name__)

@web.middleware
async def AuthMiddleware(request: web.Request, handler: Callable) -> web.Response:
    """
    认证中间件 - 处理请求认证
    
    - 验证认证令牌
    - 解析用户信息
    - 处理认证错误
    """
    # 检查是否需要认证
    if not getattr(handler, "auth_required", True):
        return await handler(request)
        
    try:
        # 获取认证令牌
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise web.HTTPUnauthorized(
                text=json.dumps({
                    "success": False,
                    "error_code": "missing_token",
                    "message": "Authentication token is missing"
                }),
                content_type=CONTENT_TYPE_JSON
            )
            
        # 验证令牌格式
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise web.HTTPUnauthorized(
                text=json.dumps({
                    "success": False,
                    "error_code": "invalid_token_format",
                    "message": "Invalid token format"
                }),
                content_type=CONTENT_TYPE_JSON
            )
            
        token = parts[1]
        
        # TODO: 验证令牌并获取用户信息
        # user = await verify_token(token)
        
        # 将用户信息添加到请求中
        # request["user"] = user
        
        return await handler(request)
        
    except web.HTTPUnauthorized:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise web.HTTPUnauthorized(
            text=json.dumps({
                "success": False,
                "error_code": "auth_error",
                "message": "Authentication failed"
            }),
            content_type=CONTENT_TYPE_JSON
        )

@web.middleware
async def LoggingMiddleware(request: web.Request, handler: Callable) -> web.Response:
    """
    日志中间件 - 记录请求和响应日志
    
    - 记录请求信息
    - 记录响应信息
    - 记录处理时间
    """
    # 记录请求开始时间
    start_time = time.time()
    
    # 生成请求ID
    request_id = request.headers.get("X-Request-ID", str(time.time()))
    
    # 记录请求信息
    logger.info(f"Request {request_id} started: {request.method} {request.path}")
    
    try:
        # 处理请求
        response = await handler(request)
        
        # 计算处理时间
        duration = time.time() - start_time
        
        # 记录响应信息
        logger.info(
            f"Request {request_id} completed: {response.status} "
            f"({duration:.3f}s)"
        )
        
        return response
        
    except Exception as e:
        # 记录错误信息
        duration = time.time() - start_time
        logger.error(
            f"Request {request_id} failed: {str(e)} "
            f"({duration:.3f}s)"
        )
        raise

@dataclass
class RateLimitInfo:
    """速率限制信息"""
    count: int = 0                          # 请求计数
    reset_time: datetime = field(default_factory=datetime.now)  # 重置时间
    
    def is_exceeded(self, limit: int) -> bool:
        """检查是否超过限制"""
        now = datetime.now()
        if now >= self.reset_time:
            self.count = 1
            self.reset_time = now + timedelta(minutes=1)
            return False
        self.count += 1
        return self.count > limit

class RateLimitMiddleware:
    """
    速率限制中间件 - 控制请求频率
    
    - 基于IP的限制
    - 基于用户的限制
    - 自定义限制规则
    """
    def __init__(self, limit: int = 100):
        self.limit = limit
        self._rate_limits: Dict[str, RateLimitInfo] = {}
    
    @web.middleware
    async def __call__(self, request: web.Request, handler: Callable) -> web.Response:
        # 获取限制键(IP或用户ID)
        limit_key = request.remote
        
        # 检查是否存在自定义限制
        custom_limit = getattr(handler, "rate_limit", self.limit)
        
        # 获取或创建限制信息
        rate_limit = self._rate_limits.get(limit_key)
        if not rate_limit:
            rate_limit = RateLimitInfo()
            self._rate_limits[limit_key] = rate_limit
        
        # 检查是否超过限制
        if rate_limit.is_exceeded(custom_limit):
            raise web.HTTPTooManyRequests(
                text=json.dumps({
                    "success": False,
                    "error_code": "rate_limit_exceeded",
                    "message": "Too many requests"
                }),
                content_type=CONTENT_TYPE_JSON
            )
        
        return await handler(request)

@web.middleware
async def CORSMiddleware(request: web.Request, handler: Callable) -> web.Response:
    """
    CORS中间件 - 处理跨域请求
    
    - 添加CORS响应头
    - 处理预检请求
    - 控制允许的源和方法
    """
    # 允许的源
    allowed_origins = ["*"]  # 可配置
    
    # 允许的方法
    allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    
    # 允许的头部
    allowed_headers = ["Content-Type", "Authorization", "X-Requested-With"]
    
    # 处理预检请求
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        response = await handler(request)
    
    # 获取请求源
    origin = request.headers.get("Origin")
    if origin:
        # 检查是否允许该源
        if "*" in allowed_origins or origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
            response.headers["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)
            response.headers["Access-Control-Max-Age"] = "86400"  # 24小时
    
    return response

@web.middleware
async def ErrorHandlerMiddleware(request: web.Request, handler: Callable) -> web.Response:
    """
    错误处理中间件 - 统一错误响应格式
    
    - 捕获和处理异常
    - 格式化错误响应
    - 记录错误日志
    """
    try:
        return await handler(request)
        
    except web.HTTPException as e:
        # 处理HTTP异常
        status = e.status
        message = e.text or str(e)
        
        if hasattr(e, "error_code"):
            error_code = e.error_code
        else:
            error_code = f"http_{status}"
        
        response = {
            "success": False,
            "error_code": error_code,
            "message": message,
            "status": status
        }
        
        return web.json_response(response, status=status)
        
    except Exception as e:
        # 处理其他异常
        logger.exception("Unhandled error in request handler")
        
        response = {
            "success": False,
            "error_code": "internal_error",
            "message": "Internal server error",
            "status": 500
        }
        
        return web.json_response(response, status=500)

# 组合中间件
def create_middleware_stack(
    auth_required: bool = True,
    enable_logging: bool = True,
    rate_limit: Optional[int] = None,
    enable_cors: bool = True
) -> list:
    """
    创建中间件栈
    
    Args:
        auth_required: 是否启用认证
        enable_logging: 是否启用日志
        rate_limit: 速率限制(每分钟请求数)
        enable_cors: 是否启用CORS
        
    Returns:
        list: 中间件列表
    """
    middlewares = []
    
    # 添加错误处理中间件(始终在最外层)
    middlewares.append(ErrorHandlerMiddleware)
    
    # 添加日志中间件
    if enable_logging:
        middlewares.append(LoggingMiddleware)
    
    # 添加认证中间件
    if auth_required:
        middlewares.append(AuthMiddleware)
    
    # 添加速率限制中间件
    if rate_limit is not None:
        middlewares.append(RateLimitMiddleware(rate_limit))
    
    # 添加CORS中间件
    if enable_cors:
        middlewares.append(CORSMiddleware)
    
    return middlewares