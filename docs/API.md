# API 文档

## Webhook 网关

Base URL: `http://127.0.0.1:8765`

### POST /webhook/tradingview

接收 TradingView alert，自动校验、风控、撮合、落库。

**Request Body** (application/json):
```json
{
  "secret":     "your-shared-secret",
  "event_id":   "tv-{ticker}-{timenow}",
  "action":     "buy" | "sell",
  "symbol":     "002180.SZ" | "688122.SH" | "002180.SZSE" | "688122.SSE",
  "price":      25.30,
  "volume":     100,
  "strategy":   "ema-cross-5-30",
  "note":       "optional free text"
}
```

**Response 200 (filled)**:
```json
{
  "status": "filled",
  "event_id": "tv-001",
  "trade": {
    "tradeid": "TRADE-1788764081269025-000007",
    "orderid": "PAPER-1788764081269025-000007",
    "symbol": "002180.SZ",
    "direction": "多",
    "price": 25.30,
    "volume": 500
  },
  "account": {
    "cash": 873850.0,
    "market_value": 12650.0,
    "equity": 886500.0,
    "init_cash": 1000000.0,
    "total_pnl": -113500.0
  }
}
```

**Response 200 (duplicate - 幂等)**:
```json
{
  "status": "duplicate",
  "event_id": "tv-001",
  "detail": "event already processed, no change applied"
}
```

**Response 401 (invalid secret)**:
```json
{"detail": "invalid secret"}
```

**Response 403 (风控)**:
```json
{"detail": "volume 99999 exceeds limit 10000"}
```

**Response 429 (日上限)**:
```json
{"detail": "daily order limit reached (100)"}
```

### GET /health

```bash
curl http://127.0.0.1:8765/health
```

```json
{"status":"ok","engine":"paper","version":"0.1.0","time":"2026-09-07T12:00:00"}
```

### GET /account

```bash
curl http://127.0.0.1:8765/account
```

```json
{
  "cash": 963895.0,
  "market_value": 38925.0,
  "equity": 1002820.0,
  "init_cash": 1000000.0,
  "total_pnl": 2820.0
}
```

### GET /positions

```bash
curl http://127.0.0.1:8765/positions
```

```json
{
  "positions": [
    {
      "symbol": "002180.SZ",
      "exchange": "SZSE",
      "volume": 500,
      "avg_price": 25.6,
      "last_price": 27.5,
      "market_value": 13750.0,
      "unrealized_pnl": 950.0,
      "realized_pnl": 570.0
    }
  ]
}
```

### GET /trades?limit=50

```bash
curl 'http://127.0.0.1:8765/trades?limit=10'
```

```json
{
  "trades": [
    {
      "tradeid": "TRADE-1788764081269025-000007",
      "orderid": "PAPER-1788764081269025-000007",
      "event_id": "tv-20260907-006",
      "symbol": "002180.SZ",
      "direction": "多",
      "offset": "开",
      "price": 27.5,
      "volume": 300,
      "traded_at": "2026-09-07T14:54:39"
    }
  ]
}
```

### GET /events?limit=50

```bash
curl 'http://127.0.0.1:8765/events?limit=10'
```

```json
{
  "events": [
    {
      "event_id": "tv-20260907-001",
      "action": "buy",
      "symbol": "002180.SZ",
      "price": 25.30,
      "volume": 500,
      "strategy": "ema-cross-5-30",
      "received_at": "2026-09-07T14:54:36"
    }
  ]
}
```

## 自动生成的 Swagger

启动后访问 `http://127.0.0.1:8765/docs` 查看完整 OpenAPI 文档。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `QPOC_SECRET` | `dev-secret-change-me` | webhook 共享密钥（生产必改）|
| `QPOC_ALLOWED_SYMBOLS` | 空（不限制）| 逗号分隔的白名单 |
| `QPOC_MAX_VOLUME` | `10000` | 单笔最大股数 |
| `QPOC_DAILY_LIMIT` | `100` | 每日最多多少笔 |
| `QPOC_DB` | `./data/quant-poc.db` | SQLite 路径 |
| `TUSHARE_TOKEN` | 无 | tushare 数据 token（回测用）|
