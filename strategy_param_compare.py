"""
strategy_param_compare.py — 双均线多参数 + MA200 过滤 横向对比
==============================================================

用法：python strategy_param_compare.py

输出（命令行 + Markdown 表格）：
  002180 纳思达 / 000100 TCL / 688122 西部超导 各 6 种参数组合的回测结果
  推荐"最适合实盘"的参数

参数选择（基于你之前 30 次扫描 TOP 3）：
  (5, 20), (5, 30), (10, 30), (10, 60), (5, 60), (10, 20)
+ MA200 过滤 on/off
= 6 × 2 = 12 组 × 3 股 = 36 次回测（实测 ~60 秒）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import STOCKS, fetch_kline, make_bars
from backtest_scan import DoubleMaWithTrendFilter
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy
from quant_core import _normalize_vt_symbol


PARAMS_TO_TEST = [
    (5, 20, False), (5, 20, True),
    (5, 30, False), (5, 30, True),
    (10, 30, False), (10, 30, True),
    (10, 60, False), (10, 60, True),
    (5, 60, False), (5, 60, True),
    (10, 20, False), (10, 20, True),
]
INIT_CAPITAL = 200_000
START = "2023-01-01"


def run_one(vt_symbol_tushare: str, fast: int, slow: int, trend_filter: bool):
    """跑一次回测，返回 stats dict。"""
    df = fetch_kline(vt_symbol_tushare, START, datetime.now().strftime("%Y-%m-%d"))
    bars = make_bars(df, vt_symbol_tushare)
    vt_symbol_vnpy = _normalize_vt_symbol(vt_symbol_tushare)

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol_vnpy, interval=Interval.DAILY,
        start=datetime(2023, 1, 1), end=datetime.now(),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=INIT_CAPITAL,
    )
    if trend_filter:
        engine.add_strategy(DoubleMaWithTrendFilter, {
            "fast_window": fast, "slow_window": slow, "trend_window": 200,
        })
    else:
        engine.add_strategy(DoubleMaStrategy, {
            "fast_window": fast, "slow_window": slow,
        })
    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()
    s = engine.calculate_statistics()

    return {
        "total_return": s["total_return"],
        "annual_return": s["annual_return"],
        "sharpe_ratio": s["sharpe_ratio"],
        "max_ddpercent": s["max_ddpercent"],
        "trade_count": int(s["total_trade_count"]),
        "profit_days": int(s["profit_days"]),
        "total_days": int(s["total_days"]),
    }


def main():
    print("="*78)
    print(f"  📊 双均线策略参数对比 - 3 只 A 股 × 6 参数 × 2 过滤 = 36 次回测")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}    起始资金: ¥{INIT_CAPITAL:,}")
    print(f"  回测期: {START} ~ 今天    数据: tushare 前复权日线")
    print("="*78)

    all_results = []  # [(stock_name, symbol, fast, slow, trend, stats), ...]

    for vt_sym, code, name in STOCKS:
        tushare_code = vt_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        print(f"\n{'─'*78}\n  📈 {name} ({code})\n{'─'*78}")

        stock_results = []
        for fast, slow, trend_filter in PARAMS_TO_TEST:
            tag = "+MA200" if trend_filter else "纯双均线"
            sig = (fast, slow, trend_filter)
            print(f"  [{tag:8s}] ({fast:2d},{slow:2d}) ... ", end="", flush=True)
            try:
                stats = run_one(tushare_code, fast, slow, trend_filter)
                stock_results.append((sig, stats))
                ret_pct = stats["total_return"] * 100
                dd_pct = stats["max_ddpercent"] * 100
                shp = stats["sharpe_ratio"]
                n = stats["trade_count"]
                print(f"收益 {ret_pct:+7.2f}%  Sharpe {shp:+.3f}  回撤 {dd_pct:6.2f}%  笔数 {n:3d}")
            except Exception as e:
                print(f"❌ {e}")

        # 排序：先按 Sharpe 降序，再按最大回撤（绝对值）升序
        stock_results.sort(key=lambda x: (-x[1]["sharpe_ratio"], abs(x[1]["max_ddpercent"])))

        print(f"\n  🏆 {name} 推荐（按 Sharpe 排序）:")
        for i, (sig, stats) in enumerate(stock_results[:3], 1):
            fast, slow, trend = sig
            tag = "+MA200" if trend else "纯双均线"
            print(f"    {i}. ({fast},{slow}) {tag:8s} → "
                  f"收益 {stats['total_return']*100:+6.2f}%  "
                  f"Sharpe {stats['sharpe_ratio']:+.3f}  "
                  f"回撤 {stats['max_ddpercent']*100:6.2f}%  "
                  f"笔数 {stats['trade_count']}")

        for sig, stats in stock_results:
            fast, slow, trend = sig
            all_results.append({
                "stock": name,
                "code": code,
                "fast": fast, "slow": slow,
                "trend": "MA200" if trend else "纯",
                "total_return": stats["total_return"],
                "annual_return": stats["annual_return"],
                "sharpe": stats["sharpe_ratio"],
                "max_dd": stats["max_ddpercent"],
                "trade_count": stats["trade_count"],
            })

    # ===== 整体推荐：找跨股票最稳的 =====
    print("\n" + "="*78)
    print("  🎯 跨股票推荐（找在 3 只股上都 Sharpe 最高的参数）")
    print("="*78)

    df_all = pd.DataFrame(all_results)
    # 把 trend 列统一成 "纯" / "MA200"（避免中文 label）
    df_all["filter"] = df_all["trend"].map({"纯": "纯双均线", "MA200": "+MA200"})

    # 按 (fast, slow, filter) 分组，对每组算 3 只股的平均 Sharpe
    grouped = df_all.groupby(["fast", "slow", "filter"]).agg(
        avg_sharpe=("sharpe", "mean"),
        min_sharpe=("sharpe", "min"),
        max_sharpe=("sharpe", "max"),
        avg_return=("total_return", "mean"),
        avg_dd=("max_dd", "mean"),
        total_trades=("trade_count", "sum"),
    ).reset_index()
    # 排序：跨股最稳 = min_sharpe 最高（3 只股都不会差到负）
    grouped = grouped.sort_values("min_sharpe", ascending=False)

    print(f"\n  {'参数':<10} {'过滤':<10} {'最低Sharpe':<10} {'平均Sharpe':<10} {'最高Sharpe':<10} {'平均收益':<10} {'平均回撤':<10}")
    print(f"  {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
    for _, r in grouped.iterrows():
        sig = f"({r['fast']},{r['slow']})"
        avg_sh = r["avg_sharpe"]
        min_sh = r["min_sharpe"]
        max_sh = r["max_sharpe"]
        avg_ret = r["avg_return"] * 100
        avg_dd = r["avg_dd"] * 100
        print(f"  {sig:<10} {r['filter']:<10} "
              f"{min_sh:+10.3f} {avg_sh:+10.3f} {max_sh:+10.3f} "
              f"{avg_ret:+10.2f}% {avg_dd:+10.2f}%")

    # 跨股票最稳 = min_sharpe 最高
    top = grouped.head(3)
    print(f"\n  🥇 TOP 3 跨股票推荐（看 min_sharpe 找最稳的）:")
    for _, r in top.iterrows():
        print(f"    → ({r['fast']},{r['slow']}) {r['filter']:<10}  "
              f"min_sharpe {r['min_sharpe']:+.3f}  "
              f"avg_sharpe {r['avg_sharpe']:+.3f}  "
              f"avg_return {r['avg_return']*100:+.2f}%")

    # 找出"3 只股 Sharpe 都 > 0" 的参数
    print(f"\n  🌟 '3 只股都不亏' 的参数（min_sharpe > 0）：")
    all_positive = grouped[grouped["min_sharpe"] > 0]
    if len(all_positive) == 0:
        print("    ❌ 没有任何参数在 3 只股上都 Sharpe > 0 — 双均线在 A 股就是这水平")
    else:
        for _, r in all_positive.iterrows():
            print(f"    ✓ ({r['fast']},{r['slow']}) {r['filter']:<10}  "
                  f"min {r['min_sharpe']:+.3f}  avg {r['avg_sharpe']:+.3f}  "
                  f"avg_ret {r['avg_return']*100:+.2f}%")

    # 写出 JSON 缓存（dashboard 可以读）
    out = Path("data/strategy_compare.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n💾 已存到 {out}（共 {len(all_results)} 条）")
    print("\n⚠️ 提醒：")
    print("  1. 这是 in-sample（用 2023-2026 全段做回测），结果偏乐观")
    print("  2. walk-forward 验证：train 2023-2024 + test 2025-2026，看 test 段表现")
    print("  3. 真要实盘：先在富途量化里画同样策略对照回测结果，差异 > 5% 说明某边算错")


if __name__ == "__main__":
    main()
