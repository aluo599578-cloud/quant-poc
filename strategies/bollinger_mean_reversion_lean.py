"""
bollinger_mean_reversion_lean.py — 布林带均值回归
==================================================

逻辑：
  - 跌破下轨 + RSI < 30 → 买入
  - 涨破中轨 + RSI > 70 → 卖出
  - 5% 止损

适合：震荡市（A 股 2023-2026 大部分时间）
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class BollingerMeanReversionLean(CtaTemplate):
    author = "quant-poc"

    bb_period: int = 20
    bb_stddev: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    stop_loss_pct: float = 0.05
    fixed_size: int = 1
    warmup_bars: int = 100

    bar_count: int = 0
    entry_price: float = 0.0

    parameters = ["bb_period", "bb_stddev", "rsi_period", "rsi_oversold", "rsi_overbought", "stop_loss_pct", "fixed_size", "warmup_bars"]
    variables = ["bar_count", "entry_price"]

    def on_init(self):
        self.write_log("布林带均值回归 Lean 策略初始化")
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
            self.bb = self.im.BB(bar.vt_symbol, self.bb_period, self.bb_stddev)
            self.rsi = self.im.RSI(bar.vt_symbol, self.rsi_period)
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
                self.put_event()
                return

        if not (self.bb.is_ready and self.rsi.is_ready):
            return
        if self.bar_count < self.warmup_bars:
            return

        rsi = self.rsi.current.value
        close = bar.close_price
        bb_lower = self.bb.lower
        bb_upper = self.bb.upper
        bb_middle = self.bb.middle

        # 跌破下轨 + RSI 超卖 → 买入（均值回归）
        if rsi < self.rsi_oversold and close < bb_lower and self.pos == 0:
            self.buy(bar.close_price, self.fixed_size)
            self.entry_price = bar.close_price
        # 涨破中轨 + RSI 超买 → 卖出
        elif (rsi > self.rsi_overbought or close > bb_middle) and self.pos > 0:
            self.sell(bar.close_price, abs(self.pos))
            self.entry_price = 0.0

        self.put_event()
