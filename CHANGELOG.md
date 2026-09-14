# Changelog

所有 notable 改动都记录在这里。版本号遵循 [Semantic Versioning](https://semver.org/)。

## [v1.0.0] - 2026-09-14

### 🎉 首次公开发行（Public Release）

**完整链路**：TradingView alert → FastAPI webhook → vnpy 撮合 → Paper Engine → Streamlit Dashboard → MCP 工具 → 富途实盘

### ✨ 新增（Features）

#### 核心框架
- `app/webhook_gateway.py` — FastAPI 接收 TradingView alert
- `app/paper_engine.py` — SQLite 模拟撮合引擎（加权平均成本 + 已实现/未实现 P&L）
- `app/broker_futu.py` — 富途 OpenD 适配器（默认模拟盘）
- `quant_core.py` — 6 个 MCP 工具的 Python 核心逻辑
- `mcp_quant_server.py` — MCP server（10 个工具，stdio 协议）

#### Lean 风格策略（12 个 vnpy 策略）
- `strategies/double_ma_lean.py` — 基础双均线
- `strategies/double_ma_trend_filter_lean.py` — 双均线 + MA200 趋势过滤
- `strategies/double_ma_stop_loss_lean.py` — 双均线 + 5% 止损
- `strategies/double_ma_trend_stop_loss_lean.py` — 双均线 + MA200 + 5% 止损
- `strategies/macd_lean.py` — MACD 金叉死叉
- `strategies/rsi_bollinger_lean.py` — RSI + 布林带反转
- `strategies/bollinger_mean_reversion_lean.py` — 布林带均值回归
- `strategies/macd_histogram_lean.py` — MACD 柱状图策略
- `strategies/volume_breakout_lean.py` — 放量突破
- `strategies/atr_trail_stop_lean.py` — ATR 跟踪止损
- `strategies/keltner_breakout_lean.py` — Keltner 通道突破
- `strategies/rsi_divergence_lean.py` — RSI 背离

#### 工具与库
- `lean_style_indicators.py` — Lean 风格 API（5/5 测试通过）：SMA/EMA/RSI/MACD/BB/ATR/MAX/MIN/STD

#### 回测与扫描脚本
- `backtest_3stocks.py` / `backtest_3stocks_lean.py` — 单股回测
- `backtest_scan.py` / `backtest_scan_lean.py` — 30 次参数扫描
- `strategy_with_stoploss.py` / `strategy_param_compare.py` — 止损/参数对比
- `walk_forward_pantum.py` / `walk_forward_all_stocks.py` / `walk_forward_new_strategies.py` — walk-forward 验证

#### 实盘交易
- `live_trading_00700.py` — 腾讯 00700.HK 单股实盘（布林带均值回归）
- `live_trading_multi.py` — 多股实盘（HK Top 5：农行/工行/中行/建行/腾讯）
- SQLite 记录所有 signals / orders / pnl
- 防重复下单（state.json 持久化）

#### 三层筛选 Pipeline
- `quant_screener.py` — A 股沪深 300 量化评分（5 维度：估值/ROE/增长/技术/事件/资金流）
- `quant_screener_hk.py` — HK 股评分（30 只沪深港通标的）
- `batch_openclaw_research.py` — 研报增强
- `run_pipeline.py` — 一键运行三层 pipeline

#### Dashboard
- `dashboard.py` / `dashboard_demo.py` / `dashboard_demo_v2.py` — Streamlit 4 Tab
- `export_static_report.py` — 静态 HTML 报告生成

#### 工具
- `tools/check_futu_env.py` — 富途环境检查
- `tools/package_for_release.py` — 打包 release zip
- `tools/build_static_release_report.py` — 静态报告

#### OpenClaw 集成
- `.openclaw-plugin/` — TypeScript 工具插件（10 个 quant_* 工具）
- `.openclaw-agents/quant-002180` / `quant-000100` / `quant-688122` — 3 个研究 Agent

### 📊 关键数据

| 指标 | 数字 |
|---|---|
| **总 commit** | 13 |
| **代码行** | ~6000 行 |
| **策略数** | 12 |
| **回测数** | 100+ |
| **HK Top Sharpe** | **+2.284**（农业银行）|
| **5 维度评分维度** | 估值/ROE/增长/技术/事件/资金流 |

### 🏆 验证结论

- 002180 / 000100 / 688122 / 688515 / 02522 / 00700 等多股回测
- 4 只股 walk-forward 验证（3 轮测试期）
- Lean 风格 vs 原版 vnpy 风格对照
- 12 个策略跨股票评分

### ⚠️ 已知限制

- **不接真实券商**（paper ledger 是 SQLite 里的虚拟数字）
- **不产生 alpha**（回测 TOP 1 策略 Sharpe 0.5~2.3，回撤 5-50%，不如手动）
- **不是产品**（没风控/合规/稳定运行保障）
- **A 股权限问题**：富途没有 A 股交易权限，quant-poc 主要面向**港股通 + 美股 + 模拟**
- **2018-2022 没测试**（所有回测都在 2023-2026，可能过拟合）

### 📝 文档

- [README.md](README.md) — 项目总览
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — 5 分钟上手
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 系统架构
- [docs/API.md](docs/API.md) — Webhook API
- [docs/FUTU_INTEGRATION.md](docs/FUTU_INTEGRATION.md) — 富途 OpenD 集成
- [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) — MCP 集成
- [docs/OPENCLAW_INTEGRATION.md](docs/OPENCLAW_INTEGRATION.md) — OpenClaw 集成
- [docs/MULTI_AGENT.md](docs/MULTI_AGENT.md) — 多 Agent 研究
- [LEAN_INSPIRED.md](LEAN_INSPIRED.md) — Lean 风格借鉴说明
- [LEAN_MIGRATION.md](LEAN_MIGRATION.md) — Lean 迁移过程记录

### 📜 License

[MIT](LICENSE) — 自由使用、修改、分发
