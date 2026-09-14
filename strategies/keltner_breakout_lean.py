"""
keltner_breakout_lean.py — Keltner 通道突破策略
================================================

Keltner 通道 = EMA ± N * ATR
- 突破上轨 → 买入
- 跌破中轨 → 卖出
- ATR 跟踪止损

适合：趋势确认（不靠单一指标）
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class KeltnerBreakoutLean(CtaTemplate):
    author = "quant-poc"

    ema_period: int = 20
    atr_period: int = 14
    atr_multiplier: float = 2.0
    fixed_size: int = 1
    warmup_bars: int = 100

    bar_count: int = 0
    trail_stop: float = 0.0

    parameters = ["ema_period", "atr_period", "atr_multiplier", "fixed_size", "warmup_bars"]
    variables = ["bar_count", "trail_stop"]

    def on_init(self):
        self.write_log("Keltner 突破策略初始化")
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
            self.ema = self.im.EMA(bar.vt_symbol, self.ema_period)
            self.atr = self.im.ATR(bar.vt_symbol, self.atr_period)
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime,
                           high=bar.high_price, low=bar.low_price, close=bar.close_price)
            return

        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime,
                       high=bar.high_price, low=bar.low_price, close=bar.close_price)
        self.bar_count += 1

        if not (self.ema.is_ready and self.atr.is_ready):
            return
        if self.bar_count < self.warmup_bars:
            return

        ema_val = self.ema.current.value
        atr_val = self.atr.current.value
        upper = ema_val + atr_val * self.atr_multiplier
        lower = ema_val - atr_val * self.atr_multiplier

        # ATR 跟踪止损
        if self.pos > 0:
            current_stop = bar.close_price - atr_val * self.atr_multiplier
            if current_stop > self.trail_stop:
                self.trail_stop = current_stop
            if bar.close_price < self.trail_stop:
                self.sell(bar.close_price, abs(self.pos))
                self.trail_stop = 0.0
                self.put_event()
                return

        # 突破上轨
        if bar.close_price > upper and self.pos == 0:
            self.buy(bar.close_price, self.fixed_size)
            self.trail_stop = bar.close_price - atr_val * self.atr_multiplier
        # 跌破中轨
        elif bar.close_price < ema_val and self.pos > 0:
            self.sell(bar.close_price, abs(self.pos))
            self.trail_stop = 0.0

        self.put_event()
