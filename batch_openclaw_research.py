"""
batch_openclaw_research.py — 批量 OpenClaw 深度研报
===================================================

输入：quant_screener 输出的 Top N 股票
输出：每只股的 OpenClaw 深度研报（自动化）

⚠️ 简化版：直接调用 OpenClaw quant-XXX agent prompt
   实际生产应该用 OpenClaw API / agent invocation

用法:
  python batch_openclaw_research.py --input data/quant_screen.json --top 5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def trigger_openclaw_research(code: str, name: str = "") -> dict:
    """
    触发 OpenClaw 深度研报。

    简化版：直接打印 OpenClaw agent 启动命令。
    实际生产用 OpenClaw API 调用 agent。
    """
    # 1. 准备 agent prompt
    code_clean = code.replace(".SZ", "").replace(".SH", "").replace(".HK", "")
    market = "SZ" if ".SZ" in code else "SH" if ".SH" in code else "HK"
    agent_name = f"quant-{code_clean}"

    print(f"\n  启动 OpenClaw Agent: {agent_name}")
    print(f"  生成 {code} {name} 深度研报...")

    # 这里实际应该调 OpenClaw API
    # 简化：用 quant_screener 的数据 + 加上"研报增强因子"做伪研报
    return {
        "code": code,
        "agent": agent_name,
        "status": "pending",
        "report_path": f"docs/research/{code_clean}_{datetime.now().strftime('%Y%m%d')}.md",
    }


def enrich_with_research_factors(screened: list) -> list:
    """
    在 quant_screener 基础上加研报增强因子：
    - 行业地位（超导垄断 / 行业龙头）
    - 政策催化（核聚变/军工/光伏等）
    - 机构覆盖（≥5 家 = 强共识）
    """
    # 简化版：基于代码的硬编码判断
    # 实际应该读研报内容
    RESEARCH_FACTORS = {
        "688122.SH": {
            "industry_pos": "超导材料国内 95% 垄断",
            "policy_catalyst": "核聚变 + 军工 + C919",
            "institutional_buy": 8,  # 8 家全看多
            "research_bonus": 25,  # 加 25 分
        },
        "002180.SZ": {
            "industry_pos": "打印机通用耗材",
            "policy_catalyst": "无",
            "institutional_buy": 2,
            "research_bonus": 5,
        },
        "000100.SZ": {
            "industry_pos": "家电",
            "policy_catalyst": "无",
            "institutional_buy": 5,
            "research_bonus": 5,
        },
        "688515.SH": {
            "industry_pos": "打印机通用耗材",
            "policy_catalyst": "国产替代",
            "institutional_buy": 3,
            "research_bonus": 10,
        },
        "00700.HK": {
            "industry_pos": "互联网",
            "policy_catalyst": "南向资金",
            "institutional_buy": 30,  # 大量覆盖
            "research_bonus": 15,
        },
    }

    for stock in screened:
        code = stock["code"]
        factors = RESEARCH_FACTORS.get(code, {})
        stock["research_factors"] = factors
        stock["score"] = stock.get("score", 0) + factors.get("research_bonus", 0)
        stock["final_score"] = stock["score"]

    return screened


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/quant_screen.json", help="quant_screener 输出")
    parser.add_argument("--top", type=int, default=5, help="要研报的 Top N")
    parser.add_argument("--out", default="data/research_enriched.json", help="输出")
    args = parser.parse_args()

    print("="*70)
    print("  batch_openclaw_research.py — 研报增强")
    print("="*70)

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"❌ {in_path} 不存在，先跑 quant_screener.py")
        return

    stocks = json.loads(in_path.read_text(encoding="utf-8"))
    print(f"\n[1] 读 {len(stocks)} 只股 from {in_path}")

    # 1. 取 Top N
    top = stocks[:args.top]
    print(f"\n[2] Top {args.top}:")
    for s in top:
        print(f"    {s['code']:<12} 量化分 {s['score']:>3}  Sharpe {s.get('sharpe', 0):+.3f}")

    # 2. 加研报增强因子
    print(f"\n[3] 加研报增强因子...")
    enriched = enrich_with_research_factors(top)
    enriched.sort(key=lambda x: -x["final_score"])

    # 3. 触发 OpenClaw 深度研报（实际会调用 agent）
    print(f"\n[4] 触发 OpenClaw 深度研报（{len(enriched)} 只）...")
    for s in enriched:
        trigger_openclaw_research(s["code"], s.get("name", ""))

    # 4. 输出
    print(f"\n[5] 最终排名（量化分 + 研报加分）:")
    print(f"  {'代码':<12} {'原分':<5} {'研报加分':<8} {'总分':<5} {'Sharpe'}")
    print(f"  {'─'*12} {'─'*5} {'─'*8} {'─'*5} {'─'*8}")
    for s in enriched:
        research_bonus = s.get("research_factors", {}).get("research_bonus", 0)
        print(f"  {s['code']:<12} {s['score']-research_bonus:>3}   "
              f"+{research_bonus:<7} {s['final_score']:>3}   "
              f"{s.get('sharpe', 0):+.3f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(enriched, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✓ 存到 {out}")


if __name__ == "__main__":
    main()
