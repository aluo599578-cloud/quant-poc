"""
test_00700_backtest.py — 00700.HK 腾讯 Lean 风格回测
========================================================

00700 腾讯 — HK 蓝筹，2023-2026 区间涨跌。

用法: python test_00700_backtest.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from futu import OpenQuoteContext, RET_OK, KLType
from vnpy.trader.object import BarData
from vnpy.trader.constant import Interval, Exchange
from vnpy_ctastrategy.backtesting import BacktestingEngine

from strategies import (
    DoubleMaLeanStrategy, DoubleMaStopLossLean, DoubleMaTrendStopLossLean,
    MacdLeanStrategy, BollingerMeanReversionLean, AtrTrailStopLean,
)


def fetch_hk_kline(code: str, max_count: int = 1500) -> pd.DataFrame:
    """从富途拉 HK K 线"""
    ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, data, _ = ctx.request_history_kline(
        code, ktype=KLType.K_DAY, max_count=max_count,
    )
    ctx.close()
    if ret != RET_OK:
        raise RuntimeError(f"futu err: {data}")
    return data


def make_bars(df: pd.DataFrame, code: str) -> list:
    bars = []
    for _, row in df.iterrows():
        bars.append(BarData(
            symbol=code,
            exchange=Exchange.SEHK,
            datetime=pd.to_datetime(str(row["time_key"])[:10]),
            interval=Interval.DAILY,
            volume=float(row["volume"]),
            turnover=float(row["turnover"]),
            open_interest=0,
            open_price=float(row["open"]),
            high_price=float(row["high"]),
            low_price=float(row["low"]),
            close_price=float(row["close"]),
            gateway_name="futu",
        ))
    return bars


def run_strategy(strategy_class, params, bars, vt_symbol, name):
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol, interval=Interval.DAILY,
        start=datetime(2023, 1, 1), end=datetime(2026, 9, 14),
        rate=0.001, slippage=0.01, size=100,  # 腾讯 1 手 = 100 股
        pricetick=0.01, capital=200_000,
    )
    engine.add_strategy(strategy_class, params)
    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()
    return engine.calculate_statistics()


def main():
    code = "HK.00700"
    name = "腾讯控股"
    vt_symbol = "00700.SEHK"

    print(f"=== {name} ({code}) - Lean 风格回测 ===\n")

    print("拉富途历史 K 线...")
    df = fetch_hk_kline(code, max_count=1500)
    print(f"  {len(df)} 根 K 线 ({df['time_key'].iloc[-1]} ~ {df['time_key'].iloc[0]})")
    print(f"  最新价: HK${df['close'].iloc[0]:.2f}")

    # 区间涨跌
    first = df["close"].iloc[-1]
    last = df["close"].iloc[0]
    stock_return = (last / first - 1) * 100
    print(f"  区间涨跌: {stock_return:+.2f}% (HK${first:.2f} → HK${last:.2f})\n")

    bars = make_bars(df, code)

    strategies = [
        ("双均线(10,30) + 5%止损", DoubleMaStopLossLean, {
            "fast_window": 10, "slow_window": 30, "stop_loss_pct": 0.05,
            "fixed_size": 1, "warmup_bars": 50,
        }),
        ("双均线(5,20) + 5%止损", DoubleMaStopLossLean, {
            "fast_window": 5, "slow_window": 20, "stop_loss_pct": 0.05,
            "fixed_size": 1, "warmup_bars": 50,
        }),
        ("双均线(10,30)", DoubleMaLeanStrategy, {
            "fast_window": 10, "slow_window": 30, "fixed_size": 1, "warmup_bars": 50,
        }),
        ("双均线+MA200+止损", DoubleMaTrendStopLossLean, {
            "fast_window": 10, "slow_window": 30, "trend_window": 200, "stop_loss_pct": 0.05,
            "fixed_size": 1, "warmup_bars": 250,
        }),
        ("MACD柱状图", MacdLeanStrategy, {
            "fixed_size": 1, "warmup_bars": 50,
        }),
        ("布林带均值回归", BollingerMeanReversionLean, {
            "fixed_size": 1, "warmup_bars": 50,
        }),
        ("ATR跟踪止损", AtrTrailStopLean, {
            "fast_window": 10, "slow_window": 30, "atr_period": 14, "atr_multiplier": 2.0,
            "fixed_size": 1, "warmup_bars": 50,
        }),
    ]

    print(f"  {'策略':<24} {'收益':<10} {'Sharpe':<8} {'回撤':<10} {'笔数':<6}")
    print(f"  {'─'*24} {'─'*10} {'─'*8} {'─'*10} {'─'*6}")

    results = []
    for label, strategy_class, params in strategies:
        try:
            stats = run_strategy(strategy_class, params, bars, vt_symbol, name)
            if stats is None:
                continue
            ret = stats.get("total_return", 0) * 100
            shp = stats.get("sharpe_ratio", 0)
            dd = stats.get("max_ddpercent", 0) * 100
            n = int(stats.get("total_trade_count", 0))
            print(f"  {label:<24} {ret:+7.2f}%  {shp:+.3f}  {dd:7.2f}%  {n:>3}")
            results.append({"strategy": label, "return": ret, "sharpe": shp, "dd": dd, "trades": n})
        except Exception as e:
            print(f"  {label:<24} ❌ {e}")

    # 排名
    if results:
        results.sort(key=lambda x: -x["return"])
        print(f"\n  🏆 排名（按收益）:")
        for i, r in enumerate(results, 1):
            alpha = r["return"] - stock_return
            print(f"    {i}. {r['strategy']:<24} 收益 {r['return']:+7.2f}%  "
                  f"Alpha {alpha:+7.2f}%  Sharpe {r['sharpe']:+.3f}")


if __name__ == "__main__":
    main()
