"""
push_demo_alerts.py — 真实推 alert 进 webhook gateway（模拟 TradingView）
=====================================================================

会真的写入 SQLite，dashboard 的 Tab4 就能看到数据。
用 TradingView 风格 vt_symbol（.SZ/.SH），更接近真实场景。
"""
import json
import time
from datetime import datetime
import requests

BASE = "http://127.0.0.1:8765"
SECRET = "test-secret-abc"


def push(action, symbol, price, volume, evt_id, strategy="dashboard-demo", note=""):
    payload = {
        "secret": SECRET,
        "event_id": evt_id,
        "action": action,
        "symbol": symbol,
        "price": price,
        "volume": volume,
        "strategy": strategy,
        "note": note,
    }
    r = requests.post(f"{BASE}/webhook/tradingview", json=payload, timeout=5)
    print(f"  {evt_id:18s} {action:4s} {symbol:12s} {volume:>5d} @ {price:>7.2f} "
          f"→ {r.json().get('status')} {r.json().get('detail', '')}")
    return r.json()


def main():
    print("推 8 条 alert 到 webhook gateway（覆盖 3 只 A 股，TradingView 风格 .SZ/.SH）\n")

    # 1. 002180 纳思达 - 开仓
    push("buy", "002180.SZ", 25.30, 500, "tv-20260907-001", "ema-cross-5-30")
    time.sleep(0.3)
    # 2. 加仓
    push("buy", "002180.SZ", 26.10, 300, "tv-20260907-002", "ema-cross-5-30")
    time.sleep(0.3)

    # 3. 688122 西部超导 - 开仓
    push("buy", "688122.SH", 95.00, 200, "tv-20260907-003", "trend-following")
    time.sleep(0.3)
    # 4. 加仓
    push("buy", "688122.SH", 92.50, 100, "tv-20260907-004", "trend-following")
    time.sleep(0.3)

    # 5. 000100 TCL 科技 - 开仓
    push("buy", "000100.SZ", 5.20, 2000, "tv-20260907-005", "value-investing")
    time.sleep(0.3)

    # 6. 002180 减仓（部分平仓 - 验证 P&L）
    push("sell", "002180.SZ", 27.50, 300, "tv-20260907-006", "take-profit")
    time.sleep(0.3)

    # 7. 688122 减仓（部分平仓 - 验证 P&L）
    push("sell", "688122.SH", 98.50, 150, "tv-20260907-007", "take-profit")
    time.sleep(0.3)

    # 8. 测试幂等（同 event_id 重发）
    print("\n测试幂等（同 event_id 重发应返回 duplicate）：")
    push("buy", "002180.SZ", 99.99, 999, "tv-20260907-001", "duplicate-test")

    # 9. 测试错 secret
    print("\n测试错误 secret 应被拒绝：")
    r = requests.post(f"{BASE}/webhook/tradingview", json={
        "secret": "wrong", "event_id": "tv-bad", "action": "buy",
        "symbol": "002180.SZ", "price": 10.0, "volume": 100,
    }, timeout=5)
    print(f"  错 secret → HTTP {r.status_code} {r.json()}")

    # 10. 看最终账户
    print("\n最终账户快照：")
    r = requests.get(f"{BASE}/account", timeout=5)
    print(f"  {json.dumps(r.json(), ensure_ascii=False, indent=2)}")
    r = requests.get(f"{BASE}/positions", timeout=5)
    print(f"  持仓：{json.dumps(r.json(), ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
