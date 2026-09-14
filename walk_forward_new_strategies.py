"""
walk_forward_new_strategies.py — 6 个新策略 walk-forward 验证
=============================================================

3 轮 walk-forward，4 只股，6 个新策略。

用法: python walk_forward_new_strategies.py
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

# 6 个策略
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

# 3 轮 walk-forward
ROUNDS = [
    ("R1 18M/24M", "2023-02-10", "2024-08-31", "2024-09-01", "2026-09-09"),
    ("R2 12M/30M", "2023-02-10", "2024-02-29", "2024-03-01", "2026-09-09"),
    ("R3 24M/18M", "2023-02-10", "2025-02-28", "2025-03-01", "2026-09-09"),
]


def run_strategy(strategy_class, params, df, tushare_code, start, end):
    df_sub = df[(df["trade_date"] >= start.replace("-", "")) & (df["trade_date"] <= end.replace("-", ""))]
    if len(df_sub) < 100:
        return None
    bars = make_bars(df_sub, tushare_code)
    vnpy_sym = tushare_code.replace(".SZ", ".SZSE").replace(".SH", ".SSE")

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vnpy_sym, interval=Interval.DAILY,
        start=datetime.strptime(start, "%Y-%m-%d"),
        end=datetime.strptime(end, "%Y-%m-%d"),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
    )
    engine.add_strategy(strategy_class, params)
    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()
    return engine.calculate_statistics()


def main():
    print("="*78)
    print("  6 个新策略 walk-forward 验证（4 只 A 股 × 3 轮 = 72 次测试期回测）")
    print("="*78)

    all_results = {}

    for vnpy_sym, code, stock_name in ALL_STOCKS:
        tushare_code = vnpy_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        print(f"\n{'='*78}")
        print(f"  {stock_name} ({tushare_code})")
        print("="*78)

        df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
        if len(df) == 0:
            print(f"  ❌ 数据拉取失败")
            continue
        print(f"  数据: {len(df)} 根 K 线")

        stock_results = []
        for round_name, train_start, train_end, test_start, test_end in ROUNDS:
            print(f"\n  --- {round_name} ---")

            best = None
            for strategy_class, label, base_params in STRATEGIES:
                # 训练期：跑默认参数
                stats = run_strategy(strategy_class, base_params, df, tushare_code, train_start, train_end)
                if stats is None:
                    continue
                ret = stats.get("total_return", 0) * 100
                shp = stats.get("sharpe_ratio", -999)
                if best is None or shp > best.get("sharpe", -999):
                    best = {
                        "label": label, "sharpe": shp, "train_return": ret,
                        "params": base_params, "strategy_class": strategy_class,
                    }

            if best is None:
                continue
            print(f"    训练期最佳: {best['label']} (Sharpe {best['sharpe']:+.3f}, 收益 {best['train_return']:+.2f}%)")

            # 测试期
            test_stats = run_strategy(best["strategy_class"], best["params"], df, tushare_code, test_start, test_end)
            if test_stats is None:
                continue
            test_ret = test_stats.get("total_return", 0) * 100
            test_shp = test_stats.get("sharpe_ratio", 0)
            test_dd = test_stats.get("max_ddpercent", 0) * 100
            test_n = int(test_stats.get("total_trade_count", 0))
            print(f"    测试期: {test_ret:+7.2f}%  Sharpe {test_shp:+.3f}  回撤 {test_dd:.1f}%  笔数 {test_n}")

            stock_results.append({
                "round": round_name,
                "best_strategy": best["label"],
                "train_sharpe": best["sharpe"],
                "test_return": test_ret, "test_sharpe": test_shp,
                "test_dd": test_dd, "test_trades": test_n,
            })

        if stock_results:
            consistent = all(r["test_sharpe"] > 0 for r in stock_results)
            print(f"\n  {stock_name} 汇总:")
            print(f"    平均测试收益: {sum(r['test_return'] for r in stock_results)/len(stock_results):+.2f}%")
            print(f"    平均测试 Sharpe: {sum(r['test_sharpe'] for r in stock_results)/len(stock_results):+.3f}")
            print(f"    一致性: {'✅ 3/3 Sharpe > 0' if consistent else '⚠️ 至少 1 轮 Sharpe ≤ 0'}")
            for r in stock_results:
                print(f"      {r['round']:<14} 最佳 {r['best_strategy']:<14} 测试 {r['test_return']:+7.2f}%  Sharpe {r['test_sharpe']:+.3f}")

            all_results[stock_name] = {
                "code": tushare_code,
                "consistent": consistent,
                "rounds": stock_results,
            }

    # 跨股票汇总
    print(f"\n{'='*78}")
    print("  4 只股 walk-forward 跨股票汇总")
    print("="*78)
    print(f"\n  {'股票':<12} {'代码':<10} {'一致性':<8}")
    print(f"  {'─'*12} {'─'*10} {'─'*8}")
    for name, r in all_results.items():
        consistent_mark = "✅ 3/3" if r["consistent"] else "⚠️ 不全"
        print(f"  {name:<12} {r['code']:<10} {consistent_mark}")

    if all_results:
        consistent_count = sum(1 for r in all_results.values() if r["consistent"])
        print(f"\n  跨 4 只股一致性: {consistent_count}/{len(all_results)} 只股 3 轮测试 Sharpe > 0")

    out = Path("data/walk_forward_new_strategies.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 结果存到 {out}")


if __name__ == "__main__":
    main()
