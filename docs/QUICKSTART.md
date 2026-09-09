# 5 分钟跑起来

## 前置条件

- Python 3.10+
- Windows / macOS / Linux 都可以
- tushare token（免费注册：https://tushare.pro）

## 步骤 1：克隆和安装

```bash
git clone https://github.com/your-username/quant-poc.git
cd quant-poc
pip install -r requirements.txt
```

## 步骤 2：配置 tushare token

```bash
# Linux / macOS
export TUSHARE_TOKEN=your_token_here

# Windows PowerShell
$env:TUSHARE_TOKEN = "your_token_here"

# Windows CMD
set TUSHARE_TOKEN=your_token_here
```

## 步骤 3：启动 webhook 网关

```bash
# 默认 dev secret，建议生产用 QPOC_SECRET 环境变量覆盖
QPOC_SECRET=my-super-secret python -m uvicorn app.webhook_gateway:app --port 8765
```

成功后会看到：
```
INFO:     Started server process
INFO:     Uvicorn running on http://127.0.0.1:8765
```

测试：
```bash
curl http://127.0.0.1:8765/health
# {"status":"ok","engine":"paper","version":"0.1.0","time":"2026-09-07T12:00:00"}
```

## 步骤 4：推一条 alert

```bash
curl -X POST http://127.0.0.1:8765/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "my-super-secret",
    "event_id": "tv-demo-001",
    "action": "buy",
    "symbol": "002180.SZ",
    "price": 25.30,
    "volume": 500,
    "strategy": "ema-cross-5-30"
  }'
```

应该看到：
```json
{
  "status": "filled",
  "event_id": "tv-demo-001",
  "trade": {"tradeid": "TRADE-...", "orderid": "PAPER-...", ...},
  "account": {"cash": 873850, "market_value": 12650, ...}
}
```

## 步骤 5：查账户和持仓

```bash
curl http://127.0.0.1:8765/account
curl http://127.0.0.1:8765/positions
curl http://127.0.0.1:8765/trades
curl http://127.0.0.1:8765/events
```

## 步骤 6：启动 dashboard

新开一个终端：
```bash
streamlit run dashboard.py --port 8501
```

浏览器开 `http://127.0.0.1:8501`，4 个 tab：
1. **组合扫描** — 配置参数跑批量回测
2. **单股深度** — 详细 K 线 + 净值 + 9 个指标
3. **历史结果** — 之前 30 次扫描的散点图
4. **Webhook 实时** — 看你刚推的 alert 在不在

## 步骤 7（可选）：跑回测

```bash
# 单策略回测（一只股一组参数）
python backtest_3stocks.py

# 30 次扫描（5 参数 × 3 股 × 2 策略）
python backtest_scan.py

# 导出离线 HTML 报告
python export_static_report.py
# 双击打开 C:\Users\18566\Desktop\深度分析报告\quant-dashboard-static.html
```

## 步骤 8（可选）：端到端测试

```bash
python tests/e2e_smoke.py
```

预期 8 项全部 OK：
```
=== 1) health ===           ok
=== 2) buy 000001.SZ ... === ok
=== 3) 错误 secret 应被拒绝 === ok
=== 4) 同 event_id 重发应幂等 === ok
=== 5) P&L 计算正确 ===       ok
=== 6) 风控超量 ===          ok
=== 7) SQLite 能查 ===       ok
=== 8) trades 端点 ===       ok
ALL CHECKS PASSED
```

## 常见问题

**Q: 端口被占用？**
```bash
# Windows
netstat -ano | findstr :8765
taskkill /F /PID <pid>

# macOS / Linux
lsof -ti:8765 | xargs kill -9
```

**Q: SQLite 锁住不能删？**
先停 webhook 网关进程再删 `data/quant-poc.db*`

**Q: tushare 数据拉不到？**
检查 `TUSHARE_TOKEN` 环境变量；tushare 免费账户有 200 次/分钟限制。

**Q: 怎么接入 TradingView？**
参考 [docs/FUTU_INTEGRATION.md](FUTU_INTEGRATION.md) 的 webhook 配置；或用 `push_demo_alerts.py` 模拟推送。
