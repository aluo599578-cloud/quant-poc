"""
macd_lean.py — MACD 策略 (Lean 风格)
====================================
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class MacdLeanStrategy(CtaTemplate):
    """MACD 金叉死叉策略 (Lean 风格)"""

    author = "quant-poc Lean-inspired"

    fast_window: int = 12
    slow_window: int = 26
    signal_window: int = 9
    fixed_size: int = 1
    warmup_bars: int = 100

    macd0: float = 0.0
    bar_count: int = 0

    parameters = ["fast_window", "slow_window", "signal_window", "fixed_size", "warmup_bars"]
    variables = ["macd0", "bar_count"]

    def on_init(self):
        self.write_log("MACD Lean 策略初始化")
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
            self.macd = self.im.MACD(bar.vt_symbol, self.fast_window, self.slow_window, self.signal_window)
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return

        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
        self.bar_count += 1

        if not self.macd.is_ready:
            return
        if self.bar_count < self.warmup_bars:
            return

        # MACD histogram > 0 买入，< 0 卖出
        hist = self.macd.current.value

        if self.macd0 != 0:
            if self.macd0 <= 0 and hist > 0 and self.pos == 0:
                # MACD 上穿 0 轴
                self.buy(bar.close_price, self.fixed_size)
            elif self.macd0 >= 0 and hist < 0 and self.pos > 0:
                # MACD 下穿 0 轴
                self.sell(bar.close_price, abs(self.pos))

        self.macd0 = hist
        self.put_event()
