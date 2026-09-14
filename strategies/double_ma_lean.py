"""
double_ma_lean.py — 基础双均线策略 (vnpy CtaTemplate + Lean 风格 indicators)
===========================================================================

参数: fast_window=5, slow_window=30, fixed_size=1, warmup_bars=100
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class DoubleMaLeanStrategy(CtaTemplate):
    """基础双均线策略 (Lean 风格 indicators)"""

    author = "quant-poc Lean-inspired"

    fast_window: int = 5
    slow_window: int = 30
    fixed_size: int = 1
    warmup_bars: int = 100

    fast_ma0: float = 0.0
    slow_ma0: float = 0.0
    bar_count: int = 0

    parameters = ["fast_window", "slow_window", "fixed_size", "warmup_bars"]
    variables = ["fast_ma0", "slow_ma0", "bar_count"]

    def on_init(self):
        self.write_log("双均线 Lean 策略初始化")
        self.im: IndicatorManager = IndicatorManager()
        self._registered = False

    def on_start(self):
        self.write_log("双均线 Lean 策略启动")
        self.put_event()

    def on_stop(self):
        self.write_log("双均线 Lean 策略停止")
        self.put_event()

    def on_tick(self, tick: TickData):
        pass

    def on_bar(self, bar: BarData):
        if not self._registered:
            self.sma_fast = self.im.SMA(bar.vt_symbol, self.fast_window)
            self.sma_slow = self.im.SMA(bar.vt_symbol, self.slow_window)
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return

        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
        self.bar_count += 1

        if not (self.sma_fast.is_ready and self.sma_slow.is_ready):
            return
        if self.bar_count < self.warmup_bars:
            return

        fast = self.sma_fast.current.value
        slow = self.sma_slow.current.value

        if self.fast_ma0 > 0 and self.slow_ma0 > 0:
            if self.fast_ma0 <= self.slow_ma0 and fast > slow and self.pos == 0:
                self.buy(bar.close_price, self.fixed_size)
            elif self.fast_ma0 >= self.slow_ma0 and fast < slow and self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))

        self.fast_ma0 = fast
        self.slow_ma0 = slow
        self.put_event()
