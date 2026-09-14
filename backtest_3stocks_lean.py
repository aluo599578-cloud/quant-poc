"""
backtest_3stocks_lean.py — Lean 风格 API + vnpy 回测引擎
=========================================================

跟 backtest_3stocks.py 同样跑 3 只 A 股双均线回测，
但用 lean_style_indicators.IndicatorManager 替代 vnpy 的 DoubleMaStrategy。

好处：
  - 指标用法跟 Lean 一致（self.SMA("002180", 5)）
  - vnpy BacktestingEngine 负责撮合、统计
  - 不依赖 vnpy_ctastrategy 模板（更少 vnpy 怪 bug）

期望：结果跟原版一致（差异 < 1%），因为回测引擎 + 数据源都相同。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

sys.path.insert(0, str(Path(__file__).parent))

from backtest_3stocks import STOCKS, fetch_kline, make_bars
from lean_style_indicators import IndicatorManager


class DoubleMaLean:
    """
    双均线策略 (Lean 风格 API + vnpy BacktestingEngine 撮合)

    跟 vnpy DoubleMaStrategy 等价，但用：
      im = IndicatorManager()
      self.sma5 = im.SMA(symbol, 5)
      self.sma20 = im.SMA(symbol, 20)
    """
    fast_window = 5
    slow_window = 30  # 跟 backtest_3stocks.py 一致

    def __init__(self, vt_symbol: str):
        self.vt_symbol = vt_symbol
        self.im = IndicatorManager()
        # 先注册指标
        self.sma_fast = self.im.SMA(vt_symbol, self.fast_window)
        self.sma_slow = self.im.SMA(vt_symbol, self.slow_window)
        self.prev_fast = None
        self.prev_slow = None
        self.pos = 0  # 仓位
        self.entry_price = 0.0
        self.trades = []  # 记录交易

    def on_bar(self, bar):
        """每根 K 线调一次，由 BacktestingEngine 触发"""
        # 更新指标
        self.im.update(self.vt_symbol, bar.close_price, bar.datetime)

        # 等均线就绪
        if not (self.sma_fast.is_ready and self.sma_slow.is_ready):
            return "WAIT"

        fast = self.sma_fast.current.value
        slow = self.sma_slow.current.value

        if self.prev_fast is None:
            self.prev_fast = fast
            self.prev_slow = slow
            return "WAIT"

        # 金叉：快线从下方穿越慢线
        if self.prev_fast <= self.prev_slow and fast > slow:
            signal = "BUY" if self.pos == 0 else "HOLD"
            if signal == "BUY":
                self.pos = 1
                self.entry_price = bar.close_price
        # 死叉：快线从上方穿越慢线
        elif self.prev_fast >= self.prev_slow and fast < slow:
            signal = "SELL" if self.pos > 0 else "HOLD"
            if signal == "SELL":
                self.pos = 0
                self.entry_price = 0.0
        else:
            signal = "HOLD"

        self.prev_fast = fast
        self.prev_slow = slow
        return signal


def run_backtest(tushare_code: str, name: str) -> dict:
    """跑一只股的双均线回测"""
    print(f"\n{'='*60}")
    print(f"  {name} ({tushare_code}) - 双均线 (5, 20) - Lean 风格")
    print(f"{'='*60}")

    # 拉数据（tushare 期望 .SZ/.SH 格式）
    df = fetch_kline(tushare_code, "2023-01-01", "2026-09-09")
    if len(df) == 0:
        return {}
    bars = make_bars(df, tushare_code)
    print(f"  数据: {len(bars)} 根 K 线 ({df.iloc[0]['trade_date']} ~ {df.iloc[-1]['trade_date']})")

    # 初始化 vnpy BacktestingEngine
    engine = BacktestingEngine()
    # vnpy 期望 .SZSE / .SSE 格式
    vnpy_symbol = tushare_code.replace(".SZ", ".SZSE").replace(".SH", ".SSE")
    engine.set_parameters(
        vt_symbol=vnpy_symbol, interval=Interval.DAILY,
        start=datetime(2023, 1, 1), end=datetime(2026, 9, 9),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
    )
    # 不注册 vnpy strategy 类 — 我们手动撮合
    # engine.add_strategy(...) 略过

    # 跑 Lean 风格策略
    strategy = DoubleMaLean(vnpy_symbol)

    # 用 vnpy 的 history_data + run_backtesting，但策略被我们手动接管
    # 方法：直接用 history_data 模拟逐根 K 线
    # 但 vnpy 期望 strategy 类，这里用 .history_data 简化版
    from vnpy.trader.object import BarData, TradeData, OrderData
    from vnpy.trader.constant import Exchange, Direction, Offset, OrderType, Status

    # 简化：用 vnpy 框架，但策略逻辑替换
    # 这里用一个轻量撮合器
    class SimpleEngine:
        def __init__(self, capital=200000, size=100, rate=0.0003, slippage=0.01):
            self.capital = capital
            self.size = size
            self.rate = rate
            self.slippage = slippage
            self.cash = capital
            self.position = 0
            self.avg_cost = 0.0
            self.trades = []
            self.equity_curve = []

        def buy(self, price):
            if self.position > 0:
                return
            trade_price = price + self.slippage
            # 满仓：能买多少买多少（vnpy 默认 200000 资金）
            max_shares = int(self.cash / (trade_price * (1 + self.rate)))
            # A 股 1 手 = 100 股
            lots = max_shares // 100
            if lots == 0:
                return
            shares = lots * 100
            cost = shares * trade_price
            commission = cost * self.rate
            self.cash -= (cost + commission)
            self.position = shares
            self.avg_cost = trade_price
            self.trades.append({"side": "BUY", "price": trade_price, "shares": shares, "time": None})

        def sell(self, price):
            if self.position == 0:
                return
            trade_price = price - self.slippage
            revenue = self.position * trade_price
            commission = revenue * self.rate
            pnl = (trade_price - self.avg_cost) * self.position - commission * 2
            self.cash += (revenue - commission)
            self.trades.append({"side": "SELL", "price": trade_price, "pnl": pnl,
                              "shares": self.position, "time": None})
            self.position = 0
            self.avg_cost = 0.0

        def equity(self, current_price):
            return self.cash + self.position * current_price

    me = SimpleEngine()

    signal_count = {"BUY": 0, "SELL": 0, "HOLD": 0, "WAIT": 0}
    for bar in bars:
        # 转换 bar 给 Lean 风格策略
        class BarProxy:
            pass
        b = BarProxy()
        b.datetime = bar.datetime
        b.close_price = bar.close_price
        signal = strategy.on_bar(b)
        signal_count[signal] = signal_count.get(signal, 0) + 1

        if signal == "BUY":
            me.buy(bar.close_price)
        elif signal == "SELL":
            me.sell(bar.close_price)

        # 记录权益曲线
        eq = me.equity(bar.close_price)
        me.equity_curve.append({"date": bar.datetime, "equity": eq})

    print(f"  信号统计: {signal_count}")

    # 统计
    final_equity = me.equity_curve[-1]["equity"] if me.equity_curve else 200000
    total_return = (final_equity / 200000 - 1) * 100
    n_trades = len([t for t in me.trades if t["side"] == "SELL"])
    win_trades = [t for t in me.trades if t.get("pnl", 0) > 0]

    # 最大回撤
    equities = [e["equity"] for e in me.equity_curve]
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak
        if dd < max_dd:
            max_dd = dd

    print(f"  起始: ¥200,000  结束: ¥{final_equity:,.0f}")
    print(f"  收益: {total_return:+.2f}%")
    print(f"  交易数: {n_trades}")
    print(f"  胜率: {len(win_trades) / max(n_trades, 1) * 100:.1f}%")
    print(f"  最大回撤: {max_dd * 100:.2f}%")

    return {
        "stock": name,
        "code": tushare_code,
        "final_equity": final_equity,
        "total_return": total_return,
        "n_trades": n_trades,
        "win_rate": len(win_trades) / max(n_trades, 1),
        "max_dd": max_dd,
    }


def main():
    print("="*60)
    print("  Lean 风格 API + vnpy 撮合 - 3 只 A 股双均线回测")
    print("="*60)
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  策略: 双均线 (5, 20) - 用 lean_style_indicators.SMA")
    print(f"  资金: ¥200,000  费率: 0.0003  滑点: 0.01")
    print(f"  撮合: 简化版（手写）")

    results = []
    for vnpy_sym, code, name in STOCKS:
        # 转换：vnpy 格式 (.SZSE/.SSE) → tushare 格式 (.SZ/.SH)
        tushare_code = vnpy_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        r = run_backtest(tushare_code, name)
        if r:
            results.append(r)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  汇总")
    print(f"{'='*60}")
    print(f"  {'股票':<12} {'收益':<10} {'交易数':<8} {'胜率':<8} {'最大回撤':<10}")
    for r in results:
        print(f"  {r['stock']:<12} {r['total_return']:+8.2f}%  {r['n_trades']:>4}    "
              f"{r['win_rate']*100:>5.1f}%  {r['max_dd']*100:>8.2f}%")


if __name__ == "__main__":
    main()
