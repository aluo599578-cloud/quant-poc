# OpenClaw 集成

> 把 10 个量化工具做成 OpenClaw 工具插件，让 LLM 在 OpenClaw 聊天里直接调用。

## 架构

```
你 (Telegram/飞书/...) → OpenClaw Agent → quant-research 插件
                                                ↓
                                    spawnSync("python", ["-c", "..."])
                                                ↓
                                    quant_core.py
                                                ↓
                                    stdout: JSON 结果
```

**为什么用 spawnSync 而不是 MCP stdio？**

- **MCP stdio**：JSON-RPC 协议走 stdout，vnpy 内部 `print()` 会污染协议导致 UnicodeDecodeError（已修过 redirect_stdout，但每次都要包）
- **spawnSync**：Node 调 Python 子进程，stdout 只承载 JSON 干净结果，vnpy 的 log 走 stderr 不污染
- **完全控制超时**：spawnSync 支持 timeout 120s，回测超时直接杀进程

## 已安装的插件

```
openclaw plugins list | grep quant
│ A 股量化研究  │ quant-research  │ openclaw │ enabled  │ ~\\Desktop\\quant-poc\\.o...w-plugin\\dist\\index.js  │ 0.1.0 │
```

**状态**：`Status: loaded` ✅
**安装方式**：`--link` 软链（`C:\Users\18566\Desktop\quant-poc\.openclaw-plugin` ↔ `~/.openclaw/extensions/`），代码改动自动生效

## 10 个工具

| 工具 | 用途 |
|---|---|
| `quant_run_backtest` | 单次回测（双均线，兼容）|
| `quant_scan_ma_params` | 双均线参数网格搜索 |
| `quant_scan_multi_stocks` | 多股横向对比 |
| `quant_run_strategy` | 5 种策略通用入口 |
| `quant_scan_strategy_params` | 任意策略网格搜索 |
| `quant_simulate_stop_loss` | stop loss 效果估算 |
| `quant_run_walk_forward` | 过拟合检测 |
| `quant_generate_pine_script` | Pine Script v6 生成 |
| `quant_get_top_results` | 读 30 次扫描缓存 |
| `quant_validate_strategy` | 风险评级 |

每个工具都返回 dict/str，OpenClaw LLM 拿来直接解读。

## 安装过程（重现）

如果你要重装或者在另一台机器上装：

```bash
# 1. 编译 TypeScript
cd C:\Users\18566\Desktop\quant-poc\.openclaw-plugin
node node_modules/typescript/bin/tsc -p tsconfig.json
node node_modules/typescript/bin/tsc -p tsconfig.json

# 2. 自动生成 manifest 工具列表
openclaw plugins build --entry ./dist/index.js

# 3. 安装（link 模式 = 软链，代码改动自动生效）
openclaw plugins install . --link --force --accept-capabilities

# 4. 重启 OpenClaw gateway
# 5. 验证
openclaw plugins list
# 应看到 "A 股量化研究  quant-research  openclaw  enabled"
```

## LLM 实际使用流程

```
你 (Telegram 消息): 找出 688122 西部超导过去 2 年最好的双均线参数
LLM (OpenClaw):
  → quant_scan_ma_params(symbol="688122.SH", fast_range=[5,10,15], slow_range=[20,30,60])
  ← [5 组结果按 Sharpe 排序]
LLM: TOP 1 是 (10, 60)，Sharpe 0.37，收益 +38.54%，回撤 -62%。
  建议加 MA200 过滤试试。

你: 加上 MA200 重做
LLM:
  → quant_scan_ma_params(symbol="688122.SH", use_trend_filter=True)
  ← [5 组结果]
LLM: 加 MA200 后 (10, 60) 收益降到 +17% 但回撤 -23%（砍半）。

你: 用 walk-forward 验证
LLM:
  → quant_run_walk_forward(strategy_type="double_ma_trend", params={...})
  ← {"train": {...}, "test": {...}, "verdict": "🟠 MODERATE OVERFIT"}
LLM: train Sharpe 0.65 → test Sharpe 0.42，衰减 35% → 🟠 中度过拟合。

你: 帮我看看 5% 止损
LLM:
  → quant_simulate_stop_loss(stop_loss_pct=0.05)
  ← {"baseline_dd": -8.5%, "with_sl_dd": -5%, "improvement": "3.5%"}
LLM: 加 5% 止损后回撤从 -8.5% 降到 -5%，但收益可能少 15-20%。

你: 那生成 Pine Script
LLM:
  → quant_generate_pine_script(strategy_type="double_ma_trend", use_trend_filter=True)
  ← Pine Script v6 文本
LLM: 把下面代码复制到 TradingView Pine Editor（替换 YOUR_SECRET 为你 webhook 的 secret）：

```pine
//@version=6
strategy("DoubleMA(5,30)+MA200", overlay=true, ...)
```

你: 看起来不错，给个评级
LLM:
  → quant_validate_strategy(stats_json="...")
  ← "🟡 可以上 paper，但仓位别大（<30% 资金）"
```

