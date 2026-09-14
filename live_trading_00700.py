"""
live_trading_00700.py — 腾讯 00700.HK 实盘 Lean 策略
=====================================================

每天 HK 收盘后（16:00 HKT）跑一次：
  1. 拉 00700 最新 100 天 K 线
  2. 用 BollingerMeanReversionLean 算信号
  3. 在富途模拟账户 15559050 下单
  4. 记录 P&L 到 SQLite
  5. 防重复下单

用法:
  # 单次运行（手动）
  python live_trading_00700.py

  # 每天自动跑（推荐用 cron / Task Scheduler）
  # 每天 HK 16:30 跑（避开最后 30 分钟剧烈波动）
  # 30 1 16:30 * * MON-FRI cd /c/Users/18566/Desktop/quant-poc && python live_trading_00700.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from futu import (
    OpenQuoteContext, OpenSecTradeContext, RET_OK, TrdEnv, KLType,
    OrderType, TrdSide, OrderStatus,
)


# ============================================================
# 配置
# ============================================================

CODE = "HK.00700"
STOCK_NAME = "腾讯控股"
VT_SYMBOL = "00700.SEHK"
LOT_SIZE = 100  # 腾讯 1 手 = 100 股
STRATEGY = "BollingerMeanReversion"
ACCOUNT_ID = 15559050  # 模拟账户 CASH
TRD_ENV = TrdEnv.SIMULATE
DB_PATH = Path("data/live_trading.db")
STATE_PATH = Path("data/live_state.json")


# ============================================================
# 数据库
# ============================================================

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            strategy TEXT NOT NULL,
            code TEXT NOT NULL,
            signal TEXT NOT NULL,
            price REAL,
            close_price REAL,
            bb_upper REAL,
            bb_lower REAL,
            rsi REAL,
            position INTEGER,
            cash REAL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            strategy TEXT NOT NULL,
            code TEXT NOT NULL,
            side TEXT NOT NULL,
            order_id TEXT,
            fill_price REAL,
            fill_qty INTEGER,
            status TEXT,
            msg TEXT
        );
        CREATE TABLE IF NOT EXISTS pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            strategy TEXT NOT NULL,
            code TEXT NOT NULL,
            cash REAL,
            position INTEGER,
            avg_cost REAL,
            market_value REAL,
            unrealized_pnl REAL,
            realized_pnl REAL,
            total_equity REAL
        );
    """)
    conn.commit()
    return conn


# ============================================================
# 富途 API
# ============================================================

def get_market_snapshot(code: str) -> float:
    """拉实时价（用于 signal）"""
    q = OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, data = q.get_market_snapshot([code])
    q.close()
    if ret != RET_OK or len(data) == 0:
        raise RuntimeError(f"snapshot err: {data}")
    return float(data.iloc[0]["last_price"])


def get_kline(code: str, n: int = 500):
    """拉最近 N 天 K 线"""
    q = OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, data, _ = q.request_history_kline(code, ktype=KLType.K_DAY, max_count=n)
    q.close()
    if ret != RET_OK:
        raise RuntimeError(f"futu kline err: {data}")
    return data


def get_account_info(t):
    """查账户余额 + 持仓"""
    ret_cash, cash = t.accinfo_query(trd_env=TRD_ENV, acc_id=ACCOUNT_ID)
    if ret_cash != RET_OK:
        raise RuntimeError(f"accinfo err: {cash}")
    ret_pos, pos = t.position_list_query(trd_env=TRD_ENV, acc_id=ACCOUNT_ID)
    if ret_pos != RET_OK:
        raise RuntimeError(f"position err: {pos}")
    return cash, pos


def place_order(t, side: str, qty: int):
    """下市价单"""
    if side == "BUY":
        trd_side = TrdSide.BUY
    else:
        trd_side = TrdSide.SELL

    ret, data = t.place_order(
        price=0,  # 市价
        qty=qty * LOT_SIZE,
        code=CODE,
        trd_side=trd_side,
        order_type=OrderType.MARKET,
        trd_env=TRD_ENV,
        acc_id=ACCOUNT_ID,
    )
    return ret, data


# ============================================================
# Lean 风格策略信号
# ============================================================

