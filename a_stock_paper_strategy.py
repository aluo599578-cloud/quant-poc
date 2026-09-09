"""
a_stock_paper_strategy.py — A 股模拟盘策略（A 股用户立刻能跑）
================================================================

用法：python a_stock_paper_strategy.py

跟 demo_hk_simple_strategy.py 的区别：
  - 不依赖富途（你的富途账户没开 A 股）
  - 用 tushare 拉 A 股数据（已有 token）
  - 用我们 quant-poc 的 PaperEngine 撮合（不真下单）
  - 跑：002180 纳思达 / 000100 TCL / 688122 西部超导

效果：每只股当下算出"信号"，如果当前无持仓+信号 → 显示"应买 N 股"；
     如果当前持仓+反向信号 → 显示"应卖"。**只是建议，不真下单**。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 让脚本能 import quant-poc
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy

from backtest_3stocks import (
    STOCKS, fetch_kline, make_bars, to_tushare_code,
)


# 策略参数
FAST_MA = 5
SLOW_MA = 20
TREND_MA = 200
STOP_LOSS_PCT = 0.05
INIT_CAPITAL = 200_000.0   # 20 万 RMB 模拟盘

# Paper state（写到 data/paper_state.json，重启保留）
STATE_FILE = Path("data/paper_state.json")


def load_state():
    """加载现有 paper 状态。"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def calc_signals(df: pd.DataFrame) -> pd.DataFrame:
    """算均线 + 信号。"""
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(FAST_MA).mean()
    df["ma_slow"] = df["close"].rolling(SLOW_MA).mean()
    df["ma_trend"] = df["close"].rolling(TREND_MA).mean()
    df["signal"] = (
        (df["ma_fast"] > df["ma_slow"]) &
        (df["close"] > df["ma_trend"])
    ).astype(int)
    return df


def evaluate_stock(symbol: str, name: str, state: dict):
    """评估单只股。

    Args:
        symbol: 纯代码（如 '002180'）— 我们内部加 .SZSE 转 vnpy 风格
        name: 显示名
    """
    print(f"\n{'='*70}")
    print(f"  📊 {name} ({symbol})")
    print(f"{'='*70}")

    # vnpy 风格 vt_symbol（vnpy enum 只认 .SZSE/.SSE 不认 .SZ/.SH）
    from quant_core import _normalize_vt_symbol

    # 推导交易所后缀（6xxxxx.SH，科创/创业/中小 .SZ）
    tushare_code = f"{symbol}.SZ" if symbol.startswith(("002", "003", "000", "300")) else f"{symbol}.SH"
    vt_symbol = _normalize_vt_symbol(tushare_code)  # 002180.SZ -> 002180.SZSE

    # 拉数据
    df = fetch_kline(tushare_code, "2023-01-01", datetime.now().strftime("%Y-%m-%d"))
    bars = make_bars(df, tushare_code)

    # 跑回测（vnpy）
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol, interval=Interval.DAILY,
        start=datetime(2023, 1, 1),
        end=datetime.now(),
        rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=INIT_CAPITAL,
    )
    engine.add_strategy(DoubleMaStrategy, {"fast_window": FAST_MA, "slow_window": SLOW_MA})
    engine.history_data = list(bars)
    engine.run_backtesting()
    engine.calculate_result()
    s = engine.calculate_statistics()

    print(f"\n[回测期] {df.iloc[0]['trade_date']} ~ {df.iloc[-1]['trade_date']} ({len(bars)} 根 K 线)")
    print(f"  起始价: {df.iloc[0]['close']:.2f}    最新价: {df.iloc[-1]['close']:.2f}    涨跌: {(df.iloc[-1]['close']/df.iloc[0]['close']-1)*100:+.1f}%")

    print(f"\n[策略回测 — 双均线 ({FAST_MA},{SLOW_MA})]")
    print(f"  总收益:   {s['total_return']*100:+.2f}%")
    print(f"  年化:     {s['annual_return']*100:+.2f}%")
    print(f"  夏普:     {s['sharpe_ratio']:+.3f}")
    print(f"  最大回撤: {s['max_ddpercent']*100:.2f}%")
    print(f"  交易笔数: {int(s['total_trade_count'])}")

    # 当前信号
    df_sig = calc_signals(df)
    last = df_sig.iloc[-1]
    print(f"\n[当前信号]")
    print(f"  MA{FAST_MA}:   {last['ma_fast']:.2f}")
    print(f"  MA{SLOW_MA}:   {last['ma_slow']:.2f}")
    print(f"  MA{TREND_MA}: {last['ma_trend']:.2f}")
    print(f"  信号: {'🟢 买入（MA5>MA20 且 close>MA200）' if last['signal']==1 else '🔴 空仓'}")

    # Paper 状态
    pos = state.get(symbol, {})
    cur_qty = pos.get("qty", 0)
    cur_cost = pos.get("cost", 0.0)

    print(f"\n[当前 paper 持仓]")
    if cur_qty > 0:
        pl_pct = (last['close'] - cur_cost) / cur_cost
        pl_amount = (last['close'] - cur_cost) * cur_qty
        print(f"  持仓: {cur_qty} 股 @ 成本 {cur_cost:.2f}")
        print(f"  现价: {last['close']:.2f}    浮盈亏: {pl_pct*100:+.2f}% (¥{pl_amount:+,.0f})")
        if pl_pct <= -STOP_LOSS_PCT:
            print(f"  🔴 触发止损！建议卖 {cur_qty} 股")
    else:
        print(f"  空仓")

    # 决策建议
    print(f"\n[操作建议]")
    if cur_qty > 0 and (last['signal']==0 or (last['close'] - cur_cost)/cur_cost <= -STOP_LOSS_PCT):
        reason = "死叉或触发止损" if last['signal']==0 else "5% 止损"
        print(f"  → 卖出 {cur_qty} 股（市价单）")
        state[symbol] = {"qty": 0, "cost": 0.0, "last_action": f"sell_{reason}", "at": datetime.now().isoformat()}
    elif cur_qty == 0 and last['signal'] == 1:
        price = last['close']
        n_lots = int(INIT_CAPITAL * 0.95 / (price * 100))  # 95% 资金买 100 股一手
        n_shares = n_lots * 100
        cost = n_shares * price
        print(f"  → 买入 {n_shares} 股 @ 市价 (HK${cost:,.0f}，占资金 {cost/INIT_CAPITAL*100:.0f}%)")
        state[symbol] = {"qty": n_shares, "cost": price, "last_action": "buy", "at": datetime.now().isoformat()}
    else:
        print(f"  → 继续持有/观望")

    print(f"  ⚠️ 这是模拟，不会真下单；要真下单用 broker_futu.py 接 OpenD")


def main():
    print("="*70)
    print(f"  📊 A 股双均线策略演示（Paper 模拟盘）")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  策略: MA{FAST_MA} > MA{SLOW_MA} 且 close > MA{TREND_MA} → 买入")
    print(f"  止损: {STOP_LOSS_PCT*100:.0f}%")
    print(f"  初始资金: ¥{INIT_CAPITAL:,.0f}")
    print(f"  数据源: tushare (token 来自 ~/.openclaw/openclaw.json)")
    print("="*70)

    state = load_state()
    for symbol, code, name in STOCKS:
        evaluate_stock(code, name, state)
    save_state(state)
    print(f"\n\n💾 Paper 状态已保存到 {STATE_FILE}")
    print(f"💡 真实下单：先在富途牛牛 App 申请 A 股市场权限 → 然后用 broker_futu.py")


if __name__ == "__main__":
    main()
