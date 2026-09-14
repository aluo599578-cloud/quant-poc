"""
debug_compare.py — 详细对比 Lean 风格 vs 原版的逐笔交易
=======================================================
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import STOCKS, fetch_kline, make_bars
from double_ma_lean_strategy import DoubleMaLeanStrategy
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy


def run_one(strategy_class, params, tushare_code, name):
    df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
    bars = make_bars(df, tushare_code)
    vnpy_sym = tushare_code.replace(".SZ", ".SZSE").replace(".SH", ".SSE")

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vnpy_sym, interval=Interval.DAILY,
        start=datetime(2023, 1, 1), end=datetime(2026, 9, 9),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
    )
    engine.add_strategy(strategy_class, params)
    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()
    stats = engine.calculate_statistics()
    return stats, engine


def main():
    print("对比 002180 纳思达:")
    tushare_code = "002180.SZ"

    print("\n--- 原版 vnpy DoubleMaStrategy ---")
    stats1, _ = run_one(DoubleMaStrategy, {"fast_window": 5, "slow_window": 30},
                       tushare_code, "纳思达")
    print(f"  total_return: {stats1['total_return']*100:+.2f}%")
    print(f"  trades: {stats1['total_trade_count']}")
    print(f"  sharpe: {stats1['sharpe_ratio']:+.3f}")
    print(f"  max_dd: {stats1['max_ddpercent']*100:.2f}%")

    print("\n--- Lean 风格 DoubleMaLeanStrategy ---")
    stats2, _ = run_one(DoubleMaLeanStrategy, {"fast_window": 5, "slow_window": 30, "fixed_size": 1},
                       tushare_code, "纳思达")
    print(f"  total_return: {stats2['total_return']*100:+.2f}%")
    print(f"  trades: {stats2['total_trade_count']}")
    print(f"  sharpe: {stats2['sharpe_ratio']:+.3f}")
    print(f"  max_dd: {stats2['max_ddpercent']*100:.2f}%")


if __name__ == "__main__":
    main()
