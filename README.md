# FST (Full Self Trading) 1.0verse

FST是一个全功能的量化交易系统，支持多品种、多策略的自动化交易。

## 系统特点

- 多策略支持：趋势、均值回归、机器学习、投资组合和高频策略
- 健壮的风险管理：多层次风险控制保障资金安全
- 多界面支持：桌面端、Web和移动端
- 高性能回测：支持历史数据回测和参数优化
- 数据管理：完整的市场数据管理和缓存系统
- 事件驱动：基于事件总线的松耦合架构
- 国际化支持：多语言用户界面

## 安装与使用

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动系统

```bash
python main.py --config config.yaml
```

### 回测模式

```bash
python main.py --backtest --backtest-start 2022-01-01 --backtest-end 2022-12-31
```

## 系统架构

FST采用模块化、层次化的架构设计，主要包括以下组件：

- 核心功能层：交易执行、市场数据、风险控制
- 策略层：各类交易策略实现
- 基础设施层：API接口、存储、消息服务
- 用户界面层：桌面、Web和移动端界面
- 服务层：业务逻辑服务
- 监控系统：性能监控和告警
- 回测系统：策略回测和优化

## 扩展开发

请参考docs/developer目录下的开发者文档。

## 许可证

Copyright (c) 2023 FST Team
