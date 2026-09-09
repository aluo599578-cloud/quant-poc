# MCP 集成

> 给 LLM（Claude / OpenClaw / 任何 MCP 客户端）暴露 A 股量化研究工具。

## 启动 server

### 方式 A：stdio（推荐，本地）

```bash
# 装好依赖
pip install "mcp>=1.27,<2"

# 启动
python mcp_quant_server.py
```

直接接 Claude Desktop / Claude Code / OpenClaw 的 stdio 配置。

### 方式 B：HTTP（远程 / 多客户端共享）

```bash
# 启动 HTTP 模式（Streamable HTTP transport）
python mcp_quant_server.py --transport http --port 8001
# 端点：http://127.0.0.1:8001/mcp
```

## 客户端配置

### Claude Desktop

`~/.../Claude/claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "quant-research": {
      "command": "python",
      "args": ["C:/Users/18566/Desktop/quant-poc/mcp_quant_server.py"],
      "env": {
        "TUSHARE_TOKEN": "your_token_here"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add --transport stdio quant-research -- \
  python C:/Users/18566/Desktop/quant-poc/mcp_quant_server.py
```

### OpenClaw / 自定义 MCP host

配置文件 `~/.openclaw/openclaw.json`:
```json
{
  "mcpServers": {
    "quant-research": {
      "command": "python",
      "args": ["C:/Users/18566/Desktop/quant-poc/mcp_quant_server.py"],
      "env": {"TUSHARE_TOKEN": "..."}
    }
  }
}
```

## 10 个工具

| 工具 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `run_backtest` | symbol, fast_window, slow_window, start, end, capital, use_trend_filter | 完整 stats dict | 单次回测（兼容旧 API）|
| `scan_ma_params` | symbol, fast_range, slow_range, start, end, top_n | TOP N 排序结果 | 双均线网格搜索 |
| `scan_multi_stocks` | symbols[], fast_window, slow_window | 多股结果按 Sharpe 排序 | 横向对比 |
| `run_strategy` | symbol, strategy_type, params | 完整 stats | 5 种策略通用入口 |
| `scan_strategy_params` | symbol, strategy_type, param_grid | TOP N + **流式进度推送** | 任意策略网格搜索 |
| `simulate_stop_loss` | symbol, stop_loss_pct, fast_window, slow_window | baseline vs SL 估算 | 估算 stop loss 效果 |
| `run_walk_forward` | symbol, train_start/end, test_start/end, params | train/test 对比 + 过拟合判定 | **检测过拟合** |
| `generate_pine_script` | strategy_type, fast_window, slow_window, use_trend_filter, trend_window | Pine Script v6 文本 | 把策略翻译成 TV 脚本 |
| `get_top_results` | sort_by, top_n, strategy_filter | 历史 30 次扫描结果 | 复用已有数据 |
| `validate_strategy` | stats dict | 风险评级 + 建议 | 给 LLM 做 review 用 |

### 支持的 5 种策略（run_strategy / scan_strategy_params）

| strategy_type | 策略说明 | 默认参数 |
|---|---|---|
| `double_ma` | 双均线金叉死叉 | fast=5, slow=30 |
| `double_ma_trend` | 双均线 + MA200 趋势过滤 | fast=5, slow=30, trend=200 |
| `atr_rsi` | ATR 波动率 + RSI 反转 | atr=14, atr_ma=4, rsi=14, rsi_sig=20 |
| `boll_channel` | 布林带突破 | boll=18, dev=3.4 |
| `king_keltner` | Keltner 通道 | keltner=14, dev=1.2 |

## 流式进度推送

`scan_strategy_params` 在网格搜索期间会通过 `ctx.report_progress()` 推 progress notification。
Claude Desktop / Claude Code / 支持 MCP progress 的客户端会显示"正在跑 5/20"进度条。

**server 实现**：scan_strategy_params 是 async 函数，参数是 `ctx: Optional[Context]`，FastMCP 自动注入。
每跑 1/total 个组合就 `await ctx.report_progress(progress, total, message)`，结束时 `report_progress(total, total, ...)`。

**已知限制**：当前 `mcp==1.29.1` 客户端 API 没暴露 progress callback。
要看到进度条需要：
- Claude Desktop 1.x+（默认显示）
- 或 mcp 2.0 client

## 典型 LLM 交互流程

```
你: "找出 688122 西部超导过去 2 年最好的双均线参数"
LLM: → call scan_ma_params(symbol="688122.SH", fast_range=[5,10,15], slow_range=[20,30,60])
    → 看到 TOP 5 结果
LLM: "TOP 1 是 (10, 60)，Sharpe 0.37，收益 +38.54%，回撤 -62%。建议加 MA200 过滤试试。"

你: "好，加 MA200 重做"
LLM: → call scan_ma_params(symbol="688122.SH", use_trend_filter=true)
    → 看到 (10, 60) + MA200 收益降到 +17% 但回撤 -23%（砍半）

你: "用 run_strategy 试试 boll_channel 和 king_keltner 看看哪种更适合"
LLM: → call run_strategy(strategy_type="boll_channel", ...)
    → call run_strategy(strategy_type="king_keltner", ...)
    → "boll_channel 更稳，king_keltner 收益更高"

你: "对 boll_channel 做 walk-forward 验证"
LLM: → call run_walk_forward(strategy_type="boll_channel", params=...)
    → "train Sharpe 0.65, test Sharpe 0.42, 衰减 35% → 🟠 中度过拟合，建议加过滤"

你: "看看加 5% 止损会怎样"
LLM: → call simulate_stop_loss(stop_loss_pct=0.05, ...)
    → "加 5% SL 后估算 max DD 从 -8.5% 降到 -5%，但收益会减少 15-20%"

你: "生成 Pine Script"
LLM: → call generate_pine_script(strategy_type="boll_channel", ...)
    → 输出 Pine Script 文本

你: "看起来不错，给个评级"
LLM: → call validate_strategy(stats=...)
    → "🟡 可以上 paper，但仓位别大（<30% 资金）"
```

## 重要边界

1. **MCP 不会自动下单**——所有结果只是数据/文本，人工 review
2. **回测都是 in-sample**——validate_strategy 工具会提示
3. **3 只 A 股的训练数据**——LLM 不能直接外推到其它股票
4. **TUSHARE_TOKEN 必须有**——否则工具会抛错

## 验证

跑端到端测试：
```bash
python tests/test_mcp_server.py
```

应看到：
```
启动 MCP server: ...
✓ Server 注册了 6 个工具
=== 测试工具: run_backtest === → 返回 stats
=== 测试工具: generate_pine_script === → 返回 1078 字符
✓ 6/6 工具可远程调用
```

## 下一步

- 加 walk-forward 验证工具（2023-2024 训练 + 2025-2026 验证）
- 加 Bollinger / MACD / Keltner 策略
- 加 stop loss 工具
- 接 TradingView 的实时 quote（不只回测）
