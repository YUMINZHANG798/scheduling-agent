# 智慧排班 Agent — 半混班智能排班系统

面向生鲜商超的半混班智能排班助手。**正式工**固定部门两班制排班（早班 8:00-16:00、晚班 14:00-22:00），专业岗位（杀鱼、切肉）由师傅稳定覆盖；**临时工**跨部门混排 3-6 小时补位，每部门每天最多 1 班临时工。高峰缺口由系统自动推荐补人，店长人工修改被记录并统计。

## 项目状态

当前为**规格设计阶段**，代码尚未开始编写。`specs/` 目录下有完整的 PRD、规格、架构、API、数据库设计文档，供开发参考。

## 业务概念

| 概念 | 说明 |
| --- | --- |
| 半混班 | 正式工部门固定两班 + 临时工跨部门混排补位 |
| 正式工 (Regular) | 固定在所属部门工作，排早班(8:00-16:00)或晚班(14:00-22:00)，不跨区 |
| 临时工 (Temporary) | 跨部门混班，每班 3-6 小时，每部门每天最多 1 班 |
| 专业固定岗 | 杀鱼、切肉等需要 S/A 级正式工师傅的岗位，不可安排临时工 |
| 保护时段 | 早市/晚高峰时段，专业师傅必须留守本区域 |
| 临时工池 | 可跨区域承担通用任务的临时工集合 |
| 部门保底 | 每个部门每个班次最低正式工在岗人数 |
| 部门临时工名额 | 每个部门每天最多 1 班临时工的上限 |
| 人工干预率 | 店长手动修改的排班项占比 |

## 技术栈

| 分层 | 选型 |
| --- | --- |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| 图表 | Apache ECharts（热力图、雷达图） |
| 状态管理 | TanStack Query |
| 后端 | Python FastAPI + Pydantic v2 |
| 数据处理 | Pandas |
| 数据库 | SQLite（Demo 阶段，零运维） |
| LLM Agent | OpenAI-compatible API + 自定义工具调用 |
| 测试 | Vitest（前端）+ Pytest（后端） |

## 目录结构

```
scheduling-agent/
├── specs/                    # 规格文档
│   ├── PRD.md                # 产品需求
│   ├── SPEC.md               # 技术规格
│   ├── ARCHITECTURE.md       # 架构设计
│   ├── API.md                # API 接口文档
│   └── 数据库表结构设计.md     # 数据库设计
├── frontend/                 # React 前端（待开发）
└── backend/                  # FastAPI 后端（待开发）
```

## 如何运行（开发中，待实现）

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload  # http://localhost:8000
```

### 前端

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

API 文档自动生成：`http://localhost:8000/docs`

## 如何测试（开发中，待实现）

```bash
# 后端测试
cd backend
pytest -v

# 前端测试
cd frontend
npx vitest run
```

## 核心数据流

```
CSV/JSON 样例数据
  → Pandas 聚合 → 历史基线 + 影响因子（天气/节假日/促销）
  → 分区域分时段需求计算
  → 排班引擎（见下）
  → KPI 计算 + 风险检测
  → LLM Agent 生成自然语言解释
  → 店长通过 React 工作台查看/修改
```

## 排班引擎如何工作

核心思路：**先排正式工固定班次，再用临时工按评分填缺口。**

### 示例场景

一个门店有 80 名员工（50 名正式工 + 30 名临时工），5 个区域（水产、肉类、果蔬、收银、补货），下周排班要覆盖 7 天 × 两班制（早班 8:00-16:00、晚班 14:00-22:00）。

### 步骤拆解

#### Step 1 — 需求计算

以"果蔬区周五"为例，系统计算需要的人：

```text
早班（8:00-16:00）：基线 2 人 → 考虑促销 → 需求 2 人
晚班（14:00-22:00）：基线 2 人 × 周五晚高峰(1.25) × 降雨(1.15) → 需求 3 人
其中正式工覆盖 2 人，临时工补 1 人（16:00-18:00 最忙的 2 小时）
```

形成一张 **需求网格**（7天 × 5区域 × 2班次 + 临时工缺口）。

#### Step 2 — 正式工排班（按部门 × 班次）

正式工按所属部门分配早班或晚班。水产区杀鱼是专业岗，只有老王（S 级）和老陈（S 级）能做。系统把他俩安排到水产区早班/晚班。

```text
老王（水产，morning）→ 水产区 周一~周日 早班 8:00-16:00
老陈（水产，morning）→ 水产区 周一~周日 早班 8:00-16:00
小林（水产，rotating）→ 系统按需求分配早班或晚班
正式工不跨区，都在水产区内工作
```

