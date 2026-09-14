"""
double_ma_trend_stop_loss_lean.py — 双均线 + MA200 + 5% 止损
===========================================================
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class DoubleMaTrendStopLossLean(CtaTemplate):
    """双均线 + MA200 + 5% 止损 (Lean 风格)"""

    author = "quant-poc Lean-inspired"

    fast_window: int = 5
    slow_window: int = 30
    trend_window: int = 200
    stop_loss_pct: float = 0.05
    fixed_size: int = 1
    warmup_bars: int = 250

    fast_ma0: float = 0.0
    slow_ma0: float = 0.0
    bar_count: int = 0
    entry_price: float = 0.0

    parameters = ["fast_window", "slow_window", "trend_window", "stop_loss_pct", "fixed_size", "warmup_bars"]
    variables = ["fast_ma0", "slow_ma0", "bar_count", "entry_price"]

    def on_init(self):
        self.write_log("双均线+MA200+止损 Lean 策略初始化")
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
            self.trend_ma = self.im.SMA(bar.vt_symbol, self.trend_window)
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return

        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
        self.bar_count += 1

        # 止损检查
        if self.pos > 0 and self.entry_price > 0:
            loss = (bar.close_price - self.entry_price) / self.entry_price
            if loss <= -self.stop_loss_pct:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0
                self.fast_ma0 = self.sma_fast.current.value
                self.slow_ma0 = self.sma_slow.current.value
                self.put_event()
                return

        if not (self.sma_fast.is_ready and self.sma_slow.is_ready and self.trend_ma.is_ready):
            return
        if self.bar_count < self.warmup_bars:
            return

        fast = self.sma_fast.current.value
        slow = self.sma_slow.current.value
        trend = self.trend_ma.current.value
        close = bar.close_price

        if self.fast_ma0 > 0 and self.slow_ma0 > 0:
            in_uptrend = close > trend
            cross_over = self.fast_ma0 <= self.slow_ma0 and fast > slow
            cross_below = self.fast_ma0 >= self.slow_ma0 and fast < slow

            if in_uptrend and cross_over and self.pos == 0:
                self.buy(bar.close_price, self.fixed_size)
                self.entry_price = bar.close_price
            elif (not in_uptrend or cross_below) and self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0

        self.fast_ma0 = fast
        self.slow_ma0 = slow
        self.put_event()
