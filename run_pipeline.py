"""
run_pipeline.py — 一键运行三层筛选 pipeline
==============================================

1. 量化评分（tushare + Lean 回测）— 5 分钟
2. 研报增强（OpenClaw 触发 + 研报因子加分）— 30 分钟
3. 最终输出：复合排名 + 推荐 Top N

用法:
  python run_pipeline.py
  python run_pipeline.py --codes 002180.SZ 000100.SZ 688122.SH 688515.SH
  python run_pipeline.py --index 000300.SH --top 20
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(description="三层筛选 pipeline")
    parser.add_argument("--codes", nargs="*", help="自定义股票列表")
    parser.add_argument("--index", default="000300.SH", help="指数代码")
    parser.add_argument("--top", type=int, default=20, help="研报增强 Top N")
    parser.add_argument("--skip-research", action="store_true", help="跳过研报层")
    args = parser.parse_args()

    print("="*70)
    print("  QUANT-POC PIPELINE — 三层筛选")
    print(f"  启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Layer 1: 量化评分
    print(f"\n{'─'*70}")
    print("Layer 1: 量化评分 (tushare + Lean 回测)")
    print(f"{'─'*70}")

    from quant_screener import main as screener_main
    import sys as _sys
    _sys.argv = ["quant_screener.py"]
    if args.codes:
        _sys.argv += ["--codes"] + args.codes
    else:
        _sys.argv += ["--index", args.index]
    _sys.argv += ["--top", "100"]  # 取 100 再筛 top
    screener_main()

    # Layer 2: 研报增强
    if not args.skip_research:
        print(f"\n{'─'*70}")
        print("Layer 2: 研报增强 (OpenClaw + 研报因子)")
        print(f"{'─'*70}")
        _sys.argv = ["batch_openclaw_research.py", "--top", str(args.top)]
        from batch_openclaw_research import main as research_main
        research_main()

    # Layer 3: 复合排名
    print(f"\n{'─'*70}")
    print("Layer 3: 复合排名")
    print(f"{'─'*70}")

    enriched_path = Path("data/research_enriched.json")
    if enriched_path.exists():
        results = json.loads(enriched_path.read_text(encoding="utf-8"))
    else:
        results = json.loads(Path("data/quant_screen.json").read_text(encoding="utf-8"))
        for r in results:
            r["final_score"] = r["score"]

    # 最终推荐
    buy_threshold = 50  # 总分 > 50 才考虑
    print(f"\n推荐（总分 > {buy_threshold}）:")
    print(f"  {'代码':<12} {'总分':<5} {'Sharpe':<8} {'PE':<8} {'决策'}")
    print(f"  {'─'*12} {'─'*5} {'─'*8} {'─'*8} {'─'*10}")

    for s in results:
        if s["final_score"] < buy_threshold:
            continue
        pe = f"{s.get('pe'):.1f}" if s.get('pe') else "—"
        decision = "🟢 买入" if s["final_score"] >= 60 else "🟡 观察"
        if s.get("sharpe", 0) < 0:
            decision = "🔴 跳过（Sharpe 负）"
        print(f"  {s['code']:<12} {s['final_score']:>3}   "
              f"{s.get('sharpe', 0):+.3f}  {pe:<8} {decision}")

    print(f"\n  ✓ Pipeline 完成 — 结果存到 data/research_enriched.json")
    print(f"  下一步: 用 Lean 策略在 Top N 上做 walk-forward 验证")


if __name__ == "__main__":
    main()