同理解锁肉类区老张和老刘，以及其他部门的正式工。

#### Step 3 — 校验部门保底正式工人数

水产区和肉类区专业岗（杀鱼、切肉）必须由正式工师傅承担，但临时工可做称重、清洁等非专业杂活。每个部门每天最多 **1 班临时工**（max_temp_per_day=1）。

每个班次必须保证至少 **2 名正式工在岗**（水产、肉类）或 **1 名正式工保底**（果蔬、收银、补货），缺口由临时工补位。

#### Step 4 — 临时工分配

正式工排定后，仍有缺口的部门（如果蔬区周五晚班需要 3 人，正式工只有 2 人），需从临时工池中分配。

- 临时工池：小唐、小马（共 2 人）
- 每部门每天最多 1 班临时工
- 每班 3-6 小时，由忙碌程度决定
- 只分配非专业任务

#### Step 5 — 临时工候选人评分

当果蔬区周五晚班缺 1 人时，系统从临时工池中筛选：

| 维度 | 权重 | 小唐 | 小马 |
| --- | --- | --- | --- |
| 技能匹配 | 35% | 果蔬 A → 31.5 | 基础补货 B → 24.5 |
| 区域熟悉度 | 20% | 熟悉 0.9 → 18 | 一般 0.5 → 10 |
| 剩余工时 | 15% | 已排 16h，限 32h → 7.5 | 已排 12h，限 28h → 8.6 |
| 高峰适配 | 10% | 有高峰经验 → 10 | 无 → 0 |
| 不影响正式工 | 15% | 临时工，不影响 → 15 | 临时工，不影响 → 15 |
| 偏好匹配 | 5% | 匹配 → 5 | 不匹配 → 0 |
| **总分** | **100%** | **87** | **58.1** |

小唐 87 分最高 → 系统安排他周五 16:00-18:00 支援果蔬区（2小时）。

#### Step 6 — 生成缺口和风险

仍有未被满足的需求 → 标记为**缺口**。同时检测：

- 是否有部门保底正式工人数不足 → `baseline_shortage` 风险
- 是否有人超工时 → `overtime` 风险
- 临时工名额是否超限 → `temp_quota_exceeded` 风险
- 技能等级是否足够 → `skill_mismatch` 风险

#### Step 7 — 计算 KPI

| KPI | 含义 | 目标 |
| --- | --- | --- |
| 专业岗覆盖率 | 专业任务是否都由 S/A 级正式工做 | 100% |
| 部门保底达成率 | 所有班次正式工是否满足保底 | ≥ 95% |
| 临时工利用率 | 临时工工时占总工时比例 | 10-25% |
| 高峰缺口数 | 高峰时段缺多少人 | 尽量为 0 |
| 人工干预率 | 店长手动修改的比例 | ≤ 10% |

### 约束模型

| 约束 | 硬/软 | 违反后果 |
| --- | --- | --- |
| 正式工固定在所属部门排班 | 硬 | 直接否决 |
| 专业岗必须正式工 S/A 级 | 硬 | 直接淘汰 |
| 部门保底不可突破 | 硬 | 拒绝修改，要求店长确认 |
| 专业岗临时工不可做 | 硬 | 临时工不分配专业任务 |
| 每部门每天最多 1 班临时工 | 硬 | 超出的需求标记为缺口 |
| 临时工不干专业工作 | 硬 | 不进入候选列表 |
| 周工时上限 | 硬 | 超过不进候选池 |
| 临时工时长为 3-6 小时 | 硬 | 自动调整至合法范围 |
| 技能匹配 | 软 | 低分但不排除 |
| 员工偏好 | 软 | 加分项 |

### LLM Agent 的作用

LLM **不参与排班计算**（人数计算、规则校验、评分排序全部由 Python 代码完成），它只负责两件事：

1. **理解用户意图** — 把自然语言问题归类到已知意图
2. **生成可读的解释** — 把结构化数据转化成店长能看懂的话

### 发给 LLM 的是什么（以"周五晚高峰果蔬缺人，谁能支援？"为例）

#### 第一步 — 意图识别

只发一小段提示词，让 LLM 分类：

```text
用户输入：周五晚高峰果蔬缺人，谁能支援？

从以下列表选择最匹配的意图：
- INTENT_GENERATE：要求生成排班
- INTENT_EXPLAIN_DEMAND：询问需求原因
- INTENT_RECOMMEND_SUPPORT：询问支援人选  ← 选中
- INTENT_EXPLAIN_BLOCKED：询问为什么不能调人
- INTENT_LIST_RISKS：询问风险
- ...
```

