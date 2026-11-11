# 净销售额指标工作台

围绕**订单**与**退款明细**搭建的可版本化指标工作台。同一个"净销售额"在更换口径后，
历史报表仍能按旧规则复现：查询时选择口径版本、日期区间与门店，页面并排比较两版结果，
差额可一路下钻到原订单和退款明细。

技术栈：React 18 + TypeScript + Vite（前端）、FastAPI（后端）、DuckDB（存储与计算）。

## 两版口径

| 版本 | 退款归属时间字段 | 规则 |
| --- | --- | --- |
| V1（已发布冻结） | `orders.order_date` | 退款扣回原订单的**支付日** |
| V2（已发布冻结） | `refunds.refund_date` | 退款扣在**实际退款日** |

两版都输出四个指标：支付额、退款额、净销售额（`paid_amount - refund_amount`）、
按金额计算的退款率（`refund_amount / paid_amount`）。

## 三个易错点的处理

1. **一单多次退款不能放大支付额**：基础指标在 SQL 中分别独立聚合，再在 Python 侧按
   `(date, store_id)` 合并，绝不在一条 SQL 里把 orders 和 refunds 直接 join 后求和。
   演示数据中 O1001 支付 300、退款两次（50+70），支付额始终是 300。
2. **只有退款的日期不能丢行**：合并采用全外连接，退款日行照常出现，支付额补 0。
   V2 下 2026-11-02（S01）即此类行。
3. **退款率分母为零留空**：派生公式求值时除零（或引用值为空）返回 `null`，前端渲染为空白，
   不显示 0% 也不显示无穷大。合计行的退款率由合计金额重新计算，不是日退款率的平均。

## 指标定义与发布治理

指标定义保存：数据粒度（grain）、时间字段（time_field）、聚合方式（aggregation）、
来源表/金额字段，以及派生指标公式。

- 公式有独立的安全解析器（`backend/app/formula.py`），语法上只接受**指标引用、数字、
  括号和 + - \* /**，不经过任何 `eval`。
- 发布前强制校验：引用的指标必须存在、依赖图不得有环、表达式必须合法、基础指标字段
  必须在白名单内。草稿可以中途保存（允许半成品），但任何非法定义都无法发布冻结。
- **已发布版本冻结**：接口层拒绝修改；改规则只能基于已发布版本复制出新草稿，发布为新版本。
  查询结果会回传该版本当时的定义快照，页面展示"本次实际使用的定义"，历史查询不受后续编辑影响。

## 演示数据

`backend/app/db.py` 内置，首次启动自动写入：

- 跨月退款：O1001（10-28 支付）的两笔退款发生在 11-02、11-05；O1004（10-29 支付）11-03 全额退。
- 一单多次退款：O1001 对应 R1、R2 两笔。
- 只有退款的日期：V2 口径下 10-31、11-02、11-03、11-04、11-05。
- 同日有支付也有退款：O1003（11-01 支付 500）同日退款 R5（20）。

## 运行

```bash
./run-dev.sh                 # 一键：建虚拟环境、装依赖、起前后端
```

或手动：

```bash
# 后端 http://localhost:8000  （文档 /docs）
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# 前端 http://localhost:5173 （/api 代理到 8000）
cd frontend
npm install --cache ./.npm-cache
npm run dev
```

DuckDB 文件落在 `backend/data.duckdb`，删除后重启即恢复初始演示数据与 V1/V2 两个冻结版本。

## 测试

```bash
cd backend && .venv/bin/pytest -q
```

25 个测试覆盖：公式解析器的合法/非法用例与除零语义、依赖缺失/循环/白名单校验、
版本冻结与发布生命周期、三个易错计算场景、合计口径与下钻规则，以及 API 端到端冒烟。

## 目录

```
backend/
  app/
    formula.py       # 安全公式解析器（AST，无 eval）
    db.py            # DuckDB schema + 演示数据 + V1/V2 冻结版本
    definitions.py   # 版本 CRUD、发布前校验、冻结控制
    engine.py        # 独立聚合 + 全外合并 + 拓扑序派生计算 + 下钻
    main.py          # FastAPI 路由
  tests/             # pytest
frontend/
  src/
    App.tsx          # 查询栏 + 两个页签
    components/
      CompareTable.tsx     # 并排对比、差额、单元格下钻
      DefinitionPanel.tsx  # 本次实际使用的定义
      DefinitionsPage.tsx  # 草稿编辑/校验/发布/冻结/复制新版本
      DrillModal.tsx       # 订单与退款明细
```
