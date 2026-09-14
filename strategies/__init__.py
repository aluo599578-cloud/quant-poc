"""
strategies/__init__.py — Lean 风格策略集合（vnpy CtaTemplate + IndicatorManager）

策略：
  趋势类（双均线系列）:
    1. DoubleMaLeanStrategy            - 基础双均线
    2. DoubleMaTrendFilterLean         - 双均线 + MA200 趋势过滤
    3. DoubleMaStopLossLean            - 双均线 + 5% 止损
    4. DoubleMaTrendStopLossLean       - 双均线 + MA200 + 5% 止损
  反转/突破类（其他指标）:
    5. MacdLeanStrategy                - MACD 金叉死叉
    6. RsiBollingerLeanStrategy        - RSI + 布林带反转
    7. BollingerMeanReversionLean      - 布林带 + RSI 均值回归
    8. MacdHistogramLean               - MACD 柱状图策略
    9. VolumeBreakoutLean              - 放量突破策略
    10. AtrTrailStopLean               - ATR 跟踪止损
    11. KeltnerBreakoutLean            - Keltner 通道突破
    12. RsiDivergenceLean              - RSI 背离策略
"""
from .double_ma_lean import DoubleMaLeanStrategy
from .double_ma_trend_filter_lean import DoubleMaTrendFilterLean
from .double_ma_stop_loss_lean import DoubleMaStopLossLean
from .double_ma_trend_stop_loss_lean import DoubleMaTrendStopLossLean
from .macd_lean import MacdLeanStrategy
from .rsi_bollinger_lean import RsiBollingerLeanStrategy
from .bollinger_mean_reversion_lean import BollingerMeanReversionLean
from .macd_histogram_lean import MacdHistogramLean
from .volume_breakout_lean import VolumeBreakoutLean
from .atr_trail_stop_lean import AtrTrailStopLean
from .keltner_breakout_lean import KeltnerBreakoutLean
from .rsi_divergence_lean import RsiDivergenceLean

__all__ = [
    "DoubleMaLeanStrategy",
    "DoubleMaTrendFilterLean",
    "DoubleMaStopLossLean",
    "DoubleMaTrendStopLossLean",
    "MacdLeanStrategy",
    "RsiBollingerLeanStrategy",
    "BollingerMeanReversionLean",
    "MacdHistogramLean",
    "VolumeBreakoutLean",
    "AtrTrailStopLean",
    "KeltnerBreakoutLean",
    "RsiDivergenceLean",
]
