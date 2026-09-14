"""
backtest_scan_lean.py — 30 次策略扫描 (Lean 风格 indicators)
============================================================

跑 3 只 A 股 × 5 组参数 × 2 模式 = 30 次回测。

用法: python backtest_scan_lean.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import STOCKS, fetch_kline, make_bars
from strategies import (
    DoubleMaLeanStrategy,
    DoubleMaTrendFilterLean,
    DoubleMaStopLossLean,
    DoubleMaTrendStopLossLean,
    MacdLeanStrategy,
    RsiBollingerLeanStrategy,
)


# 5 组参数 + 2 模式 = 10 个回测 × 3 只股 = 30 次
PARAMS = [(5, 20), (5, 30), (10, 30), (10, 60), (5, 60)]
MODES = [
    ("DoubleMaLeanStrategy", "纯双均线"),
    ("DoubleMaStopLossLean", "+ 5%止损"),
]

STRATEGY_MAP = {
    "DoubleMaLeanStrategy": DoubleMaLeanStrategy,
    "DoubleMaStopLossLean": DoubleMaStopLossLean,
}


def run_one(strategy_class, params, tushare_code):
    """跑一次回测"""
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
    return {
        "total_return": stats["total_return"],
        "annual_return": stats["annual_return"],
        "sharpe_ratio": stats["sharpe_ratio"],
        "max_ddpercent": stats["max_ddpercent"],
        "total_trade_count": int(stats["total_trade_count"]),
        "daily_win_rate": stats.get("daily_win_rate", 0),
    }


def main():
    print("="*70)
    print(f"  Lean 风格策略扫描（{len(PARAMS)} 参数 × {len(MODES)} 模式 × 3 股 = {len(PARAMS)*len(MODES)*3} 次）")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    results = []

    for vnpy_sym, code, name in STOCKS:
        tushare_code = vnpy_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        print(f"\n--- {name} ({tushare_code}) ---")

        for fast, slow in PARAMS:
            for mode_class, mode_label in MODES:
                strategy_class = STRATEGY_MAP[mode_class]
                warmup = 200 if "trend" in mode_class.lower() else 100
                stop_loss = 0.05 if "StopLoss" in mode_class else 0.0
                params = {
                    "fast_window": fast,
                    "slow_window": slow,
                    "fixed_size": 1,
                    "warmup_bars": warmup,
                }
                if stop_loss:
                    params["stop_loss_pct"] = stop_loss
                sig = f"({fast},{slow}) {mode_label}"
                print(f"  [{sig:20s}] ...", end=" ", flush=True)
                try:
                    stats = run_one(strategy_class, params, tushare_code)
                    ret = stats["total_return"] * 100
                    shp = stats["sharpe_ratio"]
                    dd = stats["max_ddpercent"] * 100
                    n = stats["total_trade_count"]
                    print(f"收益 {ret:+7.2f}%  Sharpe {shp:+.3f}  回撤 {dd:7.2f}%  笔数 {n:3d}")
                    stats.update({"stock": name, "code": code, "fast": fast, "slow": slow, "mode": mode_label})
                    results.append(stats)
                except Exception as e:
                    print(f"❌ {e}")

    # 汇总
    print(f"\n{'='*70}")
    print("  跨股票推荐")
    print("="*70)
    grouped = {}
    for r in results:
        key = (r["fast"], r["slow"], r["mode"])
        grouped.setdefault(key, []).append(r["sharpe_ratio"])

    print(f"\n  {'参数':<10} {'模式':<12} {'最低Sharpe':<10} {'平均Sharpe':<10} {'跨股均收益'}")
    print(f"  {'-'*10} {'-'*12} {'-'*10} {'-'*10} {'-'*12}")
    for (fast, slow, mode), sharpes in sorted(grouped.items(), key=lambda x: -min(x[1])):
        avg_ret = sum(r["total_return"] for r in results if (r["fast"], r["slow"], r["mode"]) == (fast, slow, mode)) / 3
        print(f"  ({fast:2d},{slow:2d})    {mode:<12} "
              f"{min(sharpes):+10.3f} {sum(sharpes)/3:+10.3f} {avg_ret*100:+11.2f}%")

    # 存结果
    out = Path("data/scan_lean.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n✓ 结果存到 {out}（{len(results)} 条）")


if __name__ == "__main__":
    main()
