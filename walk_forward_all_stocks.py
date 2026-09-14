"""
walk_forward_all_stocks.py — 4 只 A 股 walk-forward 验证
=========================================================

用法: python walk_forward_all_stocks.py
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
from strategies import DoubleMaLeanStrategy, DoubleMaStopLossLean


# 4 只股（原 3 + 奔图）
ALL_STOCKS = list(ORIGINAL_STOCKS) + [("688515.SSE", "688515", "奔图科技")]

# 5 参数 × 2 模式 = 10 组
PARAM_GRID = [
    (5, 20), (5, 30), (10, 30), (10, 60), (5, 60),
]
MODES = [
    ("pure", "纯双均线", None),
    ("stop5", "双均线 + 5% 止损", 0.05),
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


def scan_train(df, tushare_code, train_start, train_end):
    """在训练期扫描参数，找最佳"""
    best = None
    for fast, slow in PARAM_GRID:
        for mode, mode_label, stop_loss in MODES:
            strategy_class = DoubleMaStopLossLean if mode == "stop5" else DoubleMaLeanStrategy
            params = {
                "fast_window": fast, "slow_window": slow,
                "fixed_size": 1, "warmup_bars": 100,
            }
            if stop_loss:
                params["stop_loss_pct"] = stop_loss
            stats = run_strategy(strategy_class, params, df, tushare_code, train_start, train_end)
            if stats is None:
                continue
            ret = stats.get("total_return", 0) * 100
            shp = stats.get("sharpe_ratio", -999)
            if best is None or shp > best.get("sharpe", -999):
                best = {
                    "fast": fast, "slow": slow, "mode": mode,
                    "label": f"({fast},{slow}) {mode_label}",
                    "train_return": ret, "train_sharpe": shp, "sharpe": shp,
                    "params": params, "strategy_class": strategy_class,
                }
    return best


def test_with(df, tushare_code, best, test_start, test_end):
    stats = run_strategy(best["strategy_class"], best["params"], df, tushare_code, test_start, test_end)
    if stats is None:
        return None
    return {
        "test_return": stats.get("total_return", 0) * 100,
        "test_sharpe": stats.get("sharpe_ratio", 0),
        "test_dd": stats.get("max_ddpercent", 0) * 100,
        "test_trades": int(stats.get("total_trade_count", 0)),
    }


def main():
    print("="*78)
    print("  4 只 A 股 walk-forward 验证")
    print("="*78)

    all_results = {}

    for vnpy_sym, code, name in ALL_STOCKS:
        tushare_code = vnpy_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        print(f"\n{'='*78}")
        print(f"  {name} ({tushare_code})")
        print("="*78)

        df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
        if len(df) == 0:
            print(f"  ❌ 数据拉取失败")
            continue
        # 002180 / 000100 是 2023-01 开始的
        if len(df) < 200:
            print(f"  ⚠️ 数据太短 ({len(df)} 根)")
        print(f"  数据: {len(df)} 根 K 线 ({df.iloc[-1]['trade_date']} ~ {df.iloc[0]['trade_date']})")

        stock_results = []
        for round_name, train_start, train_end, test_start, test_end in ROUNDS:
            best = scan_train(df, tushare_code, train_start, train_end)
            if best is None:
                continue
            test_result = test_with(df, tushare_code, best, test_start, test_end)
            if test_result is None:
                continue
            stock_results.append({
                "round": round_name,
                "best_params": best["label"],
                "train_sharpe": best["train_sharpe"],
                **test_result,
            })

        if stock_results:
            avg_test_return = sum(r["test_return"] for r in stock_results) / len(stock_results)
            avg_test_sharpe = sum(r["test_sharpe"] for r in stock_results) / len(stock_results)
            consistent = all(r["test_sharpe"] > 0 for r in stock_results)
            print(f"\n  {name} 汇总:")
            print(f"    平均测试收益: {avg_test_return:+.2f}%")
            print(f"    平均测试 Sharpe: {avg_test_sharpe:+.3f}")
            print(f"    一致性: {'✅ 3 轮 Sharpe > 0' if consistent else '⚠️ 至少 1 轮 Sharpe ≤ 0'}")
            for r in stock_results:
                print(f"      {r['round']:<14} {r['best_params']:<28} 测试 {r['test_return']:+7.2f}%  Sharpe {r['test_sharpe']:+.3f}")

            all_results[name] = {
                "code": tushare_code,
                "avg_test_return": avg_test_return,
                "avg_test_sharpe": avg_test_sharpe,
                "consistent": consistent,
                "rounds": stock_results,
            }

    # 最终汇总
    print(f"\n{'='*78}")
    print("  4 只股 walk-forward 跨股票汇总")
    print("="*78)
    print(f"\n  {'股票':<12} {'代码':<10} {'平均测试收益':<14} {'平均Sharpe':<12} {'一致性'}")
    print(f"  {'-'*12} {'-'*10} {'-'*14} {'-'*12} {'-'*10}")
    for name, r in all_results.items():
        consistent_mark = "✅ 3/3" if r["consistent"] else "⚠️ 不全"
        print(f"  {name:<12} {r['code']:<10} {r['avg_test_return']:+10.2f}%    "
              f"{r['avg_test_sharpe']:+.3f}      {consistent_mark}")

    if all_results:
        avg_all_return = sum(r["avg_test_return"] for r in all_results.values()) / len(all_results)
        avg_all_sharpe = sum(r["avg_test_sharpe"] for r in all_results.values()) / len(all_results)
        consistent_count = sum(1 for r in all_results.values() if r["consistent"])
        print(f"\n  跨 4 只股平均:")
        print(f"    测试收益: {avg_all_return:+.2f}%")
        print(f"    测试 Sharpe: {avg_all_sharpe:+.3f}")
        print(f"    一致性: {consistent_count}/{len(all_results)} 只股 3 轮测试 Sharpe > 0")

    # 存结果
    out = Path("data/walk_forward_all_stocks.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 结果存到 {out}")


if __name__ == "__main__":
    main()
