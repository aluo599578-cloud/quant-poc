# 给 Claude Desktop 用户的 MCP 配置说明

## 1. 修改 ABS_PATH_TO_QUANT_POC

把 `ABS_PATH_TO_QUANT_POC` 替换成你的实际路径，例如：

**Windows**:
```json
{
  "mcpServers": {
    "quant-research": {
      "command": "python",
      "args": ["C:/Users/YourName/Desktop/quant-poc/mcp_quant_server.py"],
      "cwd": "C:/Users/YourName/Desktop/quant-poc",
      "env": {
        "TUSHARE_TOKEN": "your_real_token_here"
      }
    }
  }
}
```

**macOS / Linux**:
```json
{
  "mcpServers": {
    "quant-research": {
      "command": "python",
      "args": ["/Users/yourname/quant-poc/mcp_quant_server.py"],
      "cwd": "/Users/yourname/quant-poc",
      "env": {
        "TUSHARE_TOKEN": "your_real_token_here"
      }
    }
  }
}
```

## 2. 获取 tushare token

访问 https://tushare.pro 注册账号 → 个人信息 → 接口 TOKEN → 复制 32 位字符串

免费用户每天 200 次 API 调用，足够回测 3-5 只股。pro 用户更多。

## 3. 合并到 Claude Desktop 配置

**Windows**: 编辑 `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

把上面示例里的 `mcpServers` 合并到现有的 `mcpServers` 里。

## 4. 安装 Python 依赖

```bash
cd /path/to/quant-poc
pip install -r requirements.txt
```

## 5. 重启 Claude Desktop

工具列表里会出现 10 个 quant_* 工具：

- `quant_run_backtest` - 单股回测
- `quant_scan_ma_params` - 扫描均线参数
- `quant_scan_multi_stocks` - 多股票扫描
- `quant_generate_pine_script` - 生成 TradingView Pine Script
- `quant_get_top_results` - 拉取历史回测 Top N
- `quant_validate_strategy` - 验证策略代码
- `quant_run_strategy` - 运行自定义策略
- `quant_scan_strategy_params` - 异步参数扫描（带进度）
- `quant_run_walk_forward` - walk-forward 验证
- `quant_simulate_stop_loss` - 模拟止损

## 6. 验证

跟 Claude 说：

> "用 quant_run_backtest 跑一下 002180 纳思达的双均线 (5,20) 回测"

Claude 会调用工具，回测完成后给你看 Sharpe / 最大回撤 / 收益等指标。

## 7. 常见问题

**Q: Tushare token 错了怎么办？**
A: 会报 `tushare token 无效`，检查 token 字符串。

**Q: Python 没找到？**
A: 改 `command` 为完整路径，比如 `"C:/Python311/python.exe"` 或 `"/usr/bin/python3"`。

**Q: mcp 包没装？**
A: `pip install "mcp>=1.27,<2"`

**Q: 工具列表是空的？**
A: 看 Claude Desktop 日志：`%APPDATA%\Claude\logs` (Windows) 或 `~/Library/Logs/Claude` (macOS)。
