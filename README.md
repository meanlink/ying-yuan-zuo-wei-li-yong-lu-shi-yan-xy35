# 影院座位利用率实验

`cinema-seat-experiment` 是为 Orbital Cinema 影城运营团队设计的影院座位策略实验工作台。它把一版排片中的厅次和座位区域拆成可追溯的实验单元，接收票务观测，使用 Python Bootstrap 估计 treatment 与 control 的售出率差异，并在跨厅样本不平衡时强制执行分层分析后再进入收益审批。

## 真实场景

Orbital Cinema 在周末 IMAX 场次中比较传统前排策略与中排动态座位策略。排片策划负责锁定影片、厅次、场次和座位容量，票房专员按座位入账，实验分析师负责 Bootstrap 区间和分层效应量，收益经理审批下一轮排片决策。

当前人工流程依赖排片表、POS 导出和 Excel 复盘，存在三处痛点。排片版本与实验组容易在场次开始后被手工改写，跨厅样本失衡时粗差异会误导收益判断，审批结果缺少从票务观测到分层结果的审计链。

上游输入是排片版本、厅次座位区和 POS 票务观测。本应用承接实验配置、座位观测、统计分析和复盘审批，下游交付给周末排片会议和收益经理。

## 功能模块

- 排片版本。维护影片、版本、厅次、场次、座位容量和排片状态。
- 座位实验。配置 control / treatment 单元，记录厅次、场次、座位区域和样本数。
- 票务观测。按票务编码记录座位是否售出、价格、时间和来源，并阻止重复编码。
- 收益复盘。计算 Bootstrap 差异区间、厅次分层效应量和平衡比，支持重跑和收益审批。
- 横切能力。JWT 角色权限、审计日志、请求限流、统一错误响应、worker 心跳。

## 主流程和异常分支

`排片 → 实验配置 → 场次开始 → 售票观测 → Bootstrap 差异区间 → 分层效应量 → 复盘审批`

场次状态进入 `live` 后，后端拒绝修改实验组。以厅次和场次为分层的 control / treatment 样本平衡比低于 `0.78` 时，分析状态为 `rerun_required`，收益经理审批返回 `409`，只有带 `stratified=true` 的重跑结果才能审批。

## 快速启动

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
open http://localhost:18256/
```

后端地址为 `http://localhost:19256`，数据库映射端口为 `17756`。测试结束后清理容器和命名卷。

```bash
docker compose down -v --remove-orphans
```

## 演示账号

所有演示账号密码均为 `cinema123`。

| 邮箱 | 角色 | 主要权限 |
|---|---|---|
| `planner@cinema.local` | planner | 创建排片版本、配置实验单元、启动场次 |
| `analyst@cinema.local` | analyst | 查看数据、运行 Bootstrap 和分层分析 |
| `revenue@cinema.local` | revenue | 审批已经通过平衡检查的收益复盘 |
| `boxoffice@cinema.local` | boxoffice | 录入票务观测 |

## 技术栈和服务

| 服务 | 技术 | 端口或职责 |
|---|---|---|
| frontend | Nginx + 原生 HTML/CSS/ES modules | `18256` |
| backend | Python 3.11 + FastAPI + SQLAlchemy | `19256` |
| worker | Python 心跳与 Redis 保活 | 共享卷心跳 |
| db | PostgreSQL 16 | `17756` |
| redis | Redis 7 | 内部队列和 worker 心跳 |

Compose 共有五个服务。backend 和 worker 等待 db、redis 健康，frontend 等待 backend 健康。数据库、Redis 和共享产物卷使用固定命名卷。

## 目录

```text
backend/src/models.py                 领域实体和审计日志
backend/src/routes/plans.py           排片、实验、观测、分析和审批接口
backend/src/services/analytics.py     Bootstrap、平衡比、分层效应量
backend/src/services/workflow.py      状态流转和业务规则
backend/scripts/seed_demo.py          幂等演示数据
frontend/src/app.js                   页面、状态和用户动作
frontend/src/api.js                   后端 API 封装
frontend/src/styles.css               实验室档案视觉系统
test-artifacts/gb-1057/tests          API 端到端和算法测试
```

共享枚举在前后端分别出现。排片状态在 `backend/src/routes/plans.py`、`backend/src/services/workflow.py` 和 `frontend/src/app.js` 中出现，实验组枚举在 `backend/src/routes/plans.py`、`backend/src/services/analytics.py` 和 `frontend/src/app.js` 中出现。后端中间件是 `RateLimitMiddleware` 与 `RequestIdMiddleware`，前端共用组件通过 `nav`、`panel-head`、`button`、`status` 和 `trace` 结构复用，`fmtPct`、`run` 和 `load` 提供共享格式化、错误处理和加载逻辑。

## 许可证

本项目用于内部业务评审和演示，采用 MIT License。

## 票房班结与排片试行

- **票房班结对账**。票房专员按实验单元登记 POS 批次、观测座位数、售出票数和实收金额。系统保存登记时的观测快照和对账差异。登记第一张回执后，所有单元须对齐才可运行或审批分析。迟到观测会使相关回执过期，需要补对后重新分析。
- **审批后排片试行**。收益经理引用当前观测对应的已审批复盘，选择 treatment 座区、下一场日期时间和投放座数。排片策划记录排片系统回执和实际投放数；收益经理可撤回尚未执行的工单。工单检查同影厅开场冲突，保留原复盘与撤回历史。

通过页首「当前排片」在版本之间切换。已有 PostgreSQL 卷启动时自动补齐 `pos_closeouts` 和 `scheduling_pilots`。模块使用 `operations_models.py`、`operations_schemas.py`、`services/operations.py` 和 `frontend/src/operations.js`，异常及操作写入现有审计。没有登记过 POS 回执的历史排片可继续按原流程复盘。

### 试行场次结算

正式试行排片开场后，票房岗位按唯一 POS 凭证登记实际售座、票务实收与分账、卖品毛利、增量成本和活动补贴。金额按整数分保存。实际售座超过正式排片上限、分账超过实收或同场重复提交均会被拦截。

净贡献＝票务实收 − 票务分账 ＋ 卖品毛利 − 增量成本 − 活动补贴。盈亏平衡门槛按本场平均每座票务净额计算并向上取整，无票务净额且仍需覆盖成本时显示无可估计门槛。收益经理独立确认或驳回，分析员读回复核结果和收支口径。
