# infrastructure/api/websocket/handlers.py

"""Optimized WebSocket handlers with TQSdk integration"""

import asyncio
import json
import logging
import websockets
from typing import Set, Dict
from tqsdk import TqApi, TqAuth  # 天勤量化SDK集成
from cachetools import TTLCache
from prometheus_client import Counter, Histogram
from infrastructure.event_bus.event_manager import EventManager
from core.market.data_provider import DataProvider
from core.trading.order_manager import OrderManager

# 监控指标
WS_CONNECTIONS = Counter('websocket_connections', 'Active WebSocket connections')
MSG_LATENCY = Histogram('message_latency', 'Message processing latency')
ORDER_FAILURES = Counter('order_failures', 'Order placement failures')

class EnhancedWebSocketHandler:
    """Optimized WebSocket handler with TQSdk integration"""
    
    def __init__(self):
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self._connection_pool = TTLCache(maxsize=1000, ttl=300)
        self._tq_api = TqApi(auth=TqAuth("your_account", "your_token"))  # 天勤API连接
        
        # 初始化组件
        self.event_manager = EventManager()
        self.data_provider = DataProvider()
        self.order_manager = OrderManager()
        
        # 心跳配置
        self._heartbeat_interval = 30  # 秒
        self._max_retries = 3
        
        # 注册事件监听
        self.event_manager.subscribe("market_data_update", self.broadcast_market_data)
        self.event_manager.subscribe("order_update", self.broadcast_order_update)

    async def _maintain_connection(self, websocket):
        """连接维护与心跳机制"""
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                await websocket.ping()
        except websockets.ConnectionClosed:
            logger.warning("Connection lost, initiating reconnect...")
            await self._reconnect()

    async def _reconnect(self):
        """自动重连机制（指数退避）"""
        for attempt in range(self._max_retries):
            try:
                await self._tq_api._connect()  # 天勤API重连
                return
            except Exception as e:
                wait = min(2 ** attempt, 10)
                logger.error(f"Reconnect attempt {attempt+1} failed, retrying in {wait}s")
                await asyncio.sleep(wait)

    async def handle_message(self, websocket: websockets.WebSocketServerProtocol, message: str) -> None:
        """增强的消息处理（含天勤订单路由）"""
        with MSG_LATENCY.time():
            try:
                data = json.loads(message)
                action = data.get("action")
                
                # 天勤市场数据路由
                if action == "tq_subscribe":
                    await self._handle_tq_subscription(websocket, data)
                elif action == "tq_order":
                    await self._handle_tq_order(websocket, data)
                else:
                    await super().handle_message(websocket, message)
            except Exception as e:
                logger.error(f"Message handling error: {str(e)}")
                await self._send_error(websocket, str(e))

    async def _handle_tq_subscription(self, websocket, data: Dict):
        """天勤行情订阅处理"""
        symbol = data.get("symbol")
        if not symbol:
            raise ValueError("Missing symbol in subscription")
            
        # 获取天勤实时行情
        quote = await self._tq_api.get_quote(symbol)
        await websocket.send(json.dumps({
            "type": "tq_quote",
            "symbol": symbol,
            "data": quote
        }))

    async def _handle_tq_order(self, websocket, data: Dict):
        """天勤订单处理（含重试机制）"""
        for attempt in range(3):
            try:
                order = self._tq_api.insert_order(**data)
                await self._tq_api.wait_update()
                await websocket.send(json.dumps({
                    "type": "tq_order",
                    "order_id": order.order_id,
                    "status": order.status
                }))
                return
            except Exception as e:
                if attempt == 2:
                    ORDER_FAILURES.inc()
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

    async def broadcast_market_data(self, event_data: dict) -> None:
        """优化广播性能（批处理）"""
        if not self.clients:
            return
            
        message = json.dumps({"type": "market_data", "data": event_data})
        tasks = []
        for client in self.clients:
            try:
                if client.open:
                    tasks.append(client.send(message))
            except Exception:
                self.clients.remove(client)
        await asyncio.gather(*tasks, return_exceptions=True)

    def _get_connection_metrics(self) -> Dict:
        """连接状态监控"""
        return {
            "active_connections": len(self.clients),
            "message_queue": len(self._tq_api._pending_chan),
            "cache_hit_rate": self._connection_pache.currsize / self._connection_pache.maxsize
        }

async def start_optimized_server(host: str = "0.0.0.0", port: int = 8888):
    """启动优化版服务"""
    handler = EnhancedWebSocketHandler()
    async with websockets.serve(
        handler.handler,
        host,
        port,
        ping_interval=30,
        ping_timeout=90,
        max_size=2**20  # 1MB
    ):
        logger.info(f"Optimized WS server running on ws://{host}:{port}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(start_optimized_server())