"""
check_futu_env.py — 富途 OpenD 连通性检查
=======================================
跑这个：python tools/check_futu_env.py
- 不用真下单，只检查 SDK 版本 + 网络连通 + 账户列表
"""
import os
import sys

import futu
from futu import OpenSecTradeContext, RET_OK


def check_sdk_version():
    print(f"[1/3] futu-api 版本: {futu.__version__}")
    need = "10.4.6408"
    cur = futu.__version__
    parts_cur = [int(x) for x in cur.split(".")]
    parts_need = [int(x) for x in need.split(".")]
    if parts_cur < parts_need:
        print(f"  ✗ 版本过低，需要 ≥ {need}")
        print(f"  → pip install --upgrade \"futu-api>={need}\"")
        return False
    print(f"  ✓ 版本满足 (≥ {need})")
    return True


def check_opend_connection():
    print(f"\n[2/3] 连接 OpenD...")
    host = os.environ.get("FUTU_HOST", "127.0.0.1")
    port = int(os.environ.get("FUTU_PORT", "11111"))
    print(f"  地址: {host}:{port}")
    try:
        ctx = OpenSecTradeContext(host=host, port=port)
    except Exception as e:
        print(f"  ✗ 创建 context 失败: {e}")
        return False

    try:
        ret, data = ctx.get_acc_list()
        if ret != RET_OK:
            print(f"  ✗ get_acc_list 失败: {data}")
            return False
        if data is None or data.empty:
            print(f"  ⚠ 已连上但账户列表为空（先在 OpenD-GUI 解锁交易）")
            return True
        print(f"  ✓ 已连接，账户数: {len(data)}")
        print(f"  账户列表:")
        for _, row in data.iterrows():
            print(f"    - acc_id={row.get('acc_id')} type={row.get('acc_type')} state={row.get('acc_state')}")
        return True
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def check_quote_optional():
    print(f"\n[3/3] 检查行情接口（可选）...")
    try:
        from futu import OpenQuoteContext
        host = os.environ.get("FUTU_HOST", "127.0.0.1")
        port = int(os.environ.get("FUTU_PORT", "11111"))
        q = OpenQuoteContext(host=host, port=port)
        ret, data = q.get_stock_quote(["SZ.002180"])
        q.close()
        if ret == 0 and not data.empty:
            print(f"  ✓ 行情接口正常, 002180 当前价: {data.iloc[0]['last_price']}")
            return True
        print(f"  ⚠ 行情接口未响应（市场未开盘？）")
        return False
    except Exception as e:
        print(f"  ⚠ 行情检查跳过: {e}")
        return False


def main():
    print("=" * 50)
    print("富途 OpenD 环境检查")
    print("=" * 50)

    if not check_sdk_version():
        sys.exit(1)
    if not check_opend_connection():
        sys.exit(2)
    check_quote_optional()

    print("\n" + "=" * 50)
    print("✓ 环境就绪，可以开始用 BrokerFutu")
    print("=" * 50)


if __name__ == "__main__":
    main()
