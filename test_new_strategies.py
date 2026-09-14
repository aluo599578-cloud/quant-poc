"""
test_new_strategies.py — 测试 6 个新策略 × 4 只 A 股
=====================================================

新策略（除了双均线系列）：
  7. BollingerMeanReversionLean
  8. MacdHistogramLean
  9. VolumeBreakoutLean
  10. AtrTrailStopLean
  11. KeltnerBreakoutLean
  12. RsiDivergenceLean

用法: python test_new_strategies.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import STOCKS as ORIGINAL_STOCKS, fetch_kline, make_bars
from strategies import (
    BollingerMeanReversionLean, MacdHistogramLean, VolumeBreakoutLean,
    AtrTrailStopLean, KeltnerBreakoutLean, RsiDivergenceLean,
)


ALL_STOCKS = list(ORIGINAL_STOCKS) + [("688515.SSE", "688515", "奔图科技")]

STRATEGIES = [
    (BollingerMeanReversionLean, "布林带均值回归", {
        "bb_period": 20, "bb_stddev": 2.0, "rsi_period": 14,
        "rsi_oversold": 30, "rsi_overbought": 70, "stop_loss_pct": 0.05,
        "fixed_size": 1, "warmup_bars": 100,
    }),
    (MacdHistogramLean, "MACD柱状图", {
        "fast_window": 12, "slow_window": 26, "signal_window": 9,
        "stop_loss_pct": 0.05, "fixed_size": 1, "warmup_bars": 100,
    }),
    (VolumeBreakoutLean, "放量突破", {
        "lookback": 20, "vol_multiplier": 1.5, "vol_period": 5,
        "stop_loss_pct": 0.05, "fixed_size": 1, "warmup_bars": 100,
    }),
    (AtrTrailStopLean, "ATR跟踪止损", {
        "fast_window": 10, "slow_window": 30, "atr_period": 14,
        "atr_multiplier": 2.0, "fixed_size": 1, "warmup_bars": 100,
    }),
    (KeltnerBreakoutLean, "Keltner突破", {
        "ema_period": 20, "atr_period": 14, "atr_multiplier": 2.0,
        "fixed_size": 1, "warmup_bars": 100,
    }),
    (RsiDivergenceLean, "RSI背离", {
        "rsi_period": 14, "lookback": 20, "fixed_size": 1, "warmup_bars": 100,
    }),
]


def run_strategy(strategy_class, params, df, tushare_code, name):
    vnpy_sym = tushare_code.replace(".SZ", ".SZSE").replace(".SH", ".SSE")

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vnpy_sym, interval=Interval.DAILY,
        start=datetime(2023, 1, 1), end=datetime(2026, 9, 9),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
    )
    engine.add_strategy(strategy_class, params)
    engine.history_data = list(df_bars)
    engine.run_backtesting()
    engine.calculate_result()
    return engine.calculate_statistics()


def main():
    print("="*80)
    print("  6 个新策略 × 4 只 A 股 = 24 次回测")
    print("="*80)

    results = []

    for vnpy_sym, code, stock_name in ALL_STOCKS:
        tushare_code = vnpy_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        print(f"\n{'─'*80}")
        print(f"  {stock_name} ({tushare_code})")
        print(f"{'─'*80}")

        df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
        global df_bars
        df_bars = make_bars(df, tushare_code)
        print(f"  数据: {len(df_bars)} 根 K 线")
        print(f"  股价涨跌: {(df.iloc[0]['close']/df.iloc[-1]['close']-1)*100:+.1f}%\n")

        print(f"  {'策略':<14} {'收益':<10} {'Sharpe':<8} {'回撤':<10} {'笔数':<6}")
        print(f"  {'─'*14} {'─'*10} {'─'*8} {'─'*10} {'─'*6}")

        for strategy_class, label, params in STRATEGIES:
            try:
                stats = run_strategy(strategy_class, params, df, tushare_code, stock_name)
                if stats is None:
                    continue
                ret = stats.get("total_return", 0) * 100
                shp = stats.get("sharpe_ratio", 0)
                dd = stats.get("max_ddpercent", 0) * 100
                n = int(stats.get("total_trade_count", 0))
                print(f"  {label:<14} {ret:+7.2f}%  {shp:+.3f}  {dd:7.2f}%  {n:>3}")
                results.append({
                    "stock": stock_name, "code": tushare_code, "strategy": label,
                    "return": ret, "sharpe": shp, "dd": dd, "trades": n,
                })
            except Exception as e:
                print(f"  {label:<14} ❌ {e}")

    # 跨股票汇总
    print(f"\n{'='*80}")
    print("  跨股票汇总（按策略）")
    print("="*80)
    print(f"\n  {'策略':<14} {'纳思达':<10} {'TCL':<10} {'西部超导':<10} {'奔图':<10} {'平均'}")
    print(f"  {'─'*14} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")

    for strategy_class, label, _ in STRATEGIES:
        per_stock = {r["stock"]: r for r in results if r["strategy"] == label}
        cells = []
        for stock_name in ["纳思达", "TCL科技", "西部超导", "奔图科技"]:
            r = per_stock.get(stock_name)
            cells.append(f"{r['return']:+7.2f}%" if r else "  -    ")
        avg = sum(r["return"] for r in results if r["strategy"] == label) / 4
        cells.append(f"{avg:+7.2f}%")
        print(f"  {label:<14} {cells[0]:<10} {cells[1]:<10} {cells[2]:<10} {cells[3]:<10} {cells[4]:<10}")

    # 找跨股票平均收益最高的策略
    print(f"\n  🏆 跨股票平均收益排名:")
    strategy_avg = {}
    for r in results:
        strategy_avg.setdefault(r["strategy"], []).append(r["return"])
    for label, rets in sorted(strategy_avg.items(), key=lambda x: -sum(x[1])/len(x[1])):
        avg = sum(rets) / len(rets)
        avg_sharpe = sum(r["sharpe"] for r in results if r["strategy"] == label) / 4
        print(f"    {label:<14} 平均收益 {avg:+7.2f}%  平均 Sharpe {avg_sharpe:+.3f}")

    # 存
    out = Path("data/test_new_strategies.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 结果存到 {out}（{len(results)} 条）")


if __name__ == "__main__":
    main()
