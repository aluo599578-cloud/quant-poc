"""
live_trading_multi.py — 多股实盘（HK Top 5 候选）
======================================================

按 Top 5 候选股轮询跑：
  - 拉最新 K 线
  - 布林带均值回归信号
  - 在富途模拟账户分散持仓
  - 每天 HK 收盘后跑一次

用法:
  # 单次
  python live_trading_multi.py

  # 指定股票
  python live_trading_multi.py --codes HK.01288 HK.01398 HK.03988 HK.00700
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from futu import (
    OpenQuoteContext, OpenSecTradeContext, RET_OK, TrdEnv, KLType,
    OrderType, TrdSide,
)

from live_trading_00700 import (
    get_market_snapshot, get_kline, calc_indicators, generate_signal,
    place_order, get_account_info, init_db, DB_PATH, STATE_PATH, save_state,
    ACCOUNT_ID, TRD_ENV, STRATEGY,
)


# 多股实盘：每只股独立跑
def process_stock(code: str, name: str, q_ctx, t_ctx, conn, state):
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*70}")
    print(f"  {name} ({code}) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    # 1. 拉 K 线（1500 天，约 6 年）
    df = get_kline(code, 1500)
    if len(df) < 100:
        print(f"  ❌ 数据不足 ({len(df)} 根)")
        return
    print(f"  [1] 拉 {len(df)} 根 K 线")
    closes = df["close"].reset_index(drop=True)

    # 2. 实时价
    try:
        current_price = get_market_snapshot(code)
        print(f"  [2] 实时价 HK${current_price:.2f}")
        closes.iloc[-1] = current_price
    except Exception as e:
        current_price = float(closes.iloc[-1])
        print(f"  [2] 实时价失败，用历史 HK${current_price:.2f}")

    # 3. 指标
    middle, upper, lower, rsi = calc_indicators(closes)
    print(f"  [3] BB中轨 {middle:.2f} 上轨 {upper:.2f} 下轨 {lower:.2f}  RSI {rsi:.1f}")

    # 4. 持仓
    try:
        cash, pos = get_account_info(t_ctx)
        pos_qty = 0
        if len(pos) > 0:
            for _, row in pos.iterrows():
                if row.get("code") == code:
                    pos_qty = int(row.get("qty", 0))
        cash_available = float(cash.iloc[0].get("cash", 0)) if len(cash) > 0 else 0
        print(f"  [4] 现金 HK${cash_available:,.0f}  持仓 {pos_qty} 股")
    except Exception as e:
        print(f"  [4] ❌ 查账户失败: {e}")
        return

    # 5. 信号
    signal = generate_signal(current_price, upper, lower, rsi, pos_qty)
    print(f"  [5] 信号: {signal}")

    # 写 signal 到 db
    conn.execute("""
        INSERT INTO signals (ts, strategy, code, signal, price, close_price,
                              bb_upper, bb_lower, rsi, position, cash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), f"{STRATEGY}_{name}", code, signal, current_price,
          current_price, upper, lower, rsi, pos_qty, cash_available))
    conn.commit()

    # 防重复：今天同 code 同 signal 不重复
    key = f"{today}_{code}"
    last_trade = state.get(key, {}).get("last_signal")

    if last_trade == signal:
        print(f"  [6] 跳过（今天 {today} 已对 {signal} 处理）")
    elif signal == "HOLD":
        print(f"  [6] HOLD — 不下单")
        state.setdefault(key, {})["last_signal"] = signal
    elif signal == "BUY":
        # 检查资金
        lot_size = 100  # 1 手 = 100
        cost = current_price * lot_size * 1.001
        if cash_available < cost:
            print(f"  [6] 资金不足 HK${cash_available:.0f} < HK${cost:.0f}")
        else:
            # 检查总仓位不超过 60%
            target_position_value = current_price * lot_size
            current_total = pos["market_val"].sum() if len(pos) > 0 else 0
            total_after = current_total + target_position_value
            if total_after / (cash_available + current_total) > 0.6 and current_total > 0:
                print(f"  [6] 总仓位超过 60% 限制，跳过")
            else:
                print(f"  [6] 下单: 买入 {lot_size} 股 @ 市价")
                ret, data = place_order(t_ctx, "BUY", 1)
                if ret == RET_OK:
                    order_id = str(data.iloc[0]["order_id"]) if len(data) > 0 else "?"
                    print(f"      ✓ 成功 order_id={order_id}")
                    conn.execute("""
                        INSERT INTO orders (ts, strategy, code, side, order_id, fill_price,
                                             fill_qty, status, msg)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (datetime.now().isoformat(), f"{STRATEGY}_{name}", code, "BUY",
                          order_id, current_price, lot_size, "submitted", ""))
                    conn.commit()
                else:
                    print(f"      ❌ 失败: {data}")
                state.setdefault(key, {})["last_signal"] = signal
    elif signal == "SELL":
        if pos_qty == 0:
            print(f"  [6] 无持仓，不卖")
        else:
            print(f"  [6] 下单: 卖出 {pos_qty} 股 @ 市价")
            ret, data = place_order(t_ctx, "SELL", pos_qty // 100)
            if ret == RET_OK:
                order_id = str(data.iloc[0]["order_id"]) if len(data) > 0 else "?"
                print(f"      ✓ 成功 order_id={order_id}")
                conn.execute("""
                    INSERT INTO orders (ts, strategy, code, side, order_id, fill_price,
                                         fill_qty, status, msg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), f"{STRATEGY}_{name}", code, "SELL",
                      order_id, current_price, pos_qty, "submitted", ""))
                conn.commit()
            else:
                print(f"      ❌ 失败: {data}")
            state.setdefault(key, {})["last_signal"] = signal

    # P&L
    avg_cost = 0.0
    if len(pos) > 0:
        for _, row in pos.iterrows():
            if row.get("code") == code:
                avg_cost = float(row.get("cost_price", 0))
    unrealized = (current_price - avg_cost) * pos_qty if pos_qty > 0 and avg_cost > 0 else 0
    market_value = current_price * pos_qty
    total_equity = cash_available + market_value
    print(f"  [7] P&L: 浮盈 HK${unrealized:,.0f}  总权益 HK${total_equity:,.0f}")

    conn.execute("""
        INSERT INTO pnl (ts, strategy, code, cash, position, avg_cost, market_value,
                          unrealized_pnl, realized_pnl, total_equity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), f"{STRATEGY}_{name}", code, cash_available, pos_qty,
          avg_cost, market_value, unrealized, 0, total_equity))
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="*", default=[
        "HK.01288",  # 农业银行
        "HK.01398",  # 工商银行
        "HK.03988",  # 中国银行
        "HK.00939",  # 建设银行
        "HK.00700",  # 腾讯
    ])
    parser.add_argument("--account", type=int, default=ACCOUNT_ID)
    args = parser.parse_args()

    # 港股名
    HK_NAMES = {
        "HK.01288": "农业银行", "HK.01398": "工商银行",
        "HK.03988": "中国银行", "HK.00939": "建设银行",
        "HK.00700": "腾讯", "HK.02522": "一脉阳光",
        "HK.00005": "汇丰控股", "HK.09988": "阿里巴巴",
        "HK.03690": "美团", "HK.01024": "快手",
        "HK.09618": "京东集团", "HK.09888": "百度集团",
        "HK.01211": "比亚迪", "HK.01810": "小米",
        "HK.02015": "理想汽车", "HK.00992": "联想",
    }

    print("="*70)
    print(f"  multi-stock live trading - {datetime.now()}")
    print(f"  股票: {args.codes}")
    print(f"  账户: {args.account}")
    print("="*70)

    conn = init_db()
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}

    t = OpenSecTradeContext(host='127.0.0.1', port=11111, is_encrypt=False)
    try:
        for code in args.codes:
            name = HK_NAMES.get(code, code)
            try:
                process_stock(code, name, None, t, conn, state)
            except Exception as e:
                print(f"  ❌ {code} 失败: {e}")
    finally:
        t.close()
        save_state(state)
        conn.close()

    print(f"\n{'='*70}")
    print(f"  完成 {len(args.codes)} 只股")
    print(f"  数据库: {DB_PATH}")
    print(f"  下次运行: HK 收盘后 (16:00+ HKT)")


if __name__ == "__main__":
    main()
