#!/bin/bash
# package_for_release.sh — 把 quant-poc 打包成 3 种可分发的产物
#
# 产物：
#   1. quant-poc-release.zip  (1.5 MB) - 完整项目（不含运行时数据 + 编译产物）
#   2. quant-poc-static-report.html - 单文件静态报告（双击可看）
#   3. mcp-claude-desktop-config.json - MCP 配置片段（给 Claude Desktop 用户）

set -e

QUANT_POC_DIR="C:/Users/18566/Desktop/quant-poc"
RELEASE_DIR="$QUANT_POC_DIR/release"
mkdir -p "$RELEASE_DIR"

cd "$QUANT_POC_DIR"

# ===== 1. 完整项目打包 =====
echo "==> [1/3] 打包完整项目..."

# 排除规则（要进 .gitignore 里已有）
EXCLUDES=(
    "__pycache__"
    "*.pyc"
    ".git"
    "data/quant-poc.db*"
    "data/cache"
    ".openclaw-plugin/node_modules"
    ".openclaw-plugin/dist"
    ".openclaw-agents"
    "*.png"          # 根目录的截图
)

# 用 rsync（如果装了）或 zip
if command -v 7z &> /dev/null; then
    7z a -mx=9 -r "$RELEASE_DIR/quant-poc-release.zip" . \
        -xr!__pycache__ -xr!*.pyc -xr!.git \
        -xr!data/quant-poc.db -xr!data/cache \
        -xr!.openclaw-plugin/node_modules -xr!.openclaw-plugin/dist \
        -xr!.openclaw-agents -xr!*.png \
        -xr!docs/screenshots
elif command -v zip &> /dev/null; then
    # zip 排除语法
    zip -r "$RELEASE_DIR/quant-poc-release.zip" . \
        -x "*/__pycache__/*" "*.pyc" "*.git*" \
        "data/quant-poc.db*" "data/cache/*" \
        ".openclaw-plugin/node_modules/*" ".openclaw-plugin/dist/*" \
        ".openclaw-agents/*" "*.png" \
        "docs/screenshots/*"
fi

# Windows 没有 zip/7z 时用 Python
if [ ! -f "$RELEASE_DIR/quant-poc-release.zip" ]; then
    echo "  用 Python zipfile 打包..."
    python "$QUANT_POC_DIR/tools/package_for_release.py"
fi

echo "  ✓ 产物 1: $RELEASE_DIR/quant-poc-release.zip"

# ===== 2. 单文件静态 HTML 报告 =====
echo "==> [2/3] 生成静态 HTML 报告..."
python export_static_report.py
cp "$QUANT_POC_DIR/../深度分析报告/quant-dashboard-static.html" "$RELEASE_DIR/" 2>/dev/null \
    || cp "C:/Users/18566/Desktop/深度分析报告/quant-dashboard-static.html" "$RELEASE_DIR/"
echo "  ✓ 产物 2: $RELEASE_DIR/quant-dashboard-static.html"

# ===== 3. Claude Desktop MCP 配置片段 =====
echo "==> [3/3] 生成 MCP 配置..."
cat > "$RELEASE_DIR/mcp-claude-desktop-config.json" << 'EOF'
{
  "mcpServers": {
    "quant-research": {
      "command": "python",
      "args": ["ABS_PATH_TO/quant-poc/mcp_quant_server.py"],
      "env": {
        "TUSHARE_TOKEN": "your_tushare_token_here"
      }
    }
  }
}
EOF

cat > "$RELEASE_DIR/mcp-claude-desktop-config-guide.md" << 'EOF'
# 给 Claude Desktop 用户的 MCP 配置

## 1. 替换 ABS_PATH_TO

把 `ABS_PATH_TO/quant-poc/mcp_quant_server.py` 替换成实际路径，例如：

- Windows: `C:/Users/YourName/Desktop/quant-poc/mcp_quant_server.py`
- macOS: `/Users/YourName/Desktop/quant-poc/mcp_quant_server.py`
- Linux: `/home/yourname/quant-poc/mcp_quant_server.py`

## 2. 配置 Claude Desktop

把上面的 JSON 内容合并到 Claude Desktop 配置文件：

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

## 3. 重启 Claude Desktop

工具列表里会出现 10 个 quant_* 工具。

## 4. 验证

跟 Claude 说："跑一下 002180 纳思达的双均线回测"。
EOF

echo "  ✓ 产物 3: $RELEASE_DIR/mcp-claude-desktop-config.json"
echo "  ✓ 产物 3 文档: $RELEASE_DIR/mcp-claude-desktop-config-guide.md"

echo ""
echo "==> 全部完成！产物在 $RELEASE_DIR:"
ls -lh "$RELEASE_DIR/"
