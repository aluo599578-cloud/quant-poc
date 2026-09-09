# A 股量化交易 PoC（TradingView → Webhook → Paper Engine → Dashboard）

> 一个端到端可跑的 PoC：把 TradingView 的 alert 通过 webhook 推到自己服务器，本地模拟撮合，Streamlit 仪表盘实时可视化。  
> 验证"A 股能不能跑通这条链路"的技术可行性，**不接真实券商、不产生 alpha**。

![Architecture](docs/screenshots/architecture.png)

## 🚀 立刻能用

| 你想干什么 | 看什么 |
|---|---|
| 看回测结果，**不想装任何东西** | 直接看 [`release/quant-dashboard-static.html`](release/quant-dashboard-static.html) — 双击浏览器打开 |
| 自己跑回测 | 跳到下方 [⚡ 5 分钟跑起来](#⚡-5-分钟跑起来) |
| 接入 Claude Desktop / Claude Code | 看 [`release/INSTALL_MCP.md`](release/INSTALL_MCP.md) |
| 看发布清单 | [`release/RELEASE_CHECKLIST.md`](release/RELEASE_CHECKLIST.md) |

## ⚠️ 重要声明

**本项目仅供学习研究，不构成任何投资建议**。所有策略在实盘前必须经过 walk-forward、模拟盘观察和人工审核。A 股市场过去表现不代表未来收益。

## 🎯 这个项目解决什么

TradingView 是 A 股最好的图表工具，但没有现成的"alert → 模拟下单 → 看 P&L"开源链路能跑通（A 股方向的桥都跑加密/外汇）。本项目：

- 自己写一个 **FastAPI 网关**接收 TV webhook
- 写一个 **vnpy 风格的 Paper Engine** 做 A 股模拟撮合
- 写一个 **Streamlit 仪表盘**看回测结果 + 实时持仓
- 用 **tushare** 拿真实 A 股日线做回测

跑通 8 项验收：买卖、错 secret 拒绝、同 event_id 幂等、P&L 计算正确、SQLite 持久化、风控超量拒绝。

## ⚡ 5 分钟跑起来

```bash
# 1. 安装
pip install -r requirements.txt

# 2. 启动 webhook 网关
QPOC_SECRET=your-secret python -m uvicorn app.webhook_gateway:app --port 8765

# 3. 推一条 alert 进去（另一个终端）
curl -X POST http://127.0.0.1:8765/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your-secret",
    "event_id": "tv-001",
    "action": "buy",
    "symbol": "002180.SZ",
    "price": 25.30,
    "volume": 500,
    "strategy": "ema-cross-5-30"
  }'

# 4. 看效果
curl http://127.0.0.1:8765/positions

# 5. 启动 dashboard（另一个终端）
streamlit run dashboard.py --port 8501
# 浏览器开 http://127.0.0.1:8501，切到 "Webhook 实时" tab
```

## 📊 跑过的回测结果（30 次扫描）

策略：双均线（5 SMA × 30 SMA 金叉死叉），含 MA200 趋势过滤对照

| 代码 | 名称 | 最佳策略 | 总收益 | Sharpe | 回撤 |
|---|---|---|---:|---:|---:|
| 002180 | 纳思达 | DoubleMa (5,30) | +10.34% | +0.32 | -15.94% |
| 000100 | TCL 科技 | DoubleMa+MA200 (10,60) | +0.24% | +0.07 | -1.14% |
| 688122 | 西部超导 | DoubleMa (10,60) | **+38.54%** | +0.37 | -62.21% |

> **核心发现**：双均线在 2023-2026 的 A 股只能做到"少亏"或"小赚"，没有一个 Sharpe > 0.5 的策略。这是策略本身的问题，不是框架的问题。

## 🏗️ 架构

```
TradingView Pine Script alert
  ↓ HTTPS POST JSON {secret, event_id, action, symbol, price, volume}
FastAPI 网关 (app/webhook_gateway.py)
  ├─ 校验 secret / 持仓限额 / 日上限
  ├─ 幂等：同 event_id 直接返回 duplicate
  └─ 兼容 vt_symbol：.SZ/.SH (TV 风格) 和 .SZSE/.SSE (vnpy 风格)
       ↓
Paper Engine (app/paper_engine.py)
  ├─ 立即按 alert 价格成交（市价单模拟）
  ├─ 加权平均成本 + 已实现/未实现 P&L
  ├─ 纳秒前缀的 PAPER-/TRADE- ID 避免 UNIQUE 冲突
  └─ SQLite 持久化（events / orders / trades / positions）
       ↓
REST 查询端点（同时给 dashboard 用）
  /health /account /positions /trades /events
       ↓
Streamlit Dashboard (dashboard.py)
  ├─ Tab 1: 组合扫描（多股同参数对比 + 收益柱状图）
  ├─ Tab 2: 单股深度（K 线 + 净值 + 9 个核心指标）
  ├─ Tab 3: 历史结果（30 次扫描的散点图）
  └─ Tab 4: Webhook 实时（直接读 SQLite）
```

## 📁 项目结构

```
quant-poc/
├── app/
│   ├── paper_engine.py         # A 股模拟撮合引擎（vnpy 对象 + SQLite）
│   └── webhook_gateway.py      # FastAPI 网关（secret/幂等/风控）
├── dashboard.py                # Streamlit 交互式仪表盘（4 Tab）
├── dashboard_demo.py           # 自动跑演示版
├── dashboard_demo_v2.py        # v2 演示版（带 Webhook Tab）
├── backtest_3stocks.py         # 单策略回测（5/30 双均线）
├── backtest_scan.py            # 30 次扫描（5 参数 × 3 股 × 2 策略）
├── push_demo_alerts.py         # 推 7 条 alert 验证完整链路
├── export_static_report.py     # 导出 HTML 离线报告
├── tests/
│   └── e2e_smoke.py            # 8 项端到端验收
├── docs/                       # 架构 + 截图 + 接入文档
├── data/                       # .gitkeep（运行时生成 quant-poc.db）
└── requirements.txt
```

## 🛠️ 技术栈

| 层 | 选型 | 原因 |
|---|---|---|
| 网关 | FastAPI + Pydantic | 异步、类型校验、自动 Swagger |
| 撮合 | 自写 + vnpy 对象 | vnpy 是 A 股生态标准，自写避免依赖券商 |
| 数据 | tushare | 真实 A 股日线（复权/分红处理过） |
| 回测 | vnpy `BacktestingEngine` | 事件驱动，跟实盘行为一致 |
| 数据库 | SQLite | 零配置，够用，纳秒前缀 ID |
| 前端 | Streamlit + Plotly | 上手快、交互式、A 股开源项目主流 |
| 行情 | (计划) 富途 OpenD | 下一阶段接入真实账户 |
| LLM 接口 | MCP server（mcp_quant_server.py）| 让 Claude/OpenClaw 调用 6 个量化工具 |

## 🚀 接入富途（计划中，见 [docs/FUTU_INTEGRATION.md](docs/FUTU_INTEGRATION.md)）

把 `PaperEngine.submit` 换成 `broker_futu.BrokerFutu.submit`，调用 futu-api 下单。下一步：
1. 安装富途牛牛客户端（≥10.4.6408）
2. 开通量化交易权限
3. 跑 `OpenD-GUI.exe`（解锁交易密码）
4. 装 `futu-api>=10.4.6408`
5. 切换到模拟账户，先用 1 只股做 paper trading 验证

## 🤖 LLM / MCP 接入（详见 [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) 和 [docs/OPENCLAW_INTEGRATION.md](docs/OPENCLAW_INTEGRATION.md) 和 [docs/MULTI_AGENT.md](docs/MULTI_AGENT.md)）

### 方式 A：MCP server（Claude Desktop / Claude Code）

```bash
pip install "mcp>=1.27,<2"
python mcp_quant_server.py
python tests/test_mcp_server_v2.py   # 验证
```

### 方式 B：OpenClaw 工具插件（推荐，跟 OpenClaw agent 集成）

```bash
cd .openclaw-plugin
node node_modules/typescript/bin/tsc -p tsconfig.json
openclaw plugins build --entry ./dist/index.js
openclaw plugins install . --link --force --accept-capabilities
```

OpenClaw 插件已安装：`Status: loaded` ✅

### 方式 C：多 Agent 隔离（3 只股各自一个 agent）

```bash
# 一键重建
powershell -ExecutionPolicy Bypass -File setup_agents.ps1

# 使用
openclaw agent --agent quant-002180 -m "找出过去 2 年最好的双均线参数"
openclaw agent --agent quant-688122 -m "walk-forward 验证当前策略"
openclaw agent --agent quant-000100 -m "用 boll_channel 试一组新参数"
```

3 个 quant agent 已创建（`quant-002180` / `quant-000100` / `quant-688122`），各自有独立 workspace + IDENTITY + USER。

Claude Desktop / Claude Code / OpenClaw 都能调 10 个工具：`quant_run_backtest` / `quant_scan_ma_params` / `quant_scan_multi_stocks` / `quant_run_strategy` / `quant_scan_strategy_params` / `quant_simulate_stop_loss` / `quant_run_walk_forward` / `quant_generate_pine_script` / `quant_get_top_results` / `quant_validate_strategy`

支持 5 种策略：double_ma, double_ma_trend, atr_rsi, boll_channel, king_keltner。`quant_run_walk_forward` 自动检测过拟合。

`quant_scan_strategy_params` 异步实现 + Node 端 spawn 流式读 stdout + `ctx.onUpdate()` 推流式进度，OpenClaw UI 实时显示「📊 [PROGRESS N] 完成 params=... sharpe=...」。实测 6 个 PROGRESS 事件 + 最终 RESULT 全部成功解析。

## ⚠️ 局限

- **不接真实券商**——paper ledger 是 SQLite 里的虚拟数字
- **不产生 alpha**——回测 TOP 1 策略 Sharpe 0.37，回撤 -62%，不如手动
- **不是产品**——没风控/合规/稳定运行保障
- **2018-2022 没测试**——所有回测都在 2023-2026，可能过拟合

## 📝 引用

| 借鉴 | 来源 |
|---|---|
| 整体 dashboard 布局 | [zinan92/backtest](https://github.com/zinan92/backtest) |
| Paper Engine 设计 | [vnpy](https://github.com/vnpy/vnpy) 标准对象 |
| TradingView webhook 协议 | [TradingView 官方文档](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/) |
| 风险调整指标定义 | [Investopedia - Sortino/Calmar](https://www.investopedia.com/terms/s/sortinoratio.asp) |

## 📄 License

MIT
