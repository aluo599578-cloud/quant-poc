"""
webhook_gateway.py — TradingView → PaperEngine 网关
==================================================

参考：PineFlow v6 的设计思路（FastAPI + secret + 幂等 + SQLite + 风控）
替换：把 broker 适配器换成我们的 PaperEngine（A 股模拟撮合）

端点：
- POST /webhook/tradingview   接收 TV alert
- GET  /health                健康检查
- GET  /account               账户概览（现金、市值、P&L）
- GET  /positions             持仓列表
- GET  /trades?limit=50       成交明细
- GET  /events?limit=50       收到的原始 alert

TradingView alert message JSON 格式：
{
    "secret":  "your-shared-secret",
    "event_id":"tv-alert-2026-09-07-000001-001",
    "action":  "buy",
    "symbol":  "000001.SZ",          # vt_symbol: <code>.<exchange>
    "price":   12.34,
    "volume":  100,
    "strategy":"my-strategy-name",    # 可选
    "note":    "free-form text"       # 可选
}
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .paper_engine import PaperEngine

# ---- 配置 ----
WEBHOOK_SECRET = os.environ.get("QPOC_SECRET", "dev-secret-change-me")
ALLOWED_SYMBOLS = set(
    os.environ.get("QPOC_ALLOWED_SYMBOLS", "").split(",")
) - {""}  # 空集合 = 不限制
MAX_VOLUME = int(os.environ.get("QPOC_MAX_VOLUME", "10000"))
DAILY_ORDER_LIMIT = int(os.environ.get("QPOC_DAILY_LIMIT", "100"))
DB_PATH = Path(os.environ.get("QPOC_DB", "./data/quant-poc.db"))

# ---- App ----
app = FastAPI(title="Quant-PoC Webhook Gateway", version="0.1.0")
engine = PaperEngine(db_path=DB_PATH)


# ---- Pydantic 模型 ----
class TVAlert(BaseModel):
    secret: str
    event_id: str = Field(..., min_length=1, max_length=200)
    action: str = Field(..., pattern="^(buy|sell)$")
    symbol: str = Field(..., min_length=4, max_length=20)
    price: float = Field(..., gt=0)
    volume: int = Field(..., gt=0)
    strategy: Optional[str] = None
    note: Optional[str] = None


# ---- 工具 ----
def _check_secret(provided: str) -> None:
    if provided != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid secret")


def _check_symbol(symbol: str) -> None:
    if not ALLOWED_SYMBOLS:
        return
    if symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=403,
            detail=f"symbol {symbol!r} not in whitelist",
        )


def _check_volume(volume: int) -> None:
    if volume > MAX_VOLUME:
        raise HTTPException(
            status_code=403,
            detail=f"volume {volume} exceeds limit {MAX_VOLUME}",
        )


def _check_daily_limit() -> None:
    today = datetime.now().date().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM events WHERE received_at LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]
    if n >= DAILY_ORDER_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"daily order limit reached ({DAILY_ORDER_LIMIT})",
        )


# ---- 端点 ----
@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "paper",
        "version": app.version,
        "time": datetime.now().isoformat(timespec="seconds"),
    }


@app.post("/webhook/tradingview")
async def webhook(alert: TVAlert, request: Request):
    # 1) 校验
    _check_secret(alert.secret)
    _check_symbol(alert.symbol)
    _check_volume(alert.volume)
    _check_daily_limit()

    # 2) 兼容两种 vt_symbol 格式：
    #    - TradingView 风格: 002180.SZ / 600000.SH
    #    - vnpy 风格:      002180.SZSE / 600000.SSE
    # vnpy PaperEngine.submit 内部 extract_vt_symbol 能处理两种
    symbol = alert.symbol.upper()

    # 3) 幂等检查
    if engine.event_exists(alert.event_id):
        return {
            "status": "duplicate",
            "event_id": alert.event_id,
            "detail": "event already processed, no change applied",
        }

    # 4) 记录原始 alert
    now = datetime.now().isoformat(timespec="seconds")
    raw = json.dumps(alert.model_dump(), ensure_ascii=False)
    engine.record_event(
        event_id=alert.event_id,
        secret=alert.secret,
        action=alert.action,
        symbol=symbol,
        exchange=symbol.split(".")[-1] if "." in symbol else "",
        price=alert.price,
        volume=alert.volume,
        strategy=alert.strategy,
        received_at=now,
        raw_json=raw,
    )

    # 5) 撮合
    trade = engine.submit(
        event_id=alert.event_id,
        symbol=symbol,
        action=alert.action,
        price=alert.price,
        volume=alert.volume,
        strategy=alert.strategy,
    )

    return {
        "status": "filled",
        "event_id": alert.event_id,
        "trade": {
            "tradeid": trade.tradeid,
            "orderid": trade.orderid,
            "symbol": f"{trade.symbol}.{trade.exchange.value}",
            "direction": trade.direction.value,
            "price": trade.price,
            "volume": trade.volume,
        },
        "account": engine.account_snapshot(),
    }


@app.get("/account")
def account():
    return engine.account_snapshot()


@app.get("/positions")
def positions():
    return {"positions": engine.positions_snapshot()}


@app.get("/trades")
def trades(limit: int = 50):
    return {"trades": engine.recent_trades(limit)}


@app.get("/events")
def events(limit: int = 50):
    return {"events": engine.recent_events(limit)}
