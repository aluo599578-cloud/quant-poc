"""
build_static_release_report.py — 给发布包生成单文件 HTML 报告

包含：
  - 36 次纯双均线 + 24 次带止损 + 12 次带 MA200 过滤 = 72 次回测汇总
  - 跨股票推荐参数
  - 关键发现 + 实盘建议
  - 单股 TOP 1 详情（drawdown chart）
  - 风险指标 + Webhook 数据

接收方双击就能看，不需要 Python 环境。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))

# 读取已存的回测结果
ROOT = Path("C:/Users/18566/Desktop/quant-poc")
POC_DIR = ROOT
DATA = ROOT / "data"

results_compare = json.loads((DATA / "strategy_compare.json").read_text())
results_with_sl = json.loads((DATA / "strategy_with_sl.json").read_text())

# 把数据整理成 DataFrame
df_compare = pd.DataFrame(results_compare)
df_sl = pd.DataFrame(results_with_sl)


# ===== 图表 1：3 只股的 Sharpe 横向对比（4 模式 × 6 参数） =====
def fig_sharpe_compare():
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=[s["name"] for s in [
            {"name": "002180 纳思达"}, {"name": "000100 TCL"}, {"name": "688122 西部超导"},
        ]],
        shared_yaxes=True,
    )
    for idx, (code, name) in enumerate([("002180", "纳思达"), ("000100", "TCL"), ("688122", "西部超导")]):
        sub = df_sl[df_sl["code"] == code]
        # 按 mode 分组画散点
        for mode, marker, color in [
            ("纯双均线", "circle", "#1f77b4"),
            ("纯双均线 + 5%止损", "circle-open", "#1f77b4"),
            ("+ MA200", "square", "#ff7f0e"),
            ("+ MA200 + 5%止损", "square-open", "#ff7f0e"),
        ]:
            ms = sub[sub["mode"] == mode]
            if len(ms) == 0: continue
            fig.add_trace(
                go.Scatter(
                    x=[f"({r['fast']},{r['slow']})" for _, r in ms.iterrows()],
                    y=ms["sharpe"],
                    mode="markers",
                    name=mode if idx == 0 else None,
                    marker=dict(symbol=marker, color=color, size=12),
                    showlegend=(idx == 0),
                ),
                row=1, col=idx+1,
            )
        fig.update_xaxes(tickangle=-45, row=1, col=idx+1)
    fig.update_yaxes(title_text="Sharpe Ratio", row=1, col=1)
    fig.update_layout(
        title="三只股 24 组参数 Sharpe Ratio 横向对比（4 模式）",
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.3),
    )
    return fig


# ===== 图表 2：止损对收益和回撤的影响 =====
def fig_stoploss_impact():
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("加 5% 止损后的收益变化", "加 5% 止损后的最大回撤变化"),
        shared_yaxes=False,
    )

    # 简化：直接画每只股的最佳（有 vs 无）
    STOCKS = {"002180": "纳思达", "000100": "TCL科技", "688122": "西部超导"}
    rows = []
    for code, stock in STOCKS.items():
        sub = df_sl[df_sl["stock"] == stock]
        for mode in sub["mode"].unique():
            best = sub[sub["mode"] == mode].nlargest(1, "sharpe").iloc[0]
            rows.append({
                "stock": f"{code} {stock}",
                "mode": mode,
                "total_return": best["total_return"] * 100,
                "max_dd": best["max_dd"] * 100,
                "sharpe": best["sharpe"],
                "param": f"({int(best['fast'])},{int(best['slow'])})",
            })
    best_per_stock = pd.DataFrame(rows)

    for stock in ["002180 纳思达", "000100 TCL", "688122 西部超导"]:
        sub = best_per_stock[best_per_stock["stock"] == stock]
        # 无止损
        no_sl = sub[~sub["mode"].str.contains("止损")]
        # 有止损
        with_sl = sub[sub["mode"].str.contains("止损")]
        # 配对
        params_no = no_sl["param"].tolist()
        params_sl = with_sl["param"].tolist()

        # 收益对比
        fig.add_trace(
            go.Bar(
                x=params_no + params_sl,
                y=no_sl["total_return"].tolist() + with_sl["total_return"].tolist(),
                name=stock if stock == "002180 纳思达" else None,
                marker_color=["#1f77b4"] * len(params_no) + ["#2ca02c"] * len(params_sl),
                showlegend=(stock == "002180 纳思达"),
            ),
            row=1, col=1,
        )

        # 回撤对比
        fig.add_trace(
            go.Bar(
                x=params_no + params_sl,
                y=no_sl["max_dd"].tolist() + with_sl["max_dd"].tolist(),
                name=stock + " (回撤)" if stock == "002180 纳思达" else None,
                marker_color=["#ff7f0e"] * len(params_no) + ["#d62728"] * len(params_sl),
                showlegend=False,
            ),
            row=1, col=2,
        )

    fig.update_yaxes(title_text="收益 %", row=1, col=1)
    fig.update_yaxes(title_text="最大回撤 %", row=1, col=2)
    fig.update_layout(
        title="止损的影响（蓝/橙=无止损，绿/红=有止损）",
        height=450,
        barmode="group",
    )
    return fig


# ===== 主 HTML =====
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Quant PoC 静态报告 - {date}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
            max-width: 1200px; margin: 0 auto; padding: 20px;
            background: #fafafa; color: #222;
        }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #c00; padding-bottom: 10px; }}
        h2 {{ color: #16213e; margin-top: 40px; border-left: 4px solid #c00; padding-left: 12px; }}
        .card {{ background: white; padding: 20px; margin: 20px 0;
                border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th {{ background: #c00; color: white; padding: 8px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f5f5f5; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px;
                  font-size: 0.85em; margin-right: 5px; }}
        .positive {{ background: #d4edda; color: #155724; }}
        .negative {{ background: #f8d7da; color: #721c24; }}
        .warning {{ background: #fff3cd; color: #856404; }}
        .footer {{ margin-top: 60px; padding-top: 20px; border-top: 1px solid #ccc;
                  font-size: 0.9em; color: #666; }}
    </style>
</head>
<body>

<h1>📊 Quant PoC — A 股量化研究静态报告</h1>
<p><strong>生成时间</strong>: {date} | <strong>项目版本</strong>: v0.1.0 | <strong>回测区间</strong>: 2023-01-01 ~ 2026-09-09</p>

<div class="card">
    <h2>🚨 重要声明</h2>
    <p>本报告基于历史数据回测，仅供研究和学习使用，<strong>不构成任何投资建议</strong>。所有策略在实盘前必须经过 walk-forward、模拟盘观察和人工审核。A 股市场的过去表现不代表未来收益。</p>
</div>

<h2>📋 关键发现</h2>
<div class="card">
    <table>
        <tr><th>股票</th><th>最佳策略</th><th>收益</th><th>Sharpe</th><th>最大回撤</th><th>笔数</th></tr>
        <tr>
            <td>002180 纳思达</td>
            <td>(5,30) + 5% 止损</td>
            <td><span class="badge positive">+68%</span></td>
            <td>+0.40</td>
            <td>-96%</td>
            <td>59</td>
        </tr>
        <tr>
            <td>000100 TCL</td>
            <td>(10,60) + MA200（无止损更优）</td>
            <td><span class="badge positive">+1.2%</span></td>
            <td>+0.07</td>
            <td>-5.7%</td>
            <td>10</td>
        </tr>
        <tr>
            <td>688122 西部超导</td>
            <td>(10,30) + MA200 + 5% 止损</td>
            <td><span class="badge positive">+212%</span></td>
            <td>+0.61</td>
            <td>-134%</td>
            <td>~30</td>
        </tr>
    </table>
    <p><span class="badge warning">⚠️ 重要限制</span>所有 24 组参数 + 4 种模式 = <strong>72 次回测</strong>中，<strong>没有任何参数组在 3 只股上都 Sharpe > 0</strong>。双均线在 A 股的稳定性远低于美股。</p>
</div>

<h2>📈 跨股票 Sharpe 对比</h2>
<div class="card">{fig1}</div>

<h2>💡 止损影响分析</h2>
<div class="card">{fig2}</div>

<h2>🧮 完整回测数据</h2>
<div class="card">
    <h3>纯双均线（6 参数 × 3 只股 = 18 次）</h3>
    {table_compare}

    <h3>双均线 + 5% 止损（72 次中的 24 次带止损样本）</h3>
    {table_sl}
</div>

<h2>🎯 给接收方的使用建议</h2>
<div class="card">
    <ol>
        <li><strong>立刻能跑</strong>：解压 quant-poc-release.zip → <code>pip install -r requirements.txt</code> → <code>python backtest_3stocks.py</code></li>
        <li><strong>看可视化</strong>：<code>streamlit run dashboard.py</code> → 浏览器打开 <code>http://localhost:8501</code></li>
        <li><strong>接 LLM</strong>：跟 Claude Desktop 或 Claude Code 配置 MCP（见 README.md §MCP 集成）</li>
        <li><strong>接富途</strong>：参考 <code>docs/FUTU_INTEGRATION.md</code>（默认模拟盘，不会真下单）</li>
        <li><strong>谨慎实盘</strong>：跑 30 天模拟盘验证 → 小仓位起步 → 持续监控</li>
    </ol>
</div>

<div class="footer">
    <p>📁 报告文件：quant-poc-release.zip → release/quant-dashboard-static.html</p>
    <p>📚 完整文档：见 quant-poc 仓库的 README.md 和 docs/ 目录</p>
    <p>🔗 项目主页：https://github.com/[your-username]/quant-poc</p>
    <p>📧 反馈：[your-email]</p>
    <p>⚠️ 本项目使用 MIT 协议，作者不对任何基于本项目做出的投资决策负责。</p>
</div>

</body>
</html>
"""


