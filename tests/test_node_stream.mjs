// test_node_stream.mjs — 直接 spawn quant-research 插件的 runPythonStream
// 跑：node tests/test_node_stream.mjs
import { spawn } from "node:child_process";

const PYTHON = process.env.QUANT_PYTHON || "python";
const PY_SCRIPT = "C:/Users/18566/Desktop/quant-poc/quant_core.py";

console.log("直接调 quant_core.scan_strategy_params_core（通过 Python 子进程流式）\n");

const pyCode = `
import sys, json, os
sys.path.insert(0, r'${PY_SCRIPT.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'.rsplit('\\\\', 1)[0])
os.chdir(r'C:/Users/18566/Desktop/quant-poc')
import quant_core
fn = getattr(quant_core, "scan_strategy_params_core")

# Monkey-patch 进度
_original = quant_core._run_backtest_core
def _patched(*args, **kwargs):
    r = _original(*args, **kwargs)
    msg = "完成 params=" + json.dumps(r.get("params", {})) + " sharpe=" + str(round(r.get("sharpe_ratio", 0), 3))
    print("PROGRESS:" + json.dumps({"msg": msg, "result": r}, ensure_ascii=False), flush=True)
    return r
quant_core._run_backtest_core = _patched

result = fn(
    symbol="002180.SZ",
    strategy_type="double_ma",
    param_grid={"fast_window": [3, 5, 8], "slow_window": [20, 30]},
    start="2023-01-01", end="2026-09-04", capital=1_000_000, top_n=3,
)

def _to_native(x):
    if hasattr(x, 'item'): return x.item()
    if isinstance(x, (list, tuple)): return [_to_native(v) for v in x]
    if isinstance(x, dict): return {k: _to_native(v) for k, v in x.items()}
    return x
print("RESULT:" + json.dumps(_to_native(result), ensure_ascii=False), flush=True)
`;

const env = { ...process.env, PYTHONUNBUFFERED: "1" };
if (!env.HOME) env.HOME = process.env.USERPROFILE || "C:\\\\Users\\\\18566";
if (!env.USERPROFILE) env.USERPROFILE = "C:\\\\Users\\\\18566";
if (!env.TUSHARE_TOKEN) env.TUSHARE_TOKEN = "";

const proc = spawn(PYTHON, ["-c", pyCode], { env });
let buf = "";
let progressCount = 0;
let result = null;
let stderr = "";

proc.stdout.on("data", (chunk) => {
  buf += chunk.toString("utf-8");
  const lines = buf.split("\n");
  buf = lines.pop() || "";
  for (const line of lines) {
    if (!line.trim()) continue;
    if (line.startsWith("PROGRESS:")) {
      progressCount++;
      try {
        const payload = JSON.parse(line.slice("PROGRESS:".length));
        console.log(`  📊 [PROGRESS ${progressCount}] ${payload.msg}`);
      } catch (e) { /* ignore */ }
    } else if (line.startsWith("RESULT:")) {
      try {
        result = JSON.parse(line.slice("RESULT:".length));
      } catch (e) { console.error("RESULT 解析失败:", e); }
    }
  }
});

proc.stderr.on("data", (chunk) => {
  stderr += chunk.toString("utf-8");
});

proc.on("close", (code) => {
  if (code !== 0) {
    console.error(`\n❌ Python exit ${code}`);
    console.error("stderr last 500:", stderr.slice(-500));
    process.exit(1);
  }
  console.log(`\n${'='.repeat(50)}`);
  console.log(`✓ Node 端流式测试通过`);
  console.log(`  - PROGRESS 事件: ${progressCount} 个`);
  console.log(`  - 最终结果: ${result ? result.length : 0} 个`);
  if (result) {
    for (const r of result) {
      console.log(`    ${JSON.stringify(r.params)} sharpe=${r.sharpe_ratio.toFixed(3)} ret=${(r.total_return * 100).toFixed(1)}%`);
    }
  }
  if (progressCount !== 6) {
    console.error(`❌ 期望 6 个 PROGRESS，实际 ${progressCount}`);
    process.exit(1);
  }
  console.log("✅ All checks passed");
});
