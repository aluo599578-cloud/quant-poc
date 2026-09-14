"""
backtest_3stocks_lean.py — Lean 风格 indicators + vnpy 撮合框架
===============================================================

跟 backtest_3stocks.py 对比：
  原版: vnpy DoubleMaStrategy + ArrayManager
  本脚本: 双均线 Lean Strategy + IndicatorManager

期望：结果跟原版完全一致（差异 < 1%）。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import STOCKS, fetch_kline, make_bars
from double_ma_lean_strategy import DoubleMaLeanStrategy


def run_backtest(tushare_code: str, name: str) -> dict:
    """跑一只股的双均线回测"""
    print(f"\n{'='*60}")
    print(f"  {name} ({tushare_code}) - Lean 风格双均线 (5, 30)")
    print(f"{'='*60}")

    # 拉数据
    df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
    if len(df) == 0:
        return {}
    bars = make_bars(df, tushare_code)
    print(f"  数据: {len(bars)} 根 K 线 ({df.iloc[0]['trade_date']} ~ {df.iloc[-1]['trade_date']})")

    # vnpy 期望 .SZSE/.SSE
    vnpy_symbol = tushare_code.replace(".SZ", ".SZSE").replace(".SH", ".SSE")

    # 跑 vnpy BacktestingEngine
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vnpy_symbol, interval=Interval.DAILY,
        start=datetime(2023, 1, 1), end=datetime(2026, 9, 9),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
    )
    engine.add_strategy(DoubleMaLeanStrategy, {
        "fast_window": 5,
        "slow_window": 30,
        "fixed_size": 1,
        "warmup_bars": 100,
    })
    # 关键修复：直接灌入 history_data（绕过 load_data() 清空 bug）
    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()
    stats = engine.calculate_statistics()

    # 输出前 10 笔交易
    for log in engine.logs[:10]:
        if "BUY" in log or "SELL" in log:
            print(f"  {log}")

    # 输出
    return {
        "stock": name,
        "code": tushare_code,
        "total_return": stats["total_return"],
        "annual_return": stats["annual_return"],
        "sharpe": stats["sharpe_ratio"],
        "max_dd": stats["max_ddpercent"],
        "trades": int(stats["total_trade_count"]),
        "daily_win_rate": stats["daily_win_rate"] if "daily_win_rate" in stats else 0,
    }


def main():
    print("="*60)
    print("  Lean 风格双均线 (5, 30) + vnpy 撮合 - 3 只 A 股")
    print("="*60)
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  资金: ¥200,000  费率: 0.0003  滑点: 0.01")
    print(f"  撮合: vnpy BacktestingEngine（与原版一致）")

    results = []
    for vnpy_sym, code, name in STOCKS:
        tushare_code = vnpy_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        r = run_backtest(tushare_code, name)
        if r:
            results.append(r)
            print(f"\n  {r['stock']}:")
            print(f"    总收益: {r['total_return']*100:+.2f}%   年化: {r['annual_return']*100:+.2f}%")
            print(f"    Sharpe: {r['sharpe']:+.3f}   最大回撤: {r['max_dd']*100:.2f}%")
            print(f"    交易数: {r['trades']}   日胜率: {r['daily_win_rate']*100:.2f}%")

    # 对比原版
    print(f"\n{'='*60}")
    print(f"  跟原版对比（原版用 vnpy ArrayManager）")
    print(f"{'='*60}")
    print(f"  {'股票':<10} {'原版收益':<10} {'Lean 收益':<10} {'差异':<10}")
    original = {
        "纳思达": 0.0011,  # +0.11%
        "TCL科技": -0.0004,  # -0.04%
        "西部超导": -0.0057,  # -0.57%
    }
    for r in results:
        orig = original.get(r["stock"], 0)
        diff = (r["total_return"] - orig) * 100
        print(f"  {r['stock']:<10} {orig*100:+7.2f}%   {r['total_return']*100:+7.2f}%   {diff:+6.2f}%")


if __name__ == "__main__":
    main()