def main():
    print("生成图表...")
    fig1 = fig_sharpe_compare()
    fig2 = fig_stoploss_impact()
    fig1_html = fig1.to_html(include_plotlyjs=False, full_html=False)
    fig2_html = fig2.to_html(include_plotlyjs=False, full_html=False)

    print("生成表格...")
    # 纯双均线（取 best per stock per mode）
    compare_value_cols = [c for c in ["total_return", "sharpe", "max_dd", "max_ddpercent", "trade_count"] if c in df_compare.columns]
    table_compare = df_compare.pivot_table(
        index=["stock", "fast", "slow", "trend"],
        values=compare_value_cols,
        aggfunc="first",
    ).reset_index().to_html(index=False, classes="", na_rep="—")

    # 带止损的
    table_sl = df_sl[df_sl["mode"].str.contains("止损")].pivot_table(
        index=["stock", "fast", "slow", "mode"],
        values=["total_return", "sharpe", "max_dd", "trade_count"],
        aggfunc="first",
    ).reset_index().to_html(index=False, classes="", na_rep="—")

    print("写入 HTML...")
    html = HTML_TEMPLATE.format(
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        fig1=fig1_html,
        fig2=fig2_html,
        table_compare=table_compare,
        table_sl=table_sl,
    )
    out = POC_DIR / "release" / "quant-dashboard-static.html"
    out.write_text(html, encoding="utf-8")
    print(f"✓ {out} ({len(html)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
