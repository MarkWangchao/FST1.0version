#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 健康检查模块

提供系统健康检查功能，监控服务的可用性、性能和资源使用情况。
"""

import os
import time
import socket
import platform
import logging
import threading
import subprocess
import psutil
from typing import Dict, List, Any, Optional, Callable, Tuple, Union
from datetime import datetime, timedelta

from utils.logging_utils import get_logger

logger = get_logger(__name__)

class HealthCheck:
    """系统健康检查类"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化健康检查
        
        Args:
            config: 健康检查配置
        """
        self.config = config or {}
        self.status = {
            "system": {
                "status": "ok",
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "disk_usage": 0.0,
                "last_check": None
            },
            "services": {},
            "database": {
                "status": "unknown",
                "response_time": 0.0,
                "last_check": None
            },
            "api": {
                "status": "unknown",
                "response_time": 0.0,
                "last_check": None
            },
            "components": {}
        }
        self.thresholds = self.config.get("thresholds", {
            "cpu_warning": 70.0,
            "cpu_critical": 90.0,
            "memory_warning": 70.0,
            "memory_critical": 90.0,
            "disk_warning": 80.0,
            "disk_critical": 95.0,
            "response_warning": 1.0,
            "response_critical": 5.0
        })
        self.check_interval = self.config.get("check_interval", 60)  # 秒
        self.registered_checks = []
        self.stop_event = threading.Event()
        self.monitor_thread = None
    
    def start(self) -> None:
        """启动健康检查监控"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("健康检查监控已在运行")
            return
        
        logger.info("启动健康检查监控")
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self) -> None:
        """停止健康检查监控"""
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            logger.warning("健康检查监控未运行")
            return
        
        logger.info("停止健康检查监控")
        self.stop_event.set()
        self.monitor_thread.join(timeout=10)
        if self.monitor_thread.is_alive():
            logger.warning("健康检查监控线程未能正常停止")
    
    def _monitor_loop(self) -> None:
        """监控循环"""
        while not self.stop_event.is_set():
            try:
                self.check_all()
                # 记录系统状态
                if self.status["system"]["status"] != "ok":
                    logger.warning(f"系统健康状态: {self.status['system']['status']}")
                    if self.status["system"]["status"] == "critical":
                        self._send_alert("系统健康状态严重警告", self.status["system"])
            except Exception as e:
                logger.error(f"健康检查监控异常: {str(e)}")
            
            # 等待下一次检查
            self.stop_event.wait(self.check_interval)
    
    def check_all(self) -> Dict[str, Any]:
        """
        执行所有健康检查
        
        Returns:
            Dict: 健康检查结果
        """
        # 系统资源检查
        self._check_system_resources()
        
        # 服务检查
        for service_name, service_info in self.config.get("services", {}).items():
            self._check_service(service_name, service_info)
        
        # 数据库检查
        if "database" in self.config:
            self._check_database(self.config["database"])
        
        # API检查
        if "api" in self.config:
            self._check_api(self.config["api"])
        
        # 执行自定义检查
        for check_func, check_name in self.registered_checks:
            try:
                result = check_func()
                self.status["components"][check_name] = {
                    "status": result.get("status", "unknown"),
                    "details": result.get("details", {}),
                    "last_check": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"自定义健康检查 '{check_name}' 异常: {str(e)}")
                self.status["components"][check_name] = {
                    "status": "error",
                    "details": {"error": str(e)},
                    "last_check": datetime.now().isoformat()
                }
        
        # 更新整体状态
        self._update_overall_status()
        
        return self.status
    
    def _check_system_resources(self) -> None:
        """检查系统资源使用情况"""
        try:
            # CPU使用率
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            
            # 更新状态
            self.status["system"]["cpu_usage"] = cpu_usage
            self.status["system"]["memory_usage"] = memory_usage
            self.status["system"]["disk_usage"] = disk_usage
            self.status["system"]["last_check"] = datetime.now().isoformat()
            
            # 检查是否超过阈值
            status = "ok"
            
            if (cpu_usage > self.thresholds["cpu_critical"] or
                memory_usage > self.thresholds["memory_critical"] or
                disk_usage > self.thresholds["disk_critical"]):
                status = "critical"
            elif (cpu_usage > self.thresholds["cpu_warning"] or
                  memory_usage > self.thresholds["memory_warning"] or
                  disk_usage > self.thresholds["disk_warning"]):
                status = "warning"
            
            self.status["system"]["status"] = status
            
        except Exception as e:
            logger.error(f"系统资源检查异常: {str(e)}")
            self.status["system"]["status"] = "error"
            self.status["system"]["error"] = str(e)
            self.status["system"]["last_check"] = datetime.now().isoformat()
    
    def _check_service(self, service_name: str, service_info: Dict[str, Any]) -> None:
        """
        检查服务状态
        
        Args:
            service_name: 服务名称
            service_info: 服务信息
        """
        try:
            if service_name not in self.status["services"]:
                self.status["services"][service_name] = {
                    "status": "unknown",
                    "last_check": None
                }
            
            # 根据服务类型进行检查
            service_type = service_info.get("type", "process")
            
            if service_type == "process":
                # 进程检查
                process_name = service_info.get("process_name")
                if process_name:
                    running = self._is_process_running(process_name)
                    self.status["services"][service_name]["status"] = "ok" if running else "critical"
                else:
                    pid = service_info.get("pid")
                    if pid:
                        running = self._is_pid_running(pid)
                        self.status["services"][service_name]["status"] = "ok" if running else "critical"
            
            elif service_type == "http":
                # HTTP服务检查
                url = service_info.get("url")
                if url:
                    status, response_time = self._check_http_service(url)
                    self.status["services"][service_name]["status"] = status
                    self.status["services"][service_name]["response_time"] = response_time
            
            elif service_type == "tcp":
                # TCP服务检查
                host = service_info.get("host", "localhost")
                port = service_info.get("port")
                if port:
                    status, response_time = self._check_tcp_service(host, port)
                    self.status["services"][service_name]["status"] = status
                    self.status["services"][service_name]["response_time"] = response_time
            
            self.status["services"][service_name]["last_check"] = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"服务 '{service_name}' 检查异常: {str(e)}")
            self.status["services"][service_name]["status"] = "error"
            self.status["services"][service_name]["error"] = str(e)
            self.status["services"][service_name]["last_check"] = datetime.now().isoformat()
    
    def _check_database(self, db_config: Dict[str, Any]) -> None:
        """
        检查数据库状态
        
        Args:
            db_config: 数据库配置
        """
        try:
            db_type = db_config.get("type", "unknown")
            
            if db_type in ["mysql", "postgresql", "sqlite"]:
                # 这里可以添加实际的数据库连接检查逻辑
                # 由于依赖具体的数据库驱动，这里仅做示例
                start_time = time.time()
                
                # 模拟检查逻辑
                time.sleep(0.1)  # 假设检查需要0.1秒
                
                response_time = time.time() - start_time
                status = "ok"
                
                if response_time > self.thresholds["response_critical"]:
                    status = "critical"
                elif response_time > self.thresholds["response_warning"]:
                    status = "warning"
                
                self.status["database"]["status"] = status
                self.status["database"]["response_time"] = response_time
                self.status["database"]["type"] = db_type
                self.status["database"]["last_check"] = datetime.now().isoformat()
            else:
                logger.warning(f"不支持的数据库类型: {db_type}")
                self.status["database"]["status"] = "unknown"
                self.status["database"]["last_check"] = datetime.now().isoformat()
                
        except Exception as e:
            logger.error(f"数据库检查异常: {str(e)}")
            self.status["database"]["status"] = "error"
            self.status["database"]["error"] = str(e)
            self.status["database"]["last_check"] = datetime.now().isoformat()
    
    def _check_api(self, api_config: Dict[str, Any]) -> None:
        """
        检查API状态
        
        Args:
            api_config: API配置
        """
        try:
            api_url = api_config.get("url")
            
            if not api_url:
                logger.warning("API URL未配置")
                self.status["api"]["status"] = "unknown"
                self.status["api"]["last_check"] = datetime.now().isoformat()
                return
            
            status, response_time = self._check_http_service(api_url)
            
            self.status["api"]["status"] = status
            self.status["api"]["response_time"] = response_time
            self.status["api"]["url"] = api_url
            self.status["api"]["last_check"] = datetime.now().isoformat()
                
        except Exception as e:
            logger.error(f"API检查异常: {str(e)}")
            self.status["api"]["status"] = "error"
            self.status["api"]["error"] = str(e)
            self.status["api"]["last_check"] = datetime.now().isoformat()
    
    def _update_overall_status(self) -> None:
        """更新整体状态"""
        # 如果任一组件为critical，则整体为critical
        for component_type in ["system", "services", "database", "api", "components"]:
            if component_type == "services":
                for service in self.status["services"].values():
                    if service.get("status") == "critical":
                        self.status["overall"] = {"status": "critical"}
                        return
            elif component_type == "components":
                for component in self.status["components"].values():
                    if component.get("status") == "critical":
                        self.status["overall"] = {"status": "critical"}
                        return
            else:
                if self.status[component_type].get("status") == "critical":
                    self.status["overall"] = {"status": "critical"}
                    return
        
        # 如果任一组件为warning，则整体为warning
        for component_type in ["system", "services", "database", "api", "components"]:
            if component_type == "services":
                for service in self.status["services"].values():
                    if service.get("status") == "warning":
                        self.status["overall"] = {"status": "warning"}
                        return
            elif component_type == "components":
                for component in self.status["components"].values():
                    if component.get("status") == "warning":
                        self.status["overall"] = {"status": "warning"}
                        return
            else:
                if self.status[component_type].get("status") == "warning":
                    self.status["overall"] = {"status": "warning"}
                    return
        
        # 如果有任何组件为error，则整体为error
        for component_type in ["system", "services", "database", "api", "components"]:
            if component_type == "services":
                for service in self.status["services"].values():
                    if service.get("status") == "error":
                        self.status["overall"] = {"status": "error"}
                        return
            elif component_type == "components":
                for component in self.status["components"].values():
                    if component.get("status") == "error":
                        self.status["overall"] = {"status": "error"}
                        return
            else:
                if self.status[component_type].get("status") == "error":
                    self.status["overall"] = {"status": "error"}
                    return
        
        # 如果没有问题，则整体为ok
        self.status["overall"] = {"status": "ok"}
    
    def _is_process_running(self, process_name: str) -> bool:
        """
        检查进程是否运行
        
        Args:
            process_name: 进程名称
            
        Returns:
            bool: 进程是否运行
        """
        for proc in psutil.process_iter(['name']):
            try:
                if process_name.lower() in proc.info['name'].lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False
    
    def _is_pid_running(self, pid: int) -> bool:
        """
        检查PID是否运行
        
        Args:
            pid: 进程ID
            
        Returns:
            bool: 进程是否运行
        """
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except psutil.NoSuchProcess:
            return False
    
    def _check_http_service(self, url: str) -> Tuple[str, float]:
        """
        检查HTTP服务
        
        Args:
            url: 服务URL
            
        Returns:
            Tuple[str, float]: 状态和响应时间
        """
        import requests
        try:
            start_time = time.time()
            response = requests.get(url, timeout=10)
            response_time = time.time() - start_time
            
            if response.status_code >= 500:
                status = "critical"
            elif response.status_code >= 400:
                status = "warning"
            else:
                status = "ok"
                
                if response_time > self.thresholds["response_critical"]:
                    status = "critical"
                elif response_time > self.thresholds["response_warning"]:
                    status = "warning"
            
            return status, response_time
        except requests.RequestException:
            return "critical", 0.0
    
    def _check_tcp_service(self, host: str, port: int) -> Tuple[str, float]:
        """
        检查TCP服务
        
        Args:
            host: 主机地址
            port: 端口号
            
        Returns:
            Tuple[str, float]: 状态和响应时间
        """
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            response_time = time.time() - start_time
            
            if result == 0:
                status = "ok"
                
                if response_time > self.thresholds["response_critical"]:
                    status = "critical"
                elif response_time > self.thresholds["response_warning"]:
                    status = "warning"
            else:
                status = "critical"
            
            return status, response_time
        except socket.error:
            return "critical", 0.0
    
    def register_check(self, check_func: Callable[[], Dict[str, Any]], check_name: str) -> None:
        """
        注册自定义健康检查函数
        
        Args:
            check_func: 检查函数，应返回包含status键的字典
            check_name: 检查名称
        """
        self.registered_checks.append((check_func, check_name))
        logger.info(f"已注册自定义健康检查: {check_name}")
    
    def _send_alert(self, subject: str, data: Dict[str, Any]) -> None:
        """
        发送告警
        
        Args:
            subject: 告警主题
            data: 告警数据
        """
        alert_config = self.config.get("alerts", {})
        
        if not alert_config.get("enabled", False):
            return
        
        alert_methods = alert_config.get("methods", [])
        
        for method in alert_methods:
            if method == "log":
                logger.critical(f"健康检查告警: {subject}")
                logger.critical(f"详情: {data}")
            elif method == "email":
                # 这里可以添加邮件告警逻辑
                pass
            elif method == "sms":
                # 这里可以添加短信告警逻辑
                pass
            elif method == "webhook":
                # 这里可以添加webhook告警逻辑
                webhook_url = alert_config.get("webhook_url")
                if webhook_url:
                    try:
                        import requests
                        requests.post(webhook_url, json={
                            "subject": subject,
                            "data": data,
                            "timestamp": datetime.now().isoformat()
                        })
                    except Exception as e:
                        logger.error(f"发送webhook告警失败: {str(e)}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取当前健康状态
        
        Returns:
            Dict: 健康状态
        """
        return self.status
    
    def get_report(self) -> Dict[str, Any]:
        """
        生成健康报告
        
        Returns:
            Dict: 健康报告
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": self.status.get("overall", {}).get("status", "unknown"),
            "system": self.status["system"],
            "services": {},
            "database": self.status["database"],
            "api": self.status["api"],
            "components": {}
        }
        
        # 筛选有问题的服务
        for service_name, service_info in self.status["services"].items():
            if service_info.get("status") != "ok":
                report["services"][service_name] = service_info
        
        # 筛选有问题的组件
        for component_name, component_info in self.status["components"].items():
            if component_info.get("status") != "ok":
                report["components"][component_name] = component_info
        
        return report
    
    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """
        获取系统信息
        
        Returns:
            Dict: 系统信息
        """
        info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "disk_total": psutil.disk_usage('/').total,
            "network_interfaces": []
        }
        
        # 获取网络接口信息
        for iface, addrs in psutil.net_if_addrs().items():
            ips = []
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ips.append(addr.address)
            
            if ips:
                info["network_interfaces"].append({
                    "name": iface,
                    "ips": ips
                })
        
        return info