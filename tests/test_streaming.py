"""
test_streaming.py — 模拟 OpenClaw 插件的 streaming 协议
======================================================

跑：python tests/test_streaming.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    """直接调 quant_core.scan_strategy_params_core，验证 PROGRESS/RESULT 协议能跑通。"""
    import subprocess

    # 这个 Python 代码是 Node 注入到 Python 的 pyCode
    # 注意：避免 f-string 反斜杠（Python 3.11）
    py_code = r'''
import sys, json, os
sys.path.insert(0, r'C:\Users\18566\Desktop\quant-poc')
os.chdir(r'C:\Users\18566\Desktop\quant-poc')
import quant_core

# Monkey-patch：每跑一个组合 print PROGRESS:
_original = quant_core._run_backtest_core
def _patched(*args, **kwargs):
    r = _original(*args, **kwargs)
    msg = "完成 params=" + json.dumps(r.get("params", {})) + " sharpe=" + str(round(r.get("sharpe_ratio", 0), 3))
    print("PROGRESS:" + json.dumps({"msg": msg, "result": r}, ensure_ascii=False), flush=True)
    return r
quant_core._run_backtest_core = _patched

result = quant_core.scan_strategy_params_core(
    symbol='002180.SZ',
    strategy_type='double_ma',
    param_grid={'fast_window': [3, 5, 8], 'slow_window': [20, 30]},
    start='2023-01-01', end='2026-09-04', capital=1_000_000, top_n=3,
)

def _to_native(x):
    if hasattr(x, 'item'): return x.item()
    if isinstance(x, (list, tuple)): return [_to_native(v) for v in x]
    if isinstance(x, dict): return {k: _to_native(v) for k, v in x.items()}
    return x
print("RESULT:" + json.dumps(_to_native(result), ensure_ascii=False), flush=True)
'''

    print(f"启动 Python 子进程，预期: PROGRESS 行 + 最后 RESULT 行\n")
    import os
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "TUSHARE_TOKEN": os.environ.get("TUSHARE_TOKEN", "")}
    # hermes-agent runtime 缺 HOME，会 pathlib 报错
    if "HOME" not in env:
        env["HOME"] = os.path.expanduser("~") or "C:\\Users\\18566"
    if "USERPROFILE" not in env:
        env["USERPROFILE"] = "C:\\Users\\18566"
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", py_code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    progress_count = 0
    final_result = None
    buf = ""

    # 按行读 stdout，模拟 Node 的解析
    while True:
        chunk = await proc.stdout.read(4096)
        if not chunk:
            break
        buf += chunk.decode("utf-8")
        lines = buf.split("\n")
        buf = lines.pop() or ""

        for line in lines:
            if not line.strip():
                continue
            if line.startswith("PROGRESS:"):
                progress_count += 1
                payload = json.loads(line[len("PROGRESS:"):])
                print(f"  📊 [PROGRESS {progress_count}] {payload['msg']}")
            elif line.startswith("RESULT:"):
                final_result = json.loads(line[len("RESULT:"):])
                print(f"\n  ✓ RESULT: {len(final_result)} 个结果")
                for r in final_result:
                    print(f"    {r['params']} sharpe={r['sharpe_ratio']:+.3f} ret={r['total_return']*100:+.1f}%")
            else:
                print(f"  [other] {line[:100]}")

    await proc.wait()
    # stderr 可能含 vnpy 输出的非 utf-8 字符，用 replace 跳过
    stderr_bytes = await proc.stderr.read()
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        print(f"\n❌ Python exit {proc.returncode}")
        print(f"stderr: {stderr[-500:]}")
        return

    print(f"\n{'='*50}")
    print(f"✓ 流式协议测试通过")
    print(f"  - PROGRESS 事件: {progress_count} 个")
    print(f"  - 最终结果: {len(final_result) if final_result else 0} 个")
    print(f"  - 期望: 6 个 PROGRESS（3x2 笛卡尔积，全部 fast<slow 都满足）")
    if progress_count != 6:
        print(f"  ⚠️ 实际 PROGRESS 事件 {progress_count} != 期望 6")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
