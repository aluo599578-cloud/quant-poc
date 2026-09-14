"""
macd_histogram_lean.py — MACD 柱状图策略
=========================================

逻辑：
  - MACD 柱从负转正（金叉）→ 买入
  - MACD 柱从正转负（死叉）→ 卖出
  - 5% 止损

适合：捕捉趋势反转
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class MacdHistogramLean(CtaTemplate):
    author = "quant-poc"

    fast_window: int = 12
    slow_window: int = 26
    signal_window: int = 9
    stop_loss_pct: float = 0.05
    fixed_size: int = 1
    warmup_bars: int = 100

    macd_prev: float = 0.0
    bar_count: int = 0
    entry_price: float = 0.0

    parameters = ["fast_window", "slow_window", "signal_window", "stop_loss_pct", "fixed_size", "warmup_bars"]
    variables = ["macd_prev", "bar_count", "entry_price"]

    def on_init(self):
        self.write_log("MACD 柱状图策略初始化")
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

        # 止损
        if self.pos > 0 and self.entry_price > 0:
            loss = (bar.close_price - self.entry_price) / self.entry_price
            if loss <= -self.stop_loss_pct:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0
                self.macd_prev = self.macd.current.value
                self.put_event()
                return

        if not self.macd.is_ready:
            return
        if self.bar_count < self.warmup_bars:
            return

        hist = self.macd.current.value

        if self.macd_prev != 0:
            # MACD 柱从负转正 → 金叉 → 买入
            if self.macd_prev <= 0 and hist > 0 and self.pos == 0:
                self.buy(bar.close_price, self.fixed_size)
                self.entry_price = bar.close_price
            # MACD 柱从正转负 → 死叉 → 卖出
            elif self.macd_prev >= 0 and hist < 0 and self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0

        self.macd_prev = hist
        self.put_event()
