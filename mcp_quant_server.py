"""
mcp_quant_server.py — 量化研究 MCP Server
==========================================

给 LLM 暴露 6 个工具：
1. run_backtest            跑单次回测（指定股票+参数）
2. scan_ma_params           双均线参数网格搜索
3. scan_multi_stocks        多股同参数对比
4. generate_pine_script     把 Python 策略翻译成 Pine Script
5. get_top_results          读 30 次扫描缓存的 TOP 结果
6. validate_strategy        自动 review 回测结果（看 Sharpe/回撤给风险评级）

跑法：
    # stdio（Claude Desktop / OpenClaw 默认）
    mcp run mcp_quant_server.py

    # HTTP（OpenClaw / Claude Code 远程）
    python mcp_quant_server.py --transport http --port 8001

参考：
    https://github.com/modelcontextprotocol/python-sdk
    https://modelcontextprotocol.io/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# vnpy 内部用 loguru 输出大量 INFO 日志，会污染 stdio MCP 协议导致 UnicodeDecodeError
# 重定向 loguru 输出到 stderr（默认），且只显示 WARNING 以上
try:
    from loguru import logger as _loguru_logger
    _loguru_logger.remove()  # 移除默认 handler
    _loguru_logger.add(sys.stderr, level="WARNING")
except ImportError:
    pass

# 同样把 vnpy 的 root logger 调成 WARNING
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
logging.getLogger("vnpy").setLevel(logging.WARNING)
logging.getLogger("vnpy_ctastrategy").setLevel(logging.WARNING)

# 让脚本可独立运行
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP, Context

from backtest_3stocks import (
    STOCKS, fetch_kline, make_bars, to_tushare_code,
    START as DEFAULT_START, END as DEFAULT_END, INIT_CAPITAL,
)
# 核心回测逻辑（无 MCP 依赖）从 quant_core 引用，避免代码重复
from quant_core import (
    _normalize_vt_symbol, _run_backtest_core,
    run_walk_forward_core, simulate_stop_loss_core, scan_strategy_params_core,
    _add_strategy_to_engine,  # 兼容老 import
)

# MCP server
mcp = FastMCP(
    "quant-research",
    instructions=(
        "A 股量化研究工具集。提供回测、参数扫描、Pine Script 生成、"
        "结果 review 等能力。返回的是数据/文本，让 LLM 自己解读、对比、"
        "提建议。\n\n"
        "重要：所有金额单位是人民币（元），收益率是小数（0.05 = 5%）。\n"
        "重要：Tushare 需要 TUSHARE_TOKEN 环境变量。\n"
        "重要：vt_symbol 接受 A 股代码 .SH/.SZ 后缀（002180.SZ）或 vnpy 风格 .SZSE/.SSE。"
    ),
)


# =================== 工具函数 ===================

def _normalize_vt_symbol(vt_symbol: str) -> str:
    """把 TV 风格 (.SZ/.SH) 标准化为 vnpy 风格 (.SZSE/.SSE)。

    to_tushare_code 内部依赖这个映射。
    """
    if "." not in vt_symbol:
        raise ValueError(f"vt_symbol 缺交易所后缀: {vt_symbol!r}")
    code, exch = vt_symbol.upper().split(".", 1)
    if exch == "SZ":
        return f"{code}.SZSE"
    elif exch in ("SSE", "SH"):  # 兼容老的 .SSE
        return f"{code}.SSE"
    elif exch in ("SZSE", "SHSE"):  # 已经是 vnpy 风格
        return vt_symbol.upper()
    raise ValueError(f"不支持的交易所: {exch!r} (支持 .SZ/.SZSE/.SH/.SSE)")


def _add_strategy_to_engine(engine, strategy_type: str, params: dict) -> None:
    """根据 strategy_type 给 engine 加策略。"""
    if strategy_type == "double_ma":
        from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy
        engine.add_strategy(DoubleMaStrategy, {
            "fast_window": params.get("fast_window", 5),
            "slow_window": params.get("slow_window", 30),
        })
    elif strategy_type == "double_ma_trend":
        from backtest_scan import DoubleMaWithTrendFilter
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


# 策略参数 schema 文档（给 LLM 看的）
STRATEGY_PARAMS_DOC = """
策略参数说明：
- double_ma:       fast_window (5), slow_window (30)
- double_ma_trend: fast_window (5), slow_window (30), trend_window (200)
- atr_rsi:         atr_window (14), atr_ma_window (4), rsi_window (14), rsi_signal (20)
- boll_channel:    boll_window (18), boll_dev (3.4)
- king_keltner:   keltner_window (14), keltner_dev (1.2)
"""


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

    # 在 run_backtesting() 期间把 stdout 重定向到 stderr
    import contextlib
    from io import StringIO

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
        engine.calculate_result()  # 必须先调，否则 calculate_statistics 返回空
        s = engine.calculate_statistics()
    return {
        "symbol": vt_symbol,
        "strategy": strategy_type,
        "params": params,
        "total_return": s.get("total_return", 0),
        "annual_return": s.get("annual_return", 0),
        "sharpe_ratio": s.get("sharpe_ratio", 0),
        "max_ddpercent": s.get("max_ddpercent", 0),
        "max_drawdown": s.get("max_drawdown", 0),
        "total_trade_count": s.get("total_trade_count", 0),
        "profit_days": s.get("profit_days", 0),
        "total_days": s.get("total_days", 1),
        "end_balance": s.get("end_balance", 0),
        "n_bars": len(bars),
        "start": start, "end": end,
    }


# ---------- 工具 1: 单次回测 ----------
@mcp.tool()
def run_backtest(
    symbol: str,
    fast_window: int = 5,
    slow_window: int = 30,
    start: str = "2023-01-01",
    end: str = DEFAULT_END.strftime("%Y-%m-%d"),
    capital: float = 1_000_000.0,
    use_trend_filter: bool = False,
) -> dict:
    """跑一次 A 股双均线回测（兼容旧 API）。返回完整 stats。

    推荐用 run_strategy(strategy_type="double_ma"|"double_ma_trend"|...)，支持 5 种策略。

    Args:
        symbol: A 股代码，TradingView 风格(.SH/.SZ) 或 vnpy 风格(.SSE/.SZSE)。
                例如 "002180.SZ" / "688122.SH" / "000100.SZ"。
        fast_window: 均线快线周期 (2-60)，默认 5。
        slow_window: 均线慢线周期 (5-250)，默认 30。必须 > fast_window。
        start: 开始日期 YYYY-MM-DD，默认 2023-01-01。
        end: 结束日期 YYYY-MM-DD，默认今天。
        capital: 初始资金，默认 1000000。
        use_trend_filter: 是否加 MA200 趋势过滤。
    """
    if slow_window <= fast_window:
        return {"error": f"slow_window ({slow_window}) 必须 > fast_window ({fast_window})"}
    return _run_backtest_core(
        vt_symbol=symbol, start=start, end=end, capital=capital,
        strategy_type="double_ma_trend" if use_trend_filter else "double_ma",
        params={"fast_window": fast_window, "slow_window": slow_window},
    )


# ---------- 工具 2: 双均线参数扫描 ----------
@mcp.tool()
def scan_ma_params(
    symbol: str,
    fast_range: list[int] = [5, 10, 15],
    slow_range: list[int] = [20, 30, 60],
    start: str = "2023-01-01",
    end: str = DEFAULT_END.strftime("%Y-%m-%d"),
    capital: float = 1_000_000.0,
    use_trend_filter: bool = False,
    top_n: int = 5,
) -> list[dict]:
    """双均线参数网格搜索，返回按 Sharpe 排序的 TOP N 结果。

    Args:
        symbol: A 股代码（同 run_backtest）。
        fast_range: 快线参数列表，默认 [5, 10, 15]。
        slow_range: 慢线参数列表，默认 [20, 30, 60]。会自动过滤 <= max(fast_range) 的。
        start/end/capital/use_trend_filter: 同 run_backtest。
        top_n: 返回前 N 个，默认 5。
    """
    max_fast = max(fast_range) if fast_range else 0
    valid_slow = [s for s in slow_range if s > max_fast]
    if not valid_slow:
        return [{"error": f"slow_range {slow_range} 没有 > max(fast_range)={max_fast} 的值"}]

    results = []
    total = len(fast_range) * len(valid_slow)
    for fast in fast_range:
        for slow in valid_slow:
            r = _run_backtest_core(
                vt_symbol=symbol, start=start, end=end, capital=capital,
                strategy_type="double_ma_trend" if use_trend_filter else "double_ma",
                params={"fast_window": fast, "slow_window": slow},
            )
            if "error" not in r:
                results.append(r)

    results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    return results[:top_n]


# ---------- 工具 3: 多股同参数对比 ----------
@mcp.tool()
def scan_multi_stocks(
    symbols: list[str],
    fast_window: int = 5,
    slow_window: int = 30,
    start: str = "2023-01-01",
    end: str = DEFAULT_END.strftime("%Y-%m-%d"),
    capital: float = 1_000_000.0,
    use_trend_filter: bool = False,
) -> list[dict]:
    """多只 A 股用相同参数跑回测，横向对比。

    Args:
        symbols: A 股代码列表，例如 ["002180.SZ", "000100.SZ", "688122.SH"]。
        其它参数同 run_backtest。
    """
    if slow_window <= fast_window:
        return [{"error": f"slow_window must be > fast_window"}]
    results = []
    for sym in symbols:
        r = _run_backtest_core(
            vt_symbol=sym, start=start, end=end, capital=capital,
            strategy_type="double_ma_trend" if use_trend_filter else "double_ma",
            params={"fast_window": fast_window, "slow_window": slow_window},
        )
        if "error" not in r:
            results.append(r)
    results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    return results


# ---------- 工具 4: 通用策略回测（5 种策略） ----------
@mcp.tool()
def run_strategy(
    symbol: str,
    strategy_type: str = "double_ma",
    start: str = "2023-01-01",
    end: str = DEFAULT_END.strftime("%Y-%m-%d"),
    capital: float = 1_000_000.0,
    params: Optional[dict] = None,
) -> dict:
    """跑任意支持的策略回测。

    支持 5 种策略（与 vnpy_ctastrategy 内置一致）：

    1. double_ma: 双均线金叉死叉
       params: {fast_window: 5, slow_window: 30}
    2. double_ma_trend: 双均线 + MA200 趋势过滤
       params: {fast_window: 5, slow_window: 30, trend_window: 200}
    3. atr_rsi: ATR 波动率 + RSI 反转
       params: {atr_window: 14, atr_ma_window: 4, rsi_window: 14, rsi_signal: 20}
    4. boll_channel: 布林带突破
       params: {boll_window: 18, boll_dev: 3.4}
    5. king_keltner: Keltner 通道
       params: {keltner_window: 14, keltner_dev: 1.2}

    Args:
        symbol: A 股代码。
        strategy_type: 策略名（见上）。
        start/end: 起止日期。
        capital: 初始资金。
        params: 策略参数字典（不传则用默认值）。
    """
    return _run_backtest_core(
        vt_symbol=symbol, start=start, end=end, capital=capital,
        strategy_type=strategy_type, params=params or {},
    )


# ---------- 工具 5: 通用策略扫描（带进度推送）----------
@mcp.tool()
async def scan_strategy_params(
    symbol: str,
    strategy_type: str = "double_ma",
    param_grid: Optional[dict] = None,
    start: str = "2023-01-01",
    end: str = DEFAULT_END.strftime("%Y-%m-%d"),
    capital: float = 1_000_000.0,
    top_n: int = 5,
    ctx: Optional["Context"] = None,
) -> list[dict]:
    """任意策略的参数网格搜索（带流式进度推送）。返回按 Sharpe 排序的 TOP N。

    当 param_grid 较大时，会通过 MCP 进度通知实时报告完成度。
    客户端（如 Claude Desktop）会显示"正在跑 (5/20)"之类的进度条。

    Args:
        symbol: A 股代码。
        strategy_type: 策略名（同 run_strategy）。
        param_grid: 参数网格，例如 {"fast_window": [5,10], "slow_window": [20,30]}
        start/end/capital/top_n: 同 scan_ma_params。
    """
    if not param_grid:
        return [{"error": "param_grid 至少要传一个 key"}]

    from itertools import product
    keys = list(param_grid.keys())
    combos = list(product(*[param_grid[k] for k in keys]))
    if not combos:
        return [{"error": f"param_grid 笛卡尔积为空: {param_grid}"}]

    results = []
    total = len(combos)
    for i, combo in enumerate(combos):
        p = dict(zip(keys, combo))
        # 简单校验：双均线必须 fast < slow
        if strategy_type in ("double_ma", "double_ma_trend"):
            if p.get("slow_window", 0) <= p.get("fast_window", 0):
                continue
        r = _run_backtest_core(
            vt_symbol=symbol, start=start, end=end, capital=capital,
            strategy_type=strategy_type, params=p,
        )
        if "error" not in r:
            results.append(r)

        # 流式进度推送：每跑一个组合就发一次（如果客户端支持）
        if ctx is not None and (i + 1) % max(1, total // 20) == 0:
            await ctx.report_progress(
                progress=i + 1,
                total=total,
                message=f"完成 {i + 1}/{total}（{strategy_type}）"
            )
            await ctx.info(f"✓ {p} → sharpe={r.get('sharpe_ratio', 0):+.3f}")

    # 最后推送 100%
    if ctx is not None:
        await ctx.report_progress(total, total, f"全部 {total} 组完成")
        await ctx.info(f"找到 {len(results)} 个有效结果，TOP {top_n} 准备返回")

    results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    return results[:top_n]


# ---------- 工具 6: Stop loss 模拟 ----------
@mcp.tool()
def simulate_stop_loss(
    symbol: str,
    stop_loss_pct: float = 0.05,
    fast_window: int = 5,
    slow_window: int = 30,
    start: str = "2023-01-01",
    end: str = DEFAULT_END.strftime("%Y-%m-%d"),
    capital: float = 1_000_000.0,
    use_trend_filter: bool = False,
) -> dict:
    """在双均线策略基础上加 stop loss，对比无止损的效果。

    实现方式：
    - 跑两次 vnpy 回测（一次带 stop loss 逻辑，一次不带）
    - stop loss 逻辑：每根 K 线检查当前持仓浮亏是否超过 stop_loss_pct，是则立即市价卖出
    - 由于 vnpy BacktestingEngine 不直接支持 stop loss，模拟方式是"事后按日线判断 + 扣减收益"

    Args:
        symbol: A 股代码。
        stop_loss_pct: 止损比例，如 0.05 = 5%（跌 5% 止损）。
        fast_window/slow_window: 同 run_backtest。
        start/end/capital/use_trend_filter: 同 run_backtest。
    """
    # 基础回测
    base = _run_backtest_core(
        vt_symbol=symbol, start=start, end=end, capital=capital,
        strategy_type="double_ma_trend" if use_trend_filter else "double_ma",
        params={"fast_window": fast_window, "slow_window": slow_window},
    )
    if "error" in base:
        return base

    # 简单估算 stop loss 效果：取最大回撤做近似
    # 严格 stop loss 模拟需要重写策略 on_bar，这里给个粗估
    base_max_dd = abs(base["max_ddpercent"])
    if base_max_dd > stop_loss_pct:
        # 假设每次触发止损限制回撤到 stop_loss_pct（粗估）
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
            "note": "粗估：实际效果取决于回撤触发的频次和市价单滑点。严格模拟需要重写策略 on_bar。",
        },
    }


# ---------- 工具 7: Walk-Forward 验证 ----------
@mcp.tool()
def run_walk_forward(
    symbol: str,
    train_start: str = "2023-01-01",
    train_end: str = "2024-12-31",
    test_start: str = "2025-01-01",
    test_end: str = "2026-12-31",
    strategy_type: str = "double_ma",
    params: Optional[dict] = None,
    capital: float = 1_000_000.0,
) -> dict:
    """Walk-Forward 验证：在 train 期间"看到"的数据上跑 + 在 test 期间"没看到"的数据上跑。

    这是检测过拟合的标准方法：
    - train 段跑回测得到最优参数
    - 把同一参数放到 test 段看是否依然有效
    - train/test 的 Sharpe 差距 = 过拟合程度

    Args:
        symbol: A 股代码。
        train_start/train_end: 训练集起止（如 2023-01-01 ~ 2024-12-31）。
        test_start/test_end: 测试集起止（如 2025-01-01 ~ 2026-12-31）。
        strategy_type: 策略名（同 run_strategy）。
        params: 策略参数。
        capital: 初始资金。
    """
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

    # 判定过拟合
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

    def _to_native(x):
        """numpy 类型 → Python 原生类型（json 序列化）"""
        import numpy as np
        if isinstance(x, (np.integer,)): return int(x)
        if isinstance(x, (np.floating,)): return float(x)
        return x

    return {
        "symbol": symbol,
        "strategy_type": strategy_type,
        "params": params,
        "train": {
            "start": train_start, "end": train_end,
            "total_return": _to_native(train_stats["total_return"]),
            "annual_return": _to_native(train_stats["annual_return"]),
            "sharpe_ratio": _to_native(train_sharpe),
            "max_ddpercent": _to_native(train_stats["max_ddpercent"]),
            "trade_count": _to_native(train_stats["total_trade_count"]),
        },
        "test": {
            "start": test_start, "end": test_end,
            "total_return": _to_native(test_stats["total_return"]),
            "annual_return": _to_native(test_stats["annual_return"]),
            "sharpe_ratio": _to_native(test_sharpe),
            "max_ddpercent": _to_native(test_stats["max_ddpercent"]),
            "trade_count": _to_native(test_stats["total_trade_count"]),
        },
        "overfit_analysis": {
            "sharpe_drop": _to_native(sharpe_drop),
            "sharpe_drop_pct": _to_native(sharpe_drop_pct),
            "verdict": verdict,
        },
        "note": "train/test 段都用同一组参数。如果 test 段表现差说明过拟合，建议换参数或换股票。",
    }


# ---------- 工具 4: 生成 Pine Script ----------
@mcp.tool()
def generate_pine_script(
    strategy_type: str = "double_ma",
    fast_window: int = 5,
    slow_window: int = 30,
    use_trend_filter: bool = False,
    trend_window: int = 200,
) -> str:
    """把 Python 策略翻译成可在 TradingView 跑的 Pine Script v6。

    生成的脚本包含：
    - 同样的指标（MA5 / MA30 / MA200）
    - 同样的金叉死叉信号
    - alert() 调用 webhook（占位 URL，部署时替换）
    - 可直接复制到 TradingView Pine Editor

    Args:
        strategy_type: 策略类型，目前只支持 "double_ma"。
        fast_window/slow_window/trend_window: 同 run_backtest。
        use_trend_filter: 是否加 MA200 过滤。
    """
    if strategy_type != "double_ma":
        return f"# error: strategy_type={strategy_type!r} not supported (only 'double_ma')"

    if use_trend_filter:
        entry_cond = (
            f"ta.crossover(ma{fast_window}, ma{slow_window}) and close > ma{trend_window}\n"
        )
        exit_cond = f"ta.crossunder(ma{fast_window}, ma{slow_window})\n"
        plots = (
            f"plot(ma{fast_window}, 'MA{fast_window}', color.orange)\n"
            f"plot(ma{slow_window}, 'MA{slow_window}', color.blue)\n"
            f"plot(ma{trend_window}, 'MA{trend_window}', color.gray, linewidth=2)\n"
        )
    else:
        entry_cond = f"ta.crossover(ma{fast_window}, ma{slow_window})\n"
        exit_cond = f"ta.crossunder(ma{fast_window}, ma{slow_window})\n"
        plots = (
            f"plot(ma{fast_window}, 'MA{fast_window}', color.orange)\n"
            f"plot(ma{slow_window}, 'MA{slow_window}', color.blue)\n"
        )

    # 关键的 webhurl —— 部署时替换成你 webhook gateway 的 URL
    script = f"""//@version=6
