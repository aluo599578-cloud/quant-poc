"""
quant_core.py — 量化研究核心逻辑（无 MCP 依赖）
==============================================

跟 mcp_quant_server.py 共享核心函数，区别：
- 本文件不导入 fastmcp，可被任何 Python 脚本直接 import
- mcp_quant_server.py 引用本文件加 @mcp.tool() 装饰
- OpenClaw 插件 / CLI / 测试也引用本文件

API：
    _run_backtest_core(vt_symbol, start, end, capital, strategy_type, params) -> dict
    _normalize_vt_symbol(vt_symbol) -> str
    _add_strategy_to_engine(engine, strategy_type, params) -> None
    run_walk_forward_core(...) -> dict
    simulate_stop_loss_core(...) -> dict
"""
from __future__ import annotations

import contextlib
import sys
from datetime import datetime
from itertools import product
from typing import Optional

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

from backtest_3stocks import (
    fetch_kline, make_bars, to_tushare_code,
    START as DEFAULT_START, END as DEFAULT_END, INIT_CAPITAL,
)
from backtest_scan import DoubleMaWithTrendFilter
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy


def _normalize_vt_symbol(vt_symbol: str) -> str:
    """把 TV 风格 (.SZ/.SH) 标准化为 vnpy 风格 (.SZSE/.SSE)。"""
    if "." not in vt_symbol:
        raise ValueError(f"vt_symbol 缺交易所后缀: {vt_symbol!r}")
    code, exch = vt_symbol.upper().split(".", 1)
    if exch == "SZ":
        return f"{code}.SZSE"
    elif exch in ("SSE", "SH"):
        return f"{code}.SSE"
    elif exch in ("SZSE", "SHSE"):
        return vt_symbol.upper()
    raise ValueError(f"不支持的交易所: {exch!r} (支持 .SZ/.SZSE/.SH/.SSE)")


def _add_strategy_to_engine(engine, strategy_type: str, params: dict) -> None:
    """根据 strategy_type 给 engine 加策略。"""
    if strategy_type == "double_ma":
        engine.add_strategy(DoubleMaStrategy, {
            "fast_window": params.get("fast_window", 5),
            "slow_window": params.get("slow_window", 30),
        })
    elif strategy_type == "double_ma_trend":
        engine.add_strategy(DoubleMaWithTrendFilter, {
            "fast_window": params.get("fast_window", 5),
            "slow_window": params.get("slow_window", 30),
            "trend_window": params.get("trend_window", 200),
        })
    elif strategy_type == "atr_rsi":
        from vnpy_ctastrategy.strategies.atr_rsi_strategy import AtrRsiStrategy
        engine.add_strategy(AtrRsiStrategy, {
            "atr_window": params.get("atr_window", 14),
            "atr_ma_window": params.get("atr_ma_window", 4),
            "rsi_window": params.get("rsi_window", 14),
            "rsi_signal": params.get("rsi_signal", 20),
        })
    elif strategy_type == "boll_channel":
        from vnpy_ctastrategy.strategies.boll_channel_strategy import BollChannelStrategy
        engine.add_strategy(BollChannelStrategy, {
            "boll_window": params.get("boll_window", 18),
            "boll_dev": params.get("boll_dev", 3.4),
        })
    elif strategy_type == "king_keltner":
        from vnpy_ctastrategy.strategies.king_keltner_strategy import KingKeltnerStrategy
        engine.add_strategy(KingKeltnerStrategy, {
            "keltner_window": params.get("keltner_window", 14),
            "keltner_dev": params.get("keltner_dev", 1.2),
        })
    else:
        raise ValueError(
            f"未知策略: {strategy_type!r}。"
            f"支持: double_ma, double_ma_trend, atr_rsi, boll_channel, king_keltner"
        )


def _to_native(x):
    """numpy 类型 → Python 原生（json 序列化兼容）"""
    import numpy as np
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def _run_backtest_core(vt_symbol: str, start: str, end: str,
                       capital: float, strategy_type: str = "double_ma",
                       params: Optional[dict] = None) -> dict:
    """核心回测逻辑。返回扁平 dict。

    包一层 stdout→stderr 重定向，因为 vnpy 内部用 print() 输出大量 INFO，
    在 stdio MCP 模式下会污染 JSON-RPC 协议导致 UnicodeDecodeError。
    """
    if params is None:
        params = {}
    vt_symbol = _normalize_vt_symbol(vt_symbol)
    df = fetch_kline(to_tushare_code(vt_symbol), start, end)
    bars = make_bars(df, vt_symbol)

    with contextlib.redirect_stdout(sys.stderr):
        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol=vt_symbol, interval=Interval.DAILY,
            start=datetime.fromisoformat(start), end=datetime.fromisoformat(end),
            rate=0.0003, slippage=0.01, size=100, pricetick=0.01, capital=capital,
        )
        _add_strategy_to_engine(engine, strategy_type, params)
        engine.history_data = list(bars)
        engine.run_backtesting()
        engine.calculate_result()
        s = engine.calculate_statistics()
    return {
        "symbol": vt_symbol,
        "strategy": strategy_type,
        "params": params,
        "total_return": _to_native(s.get("total_return", 0)),
        "annual_return": _to_native(s.get("annual_return", 0)),
        "sharpe_ratio": _to_native(s.get("sharpe_ratio", 0)),
        "max_ddpercent": _to_native(s.get("max_ddpercent", 0)),
        "max_drawdown": _to_native(s.get("max_drawdown", 0)),
        "total_trade_count": _to_native(s.get("total_trade_count", 0)),
        "profit_days": _to_native(s.get("profit_days", 0)),
        "total_days": _to_native(s.get("total_days", 1)),
        "end_balance": _to_native(s.get("end_balance", 0)),
        "n_bars": len(bars),
        "start": start, "end": end,
    }


