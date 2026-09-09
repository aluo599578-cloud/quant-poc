# OpenClaw 多 Agent 隔离

> 把 3 只 A 股分到 3 个独立 agent，每个 agent 自己的 workspace + identity + memory + 上下文。

## 为什么需要多 Agent

单 agent 跑多只股会出这些问题：
- 上下文里同时有 3 只股，LLM 容易混
- 每只股的历史回测 / 调参结果互不相关，但都塞在一个会话里
- 一只股的事会污染另两只的对话

**3 个 agent 各自管一只股** = 隔离 + 上下文专一 + 容易 review。

## 已创建

```
$ openclaw agents list
- main (default)           🦐 爬爬虾 - 你日常用
- quant-002180             纳思达 A 股策略研究
- quant-000100             TCL 科技 A 股策略研究
- quant-688122             西部超导 A 股策略研究
```

每个 agent 有：
- **Workspace**: `~/.openclaw/agents/quant-XXXXXX/workspace`
- **IDENTITY.md**: 描述 agent 负责的股票
- **USER.md**: 用户偏好（in-sample 接受 / 风险前置 / 数字 2 位小数）
- **Model**: `minimax-portal/MiniMax-M3`
- **共享插件**: `quant-research`（所有 agent 都能用 10 个工具）

## 使用方式

### 方式 1：显式指定 agent（最直接）

```bash
# 跑 002180 的策略研究
openclaw agent --agent quant-002180 -m "找出过去 2 年最好的双均线参数"

# 跑 688122 的策略研究
openclaw agent --agent quant-688122 -m "用 walk-forward 验证当前策略"

# 跑 000100 的策略研究
openclaw agent --agent quant-000100 -m "试 boll_channel 和 king_keltner"
```

agent 启动时自动加载 IDENTITY.md + USER.md，LLM 知道自己"是 quant-002180"，默认用 002180 跑。

### 方式 2：Telegram 路由（需要 OpenClaw 路由配置）

当前 3 个 quant agent `routing rules: 0`，所有 Telegram 消息默认走 main agent。
要让消息自动路由到对应 agent：

```bash
# 例如：telegram 消息开头 "002180 " 路由到 quant-002180
openclaw agents bind --agent quant-002180 --bind "telegram:8526045917"
# 但这是绑账号，不是按消息内容路由（需要 hook）
```

**更实际的方案**：用 Telegram bot command（如 `/q002180 xxx`），hook 把 `/qXXXXX` 开头转发到对应 agent。代码在 `tools/telegram_router.py`（待实现）。

## 文件结构

```
C:\Users\18566\Desktop\quant-poc\.openclaw-agents\
├── quant-002180\
│   ├── AGENTS.md        # OpenClaw 自动生成（系统文件）
│   ├── BOOTSTRAP.md     # 首次启动指令（可删）
│   ├── SOUL.md          # OpenClaw 自动生成
│   ├── IDENTITY.md      # 🆕 我写的：你是 quant-002180
│   └── USER.md          # 🆕 我写的：用户偏好
├── quant-000100\
│   ├── AGENTS.md
│   ├── ...
│   ├── IDENTITY.md      # 🆕 你是 quant-000100
│   └── USER.md
└── quant-688122\
    ├── ...
    ├── IDENTITY.md      # 🆕 你是 quant-688122
    └── USER.md
```

## 重建命令

如果你要重建（比如 agent 删了、workspace 改路径），跑：

```bash
# 1. 删旧 agent
openclaw agents delete quant-002180 --force
openclaw agents delete quant-000100 --force
openclaw agents delete quant-688122 --force

# 2. 重新创建（PowerShell）
powershell -ExecutionPolicy Bypass -File setup_agents.ps1

# 或 bash
bash setup_agents.sh

# 3. IDENTITY/USER 文档在 .openclaw-agents/ 目录下，
#    不会被 openclaw agents add 命令覆盖
```

setup 脚本是**幂等的**：可以反复跑，重复创建同名 agent 时会先 delete 旧。

## 隔离与共享

| 资源 | 隔离？| 说明 |
|---|---|---|
| Workspace 目录 | ✅ 隔离 | 每个 agent 自己的目录 |
| 身份（IDENTITY.md）| ✅ 隔离 | 只这个 agent 启动时读 |
| 用户偏好（USER.md）| ✅ 隔离 | 同上 |
| 聊天历史（sessions/）| ✅ 隔离 | 每个 agent 自己的 sqlite |
| 历史回测缓存 | ⚠️ 共享 | `data/backtest_scan.json` 是 quant-poc 共享的 |
| tushare 数据 | ⚠️ 共享 | 同一个 token |
| 插件工具 | ❌ 全局 | `quant-research` 插件是 OpenClaw 装一次，所有 agent 都能用 |

**为什么数据共享**：3 只股用同一份历史行情 + 同一份回测结果很正常。如果你想完全隔离，把 `data/` 复制到每个 agent 的 workspace 就行（要改 quant_core.py 的路径）。

## 实际工作流示例

```bash
# 早上：3 个 agent 并行跑
openclaw agent --agent quant-002180 -m "今天 002180 跑一遍 boll_channel 双参数扫描，给我 TOP 3" &
openclaw agent --agent quant-688122 -m "688122 walk-forward 验证昨天的双均线策略" &
openclaw agent --agent quant-000100 -m "000100 用 king_keltner 试一组新参数" &
wait

# 下午：基于结果问一个 agent
openclaw agent --agent quant-688122 -m "你早上的 walk-forward 结论是什么？有没有过拟合？"

# 跨 agent 对比
openclaw agent --agent quant-002180 -m "688122 的 boll_channel 双参数扫描 Sharpe 是 0.4，002180 同样策略能跑多少？"
```

## 下一步

- [ ] **Telegram 路由 hook**：`/q002180` 前缀转发到对应 agent
- [ ] **多 agent 共享回测缓存**：写一个 `quant_shared_data/` 跨 agent 共享
- [ ] **每个 agent 单独的 webhook 网关**：3 个端口（8765/8766/8767）每个 agent 一个
- [ ] **对比 agent**：跨 agent 输出格式统一，方便自动汇总

## 故障排查

```bash
# 1. agent 没列出来
openclaw agents list
# 看不到 → 看 openclaw.json 是不是被改坏了
# 备份在 ~/.openclaw/openclaw.json.bak

# 2. 启动 agent 报错
openclaw doctor
# 通常是 workspace 路径错（Windows 反斜杠 vs forward slash）

# 3. agent 不响应 / 慢
# 看 gateway 日志：
tail -f ~/.openclaw/logs/gateway.log

# 4. IDENTITY 没生效
# LLM 启动时没读 IDENTITY？检查 workspace 下有 IDENTITY.md
ls ~/.openclaw/agents/quant-002180/agent/   # 注意路径带 /agent
```
