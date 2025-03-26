# API Endpoints

This document provides detailed information about all available endpoints in the trading platform API.

## Base URL

All API requests should be made to the following base URL:

```
https://api.tradingplatform.com/v1
```

## Market Data

### GET /markets

Returns a list of available markets.

**Parameters:**
- None

**Response:**
```json
{
  "markets": [
    {
      "id": "btc_usdt",
      "base_currency": "BTC",
      "quote_currency": "USDT",
      "status": "active",
      "min_order_size": "0.001",
      "price_precision": 2,
      "volume_24h": "1243.45"
    },
    {
      "id": "eth_usdt",
      "base_currency": "ETH",
      "quote_currency": "USDT",
      "status": "active",
      "min_order_size": "0.01",
      "price_precision": 2,
      "volume_24h": "5678.12"
    }
  ]
}
```

### GET /markets/{market_id}/ticker

Returns the current ticker information for a specific market.

**Parameters:**
- `market_id` (path parameter) - The market identifier

**Response:**
```json
{
  "market_id": "btc_usdt",
  "last_price": "42123.45",
  "bid": "42120.50",
  "ask": "42125.30",
  "high_24h": "43000.00",
  "low_24h": "41500.00",
  "volume_24h": "1243.45",
  "timestamp": "2023-03-15T08:45:12Z"
}
```

### GET /markets/{market_id}/orderbook

Returns the current order book for a specific market.

**Parameters:**
- `market_id` (path parameter) - The market identifier
- `depth` (query parameter, optional) - Number of price levels to return on each side (default: 10, max: 100)

**Response:**
```json
{
  "market_id": "btc_usdt",
  "bids": [
    ["42120.50", "1.2"],
    ["42110.30", "0.8"],
    ["42100.00", "2.5"]
  ],
  "asks": [
    ["42125.30", "0.5"],
    ["42130.00", "1.0"],
    ["42150.00", "2.2"]
  ],
  "timestamp": "2023-03-15T08:45:15Z"
}
```

## Trading

### GET /orders

Returns a list of your orders.

**Parameters:**
- `status` (query parameter, optional) - Filter by order status: open, closed, all (default: open)
- `market_id` (query parameter, optional) - Filter by market
- `limit` (query parameter, optional) - Number of orders to return (default: 100, max: 500)
- `page` (query parameter, optional) - Page number for pagination (default: 1)

**Response:**
```json
{
  "orders": [
    {
      "id": "ord123456",
      "market_id": "btc_usdt",
      "type": "limit",
      "side": "buy",
      "status": "open",
      "price": "41000.00",
      "amount": "0.1",
      "filled_amount": "0.05",
      "created_at": "2023-03-15T08:00:00Z"
    },
    {
      "id": "ord123457",
      "market_id": "eth_usdt",
      "type": "market",
      "side": "sell",
      "status": "filled",
      "amount": "1.0",
      "filled_amount": "1.0",
      "average_price": "2850.75",
      "created_at": "2023-03-15T07:30:00Z"
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 3,
    "total_items": 250
  }
}
```

### POST /orders

Creates a new order.

**Parameters (JSON body):**
```json
{
  "market_id": "btc_usdt",
  "type": "limit",
  "side": "buy",
  "price": "41000.00",
  "amount": "0.1",
  "time_in_force": "gtc"
}
```

**Response:**
```json
{
  "id": "ord123458",
  "market_id": "btc_usdt",
  "type": "limit",
  "side": "buy",
  "status": "open",
  "price": "41000.00",
  "amount": "0.1",
  "filled_amount": "0.0",
  "created_at": "2023-03-15T08:46:00Z"
}
```

### DELETE /orders/{order_id}

Cancels an existing order.

**Parameters:**
- `order_id` (path parameter) - The order identifier

**Response:**
```json
{
  "success": true,
  "order_id": "ord123458"
}
```

## Account

### GET /account/balance

Returns your account balances.

**Parameters:**
- `currency` (query parameter, optional) - Filter by currency

**Response:**
```json
{
  "balances": [
    {
      "currency": "BTC",
      "available": "1.23456789",
      "locked": "0.1",
      "total": "1.33456789"
    },
    {
      "currency": "USDT",
      "available": "5000.25",
      "locked": "4100.00",
      "total": "9100.25"
    }
  ]
}
```

### GET /account/transactions

Returns your account transaction history.

**Parameters:**
- `type` (query parameter, optional) - Filter by transaction type: deposit, withdrawal, trade
- `currency` (query parameter, optional) - Filter by currency
- `start_time` (query parameter, optional) - Start time in ISO 8601 format
- `end_time` (query parameter, optional) - End time in ISO 8601 format
- `limit` (query parameter, optional) - Number of transactions to return (default: 100, max: 500)
- `page` (query parameter, optional) - Page number for pagination (default: 1)

**Response:**
```json
{
  "transactions": [
    {
      "id": "tx123456",
      "type": "deposit",
      "currency": "BTC",
      "amount": "0.5",
      "status": "completed",
      "timestamp": "2023-03-14T10:15:30Z",
      "details": {
        "txid": "0x1234567890abcdef",
        "confirmations": 6
      }
    },
    {
      "id": "tx123457",
      "type": "trade",
      "currency": "USDT",
      "amount": "-4100.00",
      "status": "completed",
      "timestamp": "2023-03-15T07:30:00Z",
      "details": {
        "order_id": "ord123457",
        "trade_id": "trade987654",
        "fee": "4.10"
      }
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 5,
    "total_items": 412
  }
}
```

## Websocket API

For real-time updates, the platform provides a WebSocket API endpoint:

```
wss://ws.tradingplatform.com/v1
```

Detailed documentation about WebSocket channels and subscription methods is provided in a separate document.