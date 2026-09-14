"""
walk_forward_pantum.py — 奔图科技 688515.SH walk-forward 验证
=============================================================

3 轮 walk-forward：
  Round 1: 训练 2023-02-10 ~ 2024-08-31 (18月), 测试 2024-09-01 ~ 2026-09-09
  Round 2: 训练 2023-02-10 ~ 2024-02-29, 测试 2024-03-01 ~ 2026-09-09
  Round 3: 训练 2023-02-10 ~ 2025-02-28, 测试 2025-03-01 ~ 2026-09-09

每轮训练期扫描 5 组参数 + 2 模式 = 10 次回测，找最佳。
然后在测试期用最佳参数跑 1 次。

用法: python walk_forward_pantum.py
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
from strategies import DoubleMaLeanStrategy, DoubleMaStopLossLean


# 5 参数 × 2 模式 = 10 组
PARAM_GRID = [
    (5, 20), (5, 30), (10, 30), (10, 60), (5, 60),
]
MODES = [
    ("pure", "纯双均线", None),
    ("stop5", "双均线 + 5% 止损", 0.05),
]


def run_strategy(strategy_class, params, df, tushare_code, start, end):
    """跑一个策略在指定时间区间"""
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
    print(f"\n  训练期: {train_start} ~ {train_end}")
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
            label = f"({fast},{slow}) {mode_label}"
            stats = run_strategy(strategy_class, params, df, tushare_code, train_start, train_end)
            if stats is None:
                continue
            ret = stats.get("total_return", 0) * 100
            shp = stats.get("sharpe_ratio", -999)
            # 用 Sharpe 选最佳
            if best is None or shp > best.get("sharpe", -999):
                best = {
                    "fast": fast, "slow": slow, "mode": mode, "stop_loss": stop_loss,
                    "mode_label": mode_label, "label": label,
                    "train_return": ret, "train_sharpe": shp, "sharpe": shp,
                    "params": params, "strategy_class": strategy_class,
                }
    return best


def test_with(df, tushare_code, best, test_start, test_end):
    """用训练期找到的最佳参数在测试期验证"""
    print(f"\n  测试期: {test_start} ~ {test_end}")
    stats = run_strategy(best["strategy_class"], best["params"], df, tushare_code, test_start, test_end)
    if stats is None:
        return None
    test_ret = stats["total_return"] * 100
    test_shp = stats["sharpe_ratio"]
    test_dd = stats["max_ddpercent"] * 100
    test_n = int(stats["total_trade_count"])
    print(f"    {best['label']:<28} 测试收益 {test_ret:+7.2f}%  Sharpe {test_shp:+.3f}  回撤 {test_dd:.1f}%  笔数 {test_n}")
    return {
        "test_return": test_ret, "test_sharpe": test_shp,
        "test_dd": test_dd, "test_trades": test_n,
    }


def main():
    tushare_code = "688515.SH"
    name = "奔图科技"

    print("="*70)
    print(f"  {name} ({tushare_code}) - Walk-Forward 验证")
    print(f"  目的: 验证 (5,30) + 5%止损 在 3.5 年里 +326% 不是过拟合")
    print("="*70)

    df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
    print(f"\n  数据: {len(df)} 根 K 线 ({df.iloc[-1]['trade_date']} ~ {df.iloc[0]['trade_date']})")

    # 3 轮 walk-forward
    rounds = [
        # 训练/测试分割（按自然时间）
        ("Round 1", "2023-02-10", "2024-08-31", "2024-09-01", "2026-09-09"),
        ("Round 2", "2023-02-10", "2024-02-29", "2024-03-01", "2026-09-09"),
        ("Round 3", "2023-02-10", "2025-02-28", "2025-03-01", "2026-09-09"),
    ]

    results = []
    for name_round, train_start, train_end, test_start, test_end in rounds:
        print(f"\n{'='*70}")
        print(f"  {name_round}: 训练 {train_start}~{train_end}, 测试 {test_start}~{test_end}")
        print("="*70)

        best = scan_train(df, tushare_code, train_start, train_end)
        if best is None:
            print(f"  ❌ 训练期没找到结果")
            continue
        print(f"\n  训练期最佳: {best['label']} (Sharpe {best['train_sharpe']:+.3f}, 收益 {best['train_return']:+.2f}%)")

        test_result = test_with(df, tushare_code, best, test_start, test_end)
        if test_result is None:
            continue
        results.append({
            "round": name_round,
            "best_params": best["label"],
            "train_sharpe": best["train_sharpe"],
            "train_return": best["train_return"],
            **test_result,
        })

    # 汇总
    print(f"\n{'='*70}")
    print("  Walk-Forward 汇总")
    print("="*70)
    print(f"\n  {'轮次':<10} {'最佳参数':<28} {'训练Sharpe':<10} {'测试收益':<10} {'测试Sharpe':<10}")
    print(f"  {'-'*10} {'-'*28} {'-'*10} {'-'*10} {'-'*10}")
    for r in results:
        print(f"  {r['round']:<10} {r['best_params']:<28} "
              f"{r['train_sharpe']:+.3f}     {r['test_return']:+7.2f}%   {r['test_sharpe']:+.3f}")

    if results:
        avg_train_sharpe = sum(r["train_sharpe"] for r in results) / len(results)
        avg_test_return = sum(r["test_return"] for r in results) / len(results)
        avg_test_sharpe = sum(r["test_sharpe"] for r in results) / len(results)
        print(f"\n  平均:")
        print(f"    训练 Sharpe: {avg_train_sharpe:+.3f}")
        print(f"    测试收益:   {avg_test_return:+.2f}%")
        print(f"    测试 Sharpe: {avg_test_sharpe:+.3f}")

        # 判断
        consistent = all(r["test_sharpe"] > 0 for r in results)
        if consistent:
            print(f"\n  ✅ 3 轮测试 Sharpe 都 > 0 — 策略稳定，可能不是过拟合")
        else:
            failing = [r["round"] for r in results if r["test_sharpe"] <= 0]
            print(f"\n  ⚠️ {len(failing)} 轮测试 Sharpe ≤ 0: {failing} — 策略可能过拟合")

    # 存结果
    out = Path("data/walk_forward_pantum.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 结果存到 {out}")


if __name__ == "__main__":
    main()
