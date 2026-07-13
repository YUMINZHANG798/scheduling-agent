# 智慧排班 Agent — 架构设计文档

## 文档信息

| 字段 | 内容 |
| --- | --- |
| 产品名称 | 智慧排班 Agent |
| 文档版本 | v1.0 |
| 文档状态 | 初稿 |
| 创建日期 | 2026-07-12 |
| 对应 PRD | PRD.md |
| 对应 SPEC | SPEC.md |
| 密级 | 内部公开 |

## 修订历史

| 版本 | 日期 | 修订内容 | 修订人 |
| --- | --- | --- | --- |
| v1.0 | 2026-07-12 | 初始版本 | — |
| v1.1 | 2026-07-13 | employee_type 更新为 regular/temporary，排班流程区分正式工两班制和临时工混排 | — |
| v1.2 | 2026-07-13 | 正式工新增两头班(8:00-12:00,17:00-21:00)、新增员工周意愿数据流，临时工工作日固定18:00-21:00、周末灵活 | — |
| v1.3 | 2026-07-13 | 新增正式工周休假数据流（employee_weekly_leave + leave_resolution），排班算法加入休假冲突解决 | — |
| v1.4 | 2026-07-13 | 新增 HC 优化引擎与 /api/hc/* 端点（optimize / suggestions / confirm）、hc_suggestions 表；端点 /api/agent/message 统一为 /api/agent/chat | — |

---

## 1. 架构目标

### 1.1 核心目标

| 目标 | 说明 | 衡量标准 |
| --- | --- | --- |
| G-01 单门店闭环 | 围绕一个门店完成历史数据、需求计算、排班生成和解释闭环 | 无需外部服务即可完整演示 |
| G-02 LLM 编排 | LLM Agent 负责理解意图、综合因素、生成策略和组织解释 | Agent 覆盖 7 种排班意图 |
| G-03 确定性计算 | 数值聚合、规则校验、候选人评分、KPI 由 Python 模块计算 | 相同输入产生相同输出 |
| G-04 本地持久化 | 历史样例数据使用 CSV/JSON，运行结果使用 SQLite | 重置后数据可恢复 |
| G-05 可解释优先 | 每个需求和排班结果都能追溯到数据、规则和评分依据 | 关键排班项均有 explanation 字段 |
| G-06 演示稳定 | Demo 数据可重置，核心链路结果可复现 | 每日构建可重现 Demo 场景 |

### 1.2 架构原则

| 原则 | 说明 |
| --- | --- |
| 关注点分离 | 展示层、编排层、业务层、引擎层、数据层严格分层 |
| 依赖倒置 | 高层模块不依赖低层模块实现，均依赖抽象接口 |
| 可替换性 | LLM Provider、数据库、评分算法均可替换 |
| 可观测性 | 关键操作（生成、修改、Agent 调用）均记录日志 |
| 渐进增强 | 先 Demo 后产品化，架构预留扩展点 |

---

## 2. 系统上下文 (C4 L1)

```mermaid
flowchart LR
    USER[门店店长<br/>区域负责人] -->|使用| SYSTEM[智慧排班 Agent<br/>半混班排班系统]
    SYSTEM -->|读取| SEED[CSV/JSON<br/>样例数据]
    SYSTEM -->|调用| LLM[LLM Provider<br/>OpenAI / 本地模型]
    SYSTEM -->|持久化| DB[(SQLite<br/>运行时数据)]

    USER -.->|未来| EMP[员工端]
    SYSTEM -.->|未来| HR[人事系统]
    SYSTEM -.->|未来| POS[销售系统]
```

**系统职责：** 接收店长的排班指令，基于历史数据和业务规则生成半混班排班方案，并通过 Agent 提供可追溯的解释。

**外部依赖：**
- LLM Provider：提供自然语言理解与生成能力（可降级）
- 本地样例数据：CSV/JSON 文件（只读）
- SQLite：运行时数据持久化（读写）

---

## 3. 容器架构 (C4 L2)

```mermaid
flowchart TD
    subgraph 用户端
        Browser[浏览器<br/>React SPA]
    end

    subgraph 服务端
        API[FastAPI 容器<br/>Python FastAPI]
    subgraph API内部
        API_ROUTES[API 路由层]
        AGENT_CTN[LLM Agent 编排容器]
        DEMAND_CTN[需求计算容器<br/>Pandas]
        ENGINE_CTN[排班引擎容器]
        HC_CTN[HC 优化容器]
        DATA_CTN[数据访问容器]
    end
    end

    subgraph 数据存储
        CSV[(CSV/JSON 文件)]
        SQLITE[(SQLite 数据库)]
    end

    subgraph 外部
        LLM[LLM Provider]
    end

    Browser -->|HTTP REST| API_ROUTES
    API_ROUTES --> AGENT_CTN
    API_ROUTES --> DEMAND_CTN
    API_ROUTES --> ENGINE_CTN
    AGENT_CTN -->|工具调用| DEMAND_CTN
    AGENT_CTN -->|工具调用| ENGINE_CTN
    AGENT_CTN -->|工具调用| HC_CTN
    HC_CTN --> DATA_CTN
    AGENT_CTN -->|LLM 调用| LLM
    DEMAND_CTN --> CSV
    ENGINE_CTN --> DATA_CTN
    DATA_CTN --> SQLITE
    AGENT_CTN --> DATA_CTN
```

### 3.1 容器职责

| 容器 | 技术 | 职责 |
| --- | --- | --- |
| React SPA | React + TypeScript + Vite | 半混班排班工作台 UI |
| FastAPI 容器 | Python FastAPI + Pydantic | REST API 服务、请求校验、响应序列化 |
| LLM Agent 编排容器 | Python | 意图识别、工具调用编排、解释生成 |
| 需求计算容器 | Python + Pandas | 历史数据聚合、影响因子计算、需求人数生成 |
| 排班引擎容器 | Python | 专业岗锁定、临时工池管理、候选人评分、风险检测 |
| HC 优化容器 | Python | 历史缺口分析、成本模型、编制调整建议生成 |
| 数据访问容器 | Python + SQLite | SQLite CRUD 封装 |
| CSV/JSON 文件 | CSV / JSON | 静态样例数据（只读） |
| SQLite 数据库 | SQLite 3 | 运行时数据持久化（读写） |

---

## 4. 组件架构 (C4 L3)

### 4.1 前端组件架构

```mermaid
flowchart TD
    subgraph Pages
        WORKBENCH[SemiMixedSchedulingWorkbench]
    end

    subgraph Components
        HEADER[HeaderBar]
        DEMAND_INSIGHT[DemandInsightPanel]
        KPI_ROW[KpiCardsRow]
        AREA_PANEL[AreaBaselinePanel]
        WEEK_BOARD[WeeklyScheduleBoard]
        HEATMAP[DemandGapHeatmap]
        AGENT_PANEL[AgentPanel]
        INTERVENTION[InterventionDrawer]
        MODAL[ModifyReasonModal]
    end

    subgraph Hooks
        USE_GEN[useGenerateSchedule]
        USE_AGENT[useAgentChat]
        USE_SCHED[useScheduleData]
    end

    subgraph API
        API_CLIENT[apiClient]
    end

    subgraph Types
        TS_TYPES[TypeScript Types]
    end

    WORKBENCH --> HEADER
    WORKBENCH --> DEMAND_INSIGHT
    WORKBENCH --> KPI_ROW
    WORKBENCH --> AREA_PANEL
    WORKBENCH --> WEEK_BOARD
    WORKBENCH --> HEATMAP
    WORKBENCH --> AGENT_PANEL
    WORKBENCH --> INTERVENTION
    WORKBENCH --> MODAL

    HEADER --> USE_GEN
    AGENT_PANEL --> USE_AGENT
    WEEK_BOARD --> MODAL

    USE_GEN --> API_CLIENT
    USE_AGENT --> API_CLIENT
    USE_SCHED --> API_CLIENT

    API_CLIENT --> TS_TYPES
    USE_GEN --> TS_TYPES
    USE_AGENT --> TS_TYPES
    USE_SCHED --> TS_TYPES
```

### 4.2 后端组件架构

```mermaid
flowchart TD
    subgraph API_Layer
        SCHED_API[ScheduleAPI]
        AGENT_API[AgentAPI]
        DEMO_API[DemoAPI]
        HC_API[HcApi]
    end

    subgraph Service_Layer
        DEMAND_SVC[DemandService]
        SCHED_SVC[ScheduleService]
        KPI_SVC[KpiService]
        INTERV_SVC[InterventionService]
        HC_SVC[HcService]
    end

    subgraph Agent_Layer
        AGENT_SVC[AgentService]
        PROVIDER[LLMProvider]
        TOOLS[AgentTools]
        PROMPTS[PromptManager]
    end

    subgraph Engine_Layer
        GENERATOR[SchedulingGenerator]
        RULES[RulesEngine]
        SCORER[CandidateScorer]
        RISKS[RiskDetector]
        HC_ENG[HcEngine]
    end

    subgraph Data_Layer
        SEED[SeedLoader]
        STORE[SQLiteStore]
        DB[(SQLite)]
    end

    subgraph Seed_Data
        CSV[JSON/CSV Files]
    end

    %% API 层调用关系
    SCHED_API --> SCHED_SVC
    SCHED_API --> AGENT_SVC
    AGENT_API --> AGENT_SVC
    DEMO_API --> SEED
    HC_API --> HC_SVC

    %% Agent 层调用关系
    AGENT_SVC --> PROVIDER
    AGENT_SVC --> TOOLS
    AGENT_SVC --> PROMPTS
    TOOLS --> DEMAND_SVC
    TOOLS --> GENERATOR
    TOOLS --> RULES
    TOOLS --> KPI_SVC
    TOOLS --> HC_SVC

    %% 服务层调用关系
    DEMAND_SVC --> CSV
    SCHED_SVC --> GENERATOR
    SCHED_SVC --> STORE
    KPI_SVC --> STORE
    INTERV_SVC --> STORE
    HC_SVC --> HC_ENG
    HC_ENG --> STORE

    %% 引擎层调用关系
    GENERATOR --> RULES
    GENERATOR --> SCORER
    GENERATOR --> RISKS
    GENERATOR --> STORE

    %% 数据层调用关系
    SEED --> CSV
    SEED --> STORE
    STORE --> DB
```

---

## 5. 核心流程设计

### 5.1 排班生成流程

#### 5.1.1 正常流程

```mermaid
sequenceDiagram
    participant U as 店长
    participant W as React 工作台
    participant API as FastAPI
    participant AG as AgentService
    participant DE as DemandService
    participant GE as SchedulingGenerator
    participant DB as SQLite

    U->>W: 点击"生成下周半混班班表"
    W->>W: 按钮进入 loading 状态
    W->>API: POST /api/schedule/generate
    Note over API: 创建版本 ID: sch_{uuid}

    API->>AG: handle_intent("generate", store, week)
    AG->>AG: 意图识别 → generate_schedule

    AG->>DE: get_historical_summary(store, week)
    DE->>DE: Pandas 读取 CSV 聚合分析
    DE-->>AG: HistoricalSummary

    AG->>DE: calculate_demand(summary, weather, holidays)
    DE->>DE: 叠加影响因子 → 生成需求
    DE-->>AG: List[DemandResult]

    AG->>GE: generate_schedule(demands, employees, rules, weekly_preferences, weekly_leave)
    GE->>GE: Step 1: 分离正式工/临时工，读取周意愿
    GE->>GE: Step 2: 正式工排班（按周意愿+默认班次分配三班，锁定专业岗）
    GE->>GE: Step 2a: 休假冲突解决（读取 leave_preferences，按日统计，驳回超限申请）
    GE->>GE: Step 3: 校验部门保底正式工人数（扣除休假后）
    GE->>GE: Step 4: 临时工排班（按缺口×部门名额分配，工作日固定18-21，周末灵活）
    GE->>GE: Step 5: 候选人评分排序
    GE->>GE: Step 6: 检测风险
    GE-->>AG: ScheduleResult

    AG->>AG: 生成 Agent 解释
    AG-->>API: AgentResponse

    API->>DB: 保存 demand_results
    API->>DB: 保存 schedule_versions + schedule_items
    API->>DB: 保存 risk_items
    API-->>W: 完整工作台数据

    W->>W: 渲染需求洞察、班表、热力图、KPI
    W->>W: 按钮恢复可用状态

    Note over W: 可用 TanStack Query 缓存
```

#### 5.1.2 LLM 降级流程

```mermaid
sequenceDiagram
    participant U as 店长
    participant W as 工作台
    participant API as FastAPI
    participant AG as AgentService
    participant DE as DemandService
    participant GE as SchedulingGenerator
    participant DB as SQLite

    U->>W: 点击"生成下周半混班班表"
    W->>API: POST /api/schedule/generate
    API->>AG: handle_intent("generate")

    AG->>DE: get_historical_summary()
    DE-->>AG: Summary

    AG->>DE: calculate_demand()
    DE-->>AG: List[DemandResult]

    AG->>GE: generate_schedule()
    GE-->>AG: ScheduleResult

    Note over AG: LLM 调用失败（超时/异常）
    AG->>AG: 捕获异常 → 启用降级策略
    AG->>AG: 使用模板生成基础解释
    AG-->>API: AgentResponse + is_fallback=True

    API-->>W: 工作台数据 + 提示"解释服务暂不可用"

    W->>U: 展示排班结果 + 黄色提示条
```

### 5.2 人工干预流程

```mermaid
sequenceDiagram
    participant U as 店长
    participant W as 前端
    participant API as FastAPI
    participant RS as RulesEngine
    participant KS as KpiService
    participant DB as SQLite

    U->>W: 点击排班项 → 选择修改
    W->>W: 弹出 ModifyReasonModal
    U->>W: 选择修改原因 + 确认

    W->>API: PATCH /api/schedule/{version_id}/items/{item_id}
    Note over API: 请求体含修改后内容和原因

    API->>RS: validate_schedule_item(new_item)
    RS->>RS: 校验专业岗/保底/工时
    RS-->>API: 校验结果 + 风险

    alt 校验存在严重风险
        API-->>W: 409 Conflict + 风险详情
        W->>U: 提示严重风险，要求确认
        U->>W: 确认忽略风险
        W->>API: PATCH (force=true)
    end

    API->>DB: 更新 schedule_items
    API->>DB: 插入 intervention_records

    API->>KS: calculate_all(items, interventions, ...)
    KS-->>API: 更新后的 KPI

    API-->>W: 更新后数据（item + risk + kpi + intervention）

    W->>W: 刷新班表、风险列表、KPI 卡片
    W->>U: Toast 提示"修改已记录"
```

### 5.3 Agent 对话流程

```mermaid
sequenceDiagram
    participant U as 店长
    participant W as 前端
    participant API as FastAPI
    participant AG as AgentService
    participant LLM as LLM Provider
    participant EN as Engine

    U->>W: 输入"周五晚高峰果蔬缺人，谁能支援？"
    W->>W: 显示 loading 气泡
    W->>API: POST /api/agent/chat
    Note over API: {version_id, message, context}

    API->>AG: handle_message(message, context)

    AG->>AG: 意图识别
    Note over AG: user_message + context → recommend_support

    AG->>EN: 查询缺口数据
    EN-->>AG: GapInfo(date=Friday, slot=16-18, area=produce, gap=1)

    AG->>EN: 查询候选池 + 评分
    EN->>EN: CandidateScorer.rank_candidates()
    EN-->>AG: List[CandidateScore]

    AG->>AG: 构建 LLM 输入
    Note over AG: system_prompt + gap_info + candidates + rules

    AG->>LLM: chat.completions.create()
    LLM-->>AG: 生成解释

    AG->>AG: Pydantic 结构化校验
    AG-->>API: AgentResponse

    API->>API: 记录 agent_messages
    API-->>W: AgentResponse

    W->>W: 渲染 Agent 响应（结论 + 原因 + 候选人列表）
    W->>W: 显示"应用推荐"按钮
```

### 5.4 Demo 重置流程

```mermaid
sequenceDiagram
    participant U as 店长
    participant W as 前端
    participant API as FastAPI
    participant SL as SeedLoader
    participant DB as SQLite

    U->>W: 点击"重置 Demo"
    W->>U: 确认弹窗"将清空所有排班数据，确认重置？"
    U->>W: 确认

    W->>API: POST /api/demo/reset

    API->>SL: reset_all()
    SL->>SL: 清空运行时表
    Note over SL: DELETE FROM demand_results, schedule_versions, ...
    SL->>SL: 从 CSV/JSON 重新加载静态数据
    Note over SL: INSERT INTO employees, areas, area_tasks, ...
    SL-->>API: ResetResult{status, loaded_tables}

    API-->>W: {status: "ok", loaded_tables: [...]}

    W->>W: 清空本地缓存
    W->>W: 刷新页面到初始状态
    W->>U: Toast 提示"Demo 已重置"

    Note over W: TanStack Query 缓存失效
```

---

### 5.5 HC 优化流程

```mermaid
sequenceDiagram
    participant U as 店长
    participant W as 前端
    participant API as FastAPI
    participant AG as AgentService
    participant TO as AgentTools
    participant HC as HcEngine
    participant DB as SQLite

    U->>W: 点击"查看 HC 优化建议"
    W->>API: POST /api/hc/optimize
    Note over API: 可选 horizon_weeks（默认 12）

    API->>AG: handle_intent("hc_optimize")
    AG->>TO: hc_optimize(horizon_weeks?)
    TO->>HC: analyze(demands, schedules, horizon)

    HC->>HC: 按区域/员工类型聚合历史缺口
    HC->>HC: 成本模型（C_reg=1.0 / C_temp=0.4）估算前后成本
    HC->>HC: 生成分区域、分类型编制建议（delta + reason）
    HC->>DB: 写入 hc_suggestions（status=pending）
    HC-->>TO: HcOptimizeResult

    TO-->>AG: HcOptimizeResult
    AG-->>API: AgentResponse
    API-->>W: HcOptimizeResult（建议 + 成本前后对比）

    W->>U: 展示建议列表与成本趋势

    U->>W: 确认某条建议
    W->>API: POST /api/hc/suggestions/confirm
    API->>DB: 更新 hc_suggestions status=approved
    API-->>W: {status: "approved"}
```

---
## 6. 数据流设计

### 6.1 排班生成数据流

```mermaid
flowchart TD
    CSV[CSV 样例数据] -->|Pandas 读取| BASELINE[历史基线计算]
    BASELINE --> PEAK[高峰/低峰识别]
    PEAK --> HOLIDAY[节假日因子叠加]
    HOLIDAY --> WEATHER[天气因子叠加]
    WEATHER --> PROMO[促销因子叠加]
    PROMO --> DEMAND[需求人数生成]

    DEMAND --> LEAVE[休假冲突解决]
    JSON[JSON 配置数据] --> LEAVE
    LEAVE --> LOCK[专业岗锁定]
    JSON --> LOCK
    LOCK --> BASELINE_CHECK[区域保底校验]
    BASELINE_CHECK --> POOL[临时工池生成]
    JSON --> POOL
    POOL --> SCORE[候选人评分]
    SCORE --> ASSIGN[混排分配]
    ASSIGN --> GAP[缺口检测]
    GAP --> RISK[风险生成]
    RISK --> KPI[KPI 计算]
    KPI --> OUTPUT[输出到 SQLite]
```

### 6.2 请求数据流

```mermaid
flowchart LR
    subgraph 请求流向
        REQ[HTTP 请求] -->|Pydantic 校验| VAL[请求校验]
        VAL -->|依赖注入| SVC[服务层]
        SVC -->|工具调用| ENG[引擎层]
        ENG -->|CRUD| DB[(SQLite)]
        ENG --> SVC
        SVC -->|Pydantic 序列化| RES[HTTP 响应]
    end

    subgraph 错误处理
        ERR[异常] -->|自定义异常| EXC[Exception Handler]
        EXC -->|统一格式| RES
    end
```

---

### 6.3 HC 优化数据流

```mermaid
flowchart LR
    DEMAND[demand_results 历史] --> GAP[缺口分析]
    SCHED[schedule_items 历史] --> GAP
    GAP --> COST[成本模型<br/>C_reg=1.0 / C_temp=0.4]
    COST --> SUGGEST[HcSuggestion 生成<br/>current/suggested/delta]
    SUGGEST --> STORE[(hc_suggestions 表<br/>status: pending)]
    STORE --> CONFIRM[店长确认<br/>approved / rejected]
```

---
## 7. 部署架构

### 7.1 本地开发部署

```mermaid
flowchart LR
    subgraph 开发机
        FE[Vite Dev Server<br/>:5173] -->|HTTP Proxy| BE[FastAPI<br/>:8000]
        BE --> CSV[(CSV/JSON)]
        BE --> SQLITE[(SQLite)]
        BE -->|HTTP| LLM[LLM Provider API]
    end
```

### 7.2 组件通信协议

| 通信双方 | 协议 | 格式 | 说明 |
| --- | --- | --- | --- |
| 浏览器 ↔ FastAPI | HTTP/1.1 | JSON | REST API |
| FastAPI ↔ LLM | HTTPS | JSON (SSE) | OpenAI-compatible API |
| FastAPI ↔ SQLite | SQLite 驱动 | SQL | 本地文件操作 |
| FastAPI ↔ CSV/JSON | 文件 I/O | CSV/JSON | 本地文件读取 |

### 7.3 端口规划

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| Vite Dev Server | 5173 | 前端开发服务器 |
| FastAPI | 8000 | 后端 API 服务 |
| FastAPI Docs | 8000/docs | Swagger 文档 |
| FastAPI Redoc | 8000/redoc | ReDoc 文档 |

---

---

---

## 8. 扩展性设计

### 8.1 扩展点

| 扩展方向 | 当前预留 | 扩展方式 |
| --- | --- | --- |
| 多门店支持 | ScheduleVersion.store_id | 增加门店维度过滤 |
| 真实数据接入 | SeedLoader / DemandService | 替换 CSV 读取为 API 调用 |
| 更多预测因子 | DemandService factor pipeline | 新增 factor 实现类 |
| 约束求解优化 | SchedulingGenerator | 替换为 OR-Tools 等优化求解器 |
| 员工端 | ScheduleItem.employee_id | 增加员工可见的 API 端点 |
| 审批流 | ScheduleVersion.status | 增加审批状态流转 |
| 自动学习 | InterventionRecord | 分析干预原因 → 自动调整规则权重 |



---

## 9. 性能架构

### 9.1 缓存策略

| 缓存对象 | 缓存位置 | 失效策略 | 说明 |
| --- | --- | --- | --- |
| 门店配置 | React Query | 永不刷新 (staleTime: Infinity) | 静态数据，不常变更 |
| 员工数据 | React Query | 永不刷新 | 静态样例数据 |
| 区域配置 | React Query | 永不刷新 | 静态样例数据 |
| 需求结果 | React Query | 5 分钟后失效 | 每次生成排班刷新 |
| 排班版本 | React Query | 5 分钟后失效 | 修改后立即刷新 |
| Agent 响应 | 不缓存 | — | 每次独立请求 |

### 9.2 性能优化措施

| 措施 | 说明 |
| --- | --- |
| 前端代码分割 | 按组件懒加载，减少首屏体积 |
| TanStack Query 缓存 | 减少重复 API 请求 |
| ECharts 懒渲染 | 热力图仅在可见时渲染 |
| FastAPI 异步 | 非阻塞 I/O 提升并发能力 |
| Pandas 向量化 | 批量计算代替逐行循环 |
| SQLite 连接池 | 复用数据库连接 |

---

---

---


