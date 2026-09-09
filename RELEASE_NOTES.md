# Release Notes — v0.1.0

> 发布日期：2026-09-09
> GitHub Release: https://github.com/alor27/quant-poc/releases/tag/v0.1.0

## 🎯 这个版本能做什么

- **回测**：3 只 A 股（002180 / 000100 / 688122）× 72 组参数组合
- **模拟盘**：PaperEngine + SQLite 模拟撮合（不会真实下单）
- **可视化**：Streamlit Dashboard（4 Tab）+ 单文件静态 HTML 报告
- **MCP 集成**：10 个工具，Claude Desktop / Claude Code 可直接调用
- **OpenClaw 集成**：10 个 TypeScript 工具插件
- **Webhook**：TradingView → FastAPI 网关，secret 校验 + 幂等去重

## 📊 关键回测结果（2023-01-01 ~ 2026-09-09）

| 股票 | 最佳策略 | 收益 | Sharpe | 最大回撤 |
|---|---|---|---|---|
| 002180 纳思达 | (5,30) + 5% 止损 | +68% | +0.40 | -96% |
| 000100 TCL | (10,60) + MA200 | +1.2% | +0.07 | -5.7% |
| 688122 西部超导 | (10,30) + MA200 + 5% 止损 | +212% | +0.61 | -134% |

⚠️ 72 次回测中没有任何参数组在 3 只股上都 Sharpe > 0。

## 📥 下载

- **`quant-poc-release.zip`** (1.18 MB) — 完整项目 + Windows 一键安装脚本
- **`Source code (zip)`** — git archive 源码（GitHub 自动生成）
- **`Source code (tar.gz)`** — git archive 源码（GitHub 自动生成）

## 🚀 快速开始

### 选项 A：只看结果（不需要 Python）

下载 `quant-dashboard-static.html`（38 KB）→ 双击浏览器打开

### 选项 B：自己跑（Windows）

1. 下载 `quant-poc-release.zip` 解压
2. 双击 `install_windows.bat`
3. 设置环境变量 `TUSHARE_TOKEN=你的token`（去 https://tushare.pro 免费注册）
4. 双击 `run_backtest.bat`

### 选项 C：用 Claude Desktop

参考 [`release/INSTALL_MCP.md`](INSTALL_MCP.md)

## ⚠️ 风险声明

本项目**仅供学习研究**。回测结果基于历史数据，不代表未来收益。所有策略在实盘前必须经过 walk-forward 验证、模拟盘观察和人工审核。**作者不对任何基于本项目做出的投资决策负责**。

## 🐛 已知问题

- 688122 回撤 -134% 在心理上极难承受，需要仓位管理（>20% 单股上限）
- vnpy 4.4.0 `BacktestingEngine.load_data()` 会清空 `history_data`，已绕过
- futu-api 10.10+ TrdEnv 是字符串不是 enum，已在 `app/broker_futu.py` 处理
- tushare 免费版 200 次/天，跑 72 次回测 = 约 250 次 API 调用，建议 pro 版

## 📚 文档

- [README.md](README.md) — 项目总览
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — 5 分钟上手
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 系统架构
- [docs/API.md](docs/API.md) — Webhook API
- [docs/FUTU_INTEGRATION.md](docs/FUTU_INTEGRATION.md) — 富途 OpenD 集成
- [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) — MCP 集成
- [docs/OPENCLAW_INTEGRATION.md](docs/OPENCLAW_INTEGRATION.md) — OpenClaw 集成
- [docs/MULTI_AGENT.md](docs/MULTI_AGENT.md) — 多 Agent 研究

## 📜 License

MIT License — 见 [LICENSE](LICENSE) 文件
