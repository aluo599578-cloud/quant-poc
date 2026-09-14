"""
atr_trail_stop_lean.py — ATR 跟踪止损策略
========================================

逻辑：
  - 双均线金叉 → 买入
  - 持仓期间，止损价格 = max(入场价, 当前价 - 2*ATR) 跟着股价上移
  - 跌破止损价 → 卖出
  - 双均线死叉 → 强制卖出

ATR = Average True Range，波动大的股止损宽，波动小的股止损紧。

适合：避免被洗出去
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class AtrTrailStopLean(CtaTemplate):
    author = "quant-poc"

    fast_window: int = 10
    slow_window: int = 30
    atr_period: int = 14
    atr_multiplier: float = 2.0  # 止损距离 = 2*ATR
    fixed_size: int = 1
    warmup_bars: int = 100

    fast_ma0: float = 0.0
    slow_ma0: float = 0.0
    bar_count: int = 0
    trail_stop: float = 0.0

    parameters = ["fast_window", "slow_window", "atr_period", "atr_multiplier", "fixed_size", "warmup_bars"]
    variables = ["fast_ma0", "slow_ma0", "bar_count", "trail_stop"]

    def on_init(self):
        self.write_log("ATR 跟踪止损策略初始化")
        self.im: IndicatorManager = IndicatorManager()
        self._registered = False

    def on_start(self):
        self.put_event()

    def on_stop(self):
        self.put_event()

    def on_tick(self, tick: TickData):
        pass

    def on_bar(self, bar: BarData):
        if not self._registered:
            self.sma_fast = self.im.SMA(bar.vt_symbol, self.fast_window)
            self.sma_slow = self.im.SMA(bar.vt_symbol, self.slow_window)
            self.atr = self.im.ATR(bar.vt_symbol, self.atr_period)
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime,
                           high=bar.high_price, low=bar.low_price, close=bar.close_price)
            return

        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime,
                       high=bar.high_price, low=bar.low_price, close=bar.close_price)
        self.bar_count += 1

        # ATR 跟踪止损：持仓时检查
        if self.pos > 0 and self.atr.is_ready:
            current_stop = bar.close_price - self.atr.current.value * self.atr_multiplier
            # 止损价只上不下
            if current_stop > self.trail_stop:
                self.trail_stop = current_stop
            if bar.close_price < self.trail_stop:
                self.sell(bar.close_price, abs(self.pos))
                self.trail_stop = 0.0
                self.fast_ma0 = self.sma_fast.current.value
                self.slow_ma0 = self.sma_slow.current.value
                self.put_event()
                return

        if not (self.sma_fast.is_ready and self.sma_slow.is_ready and self.atr.is_ready):
            return
        if self.bar_count < self.warmup_bars:
            return

        fast = self.sma_fast.current.value
        slow = self.sma_slow.current.value

        if self.fast_ma0 > 0 and self.slow_ma0 > 0:
            # 金叉买入
            if self.fast_ma0 <= self.slow_ma0 and fast > slow and self.pos == 0:
                self.buy(bar.close_price, self.fixed_size)
                # 初始止损 = 入场价 - 2*ATR
                self.trail_stop = bar.close_price - self.atr.current.value * self.atr_multiplier
            # 死叉卖出
            elif self.fast_ma0 >= self.slow_ma0 and fast < slow and self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
                self.trail_stop = 0.0

        self.fast_ma0 = fast
        self.slow_ma0 = slow
        self.put_event()
