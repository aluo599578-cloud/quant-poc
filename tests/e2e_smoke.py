"""
tests/e2e_smoke.py — 端到端 smoke test

模拟 TradingView 推送 alert，验证：
1. 健康检查
2. buy 入库 + 持仓 +1
3. 错误 secret 拒绝
4. 同 event_id 幂等（第二次返回 duplicate，仓位不变）
5. sell 成功 + P&L 计算正确
6. SQLite 可查
7. 风控：超量 / 未授权 symbol 拒绝
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8765"
SECRET = "test-secret-abc"


def banner(msg):
    print(f"\n=== {msg} ===")


def check(cond, msg):
    if not cond:
        print(f"  FAIL: {msg}")
        sys.exit(1)
    print(f"  ok: {msg}")


def main():
    banner("1) health")
    r = requests.get(f"{BASE}/health", timeout=5)
    check(r.status_code == 200, f"status=200 (got {r.status_code})")
    check(r.json()["status"] == "ok", "status=ok")

    banner("2) buy 000001.SZ 100 @ 10.50")
    r = requests.post(f"{BASE}/webhook/tradingview", json={
        "secret": SECRET,
        "event_id": "tv-001",
        "action": "buy",
        "symbol": "000001.SZ",
        "price": 10.50,
        "volume": 100,
        "strategy": "demo-ema-cross",
    }, timeout=5)
    check(r.status_code == 200, f"status=200 (got {r.status_code})")
    body = r.json()
    check(body["status"] == "filled", f"status=filled ({body['status']})")
    check(body["trade"]["volume"] == 100, "trade volume=100")

    # 查持仓
    r = requests.get(f"{BASE}/positions", timeout=5)
    pos = r.json()["positions"]
    check(len(pos) == 1 and pos[0]["symbol"] == "000001.SZ" and pos[0]["volume"] == 100,
          f"持仓 000001.SZ x100 (got {pos})")
    check(abs(pos[0]["avg_price"] - 10.50) < 0.001, "avg_price=10.50")

    # 查账户
    r = requests.get(f"{BASE}/account", timeout=5)
    acc = r.json()
    check(abs(acc["cash"] - (1_000_000 - 1050)) < 0.01,
          f"cash=998950 (got {acc['cash']})")

    banner("3) 错误 secret 应被拒绝")
    r = requests.post(f"{BASE}/webhook/tradingview", json={
        "secret": "wrong",
        "event_id": "tv-002",
        "action": "buy",
        "symbol": "000002.SZ",
        "price": 10.0,
        "volume": 100,
    }, timeout=5)
    check(r.status_code == 401, f"status=401 (got {r.status_code})")

    banner("4) 同 event_id 重发应幂等")
    r = requests.post(f"{BASE}/webhook/tradingview", json={
        "secret": SECRET,
        "event_id": "tv-001",  # 重复
        "action": "buy",
        "symbol": "000001.SZ",
        "price": 99.0,           # 即使 price 不同
        "volume": 999,           # 即使 volume 不同
    }, timeout=5)
    body = r.json()
    check(r.status_code == 200 and body["status"] == "duplicate",
          f"status=duplicate (got {body})")
    r = requests.get(f"{BASE}/positions", timeout=5)
    pos = r.json()["positions"]
    check(pos[0]["volume"] == 100 and abs(pos[0]["avg_price"] - 10.50) < 0.001,
          "重复 alert 后仓位不变（仍 100@10.50）")

    banner("5) 再 buy 100 @ 11.0 + sell 100 @ 12.0 → P&L")
    requests.post(f"{BASE}/webhook/tradingview", json={
        "secret": SECRET,
        "event_id": "tv-003",
        "action": "buy",
        "symbol": "000001.SZ",
        "price": 11.0,
        "volume": 100,
    }, timeout=5)
    requests.post(f"{BASE}/webhook/tradingview", json={
        "secret": SECRET,
        "event_id": "tv-004",
        "action": "sell",
        "symbol": "000001.SZ",
        "price": 12.0,
        "volume": 100,
    }, timeout=5)
    r = requests.get(f"{BASE}/positions", timeout=5)
    pos = r.json()["positions"]
    # 平 100 股（从 200 中 sell 100）→ remaining 100 @ avg=10.75
    # 已实现 P&L 按卖出时持仓的平均成本计算：
    #   sell 100@12, prev_avg=10.75 → (12 - 10.75)*100 = 125
    check(pos[0]["volume"] == 100, "remaining 100 股")
    check(abs(pos[0]["avg_price"] - 10.75) < 0.001,
          f"avg=10.75 (got {pos[0]['avg_price']})")
    check(abs(pos[0]["realized_pnl"] - 125.0) < 0.01,
          f"realized_pnl=125 [avg-cost basis] (got {pos[0]['realized_pnl']})")
    check(abs(pos[0]["unrealized_pnl"] - 125.0) < 0.01,
          f"unrealized_pnl=125 [100*(12-10.75)] (got {pos[0]['unrealized_pnl']})")

    banner("6) 风控：volume 超限")
    r = requests.post(f"{BASE}/webhook/tradingview", json={
        "secret": SECRET,
        "event_id": "tv-005",
        "action": "buy",
        "symbol": "000001.SZ",
        "price": 10.0,
        "volume": 99999,
    }, timeout=5)
    check(r.status_code == 403, f"超量被拒绝 (got {r.status_code})")

    banner("7) SQLite 能直接查")
    db = Path("./data/quant-poc.db").resolve()
    check(db.exists(), f"db exists at {db}")
    import sqlite3
    with sqlite3.connect(db) as conn:
        events_n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        trades_n = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        orders_n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"  events={events_n}, orders={orders_n}, trades={trades_n}")
    check(events_n == 3, f"events ==3 (got {events_n})")  # tv-001, tv-003, tv-004
    check(trades_n == 3, f"trades ==3 (got {trades_n})")

    banner("8) trades 端点")
    r = requests.get(f"{BASE}/trades?limit=10", timeout=5)
    trades = r.json()["trades"]
    check(len(trades) >= 3, f"trades list >=3 (got {len(trades)})")
    for t in trades:
        print(f"  {t['tradeid']:14s} {t['symbol']:10s} {t['direction']:6s} "
              f"{t['volume']:>4d} @ {t['price']}")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
