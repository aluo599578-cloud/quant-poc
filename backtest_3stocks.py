"""
backtest_3stocks.py — 三只 A 股的 vnpy 回测
=============================================

策略：双均线金叉死叉（A 股最经典的 PoC 策略）
- 5 日 EMA 上穿 30 日 EMA → 买入
- 5 日 EMA 下穿 30 日 EMA → 卖出

数据：tushare 日线（前复权），最近 3 年
引擎：vnpy_ctastrategy.backtesting.BacktestingEngine
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pandas as pd
import tushare as ts
from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData, Exchange
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.template import CtaTemplate
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy


# 你的三只股。vt_symbol 用 vnpy 风格 (.SZSE / .SSE) 才能让 BacktestingEngine.set_parameters 直接解析
STOCKS = [
    ("002180.SZSE", "002180", "纳思达"),
    ("000100.SZSE", "000100", "TCL科技"),
    ("688122.SSE",  "688122", "西部超导"),
]


def to_tushare_code(vt_symbol: str) -> str:
    """vnpy 风格 → tushare 风格: 002180.SZSE -> 002180.SZ"""
    code, exch = vt_symbol.split(".")
    return f"{code}.{'SZ' if exch == 'SZSE' else 'SH'}"

START = datetime(2023, 1, 1)
END = datetime.now()
INIT_CAPITAL = 1_000_000


def fetch_kline(code_with_exch: str, start: str, end: str) -> pd.DataFrame:
    """tushare 拿前复权日线。code_with_exch 必须是 '002180.SZ' 这种完整格式。"""
    pro = ts.pro_api()
    df = pro.daily(
        ts_code=code_with_exch,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adj="qfq",  # 前复权
    )
    if df is None or df.empty:
        raise RuntimeError(f"tushare 返回空数据: {code_with_exch}")
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    return df


# tushare/vt_symbol 后缀 → vnpy Exchange 枚举值
EXCHANGE_MAP = {
    "SZSE": Exchange.SZSE,
    "SSE": Exchange.SSE,
    "SHSE": Exchange.SSE,
    "BJSE": Exchange.BSE,
}


def make_bars(df: pd.DataFrame, vt_symbol: str):
    """pandas DataFrame → vnpy BarData 列表"""
    bars = []
    code, exch_short = vt_symbol.split(".")
    exch = Exchange.SZSE if exch_short == "SZ" else Exchange.SSE
    for _, row in df.iterrows():
        bar = BarData(
            symbol=code,
            exchange=exch,
            datetime=row["trade_date"].to_pydatetime(),
            interval=Interval.DAILY,
            open_price=float(row["open"]),
            high_price=float(row["high"]),
            low_price=float(row["low"]),
            close_price=float(row["close"]),
            volume=float(row["vol"]),
            turnover=float(row.get("amount", 0)) or 0,
            gateway_name="TUSHARE",
        )
        bars.append(bar)
    return bars


def run_one(vt_symbol: str, code: str, name: str):
    print(f"\n{'='*70}\n  [{vt_symbol}] {name}\n{'='*70}")

    # 1) 拉数据
    print(f"  → tushare 拉 {vt_symbol} 日线 ({START.date()} ~ {END.date()})")
    df = fetch_kline(to_tushare_code(vt_symbol), START.strftime("%Y-%m-%d"), END.strftime("%Y-%m-%d"))
    print(f"    got {len(df)} bars, range {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}")

    # 2) 转 vnpy bars
    bars = make_bars(df, vt_symbol)

    # 3) 跑回测
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=Interval.DAILY,
        start=START,
        end=END,
        rate=0.0003,        # 佣金万三
        slippage=0.01,      # 滑点 1 分钱
        size=100,           # A 股 1 手
        pricetick=0.01,
        capital=INIT_CAPITAL,
    )
    engine.add_strategy(DoubleMaStrategy, {
        "fast_window": 5,
        "slow_window": 30,
    })
    # 直接把 bars 灌进 engine.history_data，跳过 load_data()（避免数据库依赖 + 时间窗口限制）
    engine.history_data = list(bars)

    print("  → 跑回测 ...")
    engine.run_backtesting()
    df_result = engine.calculate_result()
    stats = engine.calculate_statistics()

    # 4) 输出关键指标
    print(f"\n  --- 关键指标 ---")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"    {k:24s} {v:.4f}")
        else:
            print(f"    {k:24s} {v}")

    return {
        "code": code, "name": name,
        "n_bars": len(bars),
        "stats": stats,
        "trades": engine.trades,
    }


def main():
    results = []
    for vt_sym, code, name in STOCKS:
        try:
            r = run_one(vt_sym, code, name)
            results.append(r)
        except Exception as e:
            print(f"  ❌ {vt_sym} {name} 失败: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*70}\n  SUMMARY\n{'='*70}")
    print(f"{'代码':<8} {'名称':<8} {'总收益':>10} {'年化':>10} {'夏普':>8} {'最大回撤':>10} {'胜率':>8} {'交易数':>8}")
    for r in results:
        s = r["stats"]
        # max_ddpercent 已经是负的小数（如 -0.62 表示 -0.62%），直接乘 100 得百分数
        dd_pct = s.get('max_ddpercent', 0) * 100
        print(f"{r['code']:<8} {r['name']:<8} "
              f"{s.get('total_return', 0)*100:>9.2f}% "
              f"{s.get('annual_return', 0)*100:>9.2f}% "
              f"{s.get('sharpe_ratio', 0):>8.2f} "
              f"{dd_pct:>9.2f}% "
              f"{(s.get('profit_days', 0) / max(s.get('total_days', 1), 1))*100:>7.2f}% "
              f"{s.get('total_trade_count', 0):>8d}")


if __name__ == "__main__":
    main()
