#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 数据库初始化脚本

此脚本用于初始化SQLite数据库和创建必要的表结构。
适用于本地开发环境。
"""

import os
import sys
import sqlite3
import yaml

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def load_config():
    """加载配置文件"""
    config_path = 'config/local_config.yaml'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        sys.exit(1)

def init_sqlite_db(db_path):
    """初始化SQLite数据库"""
    # 确保目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    db_file = os.path.join(db_path, 'fst.db')
    print(f"初始化SQLite数据库: {db_file}")
    
    # 连接到数据库（如果不存在则创建）
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT UNIQUE,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )
    ''')
    
    # 创建账户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT UNIQUE NOT NULL,
        broker TEXT NOT NULL,
        user_id INTEGER,
        name TEXT,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # 创建策略表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS strategies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        status TEXT NOT NULL,
        config TEXT,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # 创建回测记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS backtests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id INTEGER,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        initial_capital REAL,
        final_capital REAL,
        sharpe_ratio REAL,
        max_drawdown REAL,
        status TEXT,
        result_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (strategy_id) REFERENCES strategies (id)
    )
    ''')
    
    # 创建API密钥表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        key_name TEXT NOT NULL,
        api_key TEXT UNIQUE NOT NULL,
        secret_key TEXT NOT NULL,
        permissions TEXT,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # 创建订单表（仅用于本地记录）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE NOT NULL,
        user_id INTEGER,
        strategy_id INTEGER,
        account_id TEXT,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        offset TEXT NOT NULL,
        volume REAL NOT NULL,
        price REAL,
        order_type TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (strategy_id) REFERENCES strategies (id)
    )
    ''')
    
    # 提交事务
    conn.commit()
    
    # 检查表是否创建成功
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("已创建表:")
    for table in tables:
        print(f"- {table[0]}")
    
    # 插入一个默认用户（开发环境使用）
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
        INSERT INTO users (username, password_hash, email)
        VALUES (?, ?, ?)
        ''', ('admin', 'pbkdf2:sha256:150000$abc123$...', 'admin@example.com'))
        conn.commit()
        print("已创建默认用户: admin")
    
    # 关闭连接
    conn.close()
    
    print("数据库初始化完成!")

def main():
    """脚本主函数"""
    print("开始数据库初始化...")
    
    # 加载配置
    config = load_config()
    
    # 检查数据库类型
    db_type = config.get('database', {}).get('type', 'sqlite')
    
    if db_type.lower() == 'sqlite':
        db_path = config.get('database', {}).get('path', 'data/database')
        init_sqlite_db(db_path)
    else:
        print(f"不支持的数据库类型: {db_type}")
        print("目前此脚本仅支持SQLite数据库初始化")
        sys.exit(1)

if __name__ == "__main__":
    main()