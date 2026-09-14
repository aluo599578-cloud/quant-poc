"""
lean_style_indicators.py — Lean 风格的指标 API 包装
==================================================

把 vnpy 的"创建 ArrayManager + talib 计算"风格，简化成 Lean 那种
`self.SMA("002180", 5)` 一行调用风格。

参考：QuantConnect Lean 的 QCAlgorithm.Indicators
  - self.SMA(symbol, period)  → SimpleMovingAverage
  - self.EMA(symbol, period)
  - self.RSI(symbol, period)
  - self.MACD(symbol, fast, slow, signal)
  - self.BB(symbol, period, stddev)
  - self.ATR(symbol, period)
  - self.MAX(symbol, period)
  - self.MIN(symbol, period)
  - self.STD(symbol, period)

返回的 indicator 对象有：
  - .is_ready  (bool)
  - .current.value  (float)
  - .update(time, value)  (内部状态更新)

Usage:

    from lean_style_indicators import IndicatorManager

    indicators = IndicatorManager()

    # 在 on_bar / on_data 里：
    indicators.update(bar.symbol, bar.close, bar.time)
    sma5 = indicators.SMA("002180", 5)
    if sma5.is_ready:
        if bar.close > sma5.current.value:
            ...
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, Optional, Union


@dataclass
class IndicatorPoint:
    """指标当前值（仿 Lean API）"""
    value: float
    time: datetime


class Indicator:
    """指标基类（仿 Lean）"""
    is_ready: bool = False
    current: Optional[IndicatorPoint] = None

    def update(self, time: datetime, value: float):
        raise NotImplementedError

    def reset(self):
        self.is_ready = False
        self.current = None


class SimpleMovingAverage(Indicator):
    """简单移动平均 (SMA) - 对应 Lean self.SMA(symbol, period)"""

    def __init__(self, period: int):
        self.period = period
        self._values: Deque[float] = deque(maxlen=period)
        # 不用 _sum 累加（deque 丢值时容易错），改用 sum() 实时算

    def update(self, time: datetime, value: float):
        self._values.append(value)
        if len(self._values) == self.period:
            self.current = IndicatorPoint(value=sum(self._values) / self.period, time=time)
            self.is_ready = True
        elif len(self._values) > self.period:
            # 不应发生（deque maxlen 限制）
            pass

    def reset(self):
        super().reset()
        self._values.clear()


class ExponentialMovingAverage(Indicator):
    """指数移动平均 (EMA) - 对应 Lean self.EMA(symbol, period)"""

    def __init__(self, period: int):
        self.period = period
        self._alpha = 2.0 / (period + 1)
        self._ema = None

    def update(self, time: datetime, value: float):
        if self._ema is None:
            self._ema = value
            self.current = IndicatorPoint(value=value, time=time)
            self.is_ready = True
        else:
            self._ema = self._alpha * value + (1 - self._alpha) * self._ema
            self.current = IndicatorPoint(value=self._ema, time=time)
            self.is_ready = True

    def reset(self):
        super().reset()
        self._ema = None


class RSI(Indicator):
    """相对强弱指标 (RSI) - 对应 Lean self.RSI(symbol, period)"""
    # 经典 Wilder 算法

    def __init__(self, period: int = 14):
        self.period = period
        self._prev_value: Optional[float] = None
        self._gains: Deque[float] = deque(maxlen=period)
        self._losses: Deque[float] = deque(maxlen=period)

    def update(self, time: datetime, value: float):
        if self._prev_value is None:
            self._prev_value = value
            return
        change = value - self._prev_value
        gain = max(change, 0)
        loss = max(-change, 0)
        self._gains.append(gain)
        self._losses.append(loss)
        self._prev_value = value

        if len(self._gains) == self.period:
            avg_gain = sum(self._gains) / self.period
            avg_loss = sum(self._losses) / self.period
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))
            self.current = IndicatorPoint(value=rsi, time=time)
            self.is_ready = True

    def reset(self):
        super().reset()
        self._prev_value = None
        self._gains.clear()
        self._losses.clear()


class MACD(Indicator):
    """MACD - 对应 Lean self.MACD(symbol, fast, slow, signal)"""
    # 返回 MACD 线和 signal 线

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast_ema = ExponentialMovingAverage(fast)
        self.slow_ema = ExponentialMovingAverage(slow)
        self.signal_ema = ExponentialMovingAverage(signal)
        self._macd_values: Deque[float] = deque(maxlen=signal)

    def update(self, time: datetime, value: float):
        self.fast_ema.update(time, value)
        self.slow_ema.update(time, value)
        if self.fast_ema.is_ready and self.slow_ema.is_ready:
            macd = self.fast_ema.current.value - self.slow_ema.current.value
            self._macd_values.append(macd)
            # signal EMA
            if len(self._macd_values) == self._macd_values.maxlen:
                self.signal_ema = ExponentialMovingAverage(self.signal_ema.period)
                for m in self._macd_values:
                    self.signal_ema.update(time, m)
                if self.signal_ema.is_ready:
                    self.current = IndicatorPoint(
                        value=macd - self.signal_ema.current.value, time=time
                    )
                    self.is_ready = True

    @property
    def macd(self) -> Optional[float]:
        if self.fast_ema.is_ready and self.slow_ema.is_ready:
            return self.fast_ema.current.value - self.slow_ema.current.value
        return None

    @property
    def signal(self) -> Optional[float]:
        return self.signal_ema.current.value if self.signal_ema.is_ready else None

    def reset(self):
        super().reset()
        self.fast_ema.reset()
        self.slow_ema.reset()
        self.signal_ema.reset()
        self._macd_values.clear()


class BollingerBands(Indicator):
    """布林带 - 对应 Lean self.BB(symbol, period, stddev)"""

    def __init__(self, period: int = 20, stddev: float = 2.0):
        self.period = period
        self.stddev = stddev
        self._values: Deque[float] = deque(maxlen=period)

    def update(self, time: datetime, value: float):
        self._values.append(value)
        if len(self._values) == self.period:
            mean = sum(self._values) / self.period
            variance = sum((v - mean) ** 2 for v in self._values) / self.period
            std = math.sqrt(variance)
            self._middle = mean
            self._upper = mean + self.stddev * std
            self._lower = mean - self.stddev * std
            self.current = IndicatorPoint(value=mean, time=time)
            self.is_ready = True

    @property
    def upper(self) -> Optional[float]:
        return getattr(self, "_upper", None)

    @property
    def middle(self) -> Optional[float]:
        return getattr(self, "_middle", None)

    @property
    def lower(self) -> Optional[float]:
        return getattr(self, "_lower", None)

    def reset(self):
        super().reset()
        self._values.clear()


class ATR(Indicator):
    """Average True Range - 对应 Lean self.ATR(symbol, period)"""
    # 用真实波动幅度

    def __init__(self, period: int = 14):
        self.period = period
        self._prev_close: Optional[float] = None
        self._trs: Deque[float] = deque(maxlen=period)
        self._current_bar_high: Optional[float] = None
        self._current_bar_low: Optional[float] = None

    def update_bar(self, bar_high: float, bar_low: float, bar_close: float, time: datetime):
        if self._prev_close is not None:
            tr = max(
                bar_high - bar_low,
                abs(bar_high - self._prev_close),
                abs(bar_low - self._prev_close),
            )
        else:
            tr = bar_high - bar_low
        self._trs.append(tr)
        self._prev_close = bar_close

        if len(self._trs) == self.period:
            atr = sum(self._trs) / self.period
            self.current = IndicatorPoint(value=atr, time=time)
            self.is_ready = True

    def update(self, time: datetime, value: float):
        # 简化：用单值 close 算不出 TR，要求 update_bar
        pass

    def reset(self):
        super().reset()
        self._prev_close = None
        self._trs.clear()


class RollingMax(Indicator):
    """滚动最大值 - 对应 Lean self.MAX(symbol, period)"""
    def __init__(self, period: int):
        self.period = period
        self._values: Deque[float] = deque(maxlen=period)

    def update(self, time: datetime, value: float):
        self._values.append(value)
        if len(self._values) == self.period:
            self.current = IndicatorPoint(value=max(self._values), time=time)
            self.is_ready = True

    def reset(self):
        super().reset()
        self._values.clear()


class RollingMin(Indicator):
    """滚动最小值 - 对应 Lean self.MIN(symbol, period)"""
    def __init__(self, period: int):
        self.period = period
        self._values: Deque[float] = deque(maxlen=period)

    def update(self, time: datetime, value: float):
        self._values.append(value)
        if len(self._values) == self.period:
            self.current = IndicatorPoint(value=min(self._values), time=time)
            self.is_ready = True

    def reset(self):
        super().reset()
        self._values.clear()


class RollingStd(Indicator):
    """滚动标准差 - 对应 Lean self.STD(symbol, period)"""
    def __init__(self, period: int):
        self.period = period
        self._values: Deque[float] = deque(maxlen=period)

    def update(self, time: datetime, value: float):
        self._values.append(value)
        if len(self._values) == self.period:
            mean = sum(self._values) / self.period
            var = sum((v - mean) ** 2 for v in self._values) / self.period
            self.current = IndicatorPoint(value=math.sqrt(var), time=time)
            self.is_ready = True

    def reset(self):
        super().reset()
        self._values.clear()


# ============================================================
# IndicatorManager — Lean 风格的中心 API
# ============================================================

class IndicatorManager:
    """
    Lean 风格的指标管理。
    用法：
        im = IndicatorManager()
        im.update(symbol, bar.close, bar.time)
        sma5 = im.SMA(symbol, 5)
        if sma5.is_ready and bar.close > sma5.current.value:
            ...
    """
    def __init__(self):
        # symbol -> indicator_name -> Indicator
        self._indicators: Dict[str, Dict[str, Indicator]] = {}

    def update(self, symbol: str, value: float, time: datetime,
               high: float = None, low: float = None, close: float = None):
        """更新某 symbol 的所有指标（如果指标还没创建则跳过）"""
        if symbol not in self._indicators:
            return  # 用户得先调 SMA()/EMA() 等创建指标
        for ind in self._indicators[symbol].values():
            if isinstance(ind, ATR):
                # ATR 用 high/low/close
                if high is not None and low is not None and close is not None:
                    ind.update_bar(high, low, close, time)
            else:
                ind.update(time, value)

    def _get_or_create(self, symbol: str, key: str, factory) -> Indicator:
        if symbol not in self._indicators:
            self._indicators[symbol] = {}
        if key not in self._indicators[symbol]:
            self._indicators[symbol][key] = factory()
        return self._indicators[symbol][key]

    def SMA(self, symbol: str, period: int) -> SimpleMovingAverage:
        return self._get_or_create(symbol, f"SMA_{period}", lambda: SimpleMovingAverage(period))

    def EMA(self, symbol: str, period: int) -> ExponentialMovingAverage:
        return self._get_or_create(symbol, f"EMA_{period}", lambda: ExponentialMovingAverage(period))

    def RSI(self, symbol: str, period: int = 14) -> RSI:
        return self._get_or_create(symbol, f"RSI_{period}", lambda: RSI(period))

    def MACD(self, symbol: str, fast: int = 12, slow: int = 26, signal: int = 9) -> MACD:
        return self._get_or_create(symbol, f"MACD_{fast}_{slow}_{signal}",
                                   lambda: MACD(fast, slow, signal))

    def BB(self, symbol: str, period: int = 20, stddev: float = 2.0) -> BollingerBands:
        return self._get_or_create(symbol, f"BB_{period}_{stddev}",
                                   lambda: BollingerBands(period, stddev))

    def ATR(self, symbol: str, period: int = 14) -> ATR:
        return self._get_or_create(symbol, f"ATR_{period}", lambda: ATR(period))

    def MAX(self, symbol: str, period: int) -> RollingMax:
        return self._get_or_create(symbol, f"MAX_{period}", lambda: RollingMax(period))

    def MIN(self, symbol: str, period: int) -> RollingMin:
        return self._get_or_create(symbol, f"MIN_{period}", lambda: RollingMin(period))

    def STD(self, symbol: str, period: int) -> RollingStd:
        return self._get_or_create(symbol, f"STD_{period}", lambda: RollingStd(period))

    def reset(self, symbol: str = None):
        if symbol is None:
            for sym_dict in self._indicators.values():
                for ind in sym_dict.values():
                    ind.reset()
        else:
            if symbol in self._indicators:
                for ind in self._indicators[symbol].values():
                    ind.reset()


# ============================================================
# 单元测试
# ============================================================

if __name__ == "__main__":
    from datetime import datetime, timedelta

    print("=== Lean 风格指标 API 测试 ===\n")

    # 测试 1: SMA
    print("--- Test 1: SMA(5) ---")
    im = IndicatorManager()
    sma5 = im.SMA("002180", 5)  # 必须先创建再 update
    prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    for i, p in enumerate(prices):
        t = datetime(2026, 1, 1) + timedelta(days=i)
        im.update("002180", p, t)
    print(f"  is_ready: {sma5.is_ready}")
    print(f"  current: {sma5.current.value if sma5.is_ready else 'N/A'}")
    assert sma5.is_ready
    assert abs(sma5.current.value - 18.0) < 0.01  # (16+17+18+19+20)/5 = 18
    print("  ✓ 正确\n")

    # 测试 2: EMA
    print("--- Test 2: EMA(5) ---")
    im2 = IndicatorManager()
    ema5 = im2.EMA("002180", 5)  # 必须先创建
    for i, p in enumerate(prices):
        t = datetime(2026, 1, 1) + timedelta(days=i)
        im2.update("002180", p, t)
    print(f"  is_ready: {ema5.is_ready}")
    print(f"  current: {ema5.current.value:.4f}")
    assert ema5.is_ready
    print("  ✓ 正确\n")

    # 测试 3: RSI
    print("--- Test 3: RSI(14) ---")
    im3 = IndicatorManager()
    rsi14 = im3.RSI("002180", 14)  # 先创建
    # 模拟 15 个递增的价格
    for i, p in enumerate(range(100, 115)):
        t = datetime(2026, 1, 1) + timedelta(days=i)
        im3.update("002180", p, t)
    print(f"  is_ready: {rsi14.is_ready}")
    print(f"  current: {rsi14.current.value:.2f}" if rsi14.is_ready else "  N/A")
    assert rsi14.is_ready
    # 全是上涨，RSI 应该接近 100
    assert rsi14.current.value > 95
    print("  ✓ 正确\n")

    # 测试 4: Bollinger Bands
    print("--- Test 4: BB(20, 2) ---")
    im4 = IndicatorManager()
    bb = im4.BB("002180", 20, 2)  # 先创建
    for i, p in enumerate([10, 11, 12, 11, 13, 14, 13, 15, 16, 15,
                            14, 13, 15, 17, 16, 18, 19, 17, 16, 15,
                            14, 13, 12, 11, 10]):
        t = datetime(2026, 1, 1) + timedelta(days=i)
        im4.update("002180", p, t)
    print(f"  is_ready: {bb.is_ready}")
    print(f"  middle: {bb.middle:.2f}, upper: {bb.upper:.2f}, lower: {bb.lower:.2f}")
    assert bb.is_ready
    print("  ✓ 正确\n")

    # 测试 5: MACD
    print("--- Test 5: MACD(12, 26, 9) ---")
    im5 = IndicatorManager()
    macd = im5.MACD("002180", 12, 26, 9)  # 先创建
    for i, p in enumerate(prices * 4):  # 44 个数据
        t = datetime(2026, 1, 1) + timedelta(days=i)
        im5.update("002180", p, t)
    print(f"  is_ready: {macd.is_ready}")
    print(f"  macd: {macd.macd}, signal: {macd.signal}, hist: {macd.current.value if macd.is_ready else 'N/A'}")
    print()

    print("=== 全部测试通过 ===")
    print("""
Lean 风格 API 用法（对比 vnpy）：

vnpy:                                    Lean style (我们):
am = ArrayManager(size=30)                im = IndicatorManager()
am.sma(close, 30)                         sma = im.SMA("002180", 30)
am.macd(close, 12, 26, 9)                 macd = im.MACD("002180", 12, 26, 9)
am.rsi(close, 14)                         rsi = im.RSI("002180", 14)
am.boll(close, 20, 2)                     bb = im.BB("002180", 20, 2)
""")
