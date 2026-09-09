import { Type, Static } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";
import { spawn, spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { Buffer } from "node:buffer";

/**
 * A 股量化研究工具插件
 *
 * 10 个工具，封装 mcp_quant_server.py 的核心能力。
 * 每个工具通过 spawn Python 调用 quant_core.py 跑回测，
 * 把 JSON 结果返回给 OpenClaw 喂给 LLM。
 *
 * 流式进度（v2 新增）：
 *   - Python 端往 stdout 写多行 JSON：每行一个 {"_progress": {...}} 或最终 {"_result": ...}
 *   - Node 端用 spawn() 异步读 stdout stream，每行触发 ctx.onUpdate
 *   - OpenClaw 把 partial result 实时推给 LLM（类似 MCP 的 report_progress）
 */

// 工具函数：spawn Python 跑 quant_core 中的函数
const PYTHON_SCRIPT = resolve(import.meta.dirname, "..", "..", "quant_core.py");
const PYTHON_EXEC = process.env.QUANT_PYTHON || "python";

type JsonResult = Record<string, unknown>;

// ---------- 同步模式：单次回测（不需要流式） ----------
function runPythonTool<T = JsonResult>(
  fnName: string,
  kwargs: Record<string, unknown>
): T {
  const kwargsJson = JSON.stringify(kwargs);
  const pyCode = `
import sys, json, os
sys.path.insert(0, r'${PYTHON_SCRIPT.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'.rsplit('\\\\', 1)[0])
os.chdir(${JSON.stringify(resolve(import.meta.dirname, "..", ".."))})
import quant_core
fn = getattr(quant_core, ${JSON.stringify(fnName)})
result = fn(**${kwargsJson})
# 强制转 JSON 安全
def _to_native(x):
    if hasattr(x, 'item'):
        return x.item()
    if isinstance(x, (list, tuple)):
        return [_to_native(v) for v in x]
    if isinstance(x, dict):
        return {k: _to_native(v) for k, v in x.items()}
    return x
print(json.dumps(_to_native(result), ensure_ascii=False))
`;
  const r = spawnSync(PYTHON_EXEC, ["-c", pyCode], {
    encoding: "utf-8",
    timeout: 120_000,
    maxBuffer: 50 * 1024 * 1024,
  });
  if (r.error) {
    throw new Error(`Python spawn failed: ${r.error.message}`);
  }
  if (r.status !== 0) {
    throw new Error(`Python exit ${r.status}: ${r.stderr.slice(-2000)}`);
  }
  if (!r.stdout || !r.stdout.trim()) {
    throw new Error(`Python 返回空 stdout。stderr: ${r.stderr.slice(-500)}`);
  }
  try {
    return JSON.parse(r.stdout) as T;
  } catch (e) {
    throw new Error(`JSON parse failed: ${(e as Error).message}\nstdout: ${r.stdout.slice(0, 500)}`);
  }
}

// ---------- 流式模式：扫描工具用，每行 JSON 触发 onUpdate ----------
async function runPythonStream<T = JsonResult>(
  fnName: string,
  kwargs: Record<string, unknown>,
  onUpdate?: (partial: { content: Array<{ type: "text"; text: string }>; details: unknown }) => void
): Promise<T> {
  const kwargsJson = JSON.stringify(kwargs);
  // Python 端协议：
  //   每跑一个组合 print 一行 PROGRESS:{...}
  //   结束时 print 一行 RESULT:{...}
  // 注意：避免 f-string 反斜杠（Python 3.11 不支持）
  const pyCode = `
import sys, json, os, time
sys.path.insert(0, r'${PYTHON_SCRIPT.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'.rsplit('\\\\', 1)[0])
os.chdir(${JSON.stringify(resolve(import.meta.dirname, "..", ".."))})
import quant_core
fn = getattr(quant_core, ${JSON.stringify(fnName)})

# Monkey-patch 进度报告：scan_strategy_params_core 每组合调一次
_original = quant_core._run_backtest_core
def _patched(*args, **kwargs):
    r = _original(*args, **kwargs)
    msg = "完成 params=" + json.dumps(r.get("params", {})) + " sharpe=" + str(round(r.get("sharpe_ratio", 0), 3))
    print("PROGRESS:" + json.dumps({"msg": msg, "result": r}, ensure_ascii=False), flush=True)
    return r
quant_core._run_backtest_core = _patched

result = fn(**${kwargsJson})

def _to_native(x):
    if hasattr(x, 'item'):
        return x.item()
    if isinstance(x, (list, tuple)):
        return [_to_native(v) for v in x]
    if isinstance(x, dict):
        return {k: _to_native(v) for k, v in x.items()}
    return x
print("RESULT:" + json.dumps(_to_native(result), ensure_ascii=False), flush=True)
`;

  return new Promise<T>((resolveP, rejectP) => {
    const proc = spawn(PYTHON_EXEC, ["-c", pyCode], {
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    let buf = "";
    let stderr = "";
    let progressCount = 0;

    proc.stdout.on("data", (chunk: Buffer) => {
      buf += chunk.toString("utf-8");
      // 按行解析（Python 端用 flush=True 每行一次）
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";  // 保留未完成的最后一行

      for (const line of lines) {
        if (!line.trim()) continue;
        if (line.startsWith("PROGRESS:")) {
          progressCount++;
          try {
            const payload = JSON.parse(line.slice("PROGRESS:".length));
            const params = payload.result && payload.result.params ? payload.result.params : {};
            const sharpe = payload.result && payload.result.sharpe_ratio !== undefined ? payload.result.sharpe_ratio : 0;
            // 避免 f-string 反斜杠问题（Python 3.11）
            const msg = "完成 params=" + JSON.stringify(params) + " sharpe=" + sharpe.toFixed(3);
            if (onUpdate) {
              onUpdate({
                content: [{
                  type: "text",
                  text: "📊 [" + progressCount + "] " + msg,
                }],
                details: {
                  progress_count: progressCount,
                  sharpe: payload.result ? payload.result.sharpe_ratio : null,
                  return_pct: payload.result ? payload.result.total_return : null,
                  params: params,
                },
              });
            }
          } catch (e) {
            // 忽略解析错误（可能行被截断）
          }
        } else if (line.startsWith("RESULT:")) {
          try {
            const result = JSON.parse(line.slice("RESULT:".length)) as T;
            resolveP(result);
          } catch (e) {
            rejectP(new Error(`RESULT 解析失败: ${(e as Error).message}\nline: ${line.slice(0, 500)}`));
          }
        }
      }
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });

    proc.on("close", (code) => {
      if (code !== 0) {
        rejectP(new Error(`Python exit ${code}: ${stderr.slice(-2000)}`));
      }
    });

    proc.on("error", (err) => {
      rejectP(new Error(`Python spawn error: ${err.message}`));
    });
  });
}

// ---- Tool 参数定义 ----

// 工具 1: run_backtest
const RunBacktestParams = Type.Object({
  symbol: Type.String({ description: 'A 股代码，如 "002180.SZ" 或 "688122.SH"' }),
  fast_window: Type.Optional(Type.Number({ default: 5, description: "快线均线周期" })),
  slow_window: Type.Optional(Type.Number({ default: 30, description: "慢线均线周期（必须 > fast）" })),
  start: Type.Optional(Type.String({ default: "2023-01-01", description: "开始日期 YYYY-MM-DD" })),
  end: Type.Optional(Type.String({ description: "结束日期 YYYY-MM-DD（默认今天）" })),
  capital: Type.Optional(Type.Number({ default: 1_000_000, description: "初始资金" })),
  use_trend_filter: Type.Optional(Type.Boolean({ default: false, description: "是否加 MA200 趋势过滤" })),
});

// 工具 4: run_strategy
const RunStrategyParams = Type.Object({
  symbol: Type.String({ description: "A 股代码" }),
  strategy_type: Type.Optional(Type.String({
    default: "double_ma",
    description: "策略类型: double_ma, double_ma_trend, atr_rsi, boll_channel, king_keltner",
  })),
  start: Type.Optional(Type.String({ default: "2023-01-01" })),
  end: Type.Optional(Type.String()),
  capital: Type.Optional(Type.Number({ default: 1_000_000 })),
  params: Type.Optional(Type.Object({}, { additionalProperties: true })),
});

// 工具 5: scan_strategy_params
const ScanStrategyParamsT = Type.Object({
  symbol: Type.String({ description: "A 股代码" }),
  strategy_type: Type.Optional(Type.String({ default: "double_ma" })),
  param_grid: Type.Object({}, { additionalProperties: true, description: '参数网格，如 {"fast_window": [5,10], "slow_window": [20,30]}' }),
  start: Type.Optional(Type.String({ default: "2023-01-01" })),
  end: Type.Optional(Type.String()),
  capital: Type.Optional(Type.Number({ default: 1_000_000 })),
  top_n: Type.Optional(Type.Number({ default: 5, description: "返回前 N 个" })),
});

// 工具 6: simulate_stop_loss
const SimulateSlParams = Type.Object({
  symbol: Type.String(),
  stop_loss_pct: Type.Optional(Type.Number({ default: 0.05, description: "止损比例 0.05 = 5%" })),
  fast_window: Type.Optional(Type.Number({ default: 5 })),
  slow_window: Type.Optional(Type.Number({ default: 30 })),
  start: Type.Optional(Type.String({ default: "2023-01-01" })),
  end: Type.Optional(Type.String()),
  capital: Type.Optional(Type.Number({ default: 1_000_000 })),
  use_trend_filter: Type.Optional(Type.Boolean({ default: false })),
});

// 工具 7: run_walk_forward
const WalkForwardParams = Type.Object({
  symbol: Type.String(),
  strategy_type: Type.Optional(Type.String({ default: "double_ma" })),
  params: Type.Optional(Type.Object({}, { additionalProperties: true })),
  train_start: Type.Optional(Type.String({ default: "2023-01-01" })),
  train_end: Type.Optional(Type.String({ default: "2024-12-31" })),
  test_start: Type.Optional(Type.String({ default: "2025-01-01" })),
  test_end: Type.Optional(Type.String({ default: "2026-12-31" })),
  capital: Type.Optional(Type.Number({ default: 1_000_000 })),
});

// 工具 2: scan_ma_params
const ScanMaParamsT = Type.Object({
  symbol: Type.String(),
  fast_range: Type.Optional(Type.Array(Type.Number(), { default: [5, 10, 15] })),
  slow_range: Type.Optional(Type.Array(Type.Number(), { default: [20, 30, 60] })),
  start: Type.Optional(Type.String({ default: "2023-01-01" })),
  end: Type.Optional(Type.String()),
  capital: Type.Optional(Type.Number({ default: 1_000_000 })),
  use_trend_filter: Type.Optional(Type.Boolean({ default: false })),
  top_n: Type.Optional(Type.Number({ default: 5 })),
});

// 工具 3: scan_multi_stocks
const ScanMultiStocksT = Type.Object({
  symbols: Type.Array(Type.String(), { description: "A 股代码列表" }),
  fast_window: Type.Optional(Type.Number({ default: 5 })),
  slow_window: Type.Optional(Type.Number({ default: 30 })),
  start: Type.Optional(Type.String({ default: "2023-01-01" })),
  end: Type.Optional(Type.String()),
  capital: Type.Optional(Type.Number({ default: 1_000_000 })),
  use_trend_filter: Type.Optional(Type.Boolean({ default: false })),
});

// 工具 8: generate_pine_script
const GenPineParams = Type.Object({
  strategy_type: Type.Optional(Type.String({ default: "double_ma" })),
  fast_window: Type.Optional(Type.Number({ default: 5 })),
  slow_window: Type.Optional(Type.Number({ default: 30 })),
  use_trend_filter: Type.Optional(Type.Boolean({ default: false })),
  trend_window: Type.Optional(Type.Number({ default: 200 })),
});

// 工具 9: get_top_results（直接读 cache 文件，不调 Python）
const GetTopParams = Type.Object({
  sort_by: Type.Optional(Type.String({ default: "sharpe_ratio" })),
  top_n: Type.Optional(Type.Number({ default: 10 })),
  strategy_filter: Type.Optional(Type.String({ description: "过滤 DoubleMa 或 DoubleMa+MA200" })),
});

// 工具 10: validate_strategy
const ValidateParams = Type.Object({
  stats_json: Type.String({ description: 'JSON 字符串，run_backtest 输出的 stats dict' }),
});

type RunBacktestP = Static<typeof RunBacktestParams>;
type RunStrategyP = Static<typeof RunStrategyParams>;
type ScanStrategyP = Static<typeof ScanStrategyParamsT>;
type SimulateSlP = Static<typeof SimulateSlParams>;
type WalkForwardP = Static<typeof WalkForwardParams>;
type ScanMaP = Static<typeof ScanMaParamsT>;
type ScanMultiP = Static<typeof ScanMultiStocksT>;
type GenPineP = Static<typeof GenPineParams>;
type GetTopP = Static<typeof GetTopParams>;
type ValidateP = Static<typeof ValidateParams>;

// ---- Plugin ----
export default defineToolPlugin({
  id: "quant-research",
  name: "A 股量化研究",
  description:
    "A 股量化研究工具集：回测、参数扫描、5 种策略对比、walk-forward 过拟合检测、stop loss 估算、Pine Script 生成。10 个工具全部基于 vnpy + tushare 真实 A 股日线（不复权到 2018）。",
  tools: (tool) => [
    // 工具 1: 单次回测（双均线，兼容旧）
    tool({
      name: "quant_run_backtest",
      description:
        "跑一次 A 股双均线回测。返回完整 stats：总收益、年化、Sharpe、最大回撤、交易笔数等。",
      parameters: RunBacktestParams,
      execute: async (p: RunBacktestP) => {
        // run_backtest 旧 API = double_ma/double_ma_trend
        if (p.use_trend_filter) {
          return runPythonTool("_run_backtest_core", {
            vt_symbol: p.symbol,
            start: p.start ?? "2023-01-01",
            end: p.end ?? new Date().toISOString().slice(0, 10),
            capital: p.capital ?? 1_000_000,
            strategy_type: "double_ma_trend",
            params: { fast_window: p.fast_window ?? 5, slow_window: p.slow_window ?? 30 },
          });
        }
        return runPythonTool("_run_backtest_core", {
          vt_symbol: p.symbol,
          start: p.start ?? "2023-01-01",
          end: p.end ?? new Date().toISOString().slice(0, 10),
          capital: p.capital ?? 1_000_000,
          strategy_type: "double_ma",
          params: { fast_window: p.fast_window ?? 5, slow_window: p.slow_window ?? 30 },
        });
      },
    }),

    // 工具 2: 双均线网格搜索
    tool({
      name: "quant_scan_ma_params",
      description:
        "双均线参数网格搜索。返回按 Sharpe 排序的 TOP N。",
      parameters: ScanMaParamsT,
      execute: async (p: ScanMaP) => {
        const fastRange = p.fast_range ?? [5, 10, 15];
        const slowRange = p.slow_range ?? [20, 30, 60];
        // 自己实现笛卡尔积（在 TS 里更简单）
        const results: JsonResult[] = [];
        for (const fast of fastRange) {
          for (const slow of slowRange) {
            if (slow <= fast) continue;
            const r = runPythonTool("_run_backtest_core", {
              vt_symbol: p.symbol,
              start: p.start ?? "2023-01-01",
              end: p.end ?? new Date().toISOString().slice(0, 10),
              capital: p.capital ?? 1_000_000,
              strategy_type: p.use_trend_filter ? "double_ma_trend" : "double_ma",
              params: { fast_window: fast, slow_window: slow },
            });
            results.push(r as JsonResult);
          }
        }
        results.sort((a, b) =>
          (b["sharpe_ratio"] as number) - (a["sharpe_ratio"] as number));
        return results.slice(0, p.top_n ?? 5);
      },
    }),

    // 工具 3: 多股对比
    tool({
      name: "quant_scan_multi_stocks",
      description: "多只 A 股同参数横向对比，按 Sharpe 排序。",
      parameters: ScanMultiStocksT,
      execute: async (p: ScanMultiP) => {
        const results: JsonResult[] = [];
        for (const sym of p.symbols) {
          const r = runPythonTool("_run_backtest_core", {
            vt_symbol: sym,
            start: p.start ?? "2023-01-01",
            end: p.end ?? new Date().toISOString().slice(0, 10),
            capital: p.capital ?? 1_000_000,
            strategy_type: p.use_trend_filter ? "double_ma_trend" : "double_ma",
            params: { fast_window: p.fast_window ?? 5, slow_window: p.slow_window ?? 30 },
          });
          results.push(r as JsonResult);
        }
        results.sort((a, b) =>
          (b["sharpe_ratio"] as number) - (a["sharpe_ratio"] as number));
        return results;
      },
    }),

    // 工具 4: 通用策略回测
    tool({
      name: "quant_run_strategy",
      description:
        "跑任意 5 种策略（double_ma/double_ma_trend/atr_rsi/boll_channel/king_keltner）。",
      parameters: RunStrategyParams,
      execute: async (p: RunStrategyP) => {
        return runPythonTool("_run_backtest_core", {
          vt_symbol: p.symbol,
          start: p.start ?? "2023-01-01",
          end: p.end ?? new Date().toISOString().slice(0, 10),
          capital: p.capital ?? 1_000_000,
          strategy_type: p.strategy_type ?? "double_ma",
          params: p.params ?? {},
        });
      },
    }),

    // 工具 5: 通用策略网格搜索（流式进度）
    tool({
      name: "quant_scan_strategy_params",
      description: "任意策略的参数网格搜索。流式返回每个组合的进度（OpenClaw UI 实时显示）。",
      parameters: ScanStrategyParamsT,
      execute: async (p: ScanStrategyP, _config: unknown, ctx: {
        onUpdate?: (partial: { content: Array<{ type: "text"; text: string }>; details: unknown }) => void;
      }) => {
        return await runPythonStream(
          "scan_strategy_params_core",
          {
            symbol: p.symbol,
            strategy_type: p.strategy_type ?? "double_ma",
            param_grid: p.param_grid,
            start: p.start ?? "2023-01-01",
            end: p.end ?? new Date().toISOString().slice(0, 10),
            capital: p.capital ?? 1_000_000,
            top_n: p.top_n ?? 5,
          },
          ctx.onUpdate,
        );
      },
    }),

    // 工具 6: stop loss 估算
    tool({
      name: "quant_simulate_stop_loss",
      description: "在双均线策略上加 stop loss，对比无止损的回撤改善。",
      parameters: SimulateSlParams,
      execute: async (p: SimulateSlP) => {
        return runPythonTool("simulate_stop_loss_core", {
          symbol: p.symbol,
          stop_loss_pct: p.stop_loss_pct ?? 0.05,
          fast_window: p.fast_window ?? 5,
          slow_window: p.slow_window ?? 30,
          start: p.start ?? "2023-01-01",
          end: p.end ?? new Date().toISOString().slice(0, 10),
          capital: p.capital ?? 1_000_000,
          use_trend_filter: p.use_trend_filter ?? false,
        });
      },
    }),

    // 工具 7: walk-forward 验证
    tool({
      name: "quant_run_walk_forward",
      description:
        "Walk-Forward 验证：train 段 (默认 2023-2024) + test 段 (2025-2026)，对比 Sharpe 衰减判定过拟合。",
      parameters: WalkForwardParams,
      execute: async (p: WalkForwardP) => {
        return runPythonTool("run_walk_forward_core", {
          symbol: p.symbol,
          strategy_type: p.strategy_type ?? "double_ma",
          params: p.params ?? {},
          train_start: p.train_start ?? "2023-01-01",
          train_end: p.train_end ?? "2024-12-31",
          test_start: p.test_start ?? "2025-01-01",
          test_end: p.test_end ?? "2026-12-31",
          capital: p.capital ?? 1_000_000,
        });
      },
    }),

    // 工具 8: 生成 Pine Script
    tool({
      name: "quant_generate_pine_script",
      description: "生成可在 TradingView 跑的 Pine Script v6 代码（含 alert webhook）。",
      parameters: GenPineParams,
      execute: async (p: GenPineP) => {
        const useTrend = p.use_trend_filter ?? false;
        const fast = p.fast_window ?? 5;
        const slow = p.slow_window ?? 30;
        const trend = p.trend_window ?? 200;
        const entryCond = useTrend
          ? `ta.crossover(ma${fast}, ma${slow}) and close > ma${trend}\n`
          : `ta.crossover(ma${fast}, ma${slow})\n`;
        const exitCond = `ta.crossunder(ma${fast}, ma${slow})\n`;
        const plots = useTrend
          ? `plot(ma${fast}, 'MA${fast}', color.orange)\nplot(ma${slow}, 'MA${slow}', color.blue)\nplot(ma${trend}, 'MA${trend}', color.gray, linewidth=2)`
          : `plot(ma${fast}, 'MA${fast}', color.orange)\nplot(ma${slow}, 'MA${slow}', color.blue)`;
        return `//@version=6
strategy("DoubleMA(${fast},${slow})${useTrend ? '+MA' + trend : ''}", overlay=true, default_qty_type=strategy.fixed, default_qty=100)
fast_len  = input.int(${fast}, "Fast MA Length")
slow_len  = input.int(${slow}, "Slow MA Length")
${useTrend ? `trend_len = input.int(${trend}, "Trend MA Length")` : "// 不使用趋势过滤"}
ma${fast}  = ta.ema(close, fast_len)
ma${slow}  = ta.ema(close, slow_len)
${useTrend ? `ma${trend} = ta.ema(close, trend_len)` : ""}
long_cond  = ${entryCond}short_cond = ${exitCond}
if long_cond
    strategy.entry("Long", strategy.long)
if short_cond
    strategy.close("Long")
${plots}
alert_msg = '{{' + \\
    '"secret": "YOUR_SECRET",' + \\
    '"event_id": "tv-{{strategy.order.id}}-{{timenow}}",' + \\
    '"action": "{{strategy.order.action}}",' + \\
    '"symbol": "{{ticker}}.{{syminfo.prefix}}",' + \\
    '"price": {{close}},' + \\
    '"volume": {{strategy.order.contracts}},' + \\
    '"strategy": "double_ma(${fast},${slow})"' + \\
    '}}'
if long_cond or short_cond
    alert(alert_msg, alert.freq_once_per_bar_close)
`;
      },
    }),

    // 工具 9: 读历史扫描缓存（直接读 JSON，不调 Python）
    tool({
      name: "quant_get_top_results",
      description: "读 backtest_scan 跑过的 30 条历史结果，按 Sharpe 排序。",
      parameters: GetTopParams,
      execute: async (p: GetTopP) => {
        const fs = await import("node:fs/promises");
        const cachePath = resolve(import.meta.dirname, "..", "..", "data", "backtest_scan.json");
        try {
          const raw = await fs.readFile(cachePath, "utf-8");
          const data: JsonResult[] = JSON.parse(raw);
          let filtered = data;
          if (p.strategy_filter) {
            filtered = filtered.filter((r) => r["strategy"] === p.strategy_filter);
          }
          const sortBy = p.sort_by ?? "sharpe_ratio";
          filtered.sort((a, b) =>
            (b[sortBy] as number) - (a[sortBy] as number));
          return filtered.slice(0, p.top_n ?? 10);
        } catch (e) {
          return { error: `读缓存失败: ${(e as Error).message}` };
        }
      },
    }),

    // 工具 10: validate_strategy
    tool({
      name: "quant_validate_strategy",
      description: "基于 stats dict 给风险评级和建议（🟢/🟡/🟠/🔴）。",
      parameters: ValidateParams,
      execute: async (p: ValidateP) => {
        const stats = JSON.parse(p.stats_json);
        const totalRet = (stats["total_return"] ?? 0) * 100;
        const annualRet = (stats["annual_return"] ?? 0) * 100;
        const sharpe = stats["sharpe_ratio"] ?? 0;
        const maxDd = (stats["max_ddpercent"] ?? 0) * 100;
        const trades = stats["total_trade_count"] ?? 0;
        const totalDays = stats["total_days"] ?? 1;
        const profitDays = stats["profit_days"] ?? 0;
        const winRate = (profitDays / Math.max(totalDays, 1)) * 100;

        const retGrade = totalRet > 30 ? "🟢 优秀" : totalRet > 10 ? "🟡 良好" : totalRet > 0 ? "🟠 一般" : "🔴 亏损";
        const sharpeGrade = sharpe > 1.0 ? "🟢 优秀" : sharpe > 0.5 ? "🟡 合格" : sharpe > 0 ? "🟠 偏弱" : "🔴 差";
        const ddGrade = maxDd > -10 ? "🟢 小" : maxDd > -20 ? "🟡 中" : maxDd > -40 ? "🟠 较大" : "🔴 极大";
        const overall = sharpe > 0.5 && maxDd > -20 && totalRet > 10
          ? "🟢 建议上 paper trading 实盘验证"
          : sharpe > 0 && totalRet > 0 && maxDd > -30
          ? "🟡 可以上 paper，但仓位别大（<30% 资金）"
          : sharpe > 0
          ? "🟠 信号不显著，建议换参数或加过滤"
          : "🔴 策略不可用，pass";

        return [
          "📊 策略评估报告",
          "",
          `总收益: ${totalRet >= 0 ? "+" : ""}${totalRet.toFixed(2)}%  ${retGrade}`,
          `年化收益: ${annualRet >= 0 ? "+" : ""}${annualRet.toFixed(2)}%`,
          `Sharpe: ${sharpe >= 0 ? "+" : ""}${sharpe.toFixed(2)}  ${sharpeGrade}`,
          `最大回撤: ${maxDd.toFixed(2)}%  ${ddGrade}`,
          `交易笔数: ${trades}`,
          `日胜率: ${winRate.toFixed(1)}%`,
          "",
          `综合评级: ${overall}`,
        ].join("\n");
      },
    }),
  ],
});
