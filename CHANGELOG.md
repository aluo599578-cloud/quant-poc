# Changelog

## v0.1.0 (2026-09-07)

首个可运行版本。

### 功能
- TradingView webhook 网关（FastAPI + secret 校验 + 幂等 + 风控）
- A 股模拟撮合引擎（vnpy 对象 + SQLite 持久化）
- vnpy 30 次策略扫描（5 参数 × 3 股 × 2 策略）
- Streamlit 仪表盘（4 Tab：组合扫描 / 单股深度 / 历史结果 / Webhook 实时）
- 风险调整指标（Sortino / Calmar / 年化波动率）
- 富途券商适配器骨架（app/broker_futu.py + mock 测试）
- 端到端 smoke test（8 项验收）
- 富途 broker mock 测试（6/6 通过）

### 已知问题
- 没有接真券商（paper ledger）
- 没有 walk-forward 验证（30 次回测全部 in-sample）
- 没有 T+1 / 涨跌停 / 停牌 真实建模
- backtest 用 vnpy 默认支持做空（A 股实际不能做空）
- max_ddpercent 的"%"显示（已是小数，dashboard 已加注释）
- webhook 网关单进程同步，>100 alert/s 会卡

### 下一个版本
- 接入富途 OpenD（生产文档在 docs/FUTU_INTEGRATION.md）
- 加 walk-forward 验证（2023-2024 训练 + 2025-2026 验证）
- 加 stop loss + ATR 仓位管理
- 接 MCP server（让 LLM 生成/调优策略）
