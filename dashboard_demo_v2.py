"""
dashboard_demo_v2.py — 演示版（已含 9 指标 + Webhook Tab）
=========================================================
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backtest_3stocks import STOCKS
from dashboard import cached_backtest, render_kline_with_signals, _load_webhook_data


st.set_page_config(page_title="A 股量化回测 Dashboard v2", layout="wide")
st.title("📈 A 股量化回测 Dashboard v2")
st.caption("含 Sortino/Calmar/年化波动率风险指标 + Webhook 实时数据 Tab")

FAST, SLOW = 5, 30
USE_TREND = False
START, END = "2023-01-01", "2026-09-04"
CAPITAL = 1_000_000.0

tab1, tab2, tab3, tab4 = st.tabs(["🔍 组合扫描", "📊 单股深度", "📜 历史结果", "📡 Webhook 实时"])

# ============ Tab 1 ============
with tab1:
    st.subheader(f"多股同策略对比 (fast={FAST}, slow={SLOW})")
    rows = []
    progress = st.progress(0.0, "回测中...")
    for i, (vt, code, name) in enumerate(STOCKS):
        progress.progress((i + 1) / len(STOCKS), f"回测 {vt}...")
        r = cached_backtest(vt, FAST, SLOW, USE_TREND, START, END, CAPITAL)
        risk = r.get("risk", {})
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
            "Sortino": round(risk.get("sortino", 0), 2)
                     if isinstance(risk.get("sortino"), (int, float)) else "N/A",
            "Calmar": round(risk.get("calmar", 0), 2),
            "年化波动率(%)": round(risk.get("annual_vol", 0), 2),
        })
    progress.empty()

    df_scan = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
    st.dataframe(df_scan, use_container_width=True, hide_index=True)

# ============ Tab 2: 单股深度（重点验证 9 指标卡）============
with tab2:
    st.subheader("单股深度分析 - 002180 纳思达（9 个核心指标）")
    r = cached_backtest("002180.SZSE", FAST, SLOW, USE_TREND, START, END, CAPITAL)
    s = r["stats"]
    risk = r.get("risk", {})
    kline = r["raw_kline"]

    # 基础 6 个
    st.markdown("**基础指标**")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("总收益", f"{s.get('total_return', 0)*100:+.2f}%")
    c2.metric("年化", f"{s.get('annual_return', 0)*100:+.2f}%")
    c3.metric("Sharpe", f"{s.get('sharpe_ratio', 0):+.2f}")
    c4.metric("最大回撤", f"{s.get('max_ddpercent', 0)*100:.2f}%")
    c5.metric("交易数", f"{int(s.get('total_trade_count', 0))}")
    c6.metric("日胜率",
              f"{int(s.get('profit_days', 0))/max(int(s.get('total_days', 1)),1)*100:.1f}%")

    # 风险调整 3 个
    st.markdown("**风险调整指标**")
    r1, r2, r3 = st.columns(3)
    r1.metric("年化波动率", f"{risk.get('annual_vol', 0):.2f}%",
              help="日收益率标准差 × √240（A 股年化交易日）")
    raw_sortino = risk.get("sortino", 0)
    sortino_str = f"{raw_sortino:+.2f}" if isinstance(raw_sortino, (int, float)) and abs(raw_sortino) <= 50 else "N/A (下行波动极小)"
    r2.metric("Sortino", sortino_str,
              help="(年化收益 - 无风险 2.5%) / 下行波动率。>1 合格，>2 优秀。")
    calmar = risk.get("calmar", 0)
    calmar_str = f"{calmar:+.2f}" if isinstance(calmar, (int, float)) and abs(calmar) <= 100 else "N/A"
    r3.metric("Calmar", calmar_str,
              help="年化收益 / |最大回撤|。>0.5 合格，>1 优秀。")

    st.plotly_chart(render_kline_with_signals(kline, r["daily_df"]), use_container_width=True)

# ============ Tab 3 ============
with tab3:
    st.subheader("backtest_scan 历史结果（30 条）")
    p = Path(__file__).parent / "data" / "backtest_scan.json"
    if p.exists():
        df_hist = pd.read_json(p).sort_values("sharpe", ascending=False)
        st.dataframe(df_hist.head(15), use_container_width=True, hide_index=True)

# ============ Tab 4: Webhook 实时 ============
with tab4:
    st.subheader("📡 TradingView Webhook → Paper Engine 实时数据")
    st.caption("直接读 SQLite，不依赖 webhook gateway 进程在跑")

    db_path = Path(__file__).parent / "data" / "quant-poc.db"
    wh = _load_webhook_data(db_path)

    if not wh.get("running"):
        st.warning(f"数据库不存在：`{db_path}`")
        st.code(f"""# 启动 webhook gateway:
cd C:\\Users\\18566\\Desktop\\quant-poc
QPOC_SECRET=test-secret-abc python -m uvicorn app.webhook_gateway:app --port 8765

# 推送 alert:
curl -X POST http://127.0.0.1:8765/webhook/tradingview \\
  -H "Content-Type: application/json" \\
  -d '{{"secret":"test-secret-abc","event_id":"e1","action":"buy","symbol":"000001.SZ","price":10.0,"volume":100}}'""")
    else:
        acc = wh["account"]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("初始资金", f"¥{acc['init_cash']:,.0f}")
        m2.metric("可用现金", f"¥{acc['cash']:,.0f}")
        pnl = acc["net_pnl"]
        m3.metric("净盈亏", f"¥{pnl:+,.0f}",
                  delta=f"{pnl/acc['init_cash']*100:+.2f}%")
        m4.metric("成交数", acc["trade_count"])
        m5.metric("事件数", acc["event_count"])

        st.markdown("### 持仓")
        positions = wh["positions"]
        if positions:
            df_pos = pd.DataFrame(positions)
            df_pos["市值"] = df_pos["volume"] * df_pos["avg_price"]
            st.dataframe(df_pos, use_container_width=True, hide_index=True)
        else:
            st.info("当前空仓。")

        col_trades, col_events = st.columns(2)
        with col_trades:
            st.markdown("### 最近成交")
            trades = wh["trades"]
            if trades:
                st.dataframe(pd.DataFrame(trades), use_container_width=True,
                             hide_index=True, height=350)
        with col_events:
            st.markdown("### 最近事件")
            events = wh["events"]
            if events:
                st.dataframe(pd.DataFrame(events), use_container_width=True,
                             hide_index=True, height=350)
