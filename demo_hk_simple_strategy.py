"""
demo_hk_simple_strategy.py — 腾讯 00700.HK 模拟账户跑双均线策略
===============================================================

用法：
  1. 打开富途牛牛客户端 → 启动 OpenD（解锁交易密码）
  2. 跑：python demo_hk_simple_strategy.py

效果：
  - 拉 00700.HK 最近 100 个交易日 K 线
  - 算 MA5 / MA20 / MA200
  - 模拟账户里：如果当前 MA5 > MA20 且 close > MA200 → 买
  - 如果 MA5 < MA20 → 卖
  - 5% 止损
  - 实时打印账户状态 + 持仓 + 触发信号
  - 一次跑完，不循环（不是实盘订阅）

⚠️ 只能下 HK 股票（你的账户不支持 A 股）
"""
from __future__ import annotations

import sys
from datetime import datetime

import pandas as pd
from futu import (
    OpenQuoteContext,
    OpenSecTradeContext,
    RET_OK,
    TrdEnv,
    TrdSide,
    OrderType,
)


SYMBOL = "HK.00700"            # 腾讯
LOT = 100                     # HK 股票 1 手
SIM_ACC_ID = 15559050         # 你的模拟账户 ID
STOP_LOSS_PCT = 0.05          # 5% 止损
FAST_MA = 5
SLOW_MA = 20
TREND_MA = 200                # MA200 过滤
INIT_CAPITAL = 500_000.0      # 模拟盘起手钱（你的模拟盘默认 100 万 HKD）


def fetch_klines(symbol: str, n: int = 300):
    """拉最近 n 个交易日 K 线。"""
    from futu import KLType
    q = OpenQuoteContext(host='127.0.0.1', port=11111, is_encrypt=False)
    try:
        ret, data, _ = q.request_history_kline(
            symbol, ktype=KLType.K_DAY, max_count=n,
        )
        if ret != RET_OK:
            print(f"❌ 拉 K 线失败: {data}")
            sys.exit(1)
        df = data.copy()
        df['date'] = pd.to_datetime(df['time_key'])
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']].set_index('date')
        return df
    finally:
        q.close()


def calc_ma(df: pd.DataFrame) -> pd.DataFrame:
    df['ma_fast'] = df['close'].rolling(FAST_MA).mean()
    df['ma_slow'] = df['close'].rolling(SLOW_MA).mean()
    df['ma_trend'] = df['close'].rolling(TREND_MA).mean()
    df['signal'] = (
        (df['ma_fast'] > df['ma_slow']) &
        (df['close'] > df['ma_trend'])
    ).astype(int)
    return df


def get_position_and_cash():
    """读模拟账户当前持仓和现金。"""
    t = OpenSecTradeContext(host='127.0.0.1', port=11111, is_encrypt=False)
    try:
        # 持仓
        ret, pos = t.position_list_query(trd_env=TrdEnv.SIMULATE)
        positions = []
        if ret == RET_OK and pos is not None:
            for _, row in pos.iterrows():
                if row['code'] == SYMBOL:
                    positions.append({
                        'qty': int(row['qty']),
                        'cost': float(row['cost_price']),
                        'current': float(row['nominal_price']),
                        'pl_ratio': float(row['pl_ratio']) / 100,
                    })

        # 资金（futu-api 10.10 方法名变了，先用 try/except 试两个）
        cash = 0.0
        for method_name in ['get_assets', 'funds_query', 'account_info_query']:
            if hasattr(t, method_name):
                try:
                    ret, fund = getattr(t, method_name)(trd_env=TrdEnv.SIMULATE)
                    if ret == RET_OK and fund is not None and not fund.empty:
                        # 取第一个数字字段
                        for col in fund.columns:
                            val = fund.iloc[0][col]
                            try:
                                if isinstance(val, (int, float)) and val > 0 and val < 1e12:
                                    cash = float(val)
                                    break
                            except Exception:
                                pass
                        if cash > 0:
                            break
                except Exception:
                    continue
        return positions, cash
    finally:
        t.close()


def market_buy(qty: int):
    """市价买入 qty 股（HK 单位是 lot，每手 100 股）。"""
    t = OpenSecTradeContext(host='127.0.0.1', port=11111, is_encrypt=False)
    try:
        ret, data = t.place_order(
            price=0.0,        # 市价单 price 传 0
            qty=qty,
            code=SYMBOL,
            trd_side=TrdSide.BUY,
            order_type=OrderType.MARKET,
            trd_env=TrdEnv.SIMULATE,
        )
        if ret != RET_OK:
            print(f"  ❌ 下单失败: {data}")
            return False
        print(f"  ✅ 已下买单: {qty} 股 @ 市价")
        return True
    finally:
        t.close()


