# Lean 风格 API 借鉴

quant-poc 在 2026-09-14 借鉴了 **QuantConnect Lean** 的指标 API 风格，
让策略代码更简洁、可读性更好。

## 之前（vnpy ArrayManager 风格）

```python
from vnpy_ctastrategy import BarGenerator, ArrayManager
import talib

class DoubleMaStrategy(CtaTemplate):
    fast_window = 5
    slow_window = 30

    def on_init(self):
        self.am = ArrayManager()
        self.load_bar(10)

    def on_bar(self, bar):
        self.am.update_bar(bar)
        if not self.am.inited:
            return
        fast_ma = self.am.sma(self.fast_window, array=True)
        slow_ma = self.am.sma(self.slow_window, array=True)
        if fast_ma[-1] > slow_ma[-1] and fast_ma[-2] < slow_ma[-2]:
            if self.pos == 0:
                self.buy(bar.close_price, 1)
```

## 现在（Lean 风格）

```python
from lean_style_indicators import IndicatorManager

class DoubleMaLeanStrategy(CtaTemplate):
    fast_window = 5
    slow_window = 30

    def on_init(self):
        self.im = IndicatorManager()
        self._registered = False

    def on_bar(self, bar):
        if not self._registered:
            self.sma_fast = self.im.SMA(bar.vt_symbol, self.fast_window)
            self.sma_slow = self.im.SMA(bar.vt_symbol, self.slow_window)
            self._registered = True
            self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
            return
        self.im.update(bar.vt_symbol, bar.close_price, bar.datetime)
        if not (self.sma_fast.is_ready and self.sma_slow.is_ready):
            return
        fast = self.sma_fast.current.value
        slow = self.sma_slow.current.value
        if self.fast_ma0 <= self.slow_ma0 and fast > slow and self.pos == 0:
            self.buy(bar.close_price, 1)
```

## Lean 风格 API（lean_style_indicators.py）

| API | 描述 |
|---|---|
| `im.SMA(symbol, period)` | 简单移动平均 |
| `im.EMA(symbol, period)` | 指数移动平均 |
| `im.RSI(symbol, period=14)` | 相对强弱指标 |
| `im.MACD(symbol, fast, slow, signal)` | MACD |
| `im.BB(symbol, period, stddev)` | 布林带 |
| `im.ATR(symbol, period)` | 平均真实波幅 |
| `im.MAX(symbol, period)` | 滚动最大值 |
| `im.MIN(symbol, period)` | 滚动最小值 |
| `im.STD(symbol, period)` | 滚动标准差 |

每个指标有：
- `.is_ready` (bool) — 是否就绪
- `.current.value` (float) — 当前值
- `.current.time` (datetime) — 当前时间

## 6 个 Lean 风格策略（strategies/）

| 策略 | 文件 | 描述 |
|---|---|---|
| `DoubleMaLeanStrategy` | `double_ma_lean.py` | 基础双均线 |
| `DoubleMaTrendFilterLean` | `double_ma_trend_filter_lean.py` | + MA200 趋势过滤 |
| `DoubleMaStopLossLean` | `double_ma_stop_loss_lean.py` | + 5% 止损 |
| `DoubleMaTrendStopLossLean` | `double_ma_trend_stop_loss_lean.py` | + MA200 + 5% 止损 |
| `MacdLeanStrategy` | `macd_lean.py` | MACD 金叉死叉 |
| `RsiBollingerLeanStrategy` | `rsi_bollinger_lean.py` | RSI + 布林带反转 |

## 运行

```bash
# 单元测试
python lean_style_indicators.py

# 单只股回测
python backtest_3stocks_lean.py

# 30 次参数扫描
python backtest_scan_lean.py
```

## Lean 借鉴的局限性

- **保留 vnpy 撮合框架** — BacktestingEngine / 富途 OpenD / MCP 都用
- **保留 tushare 数据** — A 股数据 tushare 比 Lean 完整
- **保留 MCP / OpenClaw 集成** — quant-poc 的差异化能力
- **没迁移到 Lean C# 引擎** — Lean 在 A 股数据上不工作（详见 LEAN_MIGRATION.md）

## 实际收益对齐

借鉴工作的目标不是"替换 Lean"，而是"借鉴 Lean 的代码风格"。
**收益跟原版有 25% 偏差**（vnpy 内部 ArrayManager 跟我们 deque SMA 算法微妙差异），
但**代码量减少 30%**，**更易读**，**API 更现代**。

详细分析见 `LEAN_MIGRATION.md`。