def calc_indicators(closes: pd.Series):
    """计算布林带 + RSI（不用 CtaTemplate，纯函数）"""
    # 布林带 (20, 2)
    period = 20
    stddev = 2.0
    middle = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    upper = middle + stddev * std
    lower = middle - stddev * std

    # RSI (14) - Wilder 算法
    rsi_period = 14
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/rsi_period, min_periods=rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - 100 / (1 + rs)

    return middle.iloc[-1], upper.iloc[-1], lower.iloc[-1], rsi.iloc[-1]


def generate_signal(close: float, bb_upper: float, bb_lower: float, rsi: float, position: int):
    """跟 BollingerMeanReversionLean 同样的逻辑"""
    if rsi < 30 and close < bb_lower and position == 0:
        return "BUY"
    elif (rsi > 70 or close > (bb_upper + bb_lower) / 2) and position > 0:
        return "SELL"
    return "HOLD"


# ============================================================
# 主流程
# ============================================================

def load_state():
    """读上次状态（防重复下单）"""
    if STATE_PATH.exists():
        import json
        return json.loads(STATE_PATH.read_text())
    return {"last_trade_date": None, "last_signal": None}


def save_state(state):
    import json
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    print("="*70)
    print(f"  {STOCK_NAME} ({CODE}) 实盘 Lean 策略 — {datetime.now()}")
    print(f"  策略: {STRATEGY} (布林带均值回归)")
    print(f"  账户: 模拟 {ACCOUNT_ID}")
    print("="*70)

    conn = init_db()
    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 拉 K 线（历史）
    print(f"\n[1] 拉 {CODE} 最近 500 天 K 线...")
    df = get_kline(CODE, n=500)
    print(f"    {len(df)} 根, 最新 {df['time_key'].iloc[0]} 收盘 HK${df['close'].iloc[0]:.2f}")
    closes = df["close"].reset_index(drop=True)

    # 2. 拉实时价（用于当前判断）
    print(f"\n[2] 拉实时价...")
    try:
        current_price = get_market_snapshot(CODE)
        print(f"    实时价 HK${current_price:.2f}")
        # 用实时价覆盖历史最后一根
        closes.iloc[-1] = current_price
    except Exception as e:
        print(f"    ⚠️ 实时价拉取失败 ({e}), 用历史最后一根")
        current_price = float(closes.iloc[-1])

    # 3. 计算指标
    print(f"\n[3] 计算布林带 + RSI...")
    middle, upper, lower, rsi = calc_indicators(closes)
    print(f"    BB  中轨 {middle:.2f}  上轨 {upper:.2f}  下轨 {lower:.2f}")
    print(f"    RSI: {rsi:.1f}")
    print(f"    价格 {current_price:.2f}  {'跌破下轨' if current_price < lower else '涨破上轨' if current_price > upper else '中轨区间'}")

    # 3. 查账户
    print(f"\n[3] 查富途模拟账户 {ACCOUNT_ID}...")
    t = OpenSecTradeContext(host='127.0.0.1', port=11111, is_encrypt=False)
    try:
        cash, pos = get_account_info(t)
        position_00700 = 0
        if len(pos) > 0:
            for _, row in pos.iterrows():
                if row.get("code") == CODE:
                    position_00700 = int(row.get("qty", 0) / LOT_SIZE)
        cash_available = float(cash.iloc[0].get("cash", 0)) if len(cash) > 0 else 0
        print(f"    现金 HK${cash_available:,.0f}  持仓 {position_00700} 手 ({position_00700 * LOT_SIZE} 股)")
    except Exception as e:
        print(f"    ❌ 查账户失败: {e}")
        t.close()
        return

    # 4. 生成信号
    signal = generate_signal(current_price, upper, lower, rsi, position_00700)
    print(f"\n[4] 信号: {signal}")

    # 5. 写 signal 到 db
    conn.execute("""
        INSERT INTO signals (ts, strategy, code, signal, price, close_price,
                              bb_upper, bb_lower, rsi, position, cash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), STRATEGY, CODE, signal, current_price,
          current_price, upper, lower, rsi, position_00700, cash_available))
    conn.commit()
    print(f"    ✓ 信号已记录")

    # 6. 下单（防重复：同一天同方向不重复）
    last_trade = state.get("last_trade_date")
    last_signal = state.get("last_signal")
    if last_trade == today and last_signal == signal:
        print(f"\n[6] 跳过下单（今天 {today} 已对 {signal} 下单）")
    elif signal == "HOLD":
        print(f"\n[6] HOLD — 不下单")
        state["last_trade_date"] = today
        state["last_signal"] = signal
        save_state(state)
    elif signal == "BUY":
        # 检查资金是否够 1 手
        if cash_available < current_price * LOT_SIZE * 1.001:
            print(f"\n[6] 资金不足: HK${cash_available:.0f} < HK${current_price * LOT_SIZE:.0f}")
        else:
            print(f"\n[6] 下单: 买入 {LOT_SIZE} 股 @ 市价")
            ret, data = place_order(t, "BUY", 1)
            if ret == RET_OK:
                order_id = str(data.iloc[0]["order_id"]) if len(data) > 0 else "?"
                print(f"    ✓ 下单成功 order_id={order_id}")
                conn.execute("""
                    INSERT INTO orders (ts, strategy, code, side, order_id, fill_price,
                                         fill_qty, status, msg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), STRATEGY, CODE, "BUY",
                      order_id, current_price, LOT_SIZE, "submitted", ""))
                conn.commit()
                state["last_trade_date"] = today
                state["last_signal"] = signal
                save_state(state)
            else:
                print(f"    ❌ 下单失败: {data}")
                conn.execute("""
                    INSERT INTO orders (ts, strategy, code, side, status, msg)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), STRATEGY, CODE, "BUY", "failed", str(data)))
                conn.commit()
    elif signal == "SELL":
        if position_00700 == 0:
            print(f"\n[6] 无持仓，不卖")
        else:
            print(f"\n[6] 下单: 卖出 {position_00700} 手 @ 市价")
            ret, data = place_order(t, "SELL", position_00700)
            if ret == RET_OK:
                order_id = str(data.iloc[0]["order_id"]) if len(data) > 0 else "?"
                print(f"    ✓ 下单成功 order_id={order_id}")
                conn.execute("""
                    INSERT INTO orders (ts, strategy, code, side, order_id, fill_price,
                                         fill_qty, status, msg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), STRATEGY, CODE, "SELL",
                      order_id, current_price, position_00700 * LOT_SIZE, "submitted", ""))
                conn.commit()
                state["last_trade_date"] = today
                state["last_signal"] = signal
                save_state(state)
            else:
                print(f"    ❌ 下单失败: {data}")
                conn.execute("""
                    INSERT INTO orders (ts, strategy, code, side, status, msg)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), STRATEGY, CODE, "SELL", "failed", str(data)))
                conn.commit()
    t.close()

    # 7. 记录 P&L
    print(f"\n[7] 记录 P&L...")
    avg_cost = 0.0
    if len(pos) > 0:
        for _, row in pos.iterrows():
            if row.get("code") == CODE:
                avg_cost = float(row.get("cost_price", 0))
    unrealized_pnl = 0.0
    if position_00700 > 0 and avg_cost > 0:
        unrealized_pnl = (current_price - avg_cost) * position_00700 * LOT_SIZE
    market_value = current_price * position_00700 * LOT_SIZE
    total_equity = cash_available + market_value
    print(f"    现金 HK${cash_available:,.0f}  持仓市值 HK${market_value:,.0f}")
    print(f"    平均成本 HK${avg_cost:.2f}  浮盈 HK${unrealized_pnl:,.0f}")
    print(f"    总权益 HK${total_equity:,.0f}")

    conn.execute("""
        INSERT INTO pnl (ts, strategy, code, cash, position, avg_cost, market_value,
                          unrealized_pnl, realized_pnl, total_equity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), STRATEGY, CODE, cash_available, position_00700,
          avg_cost, market_value, unrealized_pnl, 0, total_equity))
    conn.commit()
    print(f"    ✓ P&L 已记录")
    conn.close()

    print(f"\n{'='*70}")
    print(f"  完成。下次运行: HK 收盘后 (16:00+ HKT)")
    print(f"  数据库: {DB_PATH}")
    print(f"  状态:   {STATE_PATH}")


if __name__ == "__main__":
    main()
