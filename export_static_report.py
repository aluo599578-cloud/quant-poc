"""
export_static_report.py — 把回测结果导出成静态 HTML（无需 streamlit 在线）
=========================================================================
v2: 加入 Sortino / Calmar / 年化波动率 + Webhook 实时数据区
"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUT = Path("C:/Users/18566/Desktop/深度分析报告/quant-dashboard-static.html")


def fig_combined_scan():
    """组合扫描柱状图 + 散点图。"""
    df = pd.read_json("data/backtest_scan.json")

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("30 次回测 - 总收益对比", "收益 vs 回撤 散点图"),
        horizontal_spacing=0.12,
    )

    # 柱状图
    colors = ["#1f77b4" if s == "DoubleMa" else "#ff7f0e"
              for s in df["strategy"]]
    fig.add_trace(go.Bar(
        x=df["vt_symbol"].str.split(".").str[0] + " " + df["fast"].astype(str) + "/" + df["slow"].astype(str),
        y=df["total_return"],
        marker_color=colors,
        name="总收益",
        text=[f"{v:+.0f}%" for v in df["total_return"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>收益 %{y:.1f}%"
                      "<br>策略 %{customdata}<extra></extra>",
        customdata=df["strategy"],
    ), row=1, col=1)
    fig.update_yaxes(title_text="总收益 (%)", row=1, col=1)
    fig.update_xaxes(tickangle=-45, row=1, col=1)

    # 散点图
    for strategy_name, color in [("DoubleMa", "#1f77b4"), ("DoubleMa+MA200", "#ff7f0e")]:
        sub = df[df["strategy"] == strategy_name]
        fig.add_trace(go.Scatter(
            x=sub["max_dd_pct"], y=sub["total_return"],
            mode="markers+text",
            text=sub["vt_symbol"].str.split(".").str[0],
            textposition="top center",
            textfont=dict(size=8),
            name=strategy_name,
            marker=dict(size=10, color=color, line=dict(width=1, color="white")),
            hovertemplate="<b>%{text}</b><br>"
                          f"{strategy_name}<br>"
                          "回撤 %{x:.1f}%<br>"
                          "收益 %{y:.1f}%<extra></extra>",
        ), row=1, col=2)
    fig.update_xaxes(title_text="最大回撤 (%)", row=1, col=2)
    fig.update_yaxes(title_text="总收益 (%)", row=1, col=2)

    fig.update_layout(
        height=500, hovermode="closest",
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=-0.15),
    )
    return fig


def fig_top_strategy_detail():
    """TOP 1 策略：西部超导 DoubleMa (10,60) K 线 + 净值。"""
    import tushare as ts
    from vnpy.trader.constant import Interval
    from vnpy_ctastrategy.backtesting import BacktestingEngine
    from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy

    from backtest_3stocks import STOCKS, fetch_kline, make_bars, to_tushare_code

    target = "688122.SSE"  # 西部超导
    start = "2023-01-01"
    end = "2026-09-04"

    df = fetch_kline(to_tushare_code(target), start, end)
    bars = make_bars(df, target)

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=target, interval=Interval.DAILY,
        start=datetime.fromisoformat(start), end=datetime.fromisoformat(end),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=1_000_000,
    )
    engine.add_strategy(DoubleMaStrategy, {"fast_window": 10, "slow_window": 60})
    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()
    stats = engine.calculate_statistics()

    daily_df = engine.daily_df
    df["ma_fast"] = df["close"].rolling(10).mean()
    df["ma_slow"] = df["close"].rolling(60).mean()

    # 复用 dashboard 的 risk 计算
    from dashboard import _compute_risk_metrics
    risk = _compute_risk_metrics(daily_df, stats)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=df["trade_date"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="K线",
        increasing_line_color="#ef5350", decreasing_line_color="#26a69a",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["trade_date"], y=df["ma_fast"],
                             name="MA10", line=dict(color="orange")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["trade_date"], y=df["ma_slow"],
                             name="MA60", line=dict(color="blue")), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=daily_df.index, y=daily_df["balance"],
        name="策略净值", line=dict(color="purple", width=2),
        fill="tozeroy", fillcolor="rgba(128,0,128,0.1)",
    ), row=2, col=1)

    fig.update_layout(
        title=f"688122 西部超导 DoubleMa (10,60) - "
              f"收益 {stats['total_return']*100:+.2f}% / "
              f"回撤 {stats['max_ddpercent']*100:.2f}% / "
              f"Sharpe {stats['sharpe_ratio']:+.2f}",
        height=600, xaxis_rangeslider_visible=False,
        hovermode="x unified", margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(orientation="h", y=1.02),
    )
    return fig, stats, risk


def main():
    print("生成组合扫描图...")
    fig1 = fig_combined_scan()
    html1 = fig1.to_html(include_plotlyjs="cdn", full_html=False)

    print("生成 TOP 策略详情图 + 风险指标...")
    fig2, stats, risk = fig_top_strategy_detail()
    html2 = fig2.to_html(include_plotlyjs="cdn", full_html=False)

    print("读取 Webhook 实时数据...")
    webhook = _load_webhook_data(Path("data/quant-poc.db"))

    df = pd.read_json("data/backtest_scan.json")
    df_sorted = df.sort_values("sharpe", ascending=False)

    # 风险指标 HTML 卡片
    risk_html = render_risk_cards(stats, risk)

    # Webhook 实时数据 HTML
    webhook_html = render_webhook_section(webhook)

    # 写一个完整 HTML
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>A 股量化回测 Dashboard - 静态导出 v2</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
          max-width: 1400px; margin: 20px auto; padding: 0 20px; background: #f5f7fa; }}
  h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 8px; }}
  h2 {{ color: #333; margin-top: 40px; border-bottom: 1px solid #e0e0e0; padding-bottom: 6px; }}
  h3 {{ color: #555; margin-top: 24px; }}
  table {{ border-collapse: collapse; width: 100%; background: white;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 16px 0; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
  th {{ background: #1a73e8; color: white; font-weight: 600; }}
  tr:hover {{ background: #f5f9ff; }}
  .metric-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; }}
  .metric {{ display: inline-block; padding: 14px 22px; background: white;
              border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 130px; }}
  .metric-label {{ color: #666; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric-value {{ font-size: 22px; font-weight: 600; color: #1a73e8; margin-top: 4px; }}
  .positive {{ color: #26a69a; }}
  .negative {{ color: #ef5350; }}
  .chart-container {{ background: white; padding: 20px; border-radius: 8px;
                      box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 20px 0; }}
  .badge {{ display: inline-block; padding: 3px 8px; border-radius: 12px;
            font-size: 12px; font-weight: 600; }}
  .badge-double {{ background: #e3f2fd; color: #1976d2; }}
  .badge-trend {{ background: #fff3e0; color: #f57c00; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px;
          font-family: "SF Mono", Monaco, "Cascadia Code", monospace; font-size: 13px; }}
  .webhook-empty {{ background: #fff3e0; padding: 16px; border-radius: 8px;
                    border-left: 4px solid #ff9800; color: #5d4037; }}
</style>
</head>
<body>
<h1>📈 A 股量化回测 Dashboard (静态导出 v2)</h1>
<p>由 <code>export_static_report.py</code> 生成 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
含 <b>Sortino / Calmar / 年化波动率</b> 风险调整指标 + <b>📡 Webhook 实时数据</b> 区</p>

<h2>📊 TOP 1 策略 - 9 个核心指标</h2>
<p><b>688122 西部超导 + DoubleMa (10,60)</b></p>

<h3>基础指标</h3>
<div class="metric-row">
  <div class="metric">
    <div class="metric-label">总收益</div>
    <div class="metric-value positive">{stats['total_return']*100:+.2f}%</div>
  </div>
  <div class="metric">
    <div class="metric-label">年化收益</div>
    <div class="metric-value positive">{stats['annual_return']*100:+.2f}%</div>
  </div>
  <div class="metric">
    <div class="metric-label">Sharpe</div>
    <div class="metric-value">{stats['sharpe_ratio']:+.2f}</div>
  </div>
  <div class="metric">
    <div class="metric-label">最大回撤</div>
    <div class="metric-value negative">{stats['max_ddpercent']*100:.2f}%</div>
  </div>
  <div class="metric">
    <div class="metric-label">交易数</div>
    <div class="metric-value">{stats['total_trade_count']}</div>
  </div>
  <div class="metric">
    <div class="metric-label">日胜率</div>
    <div class="metric-value">{stats['profit_days']/stats['total_days']*100:.1f}%</div>
  </div>
</div>

<h3>风险调整指标</h3>
{risk_html}

<div class="chart-container">
{html2}
</div>

<h2>🔍 30 次组合扫描</h2>
<div class="chart-container">
{html1}
</div>

<h2>📡 Webhook 实时数据</h2>
{webhook_html}

<h2>📋 全部 30 次结果（按 Sharpe 排序）</h2>
<table>
  <thead>
    <tr>
      <th>股票</th><th>策略</th><th>参数</th>
      <th>总收益</th><th>年化</th><th>Sharpe</th>
      <th>最大回撤</th><th>交易数</th>
    </tr>
  </thead>
  <tbody>
"""
    for _, r in df_sorted.iterrows():
        ret_class = "positive" if r["total_return"] >= 0 else "negative"
        dd_class = "negative"
        badge_class = "badge-double" if r["strategy"] == "DoubleMa" else "badge-trend"
        full_html += f"""
    <tr>
      <td>{r['name']} <small>({r['vt_symbol']})</small></td>
      <td><span class="badge {badge_class}">{r['strategy']}</span></td>
      <td>({r['fast']}, {r['slow']})</td>
      <td class="{ret_class}">{r['total_return']:+.2f}%</td>
      <td class="{ret_class}">{r['annual_return']:+.2f}%</td>
      <td>{r['sharpe']:+.2f}</td>
      <td class="{dd_class}">{r['max_dd_pct']:+.2f}%</td>
      <td>{r['trade_count']}</td>
    </tr>"""
    full_html += """
  </tbody>
</table>

<h2>📜 使用说明</h2>
<ul>
  <li><b>实时交互版</b>（含 4 Tab）：<code>python -m streamlit run dashboard.py --server.port 8501</code></li>
  <li><b>演示版</b>（自动跑）：<code>python -m streamlit run dashboard_demo_v2.py --server.port 8504</code></li>
  <li><b>此静态版</b>（v2，含风险指标 + webhook）：<code>python export_static_report.py</code></li>
</ul>

<p><small>基于 vnpy 4.4.0 + tushare + plotly + streamlit · 参考 github.com/zinan92/backtest</small></p>
</body>
</html>"""

    OUT.write_text(full_html, encoding="utf-8")
    print(f"✅ 已生成: {OUT}")
    print(f"   大小: {OUT.stat().st_size / 1024:.1f} KB")


