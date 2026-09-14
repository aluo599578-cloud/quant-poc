"""
test_02522_backtest.py — 02522.HK 一脉阳光 历史回测
======================================================

用 Lean 风格 indicators + vnpy BacktestingEngine 跑 02522.HK 历史数据。

02522 2024-06-07 上市，HK 主板。

用法: python test_02522_backtest.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from futu import OpenQuoteContext, RET_OK, KLType
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from strategies import DoubleMaLeanStrategy, DoubleMaStopLossLean


def fetch_hk_kline(code: str, start: str, end: str) -> pd.DataFrame:
    """从富途拉 HK K 线"""
    ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
    # 用 max_count 而不是 start/end — start/end 在新 API 里签名变了
    ret, data, _ = ctx.request_history_kline(
        code, ktype=KLType.K_DAY, max_count=1000,
    )
    ctx.close()
    if ret != RET_OK:
        raise RuntimeError(f"futu err: {data}")
    return data


def main():
    code = "HK.02522"
    name = "一脉阳光"
    print(f"=== {name} ({code}) - Lean 风格回测 ===\n")

    # 拉数据
    print("拉富途历史 K 线...")
    df = fetch_hk_kline(code, "2025-01-01", "2026-09-14")
    print(f"  {len(df)} 根 K 线 ({df['time_key'].iloc[-1]} ~ {df['time_key'].iloc[0]})")
    print(f"  最新价: HK${df['close'].iloc[0]:.2f}")

    # 转成 vnpy BarData
    from vnpy.trader.object import BarData
    from vnpy.trader.constant import Exchange
    from datetime import datetime as dt
    bars = []
    for _, row in df.iterrows():
        bars.append(BarData(
            symbol=code,
            exchange=Exchange.SEHK,
            datetime=dt.strptime(str(row["time_key"])[:10], "%Y-%m-%d"),
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

    # vnpy 期望的 symbol 格式
    vnpy_sym = code.replace("HK.", "")  # 02522

    # 跑 3 个策略
    strategies = [
        ("双均线(10,30)", DoubleMaLeanStrategy, {
            "fast_window": 10, "slow_window": 30,
            "fixed_size": 1, "warmup_bars": 50,  # HK 上市晚，warmup 调小
        }),
        ("双均线(10,30) + 5%止损", DoubleMaStopLossLean, {
            "fast_window": 10, "slow_window": 30, "stop_loss_pct": 0.05,
            "fixed_size": 1, "warmup_bars": 50,
        }),
        ("双均线(5,20) + 5%止损", DoubleMaStopLossLean, {
            "fast_window": 5, "slow_window": 20, "stop_loss_pct": 0.05,
            "fixed_size": 1, "warmup_bars": 50,
        }),
    ]

    print(f"\n{'策略':<28} {'收益':<10} {'Sharpe':<10} {'回撤':<10} {'笔数':<6}")
    print(f"{'─'*28} {'─'*10} {'─'*10} {'─'*10} {'─'*6}")

    for label, strategy_class, params in strategies:
        try:
            engine = BacktestingEngine()
            engine.set_parameters(
                vt_symbol=vnpy_sym + ".SEHK", interval=Interval.DAILY,  # vnpy 期望 02522.SEHK
                start=datetime(2025, 1, 1),
                end=datetime(2026, 9, 14),
                rate=0.001, slippage=0.01, size=500,  # HK 1 手 = 500 股
                pricetick=0.01, capital=200_000,  # HK$ 20 万
            )
            engine.add_strategy(strategy_class, params)
            engine.history_data = list(bars)
            engine.run_backtesting()
            engine.calculate_result()
            stats = engine.calculate_statistics()
            ret = stats.get("total_return", 0) * 100
            shp = stats.get("sharpe_ratio", 0)
            dd = stats.get("max_ddpercent", 0) * 100
            n = int(stats.get("total_trade_count", 0))
            print(f"{label:<28} {ret:+7.2f}%  {shp:+.3f}    {dd:7.2f}%  {n:>3}")
        except Exception as e:
            print(f"{label:<28} ❌ {e}")

    # 股价区间涨跌
    first = df["close"].iloc[-1]
    last = df["close"].iloc[0]
    stock_return = (last / first - 1) * 100
    print(f"\n  股价区间涨跌: {stock_return:+.2f}% (HK${first:.2f} → HK${last:.2f})")


if __name__ == "__main__":
    main()
