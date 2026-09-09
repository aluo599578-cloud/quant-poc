# 架构详解

## 链路图

```
┌─────────────────────────────────────────────────────────────────┐
│  TradingView (云端)                                              │
│  Pine Script v6 strategy → alert → webhook POST                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS POST + shared secret
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI 网关 (app/webhook_gateway.py)                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 1. Pydantic 模型校验（schema）                             │   │
│  │    {secret, event_id, action, symbol, price, volume}      │   │
│  │ 2. secret 校验 → 401 invalid secret                       │   │
│  │ 3. 持仓限额校验 → 403 exceeds limit                        │   │
│  │ 4. 日上限校验 → 429 daily limit                            │   │
│  │ 5. 幂等检查（SQLite events.event_id UNIQUE）              │   │
│  │    → 200 duplicate（不重复扣款）                          │   │
│  │ 6. 解析 vt_symbol（.SZ/.SH 或 .SZSE/.SSE 两种格式）        │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ engine.submit(event_id, symbol, action, price, volume)
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  Paper Engine (app/paper_engine.py)                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 立即按 alert 价格成交（模拟市价单）                         │   │
│  │                                                          │   │
│  │ 1. 生成 orderid = PAPER-{纳秒}-{count:06d}                │   │
│  │    （纳秒前缀避免重启进程后 count 归零导致 UNIQUE 冲突）  │   │
│  │ 2. SQLite 写 orders 表（status=ALL_TRADED）              │   │
│  │ 3. 更新内存持仓 dict（加权平均成本算法）                   │   │
│  │ 4. 更新 cash（buy 减钱，sell 加钱）                       │   │
│  │ 5. 更新 last_prices（用于计算 unrealized P&L）            │   │
│  │ 6. 计算 realized_pnl（按平均成本法，PnL 100% 一致）       │   │
│  │ 7. SQLite 写 trades 表                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ SQLite (data/quant-poc.db)
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  SQLite                                                          │
│  ┌─────────────┬────────────┬──────────────┬────────────┐       │
│  │ events      │ orders     │ trades       │ (positions │       │
│  │             │            │              │  in-memory)│       │
│  │ event_id PK│ orderid PK │ tradeid PK   │            │       │
│  │ secret      │ event_id   │ orderid      │            │       │
│  │ action      │ symbol     │ event_id     │            │       │
│  │ symbol      │ direction  │ symbol       │            │       │
│  │ price       │ offset     │ direction    │            │       │
│  │ volume      │ price      │ offset       │            │       │
│  │ strategy    │ volume     │ price        │            │       │
│  │ received_at │ status     │ volume       │            │       │
│  │ raw_json    │ created_at │ traded_at    │            │       │
│  └─────────────┴────────────┴──────────────┴────────────┘       │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST 端点（webhook_gateway.py 同进程）
                             │ 或直接 sqlite3 读（dashboard.py）
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│  Streamlit Dashboard (dashboard.py) - 4 Tab                      │
│  ┌────────────┬────────────┬────────────┬────────────┐          │
│  │ Tab 1      │ Tab 2      │ Tab 3      │ Tab 4      │          │
│  │ 组合扫描   │ 单股深度   │ 历史结果   │ Webhook 实时│         │
│  │            │            │            │            │          │
│  │ 3 股 ×5 参数│ K线+净值  │ 30 次散点图│ 直接读SQLite│         │
│  │ ×2 策略    │ 9 指标     │            │ 持仓/成交/事件│       │
│  │ 柱状图对比 │ 含风险调整 │            │ 5 个账户卡  │          │
│  └────────────┴────────────┴────────────┴────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## 核心设计选择

### 1. 不用 broker adapter 模式，自己写 PaperEngine
**为什么**：A 股没有开源的"TV→券商"桥，现成的桥都跑加密/IBKR。  
**好处**：~280 行可控，未来要换券商只换一个文件。  
**代价**：要自己写撮合逻辑（P&L 公式、限价单/部分成交等）。

### 2. SQLite 不用 Postgres
**为什么**：单机 PoC，没有并发用户。  
**代价**：单文件 100MB 后会变慢。生产环境要换 Postgres。

### 3. vnpy 对象 + 自写撮合（不用 BacktestingEngine）
**为什么**：BacktestingEngine 是回测场景，不能直接吃 webhook。  
**做法**：用 vnpy 的 `OrderRequest/OrderData/TradeData/Direction/Offset/Exchange` 标准对象，撮合逻辑自己写。

### 4. PnL 用"加权平均成本"算法
**为什么**：最常见的 PoC 算法，简单可解释。  
**替代方案**：FIFO（先进先出）或 LIFO（后进先出），券商实际算法可能有差异。

### 5. orderid/tradeid 用纳秒时间戳前缀
**为什么**：重启进程后 `self.order_count=0` 重置，跟 SQLite 里 UNIQUE 约束冲突。  
**格式**：`PAPER-1788764081269025-000007`

### 6. 持仓只算买入的成本（不混入卖出）
**SQL 公式**：
```sql
buy_cost  = SUM(price*volume WHERE direction='多')
buy_volume = SUM(volume WHERE direction='多')
avg_price = buy_cost / buy_volume
```
不是简单的 `net_cashflow / net_volume`——后者会把"卖出的回收"也当成本。

## 安全考虑

| 层 | 措施 |
|---|---|
| Secret | TradingView 和 webhook gateway 共享 secret env 变量 |
| 幂等 | event_id 是 TradingView 时间戳 + ticker 唯一，重复推送不会双开仓 |
| 持仓限额 | 单笔最大 10000 股（env 调） |
| 日上限 | 100 笔/天（env 调） |
| 写隔离 | 全部 sqlite3.write + 显式 transaction |
| 风控 | T+1 / 涨跌停 / 停牌 都**没**做（PoC 简化） |

## 性能

| 操作 | 耗时 |
|---|---|
| 推一条 alert | < 50ms |
| 查询 /positions | < 10ms |
| 拉 tushare 891 bars（一只股 3 年日线）| ~1.5s |
| vnpy 回测 3 只股 5 参数 × 2 策略（30 次）| ~12s |

并发：当前 webhook gateway 是单进程同步，理论 100 alert/s 内无压力。生产环境要换 uvicorn workers + 消息队列。
