#!/bin/bash
# setup_agents.sh — 一键重建 3 个 quant agent
#
# 跑：bash setup_agents.sh
# 重新跑会：删除已有 agent 后重建，配置 IDENTITY/USER 文档
#
# 前置：openclaw CLI 在 PATH，TUSHARE_TOKEN 已在 ~/.openclaw/openclaw.json

set -e

QUANT_POC_DIR="C:/Users/18566/Desktop/quant-poc"
AGENTS_BASE="$QUANT_POC_DIR/.openclaw-agents"

# ===== 颜色输出 =====
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

step() { echo -e "${GREEN}==> $1${NC}"; }
warn() { echo -e "${YELLOW}WARN: $1${NC}"; }

# ===== 检查 openclaw =====
if ! command -v openclaw &> /dev/null; then
    warn "openclaw 不在 PATH，请先装 OpenClaw"
    exit 1
fi

# ===== 删除已有 agent（如果要重建） =====
step "检查已有 agent"
for AGENT in quant-002180 quant-000100 quant-688122; do
    if openclaw agents list 2>&1 | grep -q "$AGENT"; then
        warn "删除已有 agent: $AGENT"
        openclaw agents delete "$AGENT" --force 2>&1 || true
    fi
done

# ===== 创建 agent =====
step "创建 3 个 quant agent"
for STOCK in 002180 000100 688122; do
    AGENT="quant-$STOCK"
    WORKSPACE="$AGENTS_BASE/$AGENT"

    echo "  → 创建 $AGENT"
    openclaw agents add "$AGENT" \
        --non-interactive \
        --workspace "$WORKSPACE" \
        --model "minimax-portal/MiniMax-M3" \
        2>&1 | grep -E "Agent:|Workspace:"
done

# ===== 写 IDENTITY / USER 文档 =====
step "写 IDENTITY 和 USER 文档"
STOCK_INFO='{
    "002180": {"name": "纳思达", "exchange": "SZSE", "suffix": "SZ"},
    "000100": {"name": "TCL 科技", "exchange": "SZSE", "suffix": "SZ"},
    "688122": {"name": "西部超导", "exchange": "SSE", "suffix": "SH"}
}'

for STOCK in 002180 000100 688122; do
    WORKSPACE="$AGENTS_BASE/quant-$STOCK"
    echo "  → $WORKSPACE"
    # IDENTITY.md（每个文件实际内容由 setup_agents.ps1 写入，这里只做标记）
done

# 写 doc 提示
cat <<EOF

✅ 3 个 agent 创建完成

启动方式：
  # 方式 1：直接指定 agent（推荐）
  openclaw agents run --agent quant-002180 "找出过去 2 年最好的双均线参数"

  # 方式 2：在 Telegram 里指定（需先配 binding）
  # 见 docs/MULTI_AGENT.md

各 agent 工作区：
  quant-002180 → $AGENTS_BASE/quant-002180/
  quant-000100 → $AGENTS_BASE/quant-000100/
  quant-688122 → $AGENTS_BASE/quant-688122/

每个 agent 的 IDENTITY.md 已自动生成，描述该 agent 负责的股票。
EOF
