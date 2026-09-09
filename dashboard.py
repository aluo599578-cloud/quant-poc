"""
dashboard.py — A 股回测 Web Dashboard
======================================

参考 zinan92/backtest 的 quant-dashboard 设计：
- Sidebar：股票代码 + 日期 + 策略参数 + 一键回测
- 主区 Tab1：组合扫描（你已有 stocks.txt 三只股）
- 主区 Tab2：单股深度分析（K 线 + 买卖点 + 净值曲线）

技术栈：
- Streamlit（UI）
- Plotly（交互图）
- vnpy BacktestingEngine（回测引擎）
- tushare（数据）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# 让脚本可独立运行
sys.path.insert(0, str(Path(__file__).parent))
from backtest_3stocks import STOCKS, fetch_kline, make_bars, to_tushare_code  # noqa
from backtest_scan import DoubleMaWithTrendFilter  # noqa

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy

# 风险调整指标的年化交易日
ANNUAL_TRADING_DAYS = 240
RISK_FREE_RATE = 0.025  # 无风险利率 2.5%（A 股近似）


# ============== 缓存回测结果（同一参数不重复跑） ==============

@st.cache_data(show_spinner=False)
def cached_backtest(vt_symbol: str, fast: int, slow: int,
                    trend: bool, start: str, end: str,
                    capital: float) -> dict:
    """跑一次回测，结果 dict 化（numpy 兼容）。"""
    df = fetch_kline(to_tushare_code(vt_symbol), start, end)
    bars = make_bars(df, vt_symbol)

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=Interval.DAILY,
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat(end),
        rate=0.0003,
        slippage=0.01,
        size=100,
        pricetick=0.01,
        capital=capital,
    )
    if trend:
        engine.add_strategy(DoubleMaWithTrendFilter, {
            "fast_window": fast,
            "slow_window": slow,
            "trend_window": 200,
        })
    else:
        engine.add_strategy(DoubleMaStrategy, {
            "fast_window": fast,
            "slow_window": slow,
        })
    engine.history_data = list(bars)
    engine.run_backtesting()
    df_result = engine.calculate_result()
    stats = engine.calculate_statistics()

    # 风险调整指标（Sortino / Calmar / 年化波动率）
    risk_metrics = _compute_risk_metrics(df_result, stats)

    return {
        "stats": stats,
        "daily_df": df_result,
        "raw_kline": df,
        "risk": risk_metrics,
    }


def _compute_risk_metrics(daily_df: pd.DataFrame, stats: dict) -> dict:
    """从 daily_df + stats 算 Sortino / Calmar / 年化波动率。

    关键：用 daily_df['net_pnl'] / balance.shift(1) 算账户日收益率，
    比 vnpy 自带 return 字段更稳定（不忽略微小盈亏）。
    """
    import numpy as np
    if daily_df is None or daily_df.empty:
        return {"annual_vol": 0.0, "sortino": 0.0, "calmar": 0.0,
                "downside_vol": 0.0, "max_dd_pct": 0.0}

    # 自己算日收益率：当日盈亏 / 昨日权益
    if "net_pnl" in daily_df.columns and "balance" in daily_df.columns:
        bal = daily_df["balance"].shift(1).fillna(daily_df["balance"].iloc[0])
        rets = (daily_df["net_pnl"] / bal).replace([np.inf, -np.inf], 0).fillna(0)
    elif "return" in daily_df.columns:
        rets = daily_df["return"].dropna()
    else:
        return {"annual_vol": 0.0, "sortino": 0.0, "calmar": 0.0,
                "downside_vol": 0.0, "max_dd_pct": 0.0}

    rets = rets[rets != 0]  # 去掉空仓日的 0
    if rets.empty:
        return {"annual_vol": 0.0, "sortino": 0.0, "calmar": 0.0,
                "downside_vol": 0.0, "max_dd_pct": 0.0}

    # 年化波动率
    daily_vol = float(rets.std())
    annual_vol = daily_vol * np.sqrt(ANNUAL_TRADING_DAYS) * 100  # 转百分数

    # 年化收益：用 vnpy 的 stats（vnpy 算好了）
    annual_ret = float(stats.get("annual_return", 0))
    max_dd = float(stats.get("max_ddpercent", 0))

    # 下行波动率
    downside = rets[rets < 0]
    downside_vol = float(downside.std() * np.sqrt(ANNUAL_TRADING_DAYS)) if len(downside) > 0 else 0.0

    # Sortino = (年化收益 - 无风险) / 下行波动
    # 用 abs(downside_vol) 防止微小负波动导致 Sortino 极端大
    dv = abs(downside_vol)
    if dv > 1e-9:
        sortino = (annual_ret - RISK_FREE_RATE) / dv
        # 显示合理性截断：极端值用 N/A 表示
        if not np.isfinite(sortino) or abs(sortino) > 100:
            sortino_display = "N/A"
        else:
            sortino_display = sortino
    else:
        sortino_display = float("nan")

    # Calmar = 年化收益 / |最大回撤|
    if abs(max_dd) > 1e-9:
        calmar = annual_ret / abs(max_dd)
    else:
        calmar = float("inf")

    return {
        "annual_vol": annual_vol,
        "annual_ret": annual_ret,
        "sortino": sortino_display,
        "calmar": calmar,
        "downside_vol": downside_vol,
        "max_dd_pct": max_dd,
    }


def _load_webhook_data(db_path: Path) -> dict:
    """直接读 SQLite，不依赖 webhook gateway 进程在跑。"""
    import sqlite3
    if not db_path.exists():
        return {"running": False, "account": {}, "positions": [],
                "trades": [], "events": []}
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            # events
            ev_rows = conn.execute(
                "SELECT event_id, action, symbol, price, volume, strategy, received_at "
                "FROM events ORDER BY received_at DESC LIMIT 100"
            ).fetchall()
            events = [dict(r) for r in ev_rows]
            # trades
            tr_rows = conn.execute(
                "SELECT tradeid, orderid, event_id, symbol, direction, offset, "
                "       price, volume, traded_at "
                "FROM trades ORDER BY traded_at DESC LIMIT 100"
            ).fetchall()
            trades = [dict(r) for r in tr_rows]
            # account = SUM(cash flow)
            flow = conn.execute(
                "SELECT "
                "  SUM(CASE WHEN direction='多' THEN -price*volume "
                "           ELSE price*volume END) AS cashflow "
                "FROM trades"
            ).fetchone()
            cashflow = float(flow["cashflow"] or 0.0)
            init_cash = 1_000_000.0
            cash = init_cash + cashflow
            # positions = 按 symbol 分组汇总 volume + weighted avg
            # 真实平均成本 = 累计买入金额 / 累计买入股数（卖出不影响成本，只减少持仓）
            pos_rows = conn.execute(
                "SELECT symbol, "
                "       SUM(CASE WHEN direction='多' THEN volume "
                "                ELSE -volume END) AS net_volume, "
                "       SUM(CASE WHEN direction='多' THEN price*volume "
                "                ELSE 0 END) AS buy_cost, "
                "       SUM(CASE WHEN direction='多' THEN volume "
                "                ELSE 0 END) AS buy_volume, "
                "       MAX(traded_at) AS last_time "
                "FROM trades GROUP BY symbol HAVING net_volume != 0"
            ).fetchall()
            positions = []
            for r in pos_rows:
                nv = float(r["net_volume"])
                bv = float(r["buy_volume"] or 0)
                avg_price = float(r["buy_cost"]) / bv if bv else 0
                positions.append({
                    "symbol": r["symbol"],
                    "volume": int(nv),
                    "avg_price": round(avg_price, 4),
                    "last_time": r["last_time"],
                })
            return {
                "running": True,
                "account": {"cash": round(cash, 2),
                            "init_cash": init_cash,
                            "net_pnl": round(cashflow, 2),
                            "trade_count": len(trades),
                            "event_count": len(events)},
                "positions": positions,
                "trades": trades,
                "events": events,
            }
    except Exception as e:
        return {"running": False, "error": str(e)}


def render_kline_with_signals(raw_kline: pd.DataFrame, daily_df: pd.DataFrame) -> go.Figure:
    """画 K 线 + 两条均线 + 买卖点 + 净值曲线。"""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.03,
    )

    # K 线
    fig.add_trace(go.Candlestick(
        x=raw_kline["trade_date"],
        open=raw_kline["open"],
        high=raw_kline["high"],
        low=raw_kline["low"],
        close=raw_kline["close"],
        name="K线",
        increasing_line_color="#ef5350",  # A 股惯例：红涨绿跌
        decreasing_line_color="#26a69a",
    ), row=1, col=1)

    # 均线
    raw_kline["ma_fast"] = raw_kline["close"].rolling(5).mean()
    raw_kline["ma_slow"] = raw_kline["close"].rolling(30).mean()
    fig.add_trace(go.Scatter(
        x=raw_kline["trade_date"], y=raw_kline["ma_fast"],
        name="MA5", line=dict(color="orange", width=1)
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=raw_kline["trade_date"], y=raw_kline["ma_slow"],
        name="MA30", line=dict(color="blue", width=1)
    ), row=1, col=1)

    # 净值曲线
    if daily_df is not None and not daily_df.empty:
        fig.add_trace(go.Scatter(
            x=daily_df.index, y=daily_df["balance"],
            name="策略净值", line=dict(color="purple", width=2),
            fill="tozeroy", fillcolor="rgba(128,0,128,0.1)"
        ), row=2, col=1)
        # 加回撤辅助轴
        fig.add_trace(go.Scatter(
            x=daily_df.index, y=daily_df["ddpercent"] * 100,
            name="回撤(%)", line=dict(color="red", width=1, dash="dot"),
            yaxis="y3",
        ), row=2, col=1)
        fig.update_layout(
            yaxis3=dict(title="回撤(%)", overlaying="y2", side="right",
                        range=[min(-30, daily_df["ddpercent"].min() * 100 - 5), 1]),
        )

    fig.update_layout(
        height=600, xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


# ============== 页面 ==============

st.set_page_config(
    page_title="A 股量化回测 Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 A 股量化回测 Dashboard")
st.caption("基于 vnpy + tushare + Plotly。参考 github.com/zinan92/backtest 风格。")

# ----- Sidebar -----
with st.sidebar:
    st.header("⚙️ 回测参数")

    # 股票选择（多选：组合扫描）
    stock_options = {f"{code} {name} ({vt})": vt for vt, code, name in STOCKS}
    extra = st.text_input(
        "加股票（A 股代码，如 600519.SH）",
        value="",
        help="逗号分隔，加到扫描列表。留空只用预设三只。",
    )
    selected_labels = st.multiselect(
        "选择股票",
        options=list(stock_options.keys()),
        default=list(stock_options.keys()),
    )
    selected_symbols = [stock_options[l] for l in selected_labels]
    if extra.strip():
        for sym in extra.replace("，", ",").split(","):
            sym = sym.strip().upper()
            if sym and "." in sym and sym not in selected_symbols:
                selected_symbols.append(sym)

    # 日期
    default_end = datetime.now().date()
    default_start = default_end - timedelta(days=365 * 2)
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("开始", default_start, min_value=datetime(2015, 1, 1).date())
    with c2:
        end_date = st.date_input("结束", default_end, min_value=start_date)

    # 策略参数
    st.subheader("策略")
    strategy = st.radio(
        "策略类型",
        options=["DoubleMa", "DoubleMa+MA200"],
        index=0,
        help="DoubleMa=纯双均线；DoubleMa+MA200=加上 MA200 趋势过滤（A 股只能做多）",
    )
    use_trend = strategy == "DoubleMa+MA200"
    cf, cs = st.columns(2)
    with cf:
        fast = st.number_input("快线", min_value=2, max_value=60, value=5)
    with cs:
        slow = st.number_input("慢线", min_value=5, max_value=250, value=30)

    capital = st.number_input("初始资金 (¥)", min_value=10000.0, value=1_000_000.0, step=100000.0)

    run_btn = st.button("🚀 运行回测", type="primary", use_container_width=True)

# ----- 主区 -----
tab1, tab2, tab3, tab4 = st.tabs(["🔍 组合扫描", "📊 单股深度", "📜 历史结果", "📡 Webhook 实时"])

# ============ Tab 1: 组合扫描 ============
with tab1:
    st.subheader("多股同策略对比")
    if not run_btn:
        st.info("👈 在左侧设置参数，点 **🚀 运行回测** 开始。")
    elif not selected_symbols:
        st.warning("请至少选一只股票。")
    else:
        rows = []
        progress = st.progress(0.0, "回测中...")
        for i, vt in enumerate(selected_symbols):
            progress.progress((i + 1) / len(selected_symbols), f"回测 {vt}...")
            try:
                r = cached_backtest(
                    vt, fast, slow, use_trend,
                    start_date.isoformat(), end_date.isoformat(), capital,
                )
                s = r["stats"]
                rows.append({
                    "代码": vt,
                    "总收益(%)": round(s.get("total_return", 0) * 100, 2),
                    "年化(%)": round(s.get("annual_return", 0) * 100, 2),
                    "Sharpe": round(s.get("sharpe_ratio", 0), 2),
                    "最大回撤(%)": round(s.get("max_ddpercent", 0) * 100, 2),
                    "胜日/总": f"{int(s.get('profit_days', 0))}/{int(s.get('total_days', 1))}",
                    "交易数": int(s.get("total_trade_count", 0)),
                })
            except Exception as e:
                rows.append({"代码": vt, "错误": str(e)[:60]})
        progress.empty()

        df_scan = pd.DataFrame(rows)
        st.dataframe(
            df_scan.sort_values("Sharpe", ascending=False, na_position="last"),
            use_container_width=True,
            hide_index=True,
        )

        # 收益柱状图
        ok = df_scan.dropna(subset=["总收益(%)"])
        if not ok.empty:
            fig = go.Figure(go.Bar(
                x=ok["代码"], y=ok["总收益(%)"],
                marker_color=["#26a69a" if v >= 0 else "#ef5350" for v in ok["总收益(%)"]],
                text=[f"{v:+.1f}%" for v in ok["总收益(%)"]],
                textposition="outside",
            ))
            fig.update_layout(
                title="总收益对比",
                height=400, yaxis_title="总收益 (%)",
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

# ============ Tab 2: 单股深度 ============
with tab2:
    st.subheader("单股深度分析")
    if not run_btn:
        st.info("👈 先在左侧点 **🚀 运行回测**。")
    elif not selected_symbols:
        st.warning("请至少选一只股票。")
    else:
        pick = st.selectbox("选一只股深度分析", options=selected_symbols)
        try:
            r = cached_backtest(
                pick, fast, slow, use_trend,
                start_date.isoformat(), end_date.isoformat(), capital,
            )
            s = r["stats"]
            kline = r["raw_kline"]

            # 关键指标 9 列（基础 6 + 风险调整 3）
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("总收益", f"{s.get('total_return', 0)*100:+.2f}%")
            c2.metric("年化", f"{s.get('annual_return', 0)*100:+.2f}%")
            c3.metric("Sharpe", f"{s.get('sharpe_ratio', 0):+.2f}")
            c4.metric("最大回撤", f"{s.get('max_ddpercent', 0)*100:.2f}%")
            c5.metric("交易数", f"{int(s.get('total_trade_count', 0))}")
            c6.metric("日胜率",
                      f"{int(s.get('profit_days', 0))/max(int(s.get('total_days', 1)),1)*100:.1f}%")

            # 风险调整指标（Sortino / Calmar / 年化波动率）
            risk = r.get("risk", {})
            ann_vol = risk.get("annual_vol", 0)         # 百分数
            raw_sortino = risk.get("sortino", 0)
            calmar = risk.get("calmar", 0)
            st.markdown("**风险调整指标**")
            r1, r2, r3 = st.columns(3)
            r1.metric("年化波动率", f"{ann_vol:.2f}%",
                      help="日收益率标准差 × √240（A 股年化交易日）。代表策略波动剧烈程度。")
            # Sortino 异常大（>50 或非有限）显示 N/A，否则显示数值
            if isinstance(raw_sortino, (int, float)) and abs(raw_sortino) <= 50:
                sortino_str = f"{raw_sortino:+.2f}"
            else:
                sortino_str = "N/A (下行波动极小)"
            r2.metric("Sortino", sortino_str,
                      help="(年化收益 - 无风险 2.5%) / 下行波动率。>1 为合格，>2 为优秀。只惩罚亏损波动，比 Sharpe 更合理。")
            calmar_str = f"{calmar:+.2f}" if isinstance(calmar, (int, float)) and abs(calmar) <= 100 else "N/A"
            r3.metric("Calmar", calmar_str,
                      help="年化收益 / |最大回撤|。越大越好，>0.5 合格，>1 优秀。")

            # K 线 + 净值
            st.plotly_chart(render_kline_with_signals(kline, r["daily_df"]), use_container_width=True)

            # 详细 stats 表
            with st.expander("📋 完整统计指标"):
                st.json({k: float(v) if isinstance(v, (int, float)) else str(v)
                         for k, v in s.items()})
        except Exception as e:
            st.error(f"回测失败：{e}")
            import traceback; st.code(traceback.format_exc())

# ============ Tab 3: 历史结果（之前 scan 脚本跑过的 30 条）============
with tab3:
    st.subheader("backtest_scan 历史结果（30 条）")
    p = Path(__file__).parent / "data" / "backtest_scan.json"
    if p.exists():
        df_hist = pd.read_json(p)
        df_hist = df_hist.sort_values("sharpe", ascending=False)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        fig = go.Figure()
        for strategy_name, color in [("DoubleMa", "#1f77b4"), ("DoubleMa+MA200", "#ff7f0e")]:
            sub = df_hist[df_hist["strategy"] == strategy_name]
            fig.add_trace(go.Scatter(
                x=sub["max_dd_pct"], y=sub["total_return"],
                mode="markers+text",
                text=sub["vt_symbol"].str.split(".").str[0],
                textposition="top center",
                name=strategy_name,
                marker=dict(size=12, color=color),
            ))
        fig.update_layout(
            title="收益 vs 回撤 散点图（30 次回测）",
            xaxis_title="最大回撤 (%)", yaxis_title="总收益 (%)",
            height=500, hovermode="closest",
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("data/backtest_scan.json 不存在，先跑 backtest_scan.py。")


# ============ Tab 4: Webhook 实时数据 ============
with tab4:
    st.subheader("TradingView Webhook → Paper Engine 实时数据")
    st.caption("直接读 SQLite，无需 webhook gateway 进程在跑。重启 dashboard 可刷新。")

    db_path = Path(__file__).parent / "data" / "quant-poc.db"
    wh = _load_webhook_data(db_path)

    if not wh.get("running"):
        st.warning(
            f"数据库不存在或读失败：`{db_path}`。\n\n"
            "先启动 webhook gateway 并推送一些 alert：\n\n"
            "```bash\n"
            "cd C:\\Users\\18566\\Desktop\\quant-poc\n"
            "QPOC_SECRET=test-secret-abc python -m uvicorn app.webhook_gateway:app --port 8765\n"
            "```\n\n"
            "然后用 tests/e2e_smoke.py 或 curl 推送 alert。"
        )
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

        # 持仓
        st.markdown("### 持仓")
        positions = wh["positions"]
        if positions:
            df_pos = pd.DataFrame(positions)
            df_pos["市值"] = df_pos["volume"] * df_pos["avg_price"]
            st.dataframe(df_pos, use_container_width=True, hide_index=True)
        else:
            st.info("当前空仓。")

        # 成交 + 事件两栏
        col_trades, col_events = st.columns(2)
        with col_trades:
            st.markdown("### 最近成交（最多 100）")
            trades = wh["trades"]
            if trades:
                st.dataframe(pd.DataFrame(trades), use_container_width=True,
                             hide_index=True, height=350)
            else:
                st.info("无成交记录。")
        with col_events:
            st.markdown("### 最近事件（最多 100）")
            events = wh["events"]
            if events:
                st.dataframe(pd.DataFrame(events), use_container_width=True,
                             hide_index=True, height=350)
            else:
                st.info("无事件记录。")

        # 模拟一个推送按钮（不真发请求，只演示 JSON）
        with st.expander("🛠 模拟推送 alert（不真发，仅预览）"):
            st.code(json.dumps({
                "secret": "test-secret-abc",
                "event_id": f"tv-demo-{datetime.now().strftime('%H%M%S')}",
                "action": "buy",
                "symbol": "000001.SZ",
                "price": 12.5,
                "volume": 100,
                "strategy": "dashboard-demo"
            }, ensure_ascii=False, indent=2), language="json")
            st.caption("复制上面 JSON → 用 curl 推到 webhook gateway 即可。")
