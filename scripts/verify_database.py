#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库连接验证脚本
用于验证FST系统所需的各类数据库连接是否正常
包括：SQLite、InfluxDB和MongoDB
"""

import os
import sys
import yaml
import logging
import sqlite3
from pathlib import Path

# 添加项目根目录到sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("db_verify")

def load_config(config_path="config/local_config.yaml"):
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return None

def verify_sqlite(config):
    """验证SQLite数据库连接"""
    logger.info("正在验证SQLite数据库连接...")
    
    try:
        db_path = config.get('database', {}).get('path', 'data/database')
        db_file = os.path.join(db_path, 'fst.db')
        
        # 检查文件是否存在
        if not os.path.exists(db_file):
            logger.error(f"SQLite数据库文件不存在: {db_file}")
            return False
        
        # 尝试连接
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # 检查表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        table_names = [table[0] for table in tables]
        logger.info(f"SQLite数据库包含以下表: {', '.join(table_names)}")
        
        # 检查users表
        if 'users' in table_names:
            cursor.execute("SELECT COUNT(*) FROM users;")
            user_count = cursor.fetchone()[0]
            logger.info(f"用户表中有 {user_count} 条记录")
        
        conn.close()
        logger.info("SQLite数据库连接验证成功!")
        return True
    
    except Exception as e:
        logger.error(f"SQLite数据库连接验证失败: {e}")
        return False

def verify_influxdb(config):
    """验证InfluxDB连接"""
    logger.info("正在验证InfluxDB连接...")
    
    try:
        # 尝试导入InfluxDB客户端库
        try:
            from influxdb import InfluxDBClient
        except ImportError:
            logger.warning("InfluxDB客户端库未安装，请执行: pip install influxdb")
            return False
        
        # 从配置获取InfluxDB连接信息
        # 在此示例中，我们假设使用本地默认设置
        host = "localhost"
        port = 8086
        username = ""
        password = ""
        database = "fst_data"
        
        # 检查服务器是否运行
        try:
            client = InfluxDBClient(host=host, port=port, username=username, password=password)
            version = client.ping()
            logger.info(f"InfluxDB服务器已运行，版本: {version}")
            
            # 检查数据库是否存在
            databases = client.get_list_database()
            db_names = [db['name'] for db in databases]
            
            if database not in db_names:
                logger.warning(f"数据库 '{database}' 不存在，正在创建...")
                client.create_database(database)
                logger.info(f"已创建数据库 '{database}'")
            
            client.switch_database(database)
            logger.info("InfluxDB连接验证成功!")
            return True
            
        except Exception as e:
            logger.error(f"InfluxDB服务器未运行或连接失败: {e}")
            logger.info("请确保InfluxDB服务已启动，或使用Docker安装: docker run -d -p 8086:8086 influxdb:1.8")
            return False
            
    except Exception as e:
        logger.error(f"InfluxDB连接验证失败: {e}")
        return False

def verify_mongodb(config):
    """验证MongoDB连接"""
    logger.info("正在验证MongoDB连接...")
    
    try:
        # 尝试导入MongoDB客户端库
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.warning("MongoDB客户端库未安装，请执行: pip install pymongo")
            return False
        
        # 从配置获取MongoDB连接信息
        # 在此示例中，我们假设使用本地默认设置
        host = "localhost"
        port = 27017
        database = "fst_db"
        
        # 检查服务器是否运行
        try:
            client = MongoClient(host=host, port=port, serverSelectionTimeoutMS=5000)
            server_info = client.server_info()
            logger.info(f"MongoDB服务器已运行，版本: {server_info.get('version')}")
            
            # 检查并创建集合
            db = client[database]
            if "strategies" not in db.list_collection_names():
                db.create_collection("strategies")
                logger.info("已创建strategies集合")
            
            if "backtest_results" not in db.list_collection_names():
                db.create_collection("backtest_results")
                logger.info("已创建backtest_results集合")
            
            logger.info("MongoDB连接验证成功!")
            return True
            
        except Exception as e:
            logger.error(f"MongoDB服务器未运行或连接失败: {e}")
            logger.info("请确保MongoDB服务已启动，或使用Docker安装: docker run -d -p 27017:27017 mongo:4.4")
            return False
            
    except Exception as e:
        logger.error(f"MongoDB连接验证失败: {e}")
        return False

def verify_redis(config):
    """验证Redis连接"""
    logger.info("正在验证Redis连接...")
    
    try:
        # 尝试导入Redis客户端库
        try:
            import redis
        except ImportError:
            logger.warning("Redis客户端库未安装，请执行: pip install redis")
            return False
        
        # 从配置获取Redis连接信息
        redis_config = config.get('cache', {}).get('redis', {})
        host = redis_config.get('host', 'localhost')
        port = redis_config.get('port', 6379)
        db = redis_config.get('db', 0)
        
        # 检查服务器是否运行
        try:
            r = redis.Redis(host=host, port=port, db=db, socket_timeout=5)
            if r.ping():
                logger.info("Redis服务器已运行")
                
                # 尝试进行基本操作
                r.set('fst_test_key', 'test_value')
                value = r.get('fst_test_key')
                r.delete('fst_test_key')
                
                logger.info("Redis连接验证成功!")
                return True
            else:
                logger.error("Redis服务器无法响应ping")
                return False
                
        except Exception as e:
            logger.error(f"Redis服务器未运行或连接失败: {e}")
            logger.info("请确保Redis服务已启动，或使用Docker安装: docker run -d -p 6379:6379 redis:6")
            return False
            
    except Exception as e:
        logger.error(f"Redis连接验证失败: {e}")
        return False

def create_data_directories():
    """创建必要的数据目录"""
    dirs = [
        "data/logs",
        "data/database",
        "data/mock/market_data",
        "data/test",
        "data/profiling",
        "data/document",
        "data/time_series"
    ]
    
    for dir_path in dirs:
        path = Path(dir_path)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.info(f"已创建目录: {dir_path}")
        else:
            logger.info(f"目录已存在: {dir_path}")

def main():
    """主函数"""
    logger.info("开始验证数据库连接...")
    
    # 加载配置
    config = load_config()
    if not config:
        logger.error("无法加载配置，验证中止")
        return
    
    # 创建必要的数据目录
    create_data_directories()
    
    # 验证SQLite
    sqlite_ok = verify_sqlite(config)
    
    # 验证InfluxDB(可选)
    influxdb_ok = verify_influxdb(config)
    
    # 验证MongoDB(可选)
    mongodb_ok = verify_mongodb(config)
    
    # 验证Redis(可选)
    redis_ok = verify_redis(config)
    
    # 显示总结
    logger.info("\n数据库连接验证结果:")
    logger.info(f"SQLite: {'✓ 已连接' if sqlite_ok else '✗ 未连接'}")
    logger.info(f"InfluxDB: {'✓ 已连接' if influxdb_ok else '✗ 未连接'}")
    logger.info(f"MongoDB: {'✓ 已连接' if mongodb_ok else '✗ 未连接'}")
    logger.info(f"Redis: {'✓ 已连接' if redis_ok else '✗ 未连接'}")
    
    if not (influxdb_ok and mongodb_ok and redis_ok):
        logger.info("\n您可以选择安装缺少的数据库服务:")
        logger.info("1. 使用Docker(推荐):")
        
        if not influxdb_ok:
            logger.info("   InfluxDB: docker run -d --name influxdb -p 8086:8086 influxdb:1.8")
        
        if not mongodb_ok:
            logger.info("   MongoDB: docker run -d --name mongodb -p 27017:27017 mongo:4.4")
        
        if not redis_ok:
            logger.info("   Redis: docker run -d --name redis -p 6379:6379 redis:6")
        
        logger.info("\n2. 或者使用pip安装缺少的客户端库:")
        
        if not influxdb_ok:
            logger.info("   pip install influxdb")
        
        if not mongodb_ok:
            logger.info("   pip install pymongo")
        
        if not redis_ok:
            logger.info("   pip install redis")
    
    logger.info("\n验证完成!")

if __name__ == "__main__":
    main()