def render_risk_cards(stats: dict, risk: dict) -> str:
    """生成风险指标的 3 个 HTML 卡片。"""
    ann_vol = risk.get("annual_vol", 0)
    sortino = risk.get("sortino", 0)
    calmar = risk.get("calmar", 0)

    if isinstance(sortino, (int, float)) and abs(sortino) <= 50:
        sortino_str = f"{sortino:+.2f}"
        sortino_cls = "positive" if sortino > 0 else "negative"
    else:
        sortino_str = "N/A"
        sortino_cls = ""
    calmar_str = f"{calmar:+.2f}" if isinstance(calmar, (int, float)) and abs(calmar) <= 100 else "N/A"
    calmar_cls = "positive" if isinstance(calmar, (int, float)) and calmar > 0 else "negative"

    return f"""<div class="metric-row">
  <div class="metric">
    <div class="metric-label">年化波动率</div>
    <div class="metric-value">{ann_vol:.2f}%</div>
  </div>
  <div class="metric">
    <div class="metric-label">Sortino</div>
    <div class="metric-value {sortino_cls}">{sortino_str}</div>
  </div>
  <div class="metric">
    <div class="metric-label">Calmar</div>
    <div class="metric-value {calmar_cls}">{calmar_str}</div>
  </div>
</div>
<p><small>Sortino = (年化 - 2.5%) / 下行波动。Calmar = 年化 / |回撤|。
    西部超导 (10,60) 因回撤极深（-62%）导致 Calmar 仅 0.17，风险调整后表现差。</small></p>"""


