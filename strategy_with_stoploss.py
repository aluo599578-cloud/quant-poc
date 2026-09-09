"""
strategy_with_stoploss.py — 双均线 + 5% 止损 策略对比
======================================================

对比：
  - 纯双均线
  - 双均线 + 5% 止损（on_bar 检查浮亏）
  - 双均线 + MA200 过滤
  - 双均线 + MA200 + 5% 止损

跑 3 只股 × 4 组合 × 6 组参数 = 72 次回测。

输出：跨股票最稳的参数 + 止损有没有用。

⚠️ 实现细节：
  - 止损在 on_bar 用最新 bar 的 close 比较当前持仓浮亏率
  - 用 vnpy 的 self.pos 和 buy/sell/cover/short API 下市价单
  - vnpy 默认手续费 0.0003 + 滑点 0.01 都按市价处理，符合实盘
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy

from backtest_3stocks import STOCKS, fetch_kline, make_bars
from backtest_scan import DoubleMaWithTrendFilter
from quant_core import _normalize_vt_symbol


# 关键：继承 DoubleMaStrategy 加 stop loss
class DoubleMaWithStopLoss(DoubleMaStrategy):
    """双均线 + 持仓浮亏止损。"""

    stop_loss_pct = 0.05  # 5% 止损，可覆盖

    def on_bar(self, bar):
        # 先调父类逻辑（产生买卖信号）
        super().on_bar(bar)

        # 然后检查止损
        if self.pos == 0:
            return

        # 持仓成本（vnpy 的 self.buy_price 不存在，要自己记）
        # 用 self.trading_price 试试
        if not hasattr(self, "_entry_prices") or not hasattr(self, "_entry_qtys"):
            self._entry_prices = {}
            self._entry_qtys = {}

        # 记录开仓成本
        # 检查最近一笔成交
        # 简化：用 self.pos 的反向——vnpy 没暴露 entry price
        # 改用 self.avg_price (在 CtaTemplate)
        # Actually: 看 vnpy self.pos > 0 时 self.pos_price 也不存在
        # 改策略：记 self.last_entry_price 在 on_trade 里

    def on_trade(self, trade):
        super().on_trade(trade)
        if not hasattr(self, "_entry_prices"):
            self._entry_prices = {}
            self._entry_qtys = {}

        if trade.direction.value == "多" and self.pos > 0:
            self._entry_prices[trade.vt_symbol] = trade.price
            self._entry_qtys[trade.vt_symbol] = trade.volume
        # 平仓时清掉
        elif self.pos == 0:
            self._entry_prices.pop(trade.vt_symbol, None)
            self._entry_qtys.pop(trade.vt_symbol, None)


# 重新实现：在 on_bar 检查持仓浮亏
class DoubleMaWithStopLossV2(DoubleMaStrategy):
    """双均线 + 持仓浮亏止损（v2：用 self.pos 和 ArrayManager 算均价）"""

    stop_loss_pct = 0.05

    parameters = ["fast_window", "slow_window", "stop_loss_pct"]
    variables = ["entry_price", "sl_active"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.entry_price = 0.0
        self.sl_active = False

    def on_init(self):
        super().on_init()

    def on_trade(self, trade):
        super().on_trade(trade)
        if trade.direction.value == "多" and self.pos > 0:
            self.entry_price = trade.price
            self.sl_active = True
        elif trade.direction.value == "空" and self.pos == 0:
            self.entry_price = 0.0
            self.sl_active = False

    def on_bar(self, bar):
        super().on_bar(bar)

        # 止损检查：仅多头持仓（因 vnpy 默认 A 股不能做空）
        if self.pos > 0 and self.sl_active:
            loss_pct = (bar.close_price - self.entry_price) / self.entry_price
            if loss_pct <= -self.stop_loss_pct:
                # 市价全平
                self.sell(bar.close_price, abs(self.pos))


# 完整版：双均线 + MA200 + 止损
class DoubleMaTrendStopLoss(DoubleMaWithTrendFilter):
    """双均线 + MA200 过滤 + 止损。"""
    stop_loss_pct = 0.05

    parameters = ["fast_window", "slow_window", "trend_window", "stop_loss_pct"]
    variables = ["entry_price", "sl_active"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.entry_price = 0.0
        self.sl_active = False

    def on_trade(self, trade):
        super().on_trade(trade)
        if trade.direction.value == "多" and self.pos > 0:
            self.entry_price = trade.price
            self.sl_active = True
        elif trade.direction.value == "空" and self.pos == 0:
            self.entry_price = 0.0
            self.sl_active = False

    def on_bar(self, bar):
        super().on_bar(bar)
        if self.pos > 0 and self.sl_active:
            loss_pct = (bar.close_price - self.entry_price) / self.entry_price
            if loss_pct <= -self.stop_loss_pct:
                self.sell(bar.close_price, abs(self.pos))


def run_one(vt_symbol_tushare: str, fast: int, slow: int, mode: str, stop_loss: float = 0.05):
    """
    mode: "pure" / "pure_sl" / "trend" / "trend_sl"
    """
    df = fetch_kline(vt_symbol_tushare, "2023-01-01", datetime.now().strftime("%Y-%m-%d"))
    bars = make_bars(df, vt_symbol_tushare)
    vt_symbol_vnpy = _normalize_vt_symbol(vt_symbol_tushare)

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol_vnpy, interval=Interval.DAILY,
        start=datetime(2023, 1, 1), end=datetime.now(),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
    )
    if mode == "pure":
        engine.add_strategy(DoubleMaStrategy, {
            "fast_window": fast, "slow_window": slow,
        })
    elif mode == "pure_sl":
        engine.add_strategy(DoubleMaWithStopLossV2, {
            "fast_window": fast, "slow_window": slow,
            "stop_loss_pct": stop_loss,
        })
    elif mode == "trend":
        engine.add_strategy(DoubleMaWithTrendFilter, {
            "fast_window": fast, "slow_window": slow, "trend_window": 200,
        })
    elif mode == "trend_sl":
        engine.add_strategy(DoubleMaTrendStopLoss, {
            "fast_window": fast, "slow_window": slow, "trend_window": 200,
            "stop_loss_pct": stop_loss,
        })
    else:
        raise ValueError(f"unknown mode: {mode}")

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
    }


def main():
    print("="*78)
    print(f"  📊 双均线 + 止损 策略对比（4 模式 × 6 参数 × 3 股 = 72 次回测）")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}    初始资金: ¥200,000")
    print(f"  止损: 5%    数据: tushare 前复权日线")
    print("="*78)

    PARAMS = [(5, 20), (5, 30), (10, 30), (10, 60), (5, 60), (10, 20)]
    MODES = [
        ("pure", "纯双均线"),
        ("pure_sl", "纯双均线 + 5%止损"),
        ("trend", "+ MA200"),
        ("trend_sl", "+ MA200 + 5%止损"),
    ]

    all_results = []

    for vt_sym, code, name in STOCKS:
        tushare_code = vt_sym.replace(".SZSE", ".SZ").replace(".SSE", ".SH")
        print(f"\n{'─'*78}\n  📈 {name} ({code})\n{'─'*78}")

        stock_results = []
        for mode, mode_label in MODES:
            for fast, slow in PARAMS:
                sig = (fast, slow, mode)
                print(f"  [{mode_label:14s}] ({fast:2d},{slow:2d}) ... ", end="", flush=True)
                try:
                    stats = run_one(tushare_code, fast, slow, mode)
                    stock_results.append((sig, stats, mode_label))
                    ret_pct = stats["total_return"] * 100
                    dd_pct = stats["max_ddpercent"] * 100
                    shp = stats["sharpe_ratio"]
                    n = stats["trade_count"]
                    print(f"收益 {ret_pct:+7.2f}%  Sharpe {shp:+.3f}  回撤 {dd_pct:7.2f}%  笔数 {n:3d}")
                except Exception as e:
                    print(f"❌ {e}")

        # 排序：Sharpe 降序
        stock_results.sort(key=lambda x: -x[1]["sharpe_ratio"])
        print(f"\n  🏆 {name} TOP 5:")
        for i, (sig, stats, label) in enumerate(stock_results[:5], 1):
            fast, slow, _ = sig
            print(f"    {i}. ({fast},{slow}) {label:<14s} → "
                  f"收益 {stats['total_return']*100:+7.2f}%  "
                  f"Sharpe {stats['sharpe_ratio']:+.3f}  "
                  f"回撤 {stats['max_ddpercent']*100:7.2f}%  "
                  f"笔数 {stats['trade_count']}")

        for sig, stats, label in stock_results:
            fast, slow, mode = sig
            all_results.append({
                "stock": name,
                "code": code,
                "fast": fast, "slow": slow,
                "mode": label,
                "total_return": stats["total_return"],
                "sharpe": stats["sharpe_ratio"],
                "max_dd": stats["max_ddpercent"],
                "trade_count": stats["trade_count"],
            })

    # ===== 跨股票推荐 =====
    print("\n" + "="*78)
    print("  🎯 跨股票推荐（看 min_sharpe 找最稳的）")
    print("="*78)

    df_all = pd.DataFrame(all_results)

    grouped = df_all.groupby(["fast", "slow", "mode"]).agg(
        avg_sharpe=("sharpe", "mean"),
        min_sharpe=("sharpe", "min"),
        max_sharpe=("sharpe", "max"),
        avg_return=("total_return", "mean"),
        avg_dd=("max_dd", "mean"),
        total_trades=("trade_count", "sum"),
    ).reset_index().sort_values("min_sharpe", ascending=False)

    print(f"\n  {'参数':<8} {'模式':<14} {'最低Sharpe':<10} {'平均Sharpe':<10} {'最高Sharpe':<10} {'平均收益':<10} {'平均回撤':<10}")
    print(f"  {'─'*8} {'─'*14} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
    for _, r in grouped.iterrows():
        sig = f"({r['fast']},{r['slow']})"
        avg_sh = r["avg_sharpe"]
        min_sh = r["min_sharpe"]
        max_sh = r["max_sharpe"]
        avg_ret = r["avg_return"] * 100
        avg_dd = r["avg_dd"] * 100
        print(f"  {sig:<8} {r['mode']:<14} "
              f"{min_sh:+10.3f} {avg_sh:+10.3f} {max_sh:+10.3f} "
              f"{avg_ret:+10.2f}% {avg_dd:+10.2f}%")

    # 跨股票最稳 = min_sharpe 最高
    top = grouped.head(3)
    print(f"\n  🥇 TOP 3 跨股票推荐（min_sharpe 最高）:")
    for _, r in top.iterrows():
        print(f"    → ({r['fast']},{r['slow']}) {r['mode']:<14}  "
              f"min {r['min_sharpe']:+.3f}  avg {r['avg_sharpe']:+.3f}  "
              f"avg_ret {r['avg_return']*100:+.2f}%")

    # 找出"3 只股 Sharpe 都 > 0" 的参数
    print(f"\n  🌟 '3 只股都不亏' 的参数（min_sharpe > 0）：")
    all_positive = grouped[grouped["min_sharpe"] > 0]
    if len(all_positive) == 0:
        print("    ❌ 没有")
    else:
        for _, r in all_positive.iterrows():
            print(f"    ✓ ({r['fast']},{r['slow']}) {r['mode']:<14}  "
                  f"min {r['min_sharpe']:+.3f}  avg {r['avg_sharpe']:+.3f}  "
                  f"avg_ret {r['avg_return']*100:+.2f}%")

    # 写出缓存
    out = Path("data/strategy_with_sl.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n💾 已存到 {out}（{len(all_results)} 条）")
    print("\n⚠️ 止损实现细节：")
    print("  - 用 on_bar 每根 K 线检查浮亏 vs entry_price")
    print("  - 触发时市价卖（self.sell(close, pos)）")
    print("  - 没有考虑跳空（实盘可能更差）")
    print("  - 简单实现，没考虑波动率动态止损")


if __name__ == "__main__":
    main()
