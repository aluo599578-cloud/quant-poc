# 富途 OpenD 接入路径（计划中）

> ⚠️ **当前未启用**。本项目目前只用 SQLite 模拟撮合，不接真实券商。  
> 以下是从 paper 切到实盘的步骤清单，按难度递增。

## 目标

把 `app/paper_engine.py` 的"立即按 alert 价格成交"换成"调用富途 OpenD 下单 API"，并定时从富途拉真实成交回来对账。

## 阶段 0：前置条件

- [ ] **安装富途牛牛客户端**（≥10.4.6408）
  - 下载：https://www.futunn.com/download
- [ ] **申请量化交易权限**
  - 在富途牛牛 App 内申请，需身份认证 + 风险测评
  - 申请路径：我 → 量化交易 → 申请
- [ ] **下载 OpenD-GUI**（独立于客户端）
  - 通常和富途牛牛一起装
- [ ] **设置交易密码**
  - 在富途牛牛 → 设置 → 交易密码
- [ ] **安装 Python SDK**
  ```bash
  pip install "futu-api>=10.4.6408"
  ```
- [ ] **启动 OpenD-GUI**（市场时段内）
  - 桌面快捷方式或 `C:\Program Files\Futu\OpenD\OpenD-GUI.exe`
  - 用富途账号登录
  - 点击"解锁交易"按钮输入交易密码
  - 确认右下角状态显示"已连接"

## 阶段 1：环境验证（5 分钟）

写 `tools/check_futu_env.py`：

```python
"""检查 futu-api SDK 和 OpenD 连通性"""
import os
from futu import OpenSecTradeContext, TrdEnv, RET_OK, TrdMarket

def check_sdk_version():
    import futu
    print(f"futu-api 版本: {futu.__version__}")
    assert futu.__version__ >= "10.4.6408", "SDK 版本过低"

def check_opend_connection():
    host = os.environ.get("FUTU_HOST", "127.0.0.1")
    port = int(os.environ.get("FUTU_PORT", "11111"))
    ctx = OpenSecTradeContext(host=host, port=port)
    ret, data = ctx.get_account_list()
    assert ret == RET_OK, f"OpenD 未连接: {data}"
    print(f"OpenD 已连接 ({host}:{port})")
    print(f"账户列表:\n{data}")
    ctx.close()

if __name__ == "__main__":
    check_sdk_version()
    check_opend_connection()
```

跑 `python tools/check_futu_env.py` 通过后才能进阶段 2。

## 阶段 2：写 broker 适配器（2-3 天）

新建 `app/broker_futu.py`：

```python
"""
broker_futu.py — 富途券商适配器

跟 PaperEngine 同接口（submit / positions_snapshot / account_snapshot），
实现类替换 paper 即可从模拟切到实盘。
"""
import os
from futu import (
    OpenSecTradeContext, OrderType, TrdSide, TrdEnv, TrdMarket,
    RET_OK, OrderStatus
)


class BrokerFutu:
    """富途实盘券商适配器。"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 11111,
                 trd_env: TrdEnv = TrdEnv.SIMULATE):
        self.trd_env = trd_env  # 默认模拟盘
        self.ctx = OpenSecTradeContext(host=host, port=port)
    
    def submit(self, *, event_id, symbol, action, price, volume, strategy=None):
        """向富途提交订单，返回成交信息。"""
        # vt_symbol → 富途 code
        # 002180.SZSE → 'SZ.002180',  688122.SSE → 'SH.688122'
        code = self._to_futu_code(symbol)
        
        # 买卖方向
        trd_side = TrdSide.BUY if action == "buy" else TrdSide.SELL
        
        # 下单（市价单）
        ret, data = self.ctx.place_order(
            price=price,           # 市价单 price 仍需传（用当前价）
            qty=volume,
            code=code,
            trd_side=trd_side,
            order_type=OrderType.MARKET,
            trd_env=self.trd_env,
            remark=f"quant-poc:{event_id}",
        )
        if ret != RET_OK:
            raise RuntimeError(f"下单失败: {data}")
        
        order_id = data.iloc[0]["order_id"]
        
        # 等待成交（实际生产应该异步 + 回调）
        # 这里简化：轮询直到成交
        for _ in range(30):
            ret, data = self.ctx.get_order_fill_list(order_id=order_id)
            if ret == RET_OK and not data.empty:
                fill = data.iloc[0]
                return fill
            import time; time.sleep(0.5)
        
        raise TimeoutError(f"订单 {order_id} 30 秒内未成交")
    
    def positions_snapshot(self) -> list[dict]:
        ret, data = self.ctx.get_position_list(trd_env=self.trd_env)
        if ret != RET_OK:
            return []
        out = []
        for _, row in data.iterrows():
            out.append({
                "symbol": row["code"],
                "volume": int(row["qty"]),
                "avg_price": float(row["cost_price"]),
                "last_price": float(row["current_price"]),
                "market_value": float(row["market_val"]),
                "unrealized_pnl": float(row["unrealized_pl"]),
                "realized_pnl": float(row["realized_pl"]),
            })
        return out
    
    def account_snapshot(self) -> dict:
        ret, data = self.ctx.get_assets(trd_env=self.trd_env)
        if ret != RET_OK:
            return {}
        row = data.iloc[0]
        return {
            "cash": float(row["cash"]),
            "market_value": float(row["market_val"]),
            "equity": float(row["total_assets"]),
            "init_cash": float(row["total_assets"]) - float(row["total_pl"]),
            "total_pnl": float(row["total_pl"]),
        }
    
    def _to_futu_code(self, vt_symbol: str) -> str:
        """002180.SZSE → 'SZ.002180'"""
        code, exch = vt_symbol.split(".")
        if exch in ("SZSE", "SZ"):
            return f"SZ.{code}"
        elif exch in ("SSE", "SH"):
            return f"SH.{code}"
        raise ValueError(f"unsupported exchange: {exch}")
    
    def close(self):
        self.ctx.close()
```

