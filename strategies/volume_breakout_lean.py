"""
volume_breakout_lean.py — 放量突破策略
======================================

逻辑：
  - 收盘价突破 N 日高点 + 成交量 > 1.5x 均量 → 买入
  - 跌破 N 日低点 → 卖出
  - 5% 止损

适合：突破行情
"""
from vnpy_ctastrategy import CtaTemplate, TickData, BarData

from lean_style_indicators import IndicatorManager


class VolumeBreakoutLean(CtaTemplate):
    author = "quant-poc"

    lookback: int = 20  # 突破/跌破的回看窗口
    vol_multiplier: float = 1.5  # 放量倍数
    vol_period: int = 5  # 均量窗口
    stop_loss_pct: float = 0.05
    fixed_size: int = 1
    warmup_bars: int = 100

    bar_count: int = 0
    entry_price: float = 0.0

    parameters = ["lookback", "vol_multiplier", "vol_period", "stop_loss_pct", "fixed_size", "warmup_bars"]
    variables = ["bar_count", "entry_price"]

    def on_init(self):
        self.write_log("放量突破策略初始化")
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
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return

        # 用 high/low 做突破判断（不是 close）
        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime,
                       high=bar.high_price, low=bar.low_price, close=bar.close_price)
        self.bar_count += 1

        # 止损
        if self.pos > 0 and self.entry_price > 0:
            loss = (bar.close_price - self.entry_price) / self.entry_price
            if loss <= -self.stop_loss_pct:
                self.sell(bar.close_price, abs(self.pos))
                self.entry_price = 0.0
                self.put_event()
                return

        # 简化：放量突破用 close > 最近 N 根 high 的最高 + volume > N 根均量
        if self.bar_count < self.warmup_bars:
            return

        # 直接判断 close 突破（vnpy BacktestEngine 在 on_bar 给的 bar.high_price 是 K 线 high）
        # 我们用 self.am 维护历史 high/low/volume
        if not hasattr(self, "highs"):
            self.highs = []
            self.lows = []
            self.vols = []
        self.highs.append(bar.high_price)
        self.lows.append(bar.low_price)
        self.vols.append(bar.volume)
        if len(self.highs) > self.lookback:
            self.highs = self.highs[-self.lookback:]
            self.lows = self.lows[-self.lookback:]
            self.vols = self.vols[-self.lookback:]

        if len(self.highs) < self.lookback:
            return

        recent_high = max(self.highs[:-1])  # 排除当前 bar
        recent_low = min(self.lows[:-1])
        avg_vol = sum(self.vols[:-self.vol_period]) / max(len(self.vols) - self.vol_period, 1)

        # 突破
        if bar.close_price > recent_high and bar.volume > avg_vol * self.vol_multiplier and self.pos == 0:
            self.buy(bar.close_price, self.fixed_size)
            self.entry_price = bar.close_price
        # 跌破
        elif bar.close_price < recent_low and self.pos > 0:
            self.sell(bar.close_price, abs(self.pos))
            self.entry_price = 0.0

        self.put_event()
