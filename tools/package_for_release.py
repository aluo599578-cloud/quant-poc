"""
package_for_release.py — 把 quant-poc 打包成 release zip（1 MB 左右）

显式枚举要打包的目录/文件，不递归整个仓库（避免 OpenClaw 的
agent state / node_modules 拖慢打包）。接收方解压后：
  pip install -r requirements.txt
  python backtest_3stocks.py
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
ZIP = ROOT / "release" / "quant-poc-release.zip"
ZIP.parent.mkdir(exist_ok=True)

# 必须打的目录（递归）
INCLUDE_DIRS = ["app", "docs", "tests", "tools", "strategies"]

# release 目录里的关键发布产物（不递归整个目录避免把上次打包的 zip 也打包进来）
INCLUDE_RELEASE = [
    "release/quant-dashboard-static.html",
    "release/INSTALL_MCP.md",
    "release/mcp-claude-desktop-config.example.json",
    "release/install_windows.bat",
    "release/run_backtest.bat",
    "release/run_dashboard.bat",
    "release/README.txt",
    "release/RELEASE_CHECKLIST.md",
]

# 必须打的文件（散在根目录）
INCLUDE_FILES = [
    "quant_core.py",
    "mcp_quant_server.py",
    "lean_style_indicators.py",
    "backtest_3stocks.py",
    "backtest_3stocks_lean.py",
    "backtest_scan.py",
    "backtest_scan_lean.py",
    "dashboard.py",
    "dashboard_demo.py",
    "dashboard_demo_v2.py",
    "export_static_report.py",
    "demo_hk_simple_strategy.py",
    "a_stock_paper_strategy.py",
    "strategy_param_compare.py",
    "strategy_with_stoploss.py",
    "push_demo_alerts.py",
    "README.md", "LICENSE", "CHANGELOG.md",
    "backtest_results.md",
    "LEAN_INSPIRED.md",
    "LEAN_MIGRATION.md",
    "requirements.txt",
    "package_for_release.sh",
    ".gitignore",
]

# OpenClaw 插件源（不含编译产物 / node_modules）
INCLUDE_PLUGIN = [
    ".openclaw-plugin/openclaw.plugin.json",
    ".openclaw-plugin/package.json",
    ".openclaw-plugin/tsconfig.json",
    ".openclaw-plugin/README.md",
    ".openclaw-plugin/src/index.ts",
    ".openclaw-plugin/src/index.test.ts",
]


def main():
    print(f"打包 {ROOT} → {ZIP}")
    count = 0
    total = 0
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        # 递归目录
        for d in INCLUDE_DIRS:
            dirpath = ROOT / d
            if not dirpath.exists():
                continue
            for fp in dirpath.rglob("*"):
                if fp.is_file() and "__pycache__" not in fp.parts:
                    z.write(fp, fp.relative_to(ROOT).as_posix())
                    count += 1
                    total += fp.stat().st_size
        # 单文件
        for f in INCLUDE_FILES + INCLUDE_PLUGIN + INCLUDE_RELEASE:
            fp = ROOT / f
            if fp.exists() and fp.is_file():
                z.write(fp, fp.relative_to(ROOT).as_posix())
                count += 1
                total += fp.stat().st_size
    print(f"✓ {count} 个文件，{total/1024/1024:.2f} MB")
    print(f"  → {ZIP.resolve()}")


if __name__ == "__main__":
    main()
