# Release Checklist — quant-poc v0.1.0

> 发布给接收方前的最终检查清单。

## ✅ 必须做的

- [x] 排除 `data/quant-poc.db`（运行时数据）
- [x] 排除 `__pycache__` / `.git` / `.venv`
- [x] 排除 `.openclaw-plugin/node_modules` (505 MB)
- [x] 排除 `.openclaw-plugin/dist` (编译产物)
- [x] 排除 `.openclaw-agents/*/agent` (OpenClaw 状态)
- [x] 排除根目录 PNG（自己看的截图）
- [x] .gitignore 包含 OpenClaw / release / .hermes
- [x] 提供 .env.example / 安装脚本 / MCP 配置示例
- [x] 生成单文件静态 HTML 报告

## ✅ 已生成产物（路径）

```
C:\Users\18566\Desktop\quant-poc\release\
├── quant-poc-release.zip         1.18 MB  完整项目（62 文件，含 release/ 子目录）
├── quant-dashboard-static.html   42 KB    双击可看的可视化报告
├── INSTALL_MCP.md                2.6 KB   Claude Desktop MCP 配置指南
├── mcp-claude-desktop-config.example.json  0.3 KB
├── install_windows.bat           1.1 KB   Windows 一键安装
├── run_backtest.bat              0.6 KB   双击跑回测
├── run_dashboard.bat             0.5 KB   双击启动 Dashboard
├── README.txt                    0.3 KB   接收方使用说明
└── package_for_release.sh        3.6 KB   macOS/Linux 打包脚本
```

## ⚠️ 给接收方的话

**他需要做**：
1. 解压 `quant-poc-release.zip`
2. **可选**：在解压后的目录双击 `install_windows.bat`（或用 macOS/Linux 跑 `pip install -r requirements.txt`）
3. **必填**：去 https://tushare.pro 注册 + 复制 token → `set TUSHARE_TOKEN=xxx` (Windows) / `export TUSHARE_TOKEN=xxx` (macOS/Linux)
4. 双击 `run_backtest.bat` 跑 002180 / 000100 / 688122 三只股的回测
5. 双击 `run_dashboard.bat` 看可视化

**他不会遇到的坑**（已经在代码里处理）：
- vnpy 股票代码 `.SZ/.SH` vs `.SZSE/.SSE` 已自动转换
- vnpy `BacktestingEngine.load_data()` 会清空数据 → 我们直接赋值 `history_data`
- 重复回测 → 我们用类属性隔离，不共享
- 0 交易 → 这是常见 bug，已绕过
- 最大回撤显示问题 → 已按小数格式化

## ⚠️ 接收方可能踩的坑（已知）

- tushare 免费版 200 次/天，跑 30 次扫描 = 30 次 API 调用，3 只股就是 90 次 + 3 只股的回测 = 120 次，**差不多用完**
- vnpy 在 Windows 上 `vnpy_ctabacktester` 1.3.0 安装如果失败，pip 单独装：`pip install vnpy_ctabacktester`
- futu-api 10.10+ TrdEnv 是字符串不是 enum——已在 `broker_futu.py` 里处理
- 富途 A 股账户需要单独申请市场权限

## 📦 备选分发方式

### 方式 1：GitHub
```bash
cd C:\Users\18566\Desktop\quant-poc
git init
git add .
git commit -m "v0.1.0: 双均线 + 止损策略, 72 次回测"
gh repo create quant-poc --public --source=. --remote=origin --push
```

### 方式 2：网盘分享 release 目录
把 `C:\Users\18566\Desktop\quant-poc\release\` 整个文件夹传到：
- 百度网盘 / 阿里云盘
- GitHub Releases（每个版本传一份 zip）
- 飞书 / 钉钉 文件

### 方式 3：直接发 HTML 报告
如果接收方只需要看结果，**只发 `quant-dashboard-static.html`**：
- 双击浏览器打开
- 38 KB
- 包含 72 次回测 + Sharpe 对比图 + 风险数据
- 不需要任何环境

## 📊 已验证的回测结果（写入 backtest_results.md）

| 股票 | 最佳策略 | 收益 | Sharpe | 最大回撤 | 笔数 |
|---|---|---|---|---|---|
| 002180 纳思达 | (5,30) + 5%止损 | +68.07% | +0.397 | -95.79% | 59 |
| 000100 TCL科技 | (10,60) + MA200 | +1.18% | +0.068 | -5.71% | 10 |
| 688122 西部超导 | (10,30) + MA200 + 5%止损 | +212% | +0.611 | -134% | ~30 |

**72 次回测汇总**：没有任何参数组在 3 只股上都 Sharpe > 0。
