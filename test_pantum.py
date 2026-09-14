"""
test_pantum.py — 用奔图科技 688515.SH 测试 Lean 风格全套策略
================================================================

跑 6 个 Lean 风格策略在 688515.SH（2023-02 ~ 2026-09）上。

用法: python test_pantum.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import fetch_kline, make_bars
from strategies import (
    DoubleMaLeanStrategy,
    DoubleMaTrendFilterLean,
    DoubleMaStopLossLean,
    DoubleMaTrendStopLossLean,
    MacdLeanStrategy,
    RsiBollingerLeanStrategy,
)


def run_strategy(strategy_class, params, tushare_code, name):
    """跑一个策略"""
    df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
    if len(df) == 0:
        return None
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
    return engine.calculate_statistics()


STRATEGIES = [
    (DoubleMaLeanStrategy, "双均线(5,30)", {
        "fast_window": 5, "slow_window": 30, "fixed_size": 1, "warmup_bars": 100,
    }),
    (DoubleMaLeanStrategy, "双均线(10,30)", {
        "fast_window": 10, "slow_window": 30, "fixed_size": 1, "warmup_bars": 100,
    }),
    (DoubleMaLeanStrategy, "双均线(10,60)", {
        "fast_window": 10, "slow_window": 60, "fixed_size": 1, "warmup_bars": 100,
    }),
    (DoubleMaTrendFilterLean, "双均线+MA200(5,30)", {
        "fast_window": 5, "slow_window": 30, "trend_window": 200,
        "fixed_size": 1, "warmup_bars": 250,
    }),
    (DoubleMaStopLossLean, "双均线(5,30) + 5%止损", {
        "fast_window": 5, "slow_window": 30, "stop_loss_pct": 0.05,
        "fixed_size": 1, "warmup_bars": 100,
    }),
    (DoubleMaTrendStopLossLean, "双均线+MA200+5%止损(5,30)", {
        "fast_window": 5, "slow_window": 30, "trend_window": 200, "stop_loss_pct": 0.05,
        "fixed_size": 1, "warmup_bars": 250,
    }),
    (MacdLeanStrategy, "MACD金叉死叉", {
        "fast_window": 12, "slow_window": 26, "signal_window": 9,
        "fixed_size": 1, "warmup_bars": 100,
    }),
    (RsiBollingerLeanStrategy, "RSI+布林带反转", {
        "rsi_period": 14, "bb_period": 20, "bb_stddev": 2.0,
        "rsi_oversold": 30, "rsi_overbought": 70,
        "fixed_size": 1, "warmup_bars": 100,
    }),
]


def main():
    tushare_code = "688515.SH"
    name = "奔图科技"

    print("="*70)
    print(f"  {name} ({tushare_code}) - Lean 风格策略测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # 显示股价区间
    df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
    print(f"\n  数据: {len(df)} 根 K 线")
    print(f"  起始价: ¥{df.iloc[-1]['close']:.2f}  最新价: ¥{df.iloc[0]['close']:.2f}  "
          f"区间涨跌: {(df.iloc[0]['close']/df.iloc[-1]['close']-1)*100:+.1f}%")

    # 跑所有策略
    results = []
    print(f"\n  {'策略':<28} {'收益':<10} {'Sharpe':<10} {'回撤':<10} {'笔数':<6} {'日胜率'}")
    print(f"  {'-'*28} {'-'*10} {'-'*10} {'-'*10} {'-'*6} {'-'*8}")

    for strategy_class, label, params in STRATEGIES:
        try:
            stats = run_strategy(strategy_class, params, tushare_code, name)
            if stats is None:
                print(f"  {label:<28} ❌ 空数据")
                continue
            ret = stats["total_return"] * 100
            shp = stats["sharpe_ratio"]
            dd = stats["max_ddpercent"] * 100
            n = int(stats["total_trade_count"])
            wr = stats.get("daily_win_rate", 0) * 100
            print(f"  {label:<28} {ret:+7.2f}%  {shp:+.3f}    {dd:7.2f}%  {n:>3}    {wr:5.1f}%")
            stats["_label"] = label
            results.append(stats)
        except Exception as e:
            print(f"  {label:<28} ❌ {e}")

    # 推荐
    if results:
        results.sort(key=lambda x: -x["sharpe_ratio"])
        print(f"\n  🏆 TOP 3 策略:")
        for i, r in enumerate(results[:3], 1):
            print(f"    {i}. {r['_label']}: Sharpe {r['sharpe_ratio']:+.3f}, "
                  f"收益 {r['total_return']*100:+.2f}%, 回撤 {r['max_ddpercent']*100:.1f}%")

    # 存结果
    out = Path("data/test_pantum.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([{k: v for k, v in r.items()} for r in results],
                              indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 结果存到 {out}（{len(results)} 个策略）")


if __name__ == "__main__":
    main()
