# 🚀 LEAN MIGRATION PLAN

> 决策日期：2026-09-14
> 状态：**进行中** — 从 vnpy + Python 全面迁移到 QuantConnect Lean

## 决策原因（不可逆）

经用户确认：**完全替换** QuantConnect Lean（21.6k stars，工业级量化框架）。

- quant-poc 已冻结到 `legacy-quant-poc` 分支（73 文件，全部历史）
- main 分支从今天起只接收 Lean 迁移工作
- 不再继续推进 vnpy 生态

## 🚨 重大修正（2026-09-14 11:30）

**我之前的工作量估算完全错了**：

- ❌ 错误：Lean 主语言 C#，6 策略全部要 Python → C# 重写
- ✅ **正确**：Lean 算法**全部用 Python 写**（通过 PythonNet 调 C# 引擎）

证据：`Algorithm.Python/BasicTemplateAlgorithm.py`：
```python
from AlgorithmImports import *
class BasicTemplateAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2013,10, 7)
        ...
```

**修正后时间线 3-5 周**（不是 2-3 月）

| 阶段 | 任务 | 时间 | 状态 |
|---|---|---|---|
| **Phase 0** | Lean 编译 + 跑通 demo | 1-2 天 | ⏳ zip 下载中 |
| **Phase 1** | 接 tushare A 股 data source | 1 周 | ❌ |
| **Phase 2** | 接富途 OpenD brokerage | 1-2 周 | ❌ |
| **Phase 3** | 迁移 6 个 Python 策略（基本是改 API 名字）| 3-5 天 | ❌ |
| **Phase 4** | 集成 MCP（直接复用 Python SDK）| 0.5 天 | ❌ |
| **Phase 5** | 集成 OpenClaw（直接复用 Python 桥接）| 0.5 天 | ❌ |
| **Phase 6** | 重建 Dashboard | 1 周 | ❌ |
| **Phase 7** | 端到端 + 实盘测试 | 1 周 | ❌ |
| **合计** | | **3-5 周** | |

## 关键决策

1. **算法语言**：Python（QCAlgorithm） — 跟 quant-poc 一致，**几乎不用重写策略**
2. **回测引擎**：Lean Engine（C# + PythonNet）
3. **数据源**：tushare (新写 Lean DataSource)
4. **券商**：富途 OpenD (新写 Lean Brokerage)
5. **MCP**：✅ **直接复用** Python MCP SDK
6. **OpenClaw**：✅ **直接复用** Python 桥接

## 回退方案

如果 Lean 迁移在 4 周后仍无法跑通 A 股回测：
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
3. **Lean 自带中文 A 股支持** — Lean 社区有 lean-cli 但 A 股数据要自己接

## 沟通原则

- **不再劝回**——用户已确认
- Lean 卡住就回来报告，不死磕
- legacy-quant-poc 分支**永久保留**作为参考
