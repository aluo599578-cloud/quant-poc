"""
double_ma_lean_strategy.py — 双均线策略 (Lean 风格 indicators)
============================================================

继承 vnpy CtaTemplate，跟原版 DoubleMaStrategy 同样注册到
BacktestingEngine。但用 lean_style_indicators 替代 ArrayManager。

对比原版：
  原版：self.am = ArrayManager(); self.am.sma(close, 5)
  Lean：self.im = IndicatorManager(); self.im.SMA(symbol, 5)

跑：python backtest_3stocks_lean.py
"""
import numpy as np

from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
)

from lean_style_indicators import IndicatorManager


class DoubleMaLeanStrategy(CtaTemplate):
    """双均线策略（Lean 风格 indicators + vnpy 撮合）"""

    author = "quant-poc Lean-inspired"

    fast_window: int = 5
    slow_window: int = 30
    fixed_size: int = 1
    warmup_bars: int = 100  # 跟原版 ArrayManager 默认 size 一致

    fast_ma0: float = 0.0
    fast_ma1: float = 0.0
    slow_ma0: float = 0.0
    slow_ma1: float = 0.0
    bar_count: int = 0  # 跟原版 am.count 等价

    parameters = ["fast_window", "slow_window", "fixed_size", "warmup_bars"]
    variables = ["fast_ma0", "fast_ma1", "slow_ma0", "slow_ma1", "bar_count"]

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log("Lean 双均线策略初始化")

        # Lean 风格 indicators
        self.im: IndicatorManager = IndicatorManager()
        self._registered = False

    def on_start(self) -> None:
        """策略启动"""
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """策略停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick 推送 - 不处理（daily bar 策略）"""
        pass

    def on_bar(self, bar: BarData) -> None:
        """K 线推送 - 1 天 1 根"""
        # Lean 风格：去掉 BarGenerator，直接用 on_bar
        # 第一次：注册指标 + 立即 update 当前 bar（不交易）
        if not self._registered:
            self.sma_fast = self.im.SMA(bar.vt_symbol, self.fast_window)
            self.sma_slow = self.im.SMA(bar.vt_symbol, self.slow_window)
            self._registered = True
            # 立即 update 当前 bar（让它开始累积）
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return

        # 更新指标
        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
        self.bar_count += 1

        # 等均线就绪 + warmup
        if not (self.sma_fast.is_ready and self.sma_slow.is_ready):
            return
        if self.bar_count < self.warmup_bars:
            return

        fast = self.sma_fast.current.value
        slow = self.sma_slow.current.value

        # 跨日判断 + 金叉死叉
        if self.fast_ma0 > 0 and self.slow_ma0 > 0:
            # 金叉：快线从下方穿越慢线
            if self.fast_ma0 <= self.slow_ma0 and fast > slow:
                if self.pos == 0:
                    self.write_log(f"BUY  price={bar.close_price}  pos={self.pos}  fast={fast:.2f} slow={slow:.2f}")
                    self.buy(bar.close_price, self.fixed_size)
                elif self.pos < 0:
                    self.cover(bar.close_price, abs(self.pos))
                    self.write_log(f"COVER price={bar.close_price}  pos={self.pos}")
            # 死叉：快线从上方穿越慢线
            elif self.fast_ma0 >= self.slow_ma0 and fast < slow:
                if self.pos == 0:
                    self.short(bar.close_price, self.fixed_size)
                    self.write_log(f"SHORT price={bar.close_price}  pos={self.pos}")
                elif self.pos > 0:
                    self.write_log(f"SELL price={bar.close_price}  pos={self.pos}  fast={fast:.2f} slow={slow:.2f}")
                    self.sell(bar.close_price, abs(self.pos))

        # 保存当前值（供下一根 K 线比较）
        self.fast_ma0 = fast
        self.slow_ma0 = slow

        self.put_event()