## 关键设计决定

| 选项 | 选了什么 | 为什么 |
|---|---|---|
| 集成方式 | OpenClaw 工具插件 | 比 MCP 简单（不需要配 server），且 OpenClaw 本身就是 LLM 入口 |
| 工具实现 | `spawn`（流式）替代 `spawnSync`（同步）| Node 读 stdout stream 实时推 onUpdate，避免等 60s 才返回 |
| 流式协议 | Python stdout 多行 JSON：`PROGRESS:{...}` + `RESULT:{...}` | 简单、容错（行截断不破坏） |
| Monkey-patch 进度 | Python 端 patch `_run_backtest_core` | 无需改 quant_core.py 业务代码 |
| 参数 schema | typebox（OpenClaw SDK）| 自动生成 JSON Schema 给 LLM |
| 错误处理 | Python exit code + stderr 上抛 | 简单可调试 |
| 工具名前缀 | `quant_*` | 避免和 OpenClaw 内置工具冲突 |
| 安装模式 | `--link` | 改代码不用重装 |
| stderr 解码 | `errors="replace"` | vnpy 偶尔会输出非 utf-8 字符，spawn 不挂 |

## 故障排查

```bash
# 1. 插件未加载
openclaw plugins list | grep quant-research
# 看不到 → openclaw doctor

# 2. Python 调不通
# 设环境变量指定 Python：
set QUANT_PYTHON=C:\Python311\python.exe
# 然后重装：openclaw plugins install . --link --force

# 3. 工具调用失败
# OpenClaw gateway 日志（默认 ~\.openclaw\logs\）：
tail -f ~/.openclaw/logs/gateway.log

# 4. 流式进度不显示
# 验证流式协议：node tests/test_node_stream.mjs
# 应看到 6 个 PROGRESS 事件
```

## 流式进度（v2）

`quant_scan_strategy_params` 工具**流式返回进度**，OpenClaw UI 实时显示。

**协议**（Python stdout）：
```
PROGRESS:{"msg":"完成 params={...} sharpe=0.318","result":{...}}
PROGRESS:{"msg":"完成 params={...} sharpe=-0.261","result":{...}}
... (每跑一个组合发一行)
RESULT:[{"params":{...},"sharpe_ratio":0.318,...}, ...]  ← 最终
```

**Node 端**：
- `spawn()` 异步启动 Python，stdout stream 按行解析
- 每收到 `PROGRESS:` 行就调 `ctx.onUpdate({content: [...], details: {...}})`
- `onUpdate` 是 `ToolPluginExecutionContext` 提供的 streaming 通道
- 收到 `RESULT:` 行解析为最终返回值，resolve promise

**OpenClaw UI 行为**：
- LLM 看到的是 `progress_count: 1, sharpe: 0.318, params: {...}`（details）
- 用户在 UI 看到的是 `📊 [PROGRESS 1] 完成 params=... sharpe=0.318`（content）
- 类似 MCP `ctx.report_progress()`

**端到端测试**：
```bash
python tests/test_streaming.py     # Python asyncio 验证
node tests/test_node_stream.mjs   # Node spawn 验证
```

**实测**（002180.SZ, 3x2 网格）：
```
📊 [PROGRESS 1] 完成 params={"fast_window":3,"slow_window":20} sharpe=-0.318
📊 [PROGRESS 2] 完成 params={"fast_window":3,"slow_window":30} sharpe=0.012
... (4 more)
✅ RESULT: 3 个 TOP N (按 Sharpe 排序)
```

## 后续可扩展

- [ ] **加 streaming**：Python 输出多行 JSON（每行 = 一次进度），Node stream 推到 OpenClaw
- [ ] **缓存**：tools 9 (`get_top_results`) 已经在读 `data/backtest_scan.json`；可以加 1 小时自动重新跑 scan
- [ ] **多 agent 隔离**：每个 OpenClaw agent 跑自己的 quant-poc 实例（不同 `~/.openclaw-N`）
- [ ] **接富途**：加 `quant_get_quote(symbol)` 实时行情（broker_futu.py 已就绪）

## 文件位置

```
C:\Users\18566\Desktop\quant-poc\
├── quant_core.py              # Python 核心（被插件 + MCP server 共用）
├── mcp_quant_server.py        # MCP 备用入口（Claude Desktop 用）
├── .openclaw-plugin\           # OpenClaw 工具插件源码
│   ├── openclaw.plugin.json
│   ├── package.json
│   ├── tsconfig.json
│   ├── src\index.ts           # 10 个工具定义
│   ├── src\index.test.ts
│   └── dist\index.js          # 编译后（OpenClaw 实际加载这个）
└── data\backtest_scan.json    # 工具 9 读的缓存
```
