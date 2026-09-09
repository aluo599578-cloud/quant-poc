# setup_agents.ps1 — PowerShell 版本（一键重建 3 个 quant agent）
#
# 跑：powershell -ExecutionPolicy Bypass -File setup_agents.ps1
# 重新跑会：删除已有 agent 后重建

$ErrorActionPreference = "Stop"

$QuantPocDir = "C:\Users\18566\Desktop\quant-poc"
$AgentsBase = "$QuantPocDir\.openclaw-agents"

# 颜色输出
function Step($msg) { Write-Host "==> $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "WARN: $msg" -ForegroundColor Yellow }

# 检查 openclaw
if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
    Warn "openclaw 不在 PATH"
    exit 1
}

# 删除已有 agent
Step "检查并删除已有 agent"
foreach ($stock in @("002180", "000100", "688122")) {
    $agent = "quant-$stock"
    $existing = openclaw agents list 2>&1 | Select-String $agent
    if ($existing) {
        Warn "删除已有 agent: $agent"
        openclaw agents delete $agent --force 2>&1 | Out-Null
    }
}

# 创建 agent
Step "创建 3 个 quant agent"
foreach ($stock in @("002180", "000100", "688122")) {
    $agent = "quant-$stock"
    $workspace = "$AgentsBase\$agent"
    Write-Host "  → 创建 $agent" -ForegroundColor Cyan
    openclaw agents add $agent `
        --non-interactive `
        --workspace $workspace `
        --model "minimax-portal/MiniMax-M3" 2>&1 | Select-String -Pattern "Agent:|Workspace:"
}

Step "完成"
Write-Host ""
Write-Host "启动方式：" -ForegroundColor Green
Write-Host "  openclaw agents run --agent quant-002180 '找出过去 2 年最好的双均线参数'"
Write-Host "  openclaw agents run --agent quant-000100 '用 boll_channel 试试'"
Write-Host "  openclaw agents run --agent quant-688122 'walk-forward 验证'"
Write-Host ""
Write-Host "各 agent 工作区：" -ForegroundColor Green
Write-Host "  quant-002180 → $AgentsBase\quant-002180\"
Write-Host "  quant-000100 → $AgentsBase\quant-000100\"
Write-Host "  quant-688122 → $AgentsBase\quant-688122\"
Write-Host ""
Write-Host "IDENTITY.md 和 USER.md 已自动生成。" -ForegroundColor Green