不涉及任何业务数据，开销极小。

#### 第二步 — 执行工具

识别到 `INTENT_RECOMMEND_SUPPORT` 后，系统**自己调用 Python 函数**获取数据，不经过 LLM：

| 工具调用 | 输入 | 输出（结构化数据） |
| --- | --- | --- |
| `get_gap_info` | 版本 ID, 周五, 17-19, 果蔬区 | `{gap_count: 1, required: 3, current: 2}` |
| `get_candidates` | 缺口信息, 排除列表 | `[{name: "小唐", score: 87, skills: [...]}, {name: "小马", score: 58, ...}]` |
| `get_blocked_reasons` | 缺口信息 | `[{name: "老王", reason: "保护时段不可抽调"}]` |

这些数据是**纯 JSON**，完全由 Python 生成。

#### 第三步 — 生成解释

将工具返回的数据组装成提示词，发给 LLM 生成自然语言：

```
**发给 LLM 的完整 Prompt：**

系统角色：
你是一个智慧排班助手，用中文回答店长的排班问题。

当前缺口：
- 周五 16:00-18:00 果蔬区需求 3 人，当前 2 人，缺口 1 人
- 高峰时段，需要优先安排

推荐候选人（按评分排序）：
1. 小唐 — 87 分
   - 技能：果蔬A, 补货A, 收银A, 打包A
   - 当前周工时 16h / 上限 32h
   - 优点：技能全面，工时充足
   - 原因：最优推荐

2. 小马 — 58 分
   - 技能：称重B, 打包B, 基础补货B
   - 当前周工时 12h / 上限 28h
   - 注意：技能等级 B，独立处理高峰能力不足

不可调人员：
- 老王：水产区保护时段（16:00-18:00），抽调会导致水产保底不足
- 老张：肉类区保护时段，同理

请以店长为对象，生成一段回答，包含：
1. 结论：推荐谁
2. 原因：基于哪些数据
3. 下一步操作建议
```

**LLM 返回的结构化输出：**

```json
{
  "intent": "recommend_support",
  "conclusion": "建议优先安排小唐支援周五16:00-18:00果蔬区，可同时覆盖补货和称重需求",
  "reasons": [
    "小唐具备果蔬A、补货A技能，可独立完成该时段任务",
    "小唐当前周工时16小时，距32小时上限还有充足余量",
    "该安排不影响水产、肉类保护时段的专业岗保底"
  ],
  "candidates": [
    {
      "employee_name": "小唐",
      "skills": ["收银A", "补货A", "果蔬A", "打包A"],
      "score": 87,
      "recommended": true,
      "reason": "技能全面，工时充足，是当前最优选择",
      "risks": []
    },
    {
      "employee_name": "小马",
      "skills": ["称重B", "打包B", "基础补货B"],
      "score": 58,
      "recommended": false,
      "reason": "技能等级B，不建议独立处理高峰补货任务",
      "risks": ["技能不足"]
    }
  ],
  "next_actions": [
    "点击「应用推荐」安排小唐支援果蔬区",
    "查看其他候选人的排班情况"
  ]
}
```

### 关键设计原则

LLM **只做语言理解与生成**，所有业务逻辑用代码实现：

| 做的事 | 谁负责 | 原因 |
| --- | --- | --- |
| 需求人数计算 | Python + Pandas | 必须是确定性的，相同数据出相同结果 |
| 规则校验 | Python RulesEngine | 硬约束不可模糊，不可被 LLM "说服" |
| 候选人评分 | Python CandidateScorer | 评分权重需要透明、可审计、可调整 |
| 理解用户问题 | LLM | 自然语言没有固定格式，适合 LLM |
| 生成解释 | LLM | 店长要读的是人话，不是 JSON |
| 推荐理由排序 | LLM | 综合多个评分项得出"人话"结论 |

**降级策略**：LLM 不可用时（超时/异常），系统跳过解释生成，直接把结构化数据返回前端，前端用模板渲染。

### 排班生成场景的完整 LLM 交互（对比推荐场景）

生成排班时 LLM 的作用更简单——它**几乎不做任何事**，只有一步：

```
店长点击"生成下周半混班班表"
  → 意图识别（INTENT_GENERATE）
  → Python 执行全部计算（需求 → 排班 → KPI → 风险）
  → 计算完成后，把结果摘要发给 LLM
  → LLM 只负责写一段总结文字：
    "已根据历史客流、降雨和周末因素生成下周排班。
     老王、老张等专业师傅已锁定各自保护时段，
     小唐被推荐支援周五晚高峰果蔬缺口。
     当前发现 2 个缺口（周五果蔬、周六收银）。"
  → 前端拿到总结文字 + 完整的结构化数据，一起渲染
```