def render_webhook_section(wh: dict) -> str:
    """生成 Webhook 实时数据区 HTML。"""
    if not wh.get("running"):
        return f"""<div class="webhook-empty">
<p><b>数据库未就绪</b>：<code>{wh.get('error', 'data/quant-poc.db not found')}</code></p>
<p>先启动 webhook gateway 并推送一些 alert：</p>
<pre><code>cd C:\\Users\\18566\\Desktop\\quant-poc
QPOC_SECRET=test-secret-abc python -m uvicorn app.webhook_gateway:app --port 8765

curl -X POST http://127.0.0.1:8765/webhook/tradingview \\
  -H "Content-Type: application/json" \\
  -d '{{"secret":"test-secret-abc","event_id":"e1","action":"buy","symbol":"000001.SZ","price":10.0,"volume":100}}'</code></pre>
</div>"""

    acc = wh["account"]
    pnl = acc["net_pnl"]
    pnl_cls = "positive" if pnl >= 0 else "negative"

    # 持仓
    positions = wh["positions"]
    if positions:
        pos_rows = "".join(
            f"<tr><td>{p['symbol']}</td><td>{p['volume']}</td>"
            f"<td>{p['avg_price']}</td><td>{p['volume'] * p['avg_price']:,.2f}</td></tr>"
            for p in positions
        )
        pos_table = f"<table><thead><tr><th>代码</th><th>持仓数</th><th>均价</th><th>市值</th></tr></thead><tbody>{pos_rows}</tbody></table>"
    else:
        pos_table = "<p><i>当前空仓。</i></p>"

    # 成交
    trades = wh["trades"]
    if trades:
        tr_rows = "".join(
            f"<tr><td>{t['tradeid']}</td><td>{t['symbol']}</td>"
            f"<td>{t['direction']}</td><td>{t['volume']}</td>"
            f"<td>{t['price']}</td><td>{t['traded_at']}</td></tr>"
            for t in trades[:30]
        )
        tr_table = f"<table><thead><tr><th>成交号</th><th>代码</th><th>方向</th><th>数</th><th>价</th><th>时间</th></tr></thead><tbody>{tr_rows}</tbody></table>"
    else:
        tr_table = "<p><i>无成交。</i></p>"

    # 事件
    events = wh["events"]
    if events:
        ev_rows = "".join(
            f"<tr><td>{e['event_id']}</td><td>{e['action']}</td>"
            f"<td>{e['symbol']}</td><td>{e['price']}</td>"
            f"<td>{e['volume']}</td><td>{e['strategy'] or '-'}</td>"
            f"<td>{e['received_at']}</td></tr>"
            for e in events[:30]
        )
        ev_table = f"<table><thead><tr><th>Event ID</th><th>动作</th><th>代码</th><th>价</th><th>数</th><th>策略</th><th>时间</th></tr></thead><tbody>{ev_rows}</tbody></table>"
    else:
        ev_table = "<p><i>无事件。</i></p>"

    return f"""<div class="metric-row">
  <div class="metric">
    <div class="metric-label">初始资金</div>
    <div class="metric-value">¥{acc['init_cash']:,.0f}</div>
  </div>
  <div class="metric">
    <div class="metric-label">可用现金</div>
    <div class="metric-value">¥{acc['cash']:,.0f}</div>
  </div>
  <div class="metric">
    <div class="metric-label">净盈亏</div>
    <div class="metric-value {pnl_cls}">¥{pnl:+,.0f}</div>
  </div>
  <div class="metric">
    <div class="metric-label">成交数</div>
    <div class="metric-value">{acc['trade_count']}</div>
  </div>
  <div class="metric">
    <div class="metric-label">事件数</div>
    <div class="metric-value">{acc['event_count']}</div>
  </div>
</div>

<h3>📦 持仓</h3>
{pos_table}

<h3>💱 成交明细（最近 {min(30, len(trades))} 条）</h3>
{tr_table}

<h3>📨 事件日志（最近 {min(30, len(events))} 条）</h3>
{ev_table}"""


def _load_webhook_data(db_path: Path) -> dict:
    """复用 dashboard._load_webhook_data。"""
    from dashboard import _load_webhook_data as _impl
    return _impl(db_path)


if __name__ == "__main__":
    main()
