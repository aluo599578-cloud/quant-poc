"""
debug_indicators.py — 对比 vnpy ArrayManager.sma() 跟我的 SMA(5)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from vnpy_ctastrategy import ArrayManager

from lean_style_indicators import IndicatorManager
from backtest_3stocks import fetch_kline, make_bars
from datetime import datetime


def main():
    df = fetch_kline("002180.SZ", "2023-01-01", "2023-03-31")
    bars = make_bars(df, "002180.SZ")

    # 准备 prices
    closes = [b.close_price for b in bars]
    times = [b.datetime for b in bars]
    print(f"数据 {len(closes)} 根 K 线")
    print(f"前 10 根 close: {closes[:10]}")
    print()

    # vnpy ArrayManager
    am = ArrayManager()
    vnpy_sma5 = None
    vnpy_sma30 = None
    for i, (c, t) in enumerate(zip(closes, times)):
        class BarProxy:
            pass
        b = BarProxy()
        b.close_price = c
        b.datetime = t
        b.high_price = c
        b.low_price = c
        b.open_price = c
        b.open_interest = 0
        b.volume = 100
        b.turnover = c * 100
        am.update_bar(b)
        if am.inited:
            vnpy_sma5 = am.sma(5, array=True)
            vnpy_sma30 = am.sma(30, array=True)
            break

    print(f"vnpy am.inited 在第 {i+1} 根")
    if vnpy_sma5 is not None:
        print(f"  sma(5)[-1] = {vnpy_sma5[-1]:.4f}  sma(5)[-2] = {vnpy_sma5[-2]:.4f}")
        print(f"  sma(30)[-1] = {vnpy_sma30[-1]:.4f}  sma(30)[-2] = {vnpy_sma30[-2]:.4f}")

    # 我的 SMA
    print()
    im = IndicatorManager()
    my_sma5 = im.SMA("002180.SZ", 5)
    my_sma30 = im.SMA("002180.SZ", 30)
    for i, (c, t) in enumerate(zip(closes, times)):
        im.update("002180.SZ", c, t)
        if my_sma5.is_ready and my_sma30.is_ready:
            print(f"我的 SMA is_ready 在第 {i+1} 根")
            print(f"  sma(5).current = {my_sma5.current.value:.4f}")
            print(f"  sma(30).current = {my_sma30.current.value:.4f}")
            break

    # 对比
    print()
    print("对比:")
    print(f"  sma(5):   vnpy={vnpy_sma5[-1]:.4f}  my={my_sma5.current.value:.4f}  diff={abs(vnpy_sma5[-1]-my_sma5.current.value):.6f}")
    print(f"  sma(30):  vnpy={vnpy_sma30[-1]:.4f}  my={my_sma30.current.value:.4f}  diff={abs(vnpy_sma30[-1]-my_sma30.current.value):.6f}")


if __name__ == "__main__":
    main()