即使 LLM 挂掉，排班照常生成，前端只是少一段总结文字。

## 后端核心模块详解

### DemandService — 需求计算

**它做什么：** 把原始的历史经营数据（销售、客流、订单）转化为"每个时段每个区域需要几个人"。

**输入：**

| 数据 | 格式 | 内容 |
| --- | --- | --- |
| historical_sales.csv | CSV | 每天每时段的销售额和交易笔数 |
| historical_traffic.csv | CSV | 每天每时段的客流量 |
| online_orders.csv | CSV | 线上订单数和拣货数 |
| weather.csv | CSV | 每天每时段的天气、温度、降雨量 |
| holidays.csv | CSV | 节假日和周末标记 |
| 促销配置 | JSON | 促销活动的时间和区域 |

**处理过程：**

```
以"计算果蔬区周五16:00-18:00的需求"为例

1. 取历史基线
   找到过去4周周五16:00-18:00的客流和销售均值
   → 客流均值 312 人，销售均值 ¥4520
   → 折算为基准人力 2 人

2. 识别高峰
   比较该时段客流在所有时段中的百分位排名
   → top 25% → 标记为 high（晚高峰）

3. 叠加因子
   节假日：周五不是节假日，因子 1.0
   天气：预报有降雨，到店客流 -10%，线上订单 +15%
         → 果蔬区受影响较小，因子 1.0
   促销：果蔬区有促销活动 → 因子 1.3
   周末前夜：周五为周末前夜，备货需求增加 → 因子 1.1

4. 计算最终需求
   demand = 2 × 1.0 × 1.0 × 1.3 × 1.1 = 2.86 → 向上取整 → 3 人

5. 输出
   {
      date: "2026-07-17", slot: "16:00-18:00",
     area_code: "produce", task_code: "restock",
     required_count: 3,
     demand_score: 86,       // 综合需求强度 0-100
     demand_factors: ["晚高峰", "促销", "周末前夜"],
     priority: "high",
     confidence: "medium"    // 天气预报→置信度降低
   }
```

**输出：** 全周的需求网格（约 140 条），每条包含时段、区域、任务、需求人数、影响因素和置信度。

---

### SchedulingGenerator — 排班生成主流程

**它做什么：** 把需求网格 + 员工数据排成一张可执行的班表。它是排班引擎的"总指挥"，调度 RulesEngine 和 CandidateScorer 完成工作。

**输入：**

| 数据 | 来源 |
| --- | --- |
| 需求网格 List[DemandResult] | DemandService 的输出 |
| 员工列表 List[Employee] | 数据库 employees 表 |
| 区域配置 List[AreaConfig] | 数据库 areas 表 |
| 区域任务 List[AreaTask] | 数据库 area_tasks 表 |
| 保护时段 List[ProtectedSlot] | 数据库 protected_slots 表 |

**处理过程（主方法 `generate`）：**

```text
generate(demands, employees, areas, area_tasks, version_id):

  Step 1: 按时间逐 slot 逐区域遍历需求网格
  Step 2: 对每个 slot 内的每个区域任务:
    a. 如果是专业岗 → _lock_professional_positions()
         从员工池中筛选 S/A 级 + 主区域匹配 + 在职员工
         直接锁定，标记 is_protected=true
    b. 如果是普通岗 → 加入"待分配池"
  Step 3: 对所有已分配项执行 _validate_area_baselines()
         检查每个区域每个时段在岗人数 ≥ baseline_min
         不满足 → 生成 RiskItem（baseline_shortage）
  Step 4: 对"待分配池"按优先级排序（高峰 > 普通 > 低峰）
  Step 5: 调用 _build_temp_pool()
         从临时工中筛选可用的
         排除已被分配的
         排除当前时段已在岗的
  Step 6: 遍历排序后的待分配任务:
    a. 从临时工池中筛选有对应技能的候选人
    b. 调用 CandidateScorer.score() 对每个候选人打分
    c. 选择最高分者分配
    d. 若无人可分配 → 标记为缺口
  Step 7: 调用 RiskDetector 检测所有风险
  Step 8: 调用 KpiService 计算 KPI
  Step 9: 返回 ScheduleResult
```

---

### RulesEngine — 规则校验引擎

**它做什么：** 校验一条排班是否违反业务规则。不生成排班，只做"能不能这样做"的判断。

**校验方法：**

