"""
backtest_scan.py — 多策略扫描 + MA200 趋势过滤对比
==================================================

策略 A：纯双均线（5 个参数对）
策略 B：双均线 + MA200 趋势过滤（只在 MA200 之上做多）

参数对：
- (5, 20), (5, 30), (5, 60), (10, 30), (10, 60)

A 股做空限制：策略 B 只允许做多；策略 A 允许做多做空（vnpy 默认）

数据：tushare 日线，2023-01-01 ~ 今天
引擎：vnpy_ctastrategy.backtesting.BacktestingEngine
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import tushare as ts
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.template import CtaTemplate

# 复用 backtest_3stocks 的数据下载/转换
sys.path.insert(0, ".")
from backtest_3stocks import (
    STOCKS, fetch_kline, make_bars, to_tushare_code,
    START, END, INIT_CAPITAL,
)


# ============ 策略定义 ============

class DoubleMaWithTrendFilter(CtaTemplate):
    """双均线 + MA200 趋势过滤：A 股只能做多。

    - fast 上穿 slow 且 close > MA200 → 满仓买入
    - fast 下穿 slow → 卖出清仓
    - close < MA200 时不做多（即使金叉也观望）
    """
    author = "quant-poc"

    fast_window: int = 5
    slow_window: int = 30
    trend_window: int = 200

    parameters = ["fast_window", "slow_window", "trend_window"]
    variables = []

    def on_init(self) -> None:
        self.write_log("init")
        # 注意：run_backtesting 直接调 self.strategy.on_bar(bar)，不走 BarGenerator
        # ArrayManager 默认 size=100，必须显式声明足够大以容纳 trend_window
        from vnpy.trader.utility import ArrayManager
        self.am = ArrayManager(size=max(self.trend_window, self.slow_window) + 10)

    def on_start(self) -> None:
        self.write_log("start")
        self.put_event()

    def on_stop(self) -> None:
        self.write_log("stop")

    def on_tick(self, tick):
        pass  # 回测用不到 tick

    def on_bar(self, bar: BarData) -> None:
        self.cancel_all()
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        import numpy as np
        fast_ma = self.am.sma(self.fast_window, array=True)
        slow_ma = self.am.sma(self.slow_window, array=True)
        trend_ma = self.am.sma(self.trend_window, array=True)

        f0, f1 = fast_ma[-1], fast_ma[-2]
        s0, s1 = slow_ma[-1], slow_ma[-2]
        t0 = trend_ma[-1]
        close = bar.close_price

        cross_over = f0 > s0 and f1 < s1
        cross_below = f0 < s0 and f1 > s1
        above_trend = close > t0

        if cross_over and above_trend:
            if self.pos == 0:
                self.buy(close, 1)
        elif cross_below:
            if self.pos > 0:
                self.sell(close, 1)
            # 不做空

        self.put_event()

    def on_order(self, order): pass
    def on_trade(self, trade): self.put_event()
    def on_stop_order(self, stop_order): pass


# ============ 扫描 ============

@dataclass
class RunResult:
    vt_symbol: str
    name: str
    strategy: str          # "DoubleMa" | "DoubleMa+MA200"
    fast: int
    slow: int
    total_return: float
    annual_return: float
    sharpe: float
    max_dd_pct: float      # 百分比形式（已 *100）
    profit_days: int
    total_days: int
    trade_count: int
    elapsed_s: float


def run_one(vt_symbol: str, name: str, fast: int, slow: int,
            use_trend_filter: bool) -> RunResult:
    t0 = time.time()
    df = fetch_kline(to_tushare_code(vt_symbol),
                     START.strftime("%Y-%m-%d"),
                     END.strftime("%Y-%m-%d"))
    bars = make_bars(df, vt_symbol)

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=Interval.DAILY,
        start=START,
        end=END,
        rate=0.0003,
        slippage=0.01,
        size=100,
        pricetick=0.01,
        capital=INIT_CAPITAL,
    )
    if use_trend_filter:
        engine.add_strategy(DoubleMaWithTrendFilter, {
            "fast_window": fast,
            "slow_window": slow,
            "trend_window": 200,
        })
    else:
        from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy
        engine.add_strategy(DoubleMaStrategy, {
            "fast_window": fast,
            "slow_window": slow,
        })

    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()  # 必须先调，否则 calculate_statistics 返回空
    stats = engine.calculate_statistics()

    return RunResult(
        vt_symbol=vt_symbol,
        name=name,
        strategy=("DoubleMa+MA200" if use_trend_filter else "DoubleMa"),
        fast=fast, slow=slow,
        total_return=stats.get("total_return", 0) * 100,
        annual_return=stats.get("annual_return", 0) * 100,
        sharpe=stats.get("sharpe_ratio", 0),
        max_dd_pct=stats.get("max_ddpercent", 0) * 100,
        profit_days=stats.get("profit_days", 0),
        total_days=stats.get("total_days", 1),
        trade_count=stats.get("total_trade_count", 0),
        elapsed_s=time.time() - t0,
    )


def main():
    param_pairs = [(5, 20), (5, 30), (5, 60), (10, 30), (10, 60)]

    results: list[RunResult] = []
    total = len(STOCKS) * len(param_pairs) * 2  # 3 股 × 5 参数 × 2 策略 = 30
    done = 0

    for vt_sym, code, name in STOCKS:
        for fast, slow in param_pairs:
            for trend in [False, True]:
                done += 1
                tag = "纯双均线" if not trend else "+MA200"
                print(f"\n[{done}/{total}] {name} {fast}/{slow} {tag} ... ", end="", flush=True)
                try:
                    r = run_one(vt_sym, name, fast, slow, trend)
                    print(f"总收益 {r.total_return:+.2f}% 年化 {r.annual_return:+.2f}% "
                          f"Sharpe {r.sharpe:+.2f}  回撤 {r.max_dd_pct:.2f}%  "
                          f"交易 {r.trade_count}  ({r.elapsed_s:.1f}s)")
                    results.append(r)
                except Exception as e:
                    print(f"❌ 失败: {e}")
                    import traceback; traceback.print_exc()

    # 输出汇总表
    print(f"\n{'='*120}")
    print(f"  SCAN SUMMARY (共 {len(results)} 次回测)")
    print(f"{'='*120}")
    print(f"{'股票':<10} {'策略':<14} {'快线':>4} {'慢线':>4} {'总收益':>8} {'年化':>8} {'Sharpe':>7} {'回撤':>8} {'胜日/总':>10} {'交易':>5}")
    for r in results:
        print(f"{r.name:<10} {r.strategy:<14} {r.fast:>4} {r.slow:>4} "
              f"{r.total_return:>+7.2f}% {r.annual_return:>+7.2f}% "
              f"{r.sharpe:>+6.2f} {r.max_dd_pct:>+7.2f}% "
              f"{r.profit_days:>4}/{r.total_days:<4} {r.trade_count:>5}")

    # 按 Sharpe 排前 5
    print(f"\n--- TOP 5 BY SHARPE ---")
    for r in sorted(results, key=lambda x: -x.sharpe)[:5]:
        print(f"  {r.name:<10} {r.strategy:<14} ({r.fast},{r.slow}) "
              f"Sharpe {r.sharpe:+.2f} 收益 {r.total_return:+.2f}% 回撤 {r.max_dd_pct:.2f}%")

    # 保存 JSON（处理 numpy int64/float64）
    import numpy as np
    out = "C:/Users/18566/Desktop/quant-poc/data/backtest_scan.json"
    serializable = []
    for r in results:
        d = r.__dict__.copy()
        for k, v in d.items():
            if isinstance(v, (np.integer,)):
                d[k] = int(v)
            elif isinstance(v, (np.floating,)):
                d[k] = float(v)
        serializable.append(d)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"\n已保存 {len(results)} 条结果到 {out}")


if __name__ == "__main__":
    main()