## 阶段 3：切换 broker（1 天）

在 `app/webhook_gateway.py` 加环境变量切换：

```python
# 默认 paper；设 BROKER=futu 切到富途
BROKER = os.environ.get("BROKER", "paper")
if BROKER == "futu":
    from .broker_futu import BrokerFutu
    engine = BrokerFutu(trd_env=TrdEnv.SIMULATE)  # 先模拟
else:
    from .paper_engine import PaperEngine
    engine = PaperEngine(db_path=DB_PATH)
```

## 阶段 4：异步对账（2 天）

Paper Engine 假设"立即按 alert 价格成交"。实盘不可能，订单可能：

- 部分成交
- 等待中
- 撤单
- 拒单

加一个 `tools/sync_futu_orders.py` 每 30 秒跑一次：

```python
"""
定时把富途账户的成交同步到本地 SQLite
这样 dashboard 显示的就是真实成交，不只是 webhook 推过来的事件
"""
```

## 阶段 5：风控层（1 天）

加：
- 单笔最大亏损（订单提交前预估）
- 日亏损上限（已实现 + 浮亏）
- 持仓集中度（单股占总资产不超过 X%）
- 最大回撤熔断（账户从最高点回撤超过 X% 全部清仓）

## 阶段 6：测试网 → 小仓位 → 正常仓位（2 周）

- [ ] 模拟账户跑 1 周，看链路是否稳定
- [ ] 真实账户 1 只股，1 手（100 股），跑 1 周
- [ ] 真实账户 1 只股，10 手，跑 1 周
- [ ] 真实账户多只股，完整仓位

每一步都要能在不亏钱的前提下发现问题。

## 关键风险

1. **OpenD 断连**——市场时段内 OpenD 重启 / 断网 / 掉线，要自动重连
2. **订单失败**——T+1 / 涨跌停 / 停牌 / 资金不足都会拒单
3. **滑点**——市价单按对手价成交，跟 alert 价格可能差 1-2%
4. **重复下单**——Paper Engine 已有幂等，但富途那边要查 order_id 状态
5. **风控**——没有风控就上实盘是赌博

## 时间估算

| 阶段 | 工作量 | 累计 |
|---|---|---|
| 0 | 1 天（等开通权限、装 OpenD）| 1 天 |
| 1 | 0.5 天 | 1.5 天 |
| 2 | 2-3 天 | 4-5 天 |
| 3 | 1 天 | 5-6 天 |
| 4 | 2 天 | 7-8 天 |
| 5 | 1 天 | 8-9 天 |
| 6 | 2 周（实盘逐步放量）| ~3 周 |

## 现在能做的（无 OpenD 也能）

1. 写好 `app/broker_futu.py` 代码（即使没 OpenD 也能 lint）
2. 用 mock 跑接口测试：`tools/test_broker_futu.py` 假装一个 OpenD 返回
3. 写好对账逻辑（用 paper 数据先验证 schema）
4. 文档化所有边界情况（T+1 / 涨跌停 / 停牌）

这样等 OpenD 装好，能最快速度切到实盘。
