"""
test_broker_futu.py — 用 mock 测试 BrokerFutu 的接口

不需要 OpenD 也能跑：
    cd quant-poc && python -m pytest tests/test_broker_futu.py -v
或：
    python tests/test_broker_futu.py
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.broker_futu import BrokerFutu  # noqa: E402


def make_ctx_mock():
    """构造一个假的 futu OpenSecTradeContext。"""
    ctx = MagicMock()

    # 模拟 place_order 立即返回 OK + order_id
    ctx.place_order.return_value = (0, pd.DataFrame([{"order_id": "FUTU-000001"}]))

    # 模拟 get_order_fill_list 第二次调用时返回成交
    call_count = {"n": 0}
    fill_df = pd.DataFrame([{
        "fill_id": "FILL-000001",
        "order_id": "FUTU-000001",
        "code": "SZ.002180",
        "price": 25.35,
        "qty": 500,
        "create_time": "2026-09-07 14:00:00",
    }])

    def fake_get_fill_list(order_id):
        call_count["n"] += 1
        if call_count["n"] < 2:
            return (0, pd.DataFrame())  # 第一次还没成交
        return (0, fill_df)

    ctx.get_order_fill_list.side_effect = fake_get_fill_list

    # 模拟 get_assets
    ctx.get_assets.return_value = (0, pd.DataFrame([{
        "cash": 873850.0,
        "market_val": 12650.0,
        "total_assets": 886500.0,
        "total_pl": -113500.0,
    }]))

    # 模拟 get_position_list
    ctx.get_position_list.return_value = (0, pd.DataFrame([{
        "code": "SZ.002180",
        "qty": 500,
        "cost_price": 25.30,
        "current_price": 27.50,
        "market_val": 13750.0,
        "unrealized_pl": 1100.0,
        "realized_pl": 0.0,
    }]))

    return ctx


def test_submit_success():
    """正常下单：等待 1 次轮询后返回成交。"""
    ctx = make_ctx_mock()
    broker = BrokerFutu(order_timeout_s=5.0, poll_interval_s=0.05)
    broker.ctx = ctx

    t0 = time.time()
    fill = broker.submit(
        event_id="test-001",
        symbol="002180.SZ",  # TV 风格
        action="buy",
        price=25.30,
        volume=500,
    )
    elapsed = time.time() - t0
    assert fill["orderid"] == "FUTU-000001"
    assert fill["price"] == 25.35
    assert fill["volume"] == 500
    assert elapsed < 1.0  # 只轮询了 1 次
    print(f"  ✓ test_submit_success  ({elapsed:.2f}s)")


def test_submit_vnpy_symbol():
    """vnpy 风格 symbol (.SZSE/.SSE) 也能正确转换。"""
    ctx = make_ctx_mock()
    broker = BrokerFutu()
    broker.ctx = ctx
    fill = broker.submit(event_id="test-002", symbol="688122.SSE",
                         action="buy", price=95.0, volume=200)
    # 检查传给 place_order 的 code 是 'SH.688122'
    call_args = ctx.place_order.call_args
    assert call_args.kwargs["code"] == "SH.688122", f"got {call_args.kwargs['code']}"
    print(f"  ✓ test_submit_vnpy_symbol")


def test_submit_unsupported_exchange():
    """不支持的交易所应抛错。"""
    ctx = make_ctx_mock()
    broker = BrokerFutu()
    broker.ctx = ctx
    try:
        broker.submit(event_id="test-bad", symbol="000001.NYSE",
                      action="buy", price=10, volume=100)
        print("  ✗ test_submit_unsupported_exchange  (应抛 ValueError)")
    except ValueError:
        print(f"  ✓ test_submit_unsupported_exchange  (正确拒绝)")


def test_submit_timeout():
    """订单超时应该撤单 + 抛 TimeoutError。"""
    ctx = make_ctx_mock()
    # 关键：清掉 make_ctx_mock 里的 side_effect，改用新的 mock（永远不成交）
    ctx.get_order_fill_list = MagicMock(return_value=(0, pd.DataFrame()))
    broker = BrokerFutu(order_timeout_s=0.5, poll_interval_s=0.05)
    broker.ctx = ctx

    try:
        broker.submit(event_id="test-timeout", symbol="000001.SZ",
                      action="buy", price=10, volume=100)
        assert False, "应该抛 TimeoutError 但没抛"
    except TimeoutError:
        # 应该调过撤单
        assert ctx.modify_order.called, "应调 modify_order 撤单"
        assert ctx.modify_order.call_args.kwargs["modify_order_op"] == "CANCEL"
        print(f"  ✓ test_submit_timeout  (撤单已调)")


def test_account_snapshot():
    """账户快照格式正确。"""
    ctx = make_ctx_mock()
    broker = BrokerFutu()
    broker.ctx = ctx
    acc = broker.account_snapshot()
    assert acc["cash"] == 873850.0
    assert acc["market_value"] == 12650.0
    assert acc["equity"] == 886500.0
    assert acc["total_pnl"] == -113500.0
    print(f"  ✓ test_account_snapshot")


def test_positions_snapshot():
    """持仓快照格式正确。"""
    ctx = make_ctx_mock()
    broker = BrokerFutu()
    broker.ctx = ctx
    pos = broker.positions_snapshot()
    assert len(pos) == 1
    assert pos[0]["symbol"] == "SZ.002180"
    assert pos[0]["volume"] == 500
    assert pos[0]["avg_price"] == 25.30
    print(f"  ✓ test_positions_snapshot")


def main():
    print("BrokerFutu mock 测试：\n")
    test_submit_success()
    test_submit_vnpy_symbol()
    test_submit_unsupported_exchange()
    test_submit_timeout()
    test_account_snapshot()
    test_positions_snapshot()
    print("\n✓ 6/6 测试通过")


if __name__ == "__main__":
    main()