def market_sell(qty: int):
    """市价卖出。"""
    t = OpenSecTradeContext(host='127.0.0.1', port=11111, is_encrypt=False)
    try:
        ret, data = t.place_order(
            price=0.0,
            qty=qty,
            code=SYMBOL,
            trd_side=TrdSide.SELL,
            order_type=OrderType.MARKET,
            trd_env=TrdEnv.SIMULATE,
        )
        if ret != RET_OK:
            print(f"  ❌ 下单失败: {data}")
            return False
        print(f"  ✅ 已下卖单: {qty} 股 @ 市价")
        return True
    finally:
        t.close()


def main():
    print("="*70)
    print(f"  📊 {SYMBOL} 双均线策略演示（模拟账户）")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  策略: MA{FAST_MA} > MA{SLOW_MA} 且 close > MA{TREND_MA} → 买入")
    print(f"  止损: {STOP_LOSS_PCT*100:.0f}% | 账户: 模拟 #{SIM_ACC_ID}")
    print("="*70)

    # 1. 拉 K 线
    print(f"\n[1/4] 拉 {SYMBOL} 最近 300 个交易日 K 线...")
    df = fetch_klines(SYMBOL, n=300)
    print(f"  拉到 {len(df)} 根 K 线 ({df.index.min().date()} ~ {df.index.max().date()})")
    print(f"  最新收盘价: {df.iloc[-1]['close']:.2f}")

    # 2. 算均线 + 信号
    print(f"\n[2/4] 算 MA{FAST_MA}/MA{SLOW_MA}/MA{TREND_MA}...")
    df = calc_ma(df)
    last = df.iloc[-1]
    print(f"  最新 MA{FAST_MA}: {last['ma_fast']:.2f}")
    print(f"  最新 MA{SLOW_MA}: {last['ma_slow']:.2f}")
    print(f"  最新 MA{TREND_MA}: {last['ma_trend']:.2f}")
    print(f"  信号: {'🟢 买入' if last['signal'] == 1 else '🔴 空仓'}")

    # 3. 看账户当前状态
    print(f"\n[3/4] 读模拟账户状态...")
    positions, cash = get_position_and_cash()
    print(f"  可用现金: HK${cash:,.2f}")
    cur_qty = positions[0]['qty'] if positions else 0
    cur_cost = positions[0]['cost'] if positions else 0
    cur_pl = positions[0]['pl_ratio'] if positions else 0
    print(f"  当前持仓: {cur_qty} 股 @ 成本 {cur_cost:.2f}" if cur_qty > 0 else "  当前持仓: 空仓")
    if cur_qty > 0:
        print(f"  当前浮盈亏: {cur_pl*100:+.2f}%")

    # 4. 触发决策
    print(f"\n[4/4] 决策...")
    action_taken = False

    # 止损检查
    if cur_qty > 0 and cur_pl <= -STOP_LOSS_PCT:
        print(f"  🔴 触发止损 ({cur_pl*100:.2f}% < -{STOP_LOSS_PCT*100:.0f}%)，卖出全部 {cur_qty} 股")
        market_sell(cur_qty)
        action_taken = True

    # 信号检查
    if not action_taken:
        if cur_qty == 0 and last['signal'] == 1:
            # 空仓 + 买入信号 → 满仓
            price = last['close']
            n_lots = int(cash / (price * LOT))
            n_shares = n_lots * LOT
            if n_shares >= LOT:
                print(f"  🟢 买入信号 + 空仓 → 买 {n_shares} 股 (HK${price:.2f} × {n_shares})")
                market_buy(n_shares)
                action_taken = True
            else:
                print(f"  ⚠️ 现金不足 (HK${cash:,.0f}，需要 HK${price*LOT:,.0f})")
        elif cur_qty > 0 and last['signal'] == 0:
            # 已持仓 + 空仓信号 → 卖出
            print(f"  🔴 死叉信号 → 卖 {cur_qty} 股")
            market_sell(cur_qty)
            action_taken = True
        else:
            print(f"  💤 无操作（信号: {last['signal']}，持仓: {cur_qty}）")

    if not action_taken:
        print("\n  → 无操作")
    print("\n" + "="*70)
    print("演示完成。要跑实盘循环，把脚本包成 while True + time.sleep(60) 就行。")


if __name__ == "__main__":
    main()
