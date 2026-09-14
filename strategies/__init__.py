"""
strategies/__init__.py — Lean 风格策略集合（vnpy CtaTemplate + IndicatorManager）

6 个策略：
  1. DoubleMaLeanStrategy            - 基础双均线 (5, 30)
  2. DoubleMaTrendFilterLean         - 双均线 + MA200 趋势过滤
  3. DoubleMaStopLossLean            - 双均线 + 5% 止损
  4. DoubleMaTrendStopLossLean       - 双均线 + MA200 + 5% 止损
  5. MacdLeanStrategy                - MACD 策略
  6. RsiBollingerLeanStrategy        - RSI + 布林带反转

每个策略用 lean_style_indicators.IndicatorManager（Lean 风格 API）
替代 vnpy 的 ArrayManager（talib 风格 API）。
"""
from .double_ma_lean import DoubleMaLeanStrategy
from .double_ma_trend_filter_lean import DoubleMaTrendFilterLean
from .double_ma_stop_loss_lean import DoubleMaStopLossLean
from .double_ma_trend_stop_loss_lean import DoubleMaTrendStopLossLean
from .macd_lean import MacdLeanStrategy
from .rsi_bollinger_lean import RsiBollingerLeanStrategy

__all__ = [
    "DoubleMaLeanStrategy",
    "DoubleMaTrendFilterLean",
    "DoubleMaStopLossLean",
    "DoubleMaTrendStopLossLean",
    "MacdLeanStrategy",
    "RsiBollingerLeanStrategy",
]
