"""
broker_futu.py — 富途券商适配器（实盘/模拟）
============================================

跟 PaperEngine 同接口，逻辑上替换 paper 即可从模拟切到实盘。
- 默认 TrdEnv.SIMULATE（模拟盘，安全）
- 设环境变量 BROKER_FUTU_TRD_ENV=REAL 切真实账户（生产用）

⚠️ 实盘前必读 docs/FUTU_INTEGRATION.md

依赖：
- futu-api >= 10.4.6408
- OpenD-GUI 在跑（市场时段内，地址 127.0.0.1:11111）
- 量化交易权限已开通 + 交易密码已解锁
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from futu import (
    OpenSecTradeContext,
    OrderType,
    TrdSide,
    TrdEnv,
    RET_OK,
)


log = logging.getLogger(__name__)


class BrokerFutu:
    """富途券商适配器。

    接口与 PaperEngine.submit / account_snapshot / positions_snapshot 一致。
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        trd_env=None,
        order_timeout_s: float = 30.0,
        poll_interval_s: float = 0.5,
    ):
        if trd_env is None:
            trd_env = "SIMULATE"
        self.host = host
        self.port = port
        self.trd_env = trd_env
        self.order_timeout_s = order_timeout_s
        self.poll_interval_s = poll_interval_s
        self.ctx: Optional[OpenSecTradeContext] = None
        log.info(f"BrokerFutu configured for OpenD at {host}:{port}, trd_env={self.trd_env}")

    def _ensure_ctx(self):
        """延迟建 OpenSecTradeContext（避免测试时无谓重连）。"""
        if self.ctx is None:
            log.info(f"Connecting to OpenD at {self.host}:{self.port}")
            self.ctx = OpenSecTradeContext(host=self.host, port=self.port)
        return self.ctx

    # -------- 主接口 --------
    def submit(
        self,
        *,
        event_id: str,
        symbol: str,
        action: str,
        price: float,
        volume: int,
        strategy: Optional[str] = None,
    ) -> dict:
        """
        向富途提交订单。同步等待成交。

        Returns:
            {"tradeid": ..., "orderid": ..., "price": float, "volume": int, ...}
        """
        if action not in ("buy", "sell"):
            raise ValueError(f"action must be buy/sell, got {action!r}")
        if volume <= 0 or price <= 0:
            raise ValueError("volume/price must be > 0")

        futu_code = self._to_futu_code(symbol)
        trd_side = TrdSide.BUY if action == "buy" else TrdSide.SELL

        log.info(f"[{event_id}] 下单 {futu_code} {action} {volume} @ market "
                 f"(ref_price={price}, strategy={strategy})")

        ctx = self._ensure_ctx()
        # 下市价单（price 仍需传，futurn 用作参考价）
        ret, data = ctx.place_order(
            price=price,
            qty=volume,
            code=futu_code,
            trd_side=trd_side,
            order_type=OrderType.MARKET,
            trd_env=self.trd_env,
            remark=f"quant-poc:{event_id}",
        )
        if ret != RET_OK:
            raise RuntimeError(f"下单失败: {data}")

        order_id = str(data.iloc[0]["order_id"])
        log.info(f"[{event_id}] 已下单, order_id={order_id}")

        # 轮询等待成交
        t0 = time.time()
        while time.time() - t0 < self.order_timeout_s:
            ret, fill_data = ctx.get_order_fill_list(order_id=order_id)
            if ret == RET_OK and not fill_data.empty:
                fill = fill_data.iloc[0]
                return {
                    "tradeid": str(fill["fill_id"]),
                    "orderid": order_id,
                    "price": float(fill["price"]),
                    "volume": int(fill["qty"]),
                    "traded_at": str(fill["create_time"]),
                    "event_id": event_id,
                }
            time.sleep(self.poll_interval_s)

        # 超时：撤单 + 抛错
        log.warning(f"[{event_id}] {order_id} {self.order_timeout_s}s 内未成交，撤单")
        try:
            ctx.modify_order(modify_order_op="CANCEL", order_id=order_id,
                             trd_env=self.trd_env)
        except Exception as e:
            log.error(f"撤单失败: {e}")
        raise TimeoutError(
            f"订单 {order_id} ({futu_code} {action} {volume}) "
            f"{self.order_timeout_s}s 内未成交"
        )

    def account_snapshot(self) -> dict:
        ctx = self._ensure_ctx()
        ret, data = ctx.get_assets(trd_env=self.trd_env)
        if ret != RET_OK or data is None or data.empty:
            log.error(f"get_assets 失败: {data}")
            return {}
        row = data.iloc[0]
        return {
            "cash": float(row.get("cash", 0)),
            "market_value": float(row.get("market_val", 0)),
            "equity": float(row.get("total_assets", 0)),
            "init_cash": float(row.get("total_assets", 0)) - float(row.get("total_pl", 0)),
            "total_pnl": float(row.get("total_pl", 0)),
        }

    def positions_snapshot(self) -> list[dict]:
        ctx = self._ensure_ctx()
        ret, data = ctx.get_position_list(trd_env=self.trd_env)
        if ret != RET_OK or data is None or data.empty:
            return []
        out = []
        for _, row in data.iterrows():
            out.append({
                "symbol": str(row["code"]),
                "volume": int(row["qty"]),
                "avg_price": float(row.get("cost_price", 0)),
                "last_price": float(row.get("current_price", 0)),
                "market_value": float(row.get("market_val", 0)),
                "unrealized_pnl": float(row.get("unrealized_pl", 0)),
                "realized_pnl": float(row.get("realized_pl", 0)),
            })
        return out

    def close(self):
        try:
            self.ctx.close()
        except Exception as e:
            log.warning(f"close ctx error: {e}")

    # -------- 工具 --------
    @staticmethod
    def _to_futu_code(vt_symbol: str) -> str:
        """
        vnpy 风格 → 富途风格
        002180.SZSE → 'SZ.002180'
        688122.SSE  → 'SH.688122'
        002180.SZ   → 'SZ.002180'  (兼容 TV 风格)
        """
        code, exch = vt_symbol.upper().split(".")
        if exch in ("SZSE", "SZ"):
            return f"SZ.{code}"
        elif exch in ("SSE", "SH"):
            return f"SH.{code}"
        raise ValueError(f"unsupported exchange: {exch}")


def from_env() -> BrokerFutu:
    """从环境变量构造 BrokerFutu（生产用）。"""
    return BrokerFutu(
        host=os.environ.get("FUTU_HOST", "127.0.0.1"),
        port=int(os.environ.get("FUTU_PORT", "11111")),
        trd_env=("REAL" if os.environ.get("BROKER_FUTU_TRD_ENV", "SIMULATE").upper() == "REAL"
                 else "SIMULATE"),
    )
