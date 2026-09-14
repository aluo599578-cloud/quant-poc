"""
rsi_bollinger_lean.py — RSI + 布林带反转策略 (Lean 风格)
========================================================
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class RsiBollingerLeanStrategy(CtaTemplate):
    """RSI 超卖 + 布林带下轨买入；RSI 超买 + 布林带上轨卖出"""

    author = "quant-poc Lean-inspired"

    rsi_period: int = 14
    bb_period: int = 20
    bb_stddev: float = 2.0
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    fixed_size: int = 1
    warmup_bars: int = 100

    bar_count: int = 0

    parameters = ["rsi_period", "bb_period", "bb_stddev", "rsi_oversold", "rsi_overbought", "fixed_size", "warmup_bars"]
    variables = ["bar_count"]

    def on_init(self):
        self.write_log("RSI+BB Lean 策略初始化")
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
            self.rsi = self.im.RSI(bar.vt_symbol, self.rsi_period)
            self.bb = self.im.BB(bar.vt_symbol, self.bb_period, self.bb_stddev)
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return

        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
        self.bar_count += 1

        if not (self.rsi.is_ready and self.bb.is_ready):
            return
        if self.bar_count < self.warmup_bars:
            return

        rsi = self.rsi.current.value
        close = bar.close_price
        bb_lower = self.bb.lower
        bb_upper = self.bb.upper

        # 超卖 + 跌破下轨 → 买入
        if rsi < self.rsi_oversold and close < bb_lower and self.pos == 0:
            self.buy(bar.close_price, self.fixed_size)
        # 超买 + 涨破上轨 → 卖出
        elif rsi > self.rsi_overbought and close > bb_upper and self.pos > 0:
            self.sell(bar.close_price, abs(self.pos))

        self.put_event()
