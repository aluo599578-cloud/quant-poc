# 🚀 LEAN MIGRATION PLAN

> 决策日期：2026-09-14
> 状态：**进行中** — 从 vnpy + Python 全面迁移到 QuantConnect Lean + C#

## 决策原因（不可逆）

经用户确认：**完全替换** QuantConnect Lean（21.6k stars，工业级量化框架）。

- quant-poc 已冻结到 `legacy-quant-poc` 分支（73 文件，全部历史）
- main 分支从今天起只接收 Lean 迁移工作
- 不再继续推进 vnpy/Python 生态

## 时间线（2-3 个月全职）

| 阶段 | 任务 | 时间 | 状态 |
|---|---|---|---|
| **Phase 0** | Lean 编译 + 跑通自带 demo | 1 周 | ⏳ Lean clone 进行中 |
| **Phase 1** | 接 tushare A 股 data source | 1 周 | ❌ |
| **Phase 2** | 接富途 OpenD brokerage | 2-3 周 | ❌ |
| **Phase 3** | 迁移 6 个 Python 策略到 C# | 2 周 | ❌ |
| **Phase 4** | 重建 MCP 集成（如果可能） | 1 周 | ❌ |
| **Phase 5** | 重建 OpenClaw 集成 | 1 周 | ❌ |
| **Phase 6** | 重建 Dashboard | 1-2 周 | ❌ |
| **Phase 7** | 端到端 + 实盘测试 | 1 周 | ❌ |

## 关键决策

1. **语言**：C# (Lean 主) + Python (PythonNet)
2. **回测引擎**：Lean Algorithm Framework
3. **数据源**：tushare (新写 Lean DataSource)
4. **券商**：富途 OpenD (新写 Lean Brokerage)
5. **MCP**：⚠️ 暂缓（C# 官方 MCP SDK 未发布）
6. **OpenClaw**：通过 Python 桥接 (subprocess)

## 回退方案

如果 Lean 迁移在 6 周后仍无法跑通 A 股回测：
- 切回 `legacy-quant-poc` 分支
- 继续用 quant-poc 跑回测
- 损失：1-2 周工作量

## 不再做的事

- ❌ 继续在 vnpy 上开发新策略
- ❌ 修 quant-poc 的 bug
- ❌ 接更多数据源（tushare 够用）
- ❌ 加 Streamlit 新功能
- ❌ 加 MCP 新工具

## 仍然在做的事

- ✅ 跑 tushare A 股回测（直到 Lean 跑通）
- ✅ 维护现有 webhook gateway（接收 TradingView alert）
- ✅ 维护 paper engine（直到 Lean brokerage 跑通）

## 关键问题（必须解决）

1. **Lean 接富途 OpenD** — QuantConnect 社区有没有现成 brokerage？
2. **A 股实时数据** — Lean 默认接 IB 实时但贵，tushare 免费但要自己写 data source
3. **MCP C# 集成** — Anthropic 没出官方 C# MCP SDK（截至 2026-09）
4. **OpenClaw 桥接** — OpenClaw 是 TypeScript，Lean 是 C#，用 Python 桥是过渡方案

## 沟通原则

- **不再劝回**——用户已确认 5 次
- Lean 卡住就回来报告，不死磕
- legacy-quant-poc 分支**永久保留**作为参考