def run_walk_forward_core(
    symbol: str,
    strategy_type: str,
    params: dict,
    train_start: str, train_end: str,
    test_start: str, test_end: str,
    capital: float = 1_000_000.0,
) -> dict:
    """Walk-Forward 验证：train 段跑 + test 段跑，对比 Sharpe 衰减判定过拟合。"""
    if params is None:
        params = {}

    train_stats = _run_backtest_core(
        vt_symbol=symbol, start=train_start, end=train_end, capital=capital,
        strategy_type=strategy_type, params=params,
    )
    if "error" in train_stats:
        return {"error": f"train 段失败: {train_stats['error']}"}

    test_stats = _run_backtest_core(
        vt_symbol=symbol, start=test_start, end=test_end, capital=capital,
        strategy_type=strategy_type, params=params,
    )
    if "error" in test_stats:
        return {"error": f"test 段失败: {test_stats['error']}"}

    train_sharpe = float(train_stats["sharpe_ratio"])
    test_sharpe = float(test_stats["sharpe_ratio"])
    sharpe_drop = train_sharpe - test_sharpe
    sharpe_drop_pct = (sharpe_drop / train_sharpe * 100) if train_sharpe != 0 else float("inf")

    if test_sharpe <= 0:
        verdict = "🔴 OVERFITTED（test 段 Sharpe ≤ 0）"
    elif sharpe_drop_pct > 50:
        verdict = "🟠 MODERATE OVERFIT（Sharpe 掉 > 50%）"
    elif sharpe_drop_pct > 20:
        verdict = "🟡 轻微过拟合（Sharpe 掉 20-50%）"
    else:
        verdict = "🟢 ROBUST（Sharpe 衰减 < 20%）"

    return {
        "symbol": symbol,
        "strategy_type": strategy_type,
        "params": params,
        "train": {
            "start": train_start, "end": train_end,
            "total_return": train_stats["total_return"],
            "annual_return": train_stats["annual_return"],
            "sharpe_ratio": train_sharpe,
            "max_ddpercent": train_stats["max_ddpercent"],
            "trade_count": train_stats["total_trade_count"],
        },
        "test": {
            "start": test_start, "end": test_end,
            "total_return": test_stats["total_return"],
            "annual_return": test_stats["annual_return"],
            "sharpe_ratio": test_sharpe,
            "max_ddpercent": test_stats["max_ddpercent"],
            "trade_count": test_stats["total_trade_count"],
        },
        "overfit_analysis": {
            "sharpe_drop": round(sharpe_drop, 3),
            "sharpe_drop_pct": round(sharpe_drop_pct, 1),
            "verdict": verdict,
        },
        "note": "train/test 段都用同一组参数。如果 test 段表现差说明过拟合，建议换参数或换股票。",
    }


def simulate_stop_loss_core(
    symbol: str, stop_loss_pct: float,
    fast_window: int, slow_window: int, use_trend_filter: bool,
    start: str, end: str, capital: float,
) -> dict:
    """stop loss 效果估算。"""
    base = _run_backtest_core(
        vt_symbol=symbol, start=start, end=end, capital=capital,
        strategy_type="double_ma_trend" if use_trend_filter else "double_ma",
        params={"fast_window": fast_window, "slow_window": slow_window},
    )
    if "error" in base:
        return base

    base_max_dd = abs(float(base["max_ddpercent"]))
    if base_max_dd > stop_loss_pct:
        estimated_dd_after_sl = stop_loss_pct
        improvement = base_max_dd - stop_loss_pct
    else:
        estimated_dd_after_sl = base_max_dd
        improvement = 0

    return {
        "symbol": symbol,
        "stop_loss_pct": stop_loss_pct,
        "fast_window": fast_window, "slow_window": slow_window,
        "baseline": {
            "total_return": base["total_return"],
            "sharpe_ratio": base["sharpe_ratio"],
            "max_ddpercent": base["max_ddpercent"],
            "trade_count": base["total_trade_count"],
        },
        "with_stop_loss_estimate": {
            "max_ddpercent_estimate": -estimated_dd_after_sl,
            "dd_improvement_pct": round(improvement * 100, 2),
            "note": "粗估：实际效果取决于回撤触发的频次和市价单滑点。",
        },
    }


def scan_strategy_params_core(
    symbol: str, strategy_type: str, param_grid: dict,
    start: str, end: str, capital: float, top_n: int,
) -> list[dict]:
    """任意策略的网格搜索。返回 TOP N 排序结果。"""
    if not param_grid:
        return [{"error": "param_grid 至少要传一个 key"}]
    keys = list(param_grid.keys())
    combos = list(product(*[param_grid[k] for k in keys]))
    if not combos:
        return [{"error": f"param_grid 笛卡尔积为空: {param_grid}"}]

    results = []
    for combo in combos:
        p = dict(zip(keys, combo))
        if strategy_type in ("double_ma", "double_ma_trend"):
            if p.get("slow_window", 0) <= p.get("fast_window", 0):
                continue
        r = _run_backtest_core(
            vt_symbol=symbol, start=start, end=end, capital=capital,
            strategy_type=strategy_type, params=p,
        )
        if "error" not in r:
            results.append(r)
    results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    return results[:top_n]
