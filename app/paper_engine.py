"""
paper_engine.py — 极简 A股模拟撮合引擎
======================================

参考设计：
- vnpy 的 OrderRequest / TradeData / OrderData 对象（业界标准）
- PineFlow v6 的 paper ledger 设计（SQLite + 幂等 + 简单计算）

功能：
- 接收 OrderRequest（市价单，立即按 alarm 价格成交）
- 维护账户现金 + 持仓 dict
- 算已实现盈亏（P&L）
- 所有事件落 SQLite，便于审计

不在范围内（PoC 故意简化）：
- 不做撮合深度、滑点、T+1
- 不做部分成交（全部一次性成交或拒绝）
- 不做止损单、撤单
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from vnpy.trader.object import (
    Direction,
    Offset,
    OrderRequest,
    TradeData,
    OrderData,
    Exchange,
    OrderType,
    Status,
)
from vnpy.trader.utility import extract_vt_symbol


@dataclass
class Position:
    """单一 symbol 持仓。A股最少 100 股一手，price=平均成本。"""
    symbol: str          # vt_symbol like "000001.SZ"
    exchange: str
    volume: int = 0      # 正数=多，负数=空（支持双向持仓做演示）
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    def market_value(self, last_price: float) -> float:
        return self.volume * last_price

    def unrealized_pnl(self, last_price: float) -> float:
        if self.volume == 0 or self.avg_price == 0:
            return 0.0
        return self.volume * (last_price - self.avg_price)


class PaperEngine:
    """A 股模拟撮合。所有成交按 alert 价格立即发生。"""

    def __init__(self, db_path: Path, init_cash: float = 1_000_000.0):
        self.db_path = db_path
        self.init_cash = init_cash
        self.cash = init_cash
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.last_prices: dict[str, float] = {}    # symbol -> last seen price (for unrealized pnl)
        self.order_count = 0
        self.trade_count = 0
        self._init_db()

    # ---------- SQLite ----------
    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id    TEXT PRIMARY KEY,
                    secret      TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    exchange    TEXT,
                    price       REAL NOT NULL,
                    volume      INTEGER NOT NULL,
                    strategy    TEXT,
                    received_at TEXT NOT NULL,
                    raw_json    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    orderid     TEXT PRIMARY KEY,
                    event_id    TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    direction   TEXT NOT NULL,
                    offset      TEXT NOT NULL,
                    price       REAL NOT NULL,
                    volume      INTEGER NOT NULL,
                    status      TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                    tradeid     TEXT PRIMARY KEY,
                    orderid     TEXT NOT NULL,
                    event_id    TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    direction   TEXT NOT NULL,
                    offset      TEXT NOT NULL,
                    price       REAL NOT NULL,
                    volume      INTEGER NOT NULL,
                    traded_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    taken_at    TEXT PRIMARY KEY,
                    cash        REAL NOT NULL,
                    market_value REAL NOT NULL,
                    realized_pnl REAL NOT NULL
                );
            """)

    # ---------- 主流程 ----------
    def event_exists(self, event_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
            return row is not None

    def record_event(
        self,
        *,
        event_id: str,
        secret: str,
        action: str,
        symbol: str,
        exchange: str,
        price: float,
        volume: int,
        strategy: Optional[str],
        received_at: str,
        raw_json: str,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO events
                   (event_id, secret, action, symbol, exchange, price, volume,
                    strategy, received_at, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, secret, action, symbol, exchange, price, volume,
                 strategy, received_at, raw_json),
            )

    def submit(
        self,
        *,
        event_id: str,
        symbol: str,
        action: str,        # "buy" / "sell"
        price: float,
        volume: int,
        strategy: Optional[str] = None,
    ) -> TradeData:
        """
        立即按 price 撮合（市价单模拟）。
        返回成交对象。
        """
        if volume <= 0:
            raise ValueError(f"volume must be > 0, got {volume}")
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")
        if action not in ("buy", "sell"):
            raise ValueError(f"action must be 'buy' or 'sell', got {action!r}")

        # vnpy 对象：交易所从 vt_symbol 推断
        vt_symbol = symbol  # 形式 "000001.SZ"
        try:
            sym, ex = extract_vt_symbol(vt_symbol)
        except Exception:
            # fallback: 假设 SSE/SZSE 二选一，简单按后缀
            if vt_symbol.endswith(".SZ"):
                sym, ex = vt_symbol[:-3], Exchange.SZSE
            elif vt_symbol.endswith(".SH"):
                sym, ex = vt_symbol[:-3], Exchange.SSE
            else:
                sym, ex = vt_symbol, Exchange.SSE

        is_buy = action == "buy"
        direction = Direction.LONG if is_buy else Direction.SHORT
        offset = Offset.OPEN  # 简化：不区分开/平，仓位允许做反向

        self.order_count += 1
        # 用纳秒时间戳做前缀，避免重启进程后 order_count 归零导致 UNIQUE 冲突
        from datetime import datetime as _dt
        orderid = f"PAPER-{int(_dt.now().timestamp() * 1_000_000)}-{self.order_count:06d}"

        # 写订单
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO orders (orderid, event_id, symbol, direction, offset,
                                       price, volume, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (orderid, event_id, vt_symbol,
                 direction.value, offset.value,
                 price, volume, Status.ALLTRADED.value, now),
            )

        # 更新持仓 + 现金
        pos = self.positions.setdefault(vt_symbol, Position(symbol=vt_symbol, exchange=ex.value))
        prev_volume = pos.volume
        prev_avg = pos.avg_price

        if is_buy:
            new_volume = prev_volume + volume
            # 加权平均成本
            if new_volume != 0:
                pos.avg_price = (prev_volume * prev_avg + volume * price) / new_volume
            pos.volume = new_volume
            self.cash -= price * volume
        else:
            new_volume = prev_volume - volume
            # 平仓或开空时算已实现 P&L
            if prev_volume > 0 and volume <= prev_volume:
                # 平多头 → P&L = (sell_price - avg_cost) * volume
                pos.realized_pnl += (price - prev_avg) * volume
            elif prev_volume < 0 and volume <= -prev_volume:
                # 平空头 → P&L = (avg_cost - sell_price) * volume
                pos.realized_pnl += (prev_avg - price) * volume
            pos.volume = new_volume
            self.cash += price * volume

        self.last_prices[vt_symbol] = price

        # 写成交（tradeid 同样加纳秒前缀）
        self.trade_count += 1
        tradeid = f"TRADE-{int(datetime.now().timestamp() * 1_000_000)}-{self.trade_count:06d}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO trades (tradeid, orderid, event_id, symbol, direction,
                                       offset, price, volume, traded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tradeid, orderid, event_id, vt_symbol,
                 direction.value, offset.value,
                 price, volume, now),
            )

        trade = TradeData(
            symbol=sym,
            exchange=ex,
            orderid=orderid,
            tradeid=tradeid,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            datetime=datetime.fromisoformat(now),
            gateway_name="PAPER",
        )
        return trade

    # ---------- 查询 ----------
    def positions_snapshot(self) -> list[dict]:
        out = []
        for sym, pos in self.positions.items():
            if pos.volume == 0:
                continue
            last = self.last_prices.get(sym, pos.avg_price)
            out.append({
                "symbol": sym,
                "exchange": pos.exchange,
                "volume": pos.volume,
                "avg_price": round(pos.avg_price, 4),
                "last_price": round(last, 4),
                "market_value": round(pos.market_value(last), 2),
                "unrealized_pnl": round(pos.unrealized_pnl(last), 2),
                "realized_pnl": round(pos.realized_pnl, 2),
            })
        return out

    def account_snapshot(self) -> dict:
        market_value = 0.0
        for sym, pos in self.positions.items():
            if pos.volume == 0:
                continue
            last = self.last_prices.get(sym, pos.avg_price)
            market_value += pos.market_value(last)
        return {
            "cash": round(self.cash, 2),
            "market_value": round(market_value, 2),
            "equity": round(self.cash + market_value, 2),
            "init_cash": self.init_cash,
            "total_pnl": round(self.cash + market_value - self.init_cash, 2),
        }

    def recent_trades(self, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT tradeid, orderid, event_id, symbol, direction, offset,
                          price, volume, traded_at
                   FROM trades ORDER BY traded_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "tradeid": r[0], "orderid": r[1], "event_id": r[2],
                "symbol": r[3], "direction": r[4], "offset": r[5],
                "price": r[6], "volume": r[7], "traded_at": r[8],
            }
            for r in rows
        ]

    def recent_events(self, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT event_id, action, symbol, price, volume, strategy,
                          received_at
                   FROM events ORDER BY received_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "event_id": r[0], "action": r[1], "symbol": r[2],
                "price": r[3], "volume": r[4],
                "strategy": r[5], "received_at": r[6],
            }
            for r in rows
        ]
