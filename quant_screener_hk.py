"""
quant_screener_hk.py — HK 股量化评分
======================================

针对你**实际能交易**的 HK 股（沪深港通标的）。
用富途拉数据 + tushare 拉部分数据。

Top 50 HK 蓝筹 + 沪深港通股。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from futu import OpenQuoteContext, RET_OK, KLType
from vnpy.trader.constant import Interval, Exchange
from vnpy_ctastrategy.backtesting import BacktestingEngine

from strategies import BollingerMeanReversionLean


# 沪深港通主要 HK 蓝筹
HK_STOCKS = [
    # 腾讯系
    ("HK.00700", "腾讯控股"),
    ("HK.09988", "阿里巴巴-W"),
    ("HK.03690", "美团-W"),
    ("HK.01024", "快手-W"),
    ("HK.09618", "京东集团-SW"),
    ("HK.09888", "百度集团-SW"),
    # 银行
    ("HK.00005", "汇丰控股"),
    ("HK.01398", "工商银行"),
    ("HK.03988", "中国银行"),
    ("HK.00939", "建设银行"),
    ("HK.01288", "农业银行"),
    # 保险
    ("HK.01299", "友邦保险"),
    ("HK.02628", "中国人寿"),
    # 消费
    ("HK.00001", "长和"),
    ("HK.00016", "新鸿基地产"),
    # 科技
    ("HK.01810", "小米集团-W"),
    ("HK.00992", "联想集团"),
    # 新能源车
    ("HK.01211", "比亚迪股份"),
    ("HK.09868", "小鹏汽车-W"),
    ("HK.02015", "理想汽车-W"),
    # 医药
    ("HK.01093", "石药集团"),
    ("HK.01066", "威高股份"),
    # 通信
    ("HK.00941", "中国移动"),
    # 资源
    ("HK.00857", "中国石油股份"),
    ("HK.00388", "香港交易所"),
    # 半导体
    ("HK.00981", "中芯国际"),
    # 港股本地
    ("HK.00016", "新鸿基地产"),
    ("HK.00011", "恒生银行"),
    # HK IPO 热门
    ("HK.02522", "一脉阳光"),
    ("HK.06682", "范式智能"),
    ("HK.02469", "粉笔"),
]


def get_hk_fundamentals(code: str) -> dict:
    """HK 股基本财务（简化版，tushare HK 接口有限）"""
    # 简化：用市值/PE 估算（实际生产用 AAStocks 等 HK 数据源）
    return {"pe": None, "roe": None, "market_cap": None}


def fetch_hk_kline(code: str, max_count: int = 1500) -> pd.DataFrame:
    q = OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, data, _ = q.request_history_kline(code, ktype=KLType.K_DAY, max_count=max_count)
    q.close()
    if ret != RET_OK:
        return pd.DataFrame()
    return data


def make_hk_bars(df: pd.DataFrame, code: str) -> list:
    bars = []
    for _, row in df.iterrows():
        bars.append(type('BarData', (), {
            'symbol': code,
            'exchange': Exchange.SEHK,
            'datetime': pd.to_datetime(str(row["time_key"])[:10]),
            'interval': Interval.DAILY,
            'volume': float(row["volume"]),
            'turnover': float(row["turnover"]),
            'open_interest': 0,
            'open_price': float(row["open"]),
            'high_price': float(row["high"]),
            'low_price': float(row["low"]),
            'close_price': float(row["close"]),
            'gateway_name': 'futu',
        })())
    return bars


def run_lean_backtest_hk(code: str) -> float:
    """HK 版 Lean 回测（用富途数据，复用 test_00700_backtest 的成功经验）"""
    try:
        df = fetch_hk_kline(code, 1500)
        if len(df) < 200:  # 至少要 200 根才能 warmup
            return 0.0

        # 转成 BarData
        from vnpy.trader.object import BarData
        from datetime import datetime as dt
        bars = []
        for _, row in df.iterrows():
            bars.append(BarData(
                symbol=code, exchange=Exchange.SEHK,
                datetime=dt.strptime(str(row["time_key"])[:10], "%Y-%m-%d"),
                interval=Interval.DAILY, volume=float(row["volume"]),
                turnover=float(row["turnover"]), open_interest=0,
                open_price=float(row["open"]), high_price=float(row["high"]),
                low_price=float(row["low"]), close_price=float(row["close"]),
                gateway_name='futu',
            ))
        vnpy_sym = code.replace("HK.", "") + ".SEHK"

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol=vnpy_sym, interval=Interval.DAILY,
            start=datetime(2024, 1, 1),  # HK 上市晚，缩范围
            end=datetime(2026, 9, 14),
            rate=0.001, slippage=0.01, size=100, pricetick=0.01, capital=200_000,
        )
        engine.add_strategy(BollingerMeanReversionLean, {
            "bb_period": 20, "bb_stddev": 2.0, "rsi_period": 14,
            "rsi_oversold": 30, "rsi_overbought": 70, "stop_loss_pct": 0.05,
            "fixed_size": 1, "warmup_bars": 50,
        })
        engine.history_data = bars
        engine.run_backtesting()
        engine.calculate_result()
        stats = engine.calculate_statistics()
        return float(stats.get("sharpe_ratio", 0))
    except Exception as e:
        print(f"  {code} backtest err: {e}")
        return 0.0


def main():
    print("="*70)
    print("  HK 股量化评分 — 沪深港通标的")
    print("="*70)

    results = []
    for i, (code, name) in enumerate(HK_STOCKS, 1):
        if i % 5 == 0:
            print(f"  进度: {i}/{len(HK_STOCKS)}")
        sharpe = run_lean_backtest_hk(code)
        # HK 没 ROE 字段（tushare 限），简化打分
        tech_score = 25 if sharpe > 1.0 else (20 if sharpe > 0.5 else (15 if sharpe > 0.3 else 0))
        results.append({
            "code": code,
            "name": name,
            "sharpe": sharpe,
            "score": tech_score,  # 简化：只看技术分
        })

    # 排序
    results.sort(key=lambda x: -x["score"])

    print(f"\n  {'代码':<10} {'名称':<14} {'Sharpe':<8} {'分数'}")
    print(f"  {'─'*10} {'─'*14} {'─'*8} {'─'*6}")
    for r in results:
        print(f"  {r['code']:<10} {r['name']:<14} {r['sharpe']:+.3f}  {r['score']:>3}")

    out = Path("data/quant_screen_hk.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 存到 {out}")

    # 推荐
    print(f"\n  🏆 排名 (按 Sharpe):")
    for r in results[:10]:
        print(f"    {r['code']:<10} {r['name']:<14} Sharpe {r['sharpe']:+.3f}")


if __name__ == "__main__":
    main()
