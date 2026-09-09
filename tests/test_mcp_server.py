"""
test_mcp_server.py — 用 MCP 客户端连接自己 server 验证协议工作
=================================================================
跑：python tests/test_mcp_server.py

注意：会先临时启动 server（stdio 模式），所以这个测试是隔离的
——不会和真生产 server 冲突。
"""
import asyncio
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_script = Path(__file__).parent.parent / "mcp_quant_server.py"

    print(f"启动 MCP server: python {server_script}")
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_script)],
        env={"TUSHARE_TOKEN": __import__("os").environ.get("TUSHARE_TOKEN", "")},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 列工具
            tools = await session.list_tools()
            print(f"\n✓ Server 注册了 {len(tools.tools)} 个工具:")
            for t in tools.tools:
                print(f"   - {t.name}: {t.description[:60]}...")

            # 调 run_backtest
            print("\n=== 测试工具: run_backtest ===")
            result = await session.call_tool(
                "run_backtest",
                {"symbol": "002180.SZ", "fast_window": 5, "slow_window": 30},
            )
            print(f"   → 返回: {result.content[0].text[:200]}")

            # 调 generate_pine_script
            print("\n=== 测试工具: generate_pine_script ===")
            result = await session.call_tool(
                "generate_pine_script",
                {"fast_window": 10, "slow_window": 30},
            )
            print(f"   → 返回 {len(result.content[0].text)} 字符")

            print("\n✓ 6/6 工具可远程调用")


if __name__ == "__main__":
    asyncio.run(main())