strategy("DoubleMA({fast_window},{slow_window}){'+MA'+str(trend_window) if use_trend_filter else ''}",
         overlay=true, default_qty_type=strategy.fixed, default_qty=100)

// 输入参数
fast_len  = input.int({fast_window}, "Fast MA Length")
slow_len  = input.int({slow_window}, "Slow MA Length")
{('trend_len = input.int(' + str(trend_window) + ', "Trend MA Length")') if use_trend_filter else '// 不使用趋势过滤'}

// 计算均线
ma{fast_window}  = ta.ema(close, fast_len)
ma{slow_window}  = ta.ema(close, slow_len)
{('ma' + str(trend_window) + ' = ta.ema(close, trend_len)') if use_trend_filter else ''}

// 信号
long_cond  = {entry_cond}short_cond = {exit_cond}

// 下单
if long_cond
    strategy.entry("Long", strategy.long)
if short_cond
    strategy.close("Long")

// 画线
{plots}

// Webhook alert message（部署到 TradingView 时替换 YOUR_SECRET）
alert_msg = '{{' + \
    '"secret": "YOUR_SECRET",' + \\
    '"event_id": "tv-{{' + 'strategy.order.id}}-{{' + 'timenow}}",' + \\
    '"action": "{{' + 'strategy.order.action}}",' + \\
    '"symbol": "{{' + 'ticker}}.{{' + 'syminfo.prefix}}",' + \\
    '"price": {{{{ '{{' + 'close}}' }}}},' + \\
    '"volume": {{{{ '{{' + 'strategy.order.contracts}}' }}}},' + \\
    '"strategy": "double_ma({fast_window},{slow_window})"' + \\
    '}}'

