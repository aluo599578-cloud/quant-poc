"""
rsi_divergence_lean.py — RSI 背离策略
====================================

逻辑：
  - 价格创新低 + RSI 没创新低（看涨背离）→ 买入
  - 价格创新高 + RSI 没创新高（看跌背离）→ 卖出

适合：捕捉趋势反转点
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class RsiDivergenceLean(CtaTemplate):
    author = "quant-poc"

    rsi_period: int = 14
    lookback: int = 20
    fixed_size: int = 1
    warmup_bars: int = 100

    bar_count: int = 0

    parameters = ["rsi_period", "lookback", "fixed_size", "warmup_bars"]
    variables = ["bar_count"]

    def on_init(self):
        self.write_log("RSI 背离策略初始化")
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
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return

        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
        self.bar_count += 1

        # 维护历史 low/high
        if not hasattr(self, "closes"):
            self.closes = []
            self.rsis = []
        self.closes.append(bar.close_price)
        if self.rsi.is_ready:
            self.rsis.append(self.rsi.current.value)
        else:
            self.rsis.append(50)
        if len(self.closes) > self.lookback:
            self.closes = self.closes[-self.lookback:]
            self.rsis = self.rsis[-self.lookback:]

        if len(self.closes) < self.lookback:
            return
        if self.bar_count < self.warmup_bars:
            return

        # 找最近 N 根的最低价/最高价 + 对应 RSI
        recent_low = min(self.closes[:-1])
        recent_high = max(self.closes[:-1])
        recent_rsi_min = min(self.rsis[:-1])
        recent_rsi_max = max(self.rsis[:-1])

        # 看涨背离：价格创新低 + RSI 没创新低
        if bar.close_price < recent_low and self.rsi.current.value > recent_rsi_min and self.pos == 0:
            self.buy(bar.close_price, self.fixed_size)
        # 看跌背离：价格创新高 + RSI 没创新高
        elif bar.close_price > recent_high and self.rsi.current.value < recent_rsi_max and self.pos > 0:
            self.sell(bar.close_price, abs(self.pos))

        self.put_event()
