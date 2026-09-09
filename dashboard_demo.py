"""
dashboard_demo.py — Dashboard Tab1 的演示版本
=============================================
不依赖 streamlit 交互，直接渲染一次"假装按过按钮"的结果页。
用于自动截图验证。
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from backtest_3stocks import STOCKS
from dashboard import cached_backtest


st.set_page_config(page_title="A 股量化回测 Dashboard - 演示", layout="wide")
st.title("📈 A 股量化回测 Dashboard (演示运行)")
st.caption("三只股同参数批量回测，自动跑不需按钮")

FAST, SLOW = 5, 30
USE_TREND = False
START, END = "2023-01-01", "2026-09-04"
CAPITAL = 1_000_000.0

tab1, tab2, tab3 = st.tabs(["🔍 组合扫描", "📊 单股深度", "📜 历史结果"])

# ============ Tab 1 ============
with tab1:
    st.subheader(f"多股同策略对比 (fast={FAST}, slow={SLOW}, trend={USE_TREND})")
    rows = []
    progress = st.progress(0.0, "回测中...")
    for i, (vt, code, name) in enumerate(STOCKS):
        progress.progress((i + 1) / len(STOCKS), f"回测 {vt}...")
        r = cached_backtest(vt, FAST, SLOW, USE_TREND, START, END, CAPITAL)
        s = r["stats"]
        rows.append({
            "代码": vt.split(".")[0],
            "名称": name,
            "总收益(%)": round(s.get("total_return", 0) * 100, 2),
            "年化(%)": round(s.get("annual_return", 0) * 100, 2),
            "Sharpe": round(s.get("sharpe_ratio", 0), 2),
            "最大回撤(%)": round(s.get("max_ddpercent", 0) * 100, 2),
            "胜日/总": f"{int(s.get('profit_days', 0))}/{int(s.get('total_days', 1))}",
            "交易数": int(s.get("total_trade_count", 0)),
        })
    progress.empty()

    df_scan = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
    st.dataframe(df_scan, use_container_width=True, hide_index=True)

    fig = go.Figure(go.Bar(
        x=df_scan["代码"] + " " + df_scan["名称"],
        y=df_scan["总收益(%)"],
        marker_color=["#26a69a" if v >= 0 else "#ef5350" for v in df_scan["总收益(%)"]],
        text=[f"{v:+.1f}%" for v in df_scan["总收益(%)"]],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"总收益对比 ({START} ~ {END})",
        height=400, yaxis_title="总收益 (%)",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

# ============ Tab 2 ============
with tab2:
    st.subheader("单股深度分析 - 002180 纳思达（盈利案例）")
    r = cached_backtest("002180.SZSE", FAST, SLOW, USE_TREND, START, END, CAPITAL)
    s = r["stats"]
    kline = r["raw_kline"]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("总收益", f"{s.get('total_return', 0)*100:+.2f}%")
    c2.metric("年化", f"{s.get('annual_return', 0)*100:+.2f}%")
    c3.metric("Sharpe", f"{s.get('sharpe_ratio', 0):+.2f}")
    c4.metric("最大回撤", f"{s.get('max_ddpercent', 0)*100:.2f}%")
    c5.metric("交易数", f"{int(s.get('total_trade_count', 0))}")
    c6.metric("日胜率",
              f"{int(s.get('profit_days', 0))/max(int(s.get('total_days', 1)),1)*100:.1f}%")

    from dashboard import render_kline_with_signals
    st.plotly_chart(render_kline_with_signals(kline, r["daily_df"]), use_container_width=True)

# ============ Tab 3 ============
with tab3:
    st.subheader("backtest_scan 历史结果（30 条）")
    p = Path(__file__).parent / "data" / "backtest_scan.json"
    if p.exists():
        df_hist = pd.read_json(p).sort_values("sharpe", ascending=False)
        st.dataframe(df_hist.head(15), use_container_width=True, hide_index=True)

        fig = go.Figure()
        for strategy_name, color in [("DoubleMa", "#1f77b4"), ("DoubleMa+MA200", "#ff7f0e")]:
            sub = df_hist[df_hist["strategy"] == strategy_name]
            fig.add_trace(go.Scatter(
                x=sub["max_dd_pct"], y=sub["total_return"],
                mode="markers+text",
                text=sub["vt_symbol"].str.split(".").str[0],
                textposition="top center",
                name=strategy_name,
                marker=dict(size=14, color=color),
            ))
        fig.update_layout(
            title="收益 vs 回撤 散点图（30 次回测）",
            xaxis_title="最大回撤 (%)", yaxis_title="总收益 (%)",
            height=500, hovermode="closest",
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)