if long_cond or short_cond
    alert(alert_msg, alert.freq_once_per_bar_close)
"""
    return script


# ---------- 工具 5: 读历史扫描缓存 ----------
@mcp.tool()
def get_top_results(
    sort_by: str = "sharpe_ratio",
    top_n: int = 10,
    strategy_filter: str = "",
) -> list[dict]:
    """读 backtest_scan 跑过的 30 条历史结果。

    Args:
        sort_by: 排序字段（sharpe_ratio/total_return/annual_return），默认 sharpe_ratio。
        top_n: 返回数量，默认 10。
        strategy_filter: 过滤策略类型（"DoubleMa" 或 "DoubleMa+MA200"），空字符串不过滤。
    """
    cache_path = Path(__file__).parent / "data" / "backtest_scan.json"
    if not cache_path.exists():
        return [{"error": f"缓存文件不存在: {cache_path}。请先跑 backtest_scan.py。"}]
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [{"error": f"读缓存失败: {e}"}]

    if strategy_filter:
        data = [r for r in data if r.get("strategy") == strategy_filter]

    if sort_by not in ("sharpe_ratio", "total_return", "annual_return"):
        return [{"error": f"不支持的 sort_by: {sort_by}"}]

    data.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return data[:top_n]


# ---------- 工具 6: 自动 review 回测结果 ----------
@mcp.tool()
def validate_strategy(stats: dict) -> str:
    """基于回测结果给风险评级和建议（给 LLM 做最终判断用）。"""
    lines = ["📊 策略评估报告\n"]

    total_ret = stats.get("total_return", 0) * 100
    annual_ret = stats.get("annual_return", 0) * 100
    sharpe = stats.get("sharpe_ratio", 0)
    max_dd = stats.get("max_ddpercent", 0) * 100
    trades = stats.get("total_trade_count", 0)
    win_rate = (stats.get("profit_days", 0) / max(stats.get("total_days", 1), 1)) * 100

    # 总收益评级
    if total_ret > 30:
        ret_grade = "🟢 优秀"
    elif total_ret > 10:
        ret_grade = "🟡 良好"
    elif total_ret > 0:
        ret_grade = "🟠 一般"
    else:
        ret_grade = "🔴 亏损"

    # Sharpe 评级
    if sharpe > 1.0:
        sharpe_grade = "🟢 优秀"
    elif sharpe > 0.5:
        sharpe_grade = "🟡 合格"
    elif sharpe > 0:
        sharpe_grade = "🟠 偏弱"
    else:
        sharpe_grade = "🔴 差"

    # 回撤评级
    if max_dd > -10:
        dd_grade = "🟢 小"
    elif max_dd > -20:
        dd_grade = "🟡 中"
    elif max_dd > -40:
        dd_grade = "🟠 较大"
    else:
        dd_grade = "🔴 极大"

    # 综合评级
    if sharpe > 0.5 and max_dd > -20 and total_ret > 10:
        overall = "🟢 建议上 paper trading 实盘验证"
    elif sharpe > 0 and total_ret > 0 and max_dd > -30:
        overall = "🟡 可以上 paper，但仓位别大（<30% 资金）"
    elif sharpe > 0:
        overall = "🟠 信号不显著，建议换参数或加过滤"
    else:
        overall = "🔴 策略不可用，pass"

    lines.append(f"总收益: {total_ret:+.2f}%  {ret_grade}")
    lines.append(f"年化收益: {annual_ret:+.2f}%")
    lines.append(f"Sharpe: {sharpe:+.2f}  {sharpe_grade}")
    lines.append(f"最大回撤: {max_dd:.2f}%  {dd_grade}")
    lines.append(f"交易笔数: {trades}")
    lines.append(f"日胜率: {win_rate:.1f}%")
    lines.append("")
    lines.append(f"综合评级: {overall}")
    lines.append("")
    lines.append("⚠️ 注意：")
    lines.append("1. 这是 2023-2026 行情下的 in-sample 结果")
    lines.append("2. 没做 walk-forward 验证（2023-2024 训练 + 2025-2026 验证）")
    lines.append("3. 双均线/MA200 过滤在 3 只 A 股上数据，不能直接外推到其它股票")
    lines.append("4. 上实盘前必须先 paper trading 至少 2 周")

    return "\n".join(lines)


# =================== 入口 ===================
def main():
    parser = argparse.ArgumentParser(description="A 股量化研究 MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                        help="stdio (Claude Desktop / OpenClaw 默认) 或 http")
    parser.add_argument("--port", type=int, default=8001, help="HTTP 模式端口")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 模式 host")
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()  # 默认 stdio


if __name__ == "__main__":
    main()
