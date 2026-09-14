"""
quant_screener.py — 量化版研报评分器
======================================

用 tushare 财务数据 + 价格动量给 A 股打分。
这是 OpenClaw 深度研报之前的"快速筛选层"。

用法:
  # 筛沪深 300
  python quant_screener.py --index csi300

  # 筛中证 500
  python quant_screener.py --index csi500

  # 自定义列表
  python quant_screener.py --codes 002180.SZ 000100.SZ 688515.SH ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import tushare as ts
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import fetch_kline, make_bars
from strategies import BollingerMeanReversionLean


def get_tushare_pro():
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise ValueError("TUSHARE_TOKEN env var not set")
    return ts.pro_api(token)


def get_index_stocks(index_code: str = "000300.SH") -> list[str]:
    """获取指数成分股"""
    pro = get_tushare_pro()
    df = pro.index_weight(index_code=index_code, start_date=datetime.now().strftime("%Y%m%d"))
    if df is None or len(df) == 0:
        # 用今天的日期没数据，回退到上个月
        last_month = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        df = pro.index_weight(index_code=index_code, start_date=last_month)
    if df is None or len(df) == 0:
        return []
    return list(df["con_code"].unique())


def get_financial_metrics(code: str) -> dict:
    """拉一只股的财务数据"""
    pro = get_tushare_pro()
    metrics = {"code": code, "pe": None, "pb": None, "roe": None,
               "revenue_growth": None, "profit_growth": None, "market_cap": None}

    # 1. 每日指标 (PE / PB / 总市值)
    today = datetime.now().strftime("%Y%m%d")
    last_month = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    try:
        df = pro.daily_basic(ts_code=code, start_date=last_month, end_date=today)
        if df is not None and len(df) > 0:
            latest = df.iloc[0]
            metrics["pe"] = float(latest.get("pe_ttm", 0)) or None
            metrics["pb"] = float(latest.get("pb", 0)) or None
            metrics["market_cap"] = float(latest.get("total_mv", 0)) or None  # 百万
    except Exception as e:
        print(f"  {code} daily_basic err: {e}")

    # 2. 财务指标 (ROE / 增速)
    try:
        df = pro.fina_indicator(ts_code=code, period=datetime.now().strftime("%Y%m%d"))
        if df is None or len(df) == 0:
            # 上一季度
            last_q = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
            df = pro.fina_indicator(ts_code=code, period=last_q)
        if df is not None and len(df) > 0:
            latest = df.iloc[0]
            metrics["roe"] = float(latest.get("roe", 0)) or None
            metrics["revenue_growth"] = float(latest.get("or_yoy", 0)) or None  # 营收同比
            metrics["profit_growth"] = float(latest.get("netprofit_yoy", 0)) or None
    except Exception as e:
        print(f"  {code} fina_indicator err: {e}")

    return metrics


def run_lean_backtest(code: str) -> float:
    """跑布林带均值回归回测，返回 Sharpe"""
    try:
        df = fetch_kline(code, "2023-01-01", "2026-09-09")
        if len(df) < 100:
            return 0.0
        bars = make_bars(df, code)
        vnpy_sym = code.replace(".SZ", ".SZSE").replace(".SH", ".SSE")

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol=vnpy_sym, interval=Interval.DAILY,
            start=datetime(2023, 1, 1), end=datetime(2026, 9, 9),
            rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
        )
        engine.add_strategy(BollingerMeanReversionLean, {
            "bb_period": 20, "bb_stddev": 2.0, "rsi_period": 14,
            "rsi_oversold": 30, "rsi_overbought": 70, "stop_loss_pct": 0.05,
            "fixed_size": 1, "warmup_bars": 100,
        })
        engine.history_data = list(bars)
        engine.run_backtesting()
        engine.calculate_result()
        stats = engine.calculate_statistics()
        return float(stats.get("sharpe_ratio", 0))
    except Exception as e:
        print(f"  {code} backtest err: {e}")
        return 0.0


def score_stock(metrics: dict, sharpe: float) -> dict:
    """打分：4 个维度各 25 分"""
    score = 0
    breakdown = {}

    # 估值 (25分)
    pe = metrics.get("pe") or 0
    if pe <= 0:
        valuation = 10  # 亏损公司
    elif pe < 20:
        valuation = 25
    elif pe < 40:
        valuation = 20
    elif pe < 80:
        valuation = 12
    else:
        valuation = 5
    breakdown["valuation"] = valuation
    score += valuation

    # 盈利质量 (25分) - ROE
    roe = metrics.get("roe") or 0
    if roe > 20:
        profitability = 25
    elif roe > 15:
        profitability = 22
    elif roe > 10:
        profitability = 18
    elif roe > 5:
        profitability = 12
    else:
        profitability = 5
    breakdown["profitability"] = profitability
    score += profitability

    # 增长 (25分) - 营收同比
    growth = metrics.get("revenue_growth") or 0
    if growth > 30:
        g_score = 25
    elif growth > 15:
        g_score = 20
    elif growth > 5:
        g_score = 15
    elif growth > 0:
        g_score = 10
    else:
        g_score = 3
    breakdown["growth"] = g_score
    score += g_score

    # 技术面 (25分) - Lean 布林带 Sharpe
    if sharpe > 1.0:
        tech = 25
    elif sharpe > 0.5:
        tech = 20
    elif sharpe > 0.3:
        tech = 15
    elif sharpe > 0.0:
        tech = 10
    else:
        tech = 0
    breakdown["technical"] = tech
    score += tech

    metrics["sharpe"] = sharpe
    metrics["score"] = score
    metrics["breakdown"] = breakdown
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="000300.SH", help="指数代码（000300.SH=沪深300）")
    parser.add_argument("--codes", nargs="*", help="自定义股票列表（覆盖 --index）")
    parser.add_argument("--top", type=int, default=20, help="输出 Top N")
    parser.add_argument("--out", default="data/quant_screen.json", help="输出文件")
    args = parser.parse_args()

    print("="*70)
    print("  quant_screener.py — 量化版研报评分器")
    print("="*70)

    if args.codes:
        codes = args.codes
        print(f"\n[1] 自定义股票: {len(codes)} 只")
    else:
        print(f"\n[1] 拉 {args.index} 成分股...")
        codes = get_index_stocks(args.index)
        print(f"    {len(codes)} 只")
        if len(codes) == 0:
            print("    ❌ 拉取失败，用 demo 列表")
            codes = ["002180.SZ", "000100.SZ", "688122.SH", "688515.SH",
                     "002594.SZ", "300750.SZ", "600519.SH", "601318.SH",
                     "000858.SZ", "600276.SH", "000333.SZ", "300059.SZ"]

    print(f"\n[2] 给 {len(codes)} 只股打分...")

    results = []
    for i, code in enumerate(codes, 1):
        if i % 10 == 0:
            print(f"    进度: {i}/{len(codes)}")
        metrics = get_financial_metrics(code)
        sharpe = run_lean_backtest(code)
        scored = score_stock(metrics, sharpe)
        results.append(scored)

    # 排序
    results.sort(key=lambda x: -x["score"])

    # 输出
    print(f"\n[3] Top {args.top} 评分:")
    print(f"  {'代码':<12} {'分数':<5} {'估值':<5} {'盈利':<5} {'增长':<5} {'技术':<5} {'PE':<8} {'ROE':<6} {'Sharpe':<8}")
    print(f"  {'─'*12} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*8} {'─'*6} {'─'*8}")
    for r in results[:args.top]:
        pe = f"{r.get('pe'):.1f}" if r.get('pe') else "—"
        roe = f"{r.get('roe'):.1f}" if r.get('roe') else "—"
        print(f"  {r['code']:<12} {r['score']:>3}   "
              f"{r['breakdown']['valuation']:>3}   "
              f"{r['breakdown']['profitability']:>3}   "
              f"{r['breakdown']['growth']:>3}   "
              f"{r['breakdown']['technical']:>3}   "
              f"{pe:<8} {roe:<6} {r['sharpe']:+.3f}")

    # 存
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 存到 {out}（{len(results)} 只）")


if __name__ == "__main__":
    main()
