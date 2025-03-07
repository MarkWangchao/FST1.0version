#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FST (Full Self Trading) - 主程序入口

此模块是整个交易系统的入口点，负责初始化各个组件
并启动交易流程。

生产级特性:
1. 异步任务处理
2. 交易时段验证
3. 资金账户熔断机制
4. Prometheus监控指标
5. Docker容器支持
"""

import os
import sys
import logging
import argparse
import time
import json
import yaml
import signal
import asyncio
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
import traceback

# 添加当前目录到系统路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入核心组件
from infrastructure.api.broker_adapters.tqsdk_adapter import TqsdkAdapter
from core.market.data_provider import DataProvider
from core.trading.account_manager import AccountManager
from core.trading.strategy_executor import StrategyExecutor
from utils.config_loader import load_config, generate_default_config
from utils.time_utils import get_current_trading_date, is_trading_time
from monitoring.health_check import HealthCheck
from core.trading.circuit_breaker import CircuitBreaker

# 尝试导入可选的Prometheus依赖
try:
    from prometheus_client import start_http_server, Counter, Gauge, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# 系统常量
DEFAULT_CONFIG_PATH = 'config/trading_config.yaml'
MAX_RETRY_COUNT = 3
RETRY_INTERVAL = 5  # 秒
PROMETHEUS_PORT = 9090
HEALTH_CHECK_INTERVAL = 60  # 秒
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = -0.05  # 账户亏损5%触发熔断

# 全局变量
prometheus_metrics = {}

def setup_logging(log_level="INFO", debug=False):
    """
    配置日志系统
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        debug: 是否启用调试模式
    """
    log_dir = os.path.join("data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"fst_{datetime.now().strftime('%Y%m%d')}.log")
    
    # 将字符串日志级别转换为logging模块常量
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    # 如果开启调试模式，强制使用DEBUG级别
    if debug:
        numeric_level = logging.DEBUG
    
    # 创建根日志记录器
    logger = logging.getLogger()
    logger.setLevel(numeric_level)
    
    # 清除已有的处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 创建文件处理器 (每天轮换)
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30  # 保留30天的日志
    )
    file_handler.setLevel(numeric_level)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 创建并返回FST专用日志器
    fst_logger = logging.getLogger("fst")
    
    if debug:
        fst_logger.info("调试模式已启用 - 日志级别设置为DEBUG")
    
    return fst_logger

def setup_prometheus_metrics():
    """
    设置Prometheus监控指标
    
    Returns:
        dict: 监控指标对象字典
    """
    if not PROMETHEUS_AVAILABLE:
        return {}
    
    metrics = {
        # 系统指标
        'system_info': Gauge('fst_system_info', 'FST系统信息', ['version']),
        'uptime_seconds': Gauge('fst_uptime_seconds', 'FST运行时间(秒)'),
        
        # 交易指标
        'order_total': Counter('fst_order_total', '订单总数', ['status']),
        'trade_volume': Counter('fst_trade_volume', '成交量', ['symbol']),
        'account_balance': Gauge('fst_account_balance', '账户资金', ['account_id']),
        'position_value': Gauge('fst_position_value', '持仓市值', ['account_id', 'symbol']),
        
        # 策略指标
        'strategy_count': Gauge('fst_strategy_count', '策略数量'),
        'strategy_signals': Counter('fst_strategy_signals', '策略信号数', ['strategy_id', 'signal_type']),
        
        # 性能指标
        'api_latency': Histogram('fst_api_latency_seconds', 'API调用延迟', ['api_type']),
        'strategy_exec_time': Histogram('fst_strategy_exec_time_seconds', '策略执行时间'),
        
        # 错误指标
        'error_count': Counter('fst_error_count', '错误数量', ['component', 'error_type']),
    }
    
    # 初始化系统信息
    metrics['system_info'].labels(version='1.0.0').set(1)
    
    return metrics

def start_prometheus_server(port=PROMETHEUS_PORT, logger=None):
    """
    启动Prometheus指标服务器
    
    Args:
        port: HTTP服务器端口
        logger: 日志记录器
    """
    if PROMETHEUS_AVAILABLE:
        try:
            start_http_server(port)
            if logger:
                logger.info(f"Prometheus指标服务器已启动，端口: {port}")
        except Exception as e:
            if logger:
                logger.error(f"启动Prometheus服务器失败: {e}")
    elif logger:
        logger.warning("Prometheus依赖未安装，监控指标不可用")

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='FST (Full Self Trading) 交易系统')
    
    parser.add_argument('--config', type=str, default=DEFAULT_CONFIG_PATH,
                      help=f'配置文件路径 (默认: {DEFAULT_CONFIG_PATH})')
    
    parser.add_argument('--backtest', action='store_true',
                      help='启用回测模式')
    
    parser.add_argument('--start-date', type=str, 
                      help='回测开始日期 (YYYY-MM-DD)')
    
    parser.add_argument('--end-date', type=str, 
                      help='回测结束日期 (YYYY-MM-DD)')
    
    parser.add_argument('--log-level', type=str, default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='日志级别')
    
    parser.add_argument('--debug', action='store_true',
                      help='启用调试模式 (覆盖log-level设置为DEBUG)')
                      
    parser.add_argument('--profile', action='store_true',
                      help='启用性能分析')
                      
    parser.add_argument('--generate-config', action='store_true',
                      help='生成默认配置文件并退出')
                      
    parser.add_argument('--max-retries', type=int, default=MAX_RETRY_COUNT,
                      help=f'API连接最大重试次数 (默认: {MAX_RETRY_COUNT})')
                      
    parser.add_argument('--retry-interval', type=int, default=RETRY_INTERVAL,
                      help=f'API连接重试间隔(秒) (默认: {RETRY_INTERVAL})')
                      
    parser.add_argument('--prometheus-port', type=int, default=PROMETHEUS_PORT,
                      help=f'Prometheus指标服务器端口 (默认: {PROMETHEUS_PORT})')
                      
    parser.add_argument('--disable-prometheus', action='store_true',
                      help='禁用Prometheus监控')
                      
    parser.add_argument('--disable-circuit-breaker', action='store_true',
                      help='禁用资金账户熔断机制')
                      
    parser.add_argument('--circuit-breaker-threshold', type=float, 
                      default=DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
                      help=f'熔断触发阈值 (默认: {DEFAULT_CIRCUIT_BREAKER_THRESHOLD}, 表示账户亏损5%)')
                      
    parser.add_argument('--force-trading', action='store_true',
                      help='强制交易模式(忽略非交易时段检查)')
                      
    parser.add_argument('--docker-mode', action='store_true',
                      help='Docker容器运行模式')
    
    return parser.parse_args()

def load_configuration(config_path, logger):
    """
    加载配置文件，处理各种错误情况
    
    Args:
        config_path: 配置文件路径
        logger: 日志记录器
        
    Returns:
        dict: 配置信息
    """
    try:
        # 检查配置文件是否存在
        if not os.path.exists(config_path):
            logger.error(f"配置文件不存在: {config_path}")
            
            # 询问是否创建默认配置
            if config_path == DEFAULT_CONFIG_PATH:
                logger.info("尝试创建默认配置文件...")
                default_config = generate_default_config()
                
                # 确保配置目录存在
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                
                # 保存默认配置
                with open(config_path, 'w', encoding='utf-8') as f:
                    if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                        yaml.dump(default_config, f, default_flow_style=False)
                    else:
                        json.dump(default_config, f, indent=4)
                
                logger.info(f"已创建默认配置文件: {config_path}")
                return default_config
            else:
                raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        # 加载配置
        config = load_config(config_path)
        
        # 验证配置的必要字段
        required_sections = ['account', 'trading', 'risk']
        for section in required_sections:
            if section not in config:
                logger.warning(f"配置中缺少'{section}'部分")
        
        if 'account' in config:
            required_account_fields = ['account_id']
            for field in required_account_fields:
                if field not in config['account']:
                    logger.error(f"配置中缺少必要的账户字段: {field}")
                    raise ValueError(f"配置中缺少必要的账户字段: {field}")
        
        # 验证交易时段配置
        if 'trading' in config and 'sessions' in config['trading']:
            sessions = config['trading']['sessions']
            if not isinstance(sessions, list) or not sessions:
                logger.warning("配置中的交易时段格式无效")
        
        return config
    
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        logger.error(f"解析配置文件失败: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"加载配置时出错: {str(e)}")
        logger.debug(f"详细异常信息: {traceback.format_exc()}")
        raise

def connect_api_with_retry(api_adapter, max_retries, retry_interval, logger):
    """
    带重试机制的API连接
    
    Args:
        api_adapter: API适配器实例
        max_retries: 最大重试次数
        retry_interval: 重试间隔(秒)
        logger: 日志记录器
        
    Returns:
        bool: 连接是否成功
    """
    retry_count = 0
    
    # 记录指标的辅助函数
    def record_latency(start_time, success=True):
        if PROMETHEUS_AVAILABLE and 'api_latency' in prometheus_metrics:
            latency = time.time() - start_time
            prometheus_metrics['api_latency'].labels(api_type='connect').observe(latency)
        
        if not success and PROMETHEUS_AVAILABLE and 'error_count' in prometheus_metrics:
            prometheus_metrics['error_count'].labels(component='api', error_type='connection').inc()
    
    while retry_count <= max_retries:
        try:
            logger.info(f"尝试连接到交易接口 (尝试 {retry_count + 1}/{max_retries + 1})...")
            start_time = time.time()
            api_adapter.connect()
            record_latency(start_time, True)
            logger.info("成功连接到交易接口")
            return True
        except Exception as e:
            record_latency(start_time, False)
            retry_count += 1
            if retry_count <= max_retries:
                logger.warning(f"连接失败: {str(e)}, {retry_interval}秒后重试...")
                time.sleep(retry_interval)
            else:
                logger.error(f"连接失败，已达到最大重试次数: {str(e)}")
                logger.debug(f"详细异常信息: {traceback.format_exc()}")
                return False
    
    return False

def init_components(config, args, logger):
    """
    初始化系统各组件
    
    Args:
        config: 配置信息
        args: 命令行参数
        logger: 日志记录器
        
    Returns:
        tuple: (api_adapter, data_provider, account_manager, strategy_executor, circuit_breaker, health_checker)
    """
    components = {}
    
    try:
        # 初始化API适配器
        logger.info("初始化API适配器...")
        api_adapter = TqsdkAdapter(
            account=config['account']['account_id'],
            password=config['account'].get('password', ''),
            auth_id=config.get('account', {}).get('auth_id', None),
            auth_code=config.get('account', {}).get('auth_code', None),
            backtest_mode=args.backtest,
            start_dt=args.start_date,
            end_dt=args.end_date
        )
        components['api_adapter'] = api_adapter
        
        # 连接API（带重试机制）
        if not connect_api_with_retry(
            api_adapter, 
            args.max_retries,
            args.retry_interval,
            logger
        ):
            raise ConnectionError("无法连接到交易接口，请检查网络或账户信息")
        
        # 初始化市场数据提供者
        logger.info("初始化市场数据提供者...")
        data_provider = DataProvider(api_adapter)
        components['data_provider'] = data_provider
        
        # 初始化账户管理器
        logger.info("初始化账户管理器...")
        account_manager = AccountManager(api_adapter)
        components['account_manager'] = account_manager
        
        # 初始化熔断器（除非禁用）
        circuit_breaker = None
        if not args.disable_circuit_breaker:
            logger.info("初始化资金账户熔断机制...")
            threshold = args.circuit_breaker_threshold
            circuit_breaker = CircuitBreaker(
                account_manager=account_manager,
                threshold=threshold,
                callback=lambda: logger.critical(f"触发资金账户熔断! 阈值: {threshold}")
            )
            components['circuit_breaker'] = circuit_breaker
        
        # 初始化健康检查器
        logger.info("初始化系统健康检查...")
        health_checker = HealthCheck(
            api_adapter=api_adapter,
            account_manager=account_manager,
            interval=HEALTH_CHECK_INTERVAL
        )
        components['health_checker'] = health_checker
        
        # 初始化策略执行器
        logger.info("初始化策略执行器...")
        strategy_executor = StrategyExecutor(
            api_adapter=api_adapter,
            data_provider=data_provider,
            account_manager=account_manager,
            config=config,
            circuit_breaker=circuit_breaker
        )
        components['strategy_executor'] = strategy_executor
        
        # 加载策略
        logger.info("加载交易策略...")
        strategy_executor.load_strategies()
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE and prometheus_metrics:
            prometheus_metrics['strategy_count'].set(strategy_executor.get_strategy_count())
        
        return (api_adapter, data_provider, account_manager, strategy_executor, 
                circuit_breaker, health_checker)
        
    except Exception as e:
        logger.error(f"初始化组件时出错: {str(e)}")
        logger.debug(f"详细异常信息: {traceback.format_exc()}")
        
        # 记录Prometheus错误指标
        if PROMETHEUS_AVAILABLE and 'error_count' in prometheus_metrics:
            prometheus_metrics['error_count'].labels(
                component='init', error_type='component_init'
            ).inc()
        
        # 关闭已创建的组件
        for name, component in components.items():
            try:
                if hasattr(component, 'disconnect'):
                    logger.info(f"关闭组件: {name}")
                    component.disconnect()
                elif hasattr(component, 'close'):
                    logger.info(f"关闭组件: {name}")
                    component.close()
                elif hasattr(component, 'stop'):
                    logger.info(f"停止组件: {name}")
                    component.stop()
            except Exception as close_error:
                logger.error(f"关闭组件 {name} 时出错: {str(close_error)}")
        
        raise

def check_trading_session(config, logger, force_trading=False):
    """
    检查当前是否在交易时段内
    
    Args:
        config: 配置信息
        logger: 日志记录器
        force_trading: 是否强制交易（忽略时段检查）
        
    Returns:
        bool: 是否在交易时段内
    """
    if force_trading:
        logger.warning("强制交易模式已启用，忽略交易时段检查")
        return True
        
    # 回测模式无需检查
    if config.get('backtest', {}).get('enabled', False):
        return True
    
    # 检查配置中是否定义了交易时段
    if not config.get('trading', {}).get('sessions'):
        logger.warning("配置中未定义交易时段，默认允许交易")
        return True
    
    return is_trading_time(config['trading']['sessions'])

async def update_prometheus_metrics(account_manager, strategy_executor, start_time):
    """
    更新Prometheus监控指标
    
    Args:
        account_manager: 账户管理器
        strategy_executor: 策略执行器
        start_time: 系统启动时间
    """
    if not PROMETHEUS_AVAILABLE or not prometheus_metrics:
        return
    
    # 更新运行时间
    prometheus_metrics['uptime_seconds'].set(time.time() - start_time)
    
    # 更新账户指标
    accounts = account_manager.get_accounts()
    for account_id, account_info in accounts.items():
        prometheus_metrics['account_balance'].labels(account_id=account_id).set(
            account_info.get('balance', 0)
        )
        
        # 更新持仓指标
        positions = account_manager.get_positions(account_id)
        for symbol, position in positions.items():
            prometheus_metrics['position_value'].labels(
                account_id=account_id, symbol=symbol
            ).set(position.get('market_value', 0))
    
    # 更新策略指标
    prometheus_metrics['strategy_count'].set(strategy_executor.get_strategy_count())

async def health_check_loop(health_checker, logger):
    """
    健康检查循环
    
    Args:
        health_checker: 健康检查器
        logger: 日志记录器
    """
    while True:
        try:
            check_result = health_checker.run_checks()
            if not check_result['all_passed']:
                logger.warning(f"健康检查失败: {check_result['failed_checks']}")
                
                # 更新Prometheus指标
                if PROMETHEUS_AVAILABLE and 'error_count' in prometheus_metrics:
                    for check in check_result['failed_checks']:
                        prometheus_metrics['error_count'].labels(
                            component='health', error_type=check
                        ).inc()
        except Exception as e:
            logger.error(f"运行健康检查时出错: {str(e)}")
        
        await asyncio.sleep(health_checker.interval)

async def circuit_breaker_loop(circuit_breaker, logger):
    """
    熔断器监控循环
    
    Args:
        circuit_breaker: 熔断器
        logger: 日志记录器
    """
    if not circuit_breaker:
        return
        
    while True:
        try:
            # 检查是否应该触发熔断
            if circuit_breaker.should_break():
                logger.critical("触发资金账户熔断!")
                circuit_breaker.trigger()
                
                # 更新Prometheus指标
                if PROMETHEUS_AVAILABLE and 'error_count' in prometheus_metrics:
                    prometheus_metrics['error_count'].labels(
                        component='trading', error_type='circuit_breaker'
                    ).inc()
        except Exception as e:
            logger.error(f"熔断器检查时出错: {str(e)}")
        
        await asyncio.sleep(10)  # 每10秒检查一次

async def strategy_runner(strategy_executor, config, logger, force_trading=False):
    """
    策略执行管理器
    
    Args:
        strategy_executor: 策略执行器
        config: 配置信息
        logger: 日志记录器
        force_trading: 是否强制交易
    """
    while True:
        try:
            # 检查是否在交易时段
            if check_trading_session(config, logger, force_trading):
                if not strategy_executor.is_running():
                    logger.info("进入交易时段，启动策略执行器")
                    strategy_executor.start()
            else:
                if strategy_executor.is_running():
                    logger.info("退出交易时段，暂停策略执行器")
                    strategy_executor.pause()
        except Exception as e:
            logger.error(f"策略执行管理时出错: {str(e)}")
            
            # 更新Prometheus指标
            if PROMETHEUS_AVAILABLE and 'error_count' in prometheus_metrics:
                prometheus_metrics['error_count'].labels(
                    component='strategy', error_type='management'
                ).inc()
        
        await asyncio.sleep(60)  # 每分钟检查一次

def setup_signal_handlers(strategy_executor, api_adapter, logger):
    """
    设置信号处理器
    
    Args:
        strategy_executor: 策略执行器
        api_adapter: API适配器
        logger: 日志记录器
    """
    def signal_handler(sig, frame):
        logger.info(f"接收到信号: {sig}, 正在优雅关闭...")
        
        try:
            # 停止所有策略
            logger.info("停止所有策略...")
            strategy_executor.stop()
            
            # 关闭API连接
            logger.info("断开API连接...")
            api_adapter.disconnect()
            
            logger.info("系统已安全关闭")
        except Exception as e:
            logger.error(f"关闭时出错: {str(e)}")
        
        sys.exit(0)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main_async(args, logger, config, components):
    """
    异步主函数
    
    Args:
        args: 命令行参数
        logger: 日志记录器
        config: 配置信息
        components: 系统组件
    """
    api_adapter, data_provider, account_manager, strategy_executor, circuit_breaker, health_checker = components
    
    # 系统启动时间
    start_time = time.time()
    
    # 启动健康检查器
    logger.info("启动系统健康检查...")
    health_checker.start()
    
    # 设置信号处理器
    setup_signal_handlers(strategy_executor, api_adapter, logger)
    
    # 创建任务
    tasks = [
        health_check_loop(health_checker, logger),
        strategy_runner(strategy_executor, config, logger, args.force_trading),
    ]
    
    # 添加熔断器监控（如果启用）
    if circuit_breaker:
        tasks.append(circuit_breaker_loop(circuit_breaker, logger))
    
    # 添加Prometheus指标更新（如果启用）
    if PROMETHEUS_AVAILABLE and prometheus_metrics:
        async def prometheus_updater():
            while True:
                await update_prometheus_metrics(account_manager, strategy_executor, start_time)
                await asyncio.sleep(15)  # 每15秒更新一次
        
        tasks.append(prometheus_updater())
    
    # 运行所有任务
    await asyncio.gather(*tasks)

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 生成默认配置文件并退出
    if args.generate_config:
        config_dir = os.path.dirname(args.config)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        default_config = generate_default_config()
        with open(args.config, 'w', encoding='utf-8') as f:
            if args.config.endswith('.yaml') or args.config.endswith('.yml'):
                yaml.dump(default_config, f, default_flow_style=False)
            else:
                json.dump(default_config, f, indent=4)
        
        print(f"已生成默认配置文件: {args.config}")
        return 0
    
    # 设置日志
    logger = setup_logging(args.log_level, args.debug)
    logger.info("=" * 50)
    logger.info("FST (Full Self Trading) 系统启动")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查Docker模式
    if args.docker_mode:
        logger.info("系统运行在Docker容器中")
    
    # 设置Prometheus监控（如果启用）
    if not args.disable_prometheus and PROMETHEUS_AVAILABLE:
        global prometheus_metrics
        prometheus_metrics = setup_prometheus_metrics()
        start_prometheus_server(args.prometheus_port, logger)
    
    if args.profile:
        import cProfile
        import pstats
        logger.info("性能分析已启用")
        profile = cProfile.Profile()
        profile.enable()
    
    try:
        # 加载配置
        config = load_configuration(args.config, logger)
        logger.info(f"已加载配置: {args.config}")
        
        # 检查回测模式
        if args.backtest:
            if not args.start_date or not args.end_date:
                logger.error("回测模式需要指定开始日期和结束日期")
                return 1
            logger.info(f"回测模式已启用: {args.start_date} 至 {args.end_date}")
            config['backtest'] = {'enabled': True}
        
        # 初始化所有组件
        components = init_components(config, args, logger)
        
        # 创建并启动异步事件循环
        logger.info("启动系统异步事件循环...")
        asyncio.run(main_async(args, logger, config, components))
        
        logger.info("系统正常退出")
    
    except FileNotFoundError as e:
        logger.error(f"文件未找到: {str(e)}")
        logger.info(f"提示: 使用 --generate-config 生成默认配置文件")
        return 1
    except ValueError as e:
        logger.error(f"配置值错误: {str(e)}")
        return 1
    except ConnectionError as e:
        logger.error(f"连接错误: {str(e)}")
        return 1
    except Exception as e:
        logger.error(f"系统运行时出错: {str(e)}")
        logger.debug(f"详细异常信息: {traceback.format_exc()}")
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE and 'error_count' in prometheus_metrics:
            prometheus_metrics['error_count'].labels(
                component='main', error_type='runtime'
            ).inc()
        
        return 1
    
    finally:
        if args.profile and 'profile' in locals():
            profile.disable()
            stats_file = os.path.join("data", "reports", f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.prof")
            os.makedirs(os.path.dirname(stats_file), exist_ok=True)
            profile.dump_stats(stats_file)
            
            # 创建可读的性能报告
            readable_stats_file = os.path.join("data", "reports", f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(readable_stats_file, 'w') as f:
                stats = pstats.Stats(profile, stream=f)
                stats.sort_stats('cumulative')
                stats.print_stats(50)  # 打印前50项
            
            logger.info(f"性能分析报告已保存至: {stats_file} 和 {readable_stats_file}")
        
        logger.info("=" * 50)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())