```python
# 每条返回一个 RuleCheckResult {passed: bool, risk_level, message}

check_professional_qualification(employee, task)
  → 如果 task 是专业岗且 employee 等级 < S/A → 不通过

check_protected_hours(employee, slot, area, protected_slots)
  → 如果当前 slot 在保护时段内且 employee 要跨区 → 不通过

check_area_baseline(area, slot, current_count, baseline_min)
  → 如果 current_count < baseline_min → 警告

check_weekly_hours(employee_id, current_hours, slot_hours, max_hours)
  → 如果 current_hours + slot_hours > max_hours → 不通过

check_skill_requirement(employee, task)
  → 如果 employee 没有该 task 的技能 → 不通过
```

**谁调用它：**

- **生成排班时**：SchedulingGenerator 用它过滤不可用的候选人
- **店长手动修改时**：API 端点先调 RulesEngine 做校验，有严重风险则拒绝修改或要求店长二次确认

---

### CandidateScorer — 候选人评分器

**它做什么：** 对多个候选员工进行多维度加权评分，输出排序结果。

**评分公式：**

```
总分 = 技能匹配分(0-35) + 区域熟悉度分(0-20) + 剩余工时分(0-15)
      + 高峰适配分(0-10) + 主区域不影响分(0-15) + 偏好匹配分(0-5)
      - 风险扣分(可选)
```

**各维度详解：**

| 维度 | 权重 | 计算逻辑 | 示例（小唐补果蔬缺口） |
| --- | --- | --- | --- |
| 技能匹配 | 35 | S→35, A→31.5, B→24.5, C→0 | 果蔬A → 31.5 |
| 区域熟悉度 | 20 | 主区域→20, 曾支援→16, 未支援但能做→10, 不熟悉→0 | 果蔬熟悉度0.9 → 18 |
| 剩余工时 | 15 | 15 × (max - current) / max | (32-16)/32 × 15 → 7.5 |
| 高峰适配 | 10 | 有高峰经验→10, 否则→0 | 有经验 → 10 |
| 主区域不影响 | 15 | 抽调不影响任何区域保底→15 | 流动员工 → 15 |
| 偏好匹配 | 5 | 匹配→5 | 匹配 → 5 |
| **风险扣分** | — | 超工时→扣30, 技能不足→扣20, 跨区频率过高→扣5 | 无风险 → 0 |
| **总分** | | | **87** |

**批量评分方法 `rank_candidates`：**

```python
def rank_candidates(candidates, task, slot, current_assignments, top_n=5):
    scores = []
    for emp in candidates:
        # 先过规则引擎做硬约束过滤
        if not rules_engine.check_professional_qualification(emp, task).passed:
            continue
        if not rules_engine.check_protected_hours(emp, slot, ...).passed:
            continue
        if not rules_engine.check_weekly_hours(emp, ...).passed:
            continue

        # 通过硬约束 → 计算加权分
        total = self.score(emp, task, slot, current_assignments)
        scores.append(total)

    return sorted(scores, key=lambda x: x.total, reverse=True)[:top_n]
```

---

### 三个模块如何配合（完整时序）

```
SchedulingGenerator.generate()
  │
  ├── 遍历每个 slot 每个区域
  │     ├── 专业岗 → 直接锁定（不调 RulesEngine，因为需求明确）
  │     ├── 普通岗 → 加入待分配列表
  │
  ├── _validate_area_baselines()
  │     └── 调 RulesEngine.check_area_baseline() → 发现保底不足 → 记录 RiskItem
  │
  ├── _build_mixed_pool()
  │     └── 调 RulesEngine.check_protected_hours() 过滤保护时段人员
  │
  └── _assign_mixed_tasks()
        └── 对每个待分配任务:
              ├── 调 RulesEngine.check_skill_requirement() 过滤无技能人员
              ├── 调 RulesEngine.check_weekly_hours() 过滤超工时人员
              └── 调 CandidateScorer.rank_candidates() 对剩余人选评分排序
```

## 推荐开发顺序

1. **数据库 DDL + 种子数据加载** — 先有数据，后面所有模块才能跑
2. **DemandService** — 最独立，不依赖其他模块，输入 CSV，输出需求网格
3. **排班引擎**（RulesEngine → CandidateScorer → SchedulingGenerator） — 先写校验规则再写评分，最后串流程
4. **API 端点** — 把以上功能暴露成 HTTP 接口
5. **前端核心组件** — KPI 卡片、区域面板、周班表、热力图
6. **Agent 集成** — LLM 工具调用 + 解释生成
7. **前端 Agent 面板 + 干预弹窗**
