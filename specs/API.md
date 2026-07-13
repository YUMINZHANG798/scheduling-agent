# 智慧排班 Agent — API 接口文档

## 文档信息

| 字段 | 内容 |
| --- | --- |
| 产品名称 | 智慧排班 Agent |
| 文档版本 | v1.0 |
| API 基础路径 | `http://localhost:8000/api` |
| 数据格式 | JSON (Content-Type: application/json) |
| 字符编码 | UTF-8 |
| 文档状态 | 初稿 |
| 创建日期 | 2026-07-12 |

## 修订历史

| 版本 | 日期 | 修订内容 | 修订人 |
| --- | --- | --- | --- |
| v1.0 | 2026-07-12 | 初始版本 | — |
| v1.1 | 2026-07-13 | employee_type 更新为 regular/temporary，assignment_type 更新为 regular/temporary，新增 regular_shift_type 字段 | — |
| v1.2 | 2026-07-13 | regular_shift_type 新增 split（两头班），临时工调整 | — |

---

## 1. 接口总览

### 1.1 接口分组

| 分组 | 基础路径 | 说明 |
| --- | --- | --- |
| 排班管理 | `/api/schedule` | 排班生成、查询、修改、KPI、风险 |
| Agent 服务 | `/api/agent` | 对话、需求解释、候选人推荐 |
| Demo 管理 | `/api/demo` | 数据重置、源数据查看 |
| HC 优化 | `/api/hc` | 编制优化建议生成、查询、确认 |

### 1.2 接口速查表

| 方法 | 路径 | 说明 | 本页章节 |
| --- | --- | --- | --- |
| POST | `/api/schedule/generate` | 生成排班 | 2.1 |
| GET | `/api/schedule/{version_id}` | 获取排班版本 | 2.2 |
| PATCH | `/api/schedule/{version_id}/items/{item_id}` | 修改排班项 | 2.3 |
| GET | `/api/schedule/{version_id}/preferences` | 获取员工周意愿 | 2.4 |
| GET | `/api/schedule/{version_id}/leave-preferences` | 获取员工周休假意愿 | 2.5 |
| GET | `/api/schedule/{version_id}/leave-resolution` | 获取休假冲突解决结果 | 2.6 |
| GET | `/api/schedule/{version_id}/kpis` | 获取 KPI | 2.7 |
| GET | `/api/schedule/{version_id}/risks` | 获取风险列表 | 2.8 |
| POST | `/api/agent/chat` | Agent 对话 | 3.1 |
| POST | `/api/agent/recommend-support` | 推荐支援候选人 | 3.2 |
| POST | `/api/agent/explain-demand` | 解释需求计算 | 3.3 |
| POST | `/api/demo/reset` | 重置样例数据 | 4.1 |
| GET | `/api/demo/source-data` | 查看历史数据摘要 | 4.2 |
| POST | `/api/hc/optimize` | 生成 HC 优化建议 | 5.1 |
| GET | `/api/hc/suggestions` | 获取建议列表 | 5.2 |
| POST | `/api/hc/suggestions/confirm` | 确认/驳回建议 | 5.3 |

---

## 2. 排班管理 API

### 2.1 生成排班

生成一周半混班排班。生成逻辑（历史数据摘要 → 需求计算 → 排班生成 → 规则校验 → 风险检测 → KPI 计算 → 解释生成）见 [SPEC.md §8]。

```
POST /api/schedule/generate
```

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| store_id | string | 是 | — | 门店 ID，当前仅支持 `fresh_store_001` |
| week_start | string | 是 | — | 排班周起始日期，格式 `YYYY-MM-DD`，必须为周一 |
| instruction | string | 否 | `""` | 用户自定义排班指令，Agent 会参考该指令生成排班 |

#### 请求示例

```json
{
  "store_id": "fresh_store_001",
  "week_start": "2026-07-13",
  "instruction": "根据历史数据、天气和节假日生成下周半混班班表"
}
```

> 响应字段类型（`version_id` / `agent_summary` / `agent_fallback` / `demand_insights`[DemandInsight] / `demand_results`[DemandResult] / `schedule_items`[ScheduleItem] / `kpis`[KpiResult] / `risks`[RiskItem]）详见 [SPEC.md §4.3]；表字段详见 [数据库表结构设计.md §3.x]。

#### 响应示例

```json
{
  "version_id": "sch_a1b2c3d",
  "agent_summary": "已根据历史客流、周五晚高峰、降雨和周末因素生成下周半混班班表。老王和老陈锁定水产区保护时段，老张和老刘锁定肉类区保护时段；小唐支援周五晚高峰果蔬和收银缺口。",
  "agent_fallback": false,
  "demand_insights": [ { "date": "2026-07-17", "weekday": "Friday", "slot": "16:00-17:00", "area_code": "produce", "area_name": "果蔬区", "required_count": 3, "demand_score": 86, "demand_factors": ["周五晚高峰", "历史客流高", "降雨"], "priority": "high", "confidence": "medium" } ],
  "demand_results": [ { "id": "dr_001", "date": "2026-07-13", "weekday": "Monday", "slot": "08:00-09:00", "area_code": "aquatic", "task_code": "fish_butcher", "required_count": 1, "demand_score": 75, "demand_factors": ["早高峰", "历史基线"], "priority": "high", "confidence": "high", "is_protected": 1 } ],
  "schedule_items": [
    { "id": "si_001", "date": "2026-07-13", "slot": "08:00-16:00", "area_code": "aquatic", "area_name": "水产区", "task_code": "fish_butcher", "task_name": "杀鱼", "employee_id": "emp_001", "employee_name": "老王", "employee_type": "regular", "assignment_type": "regular", "risk_level": "none", "explanation": "老王为水产区S级杀鱼师傅，排早班8:00-16:00", "source": "system", "is_protected": 1 },
    { "id": "si_002", "date": "2026-07-17", "slot": "18:00-21:00", "area_code": "produce", "area_name": "果蔬区", "task_code": "restock", "task_name": "补货", "employee_id": "emp_013", "employee_name": "小唐", "employee_type": "temporary", "assignment_type": "temporary", "risk_level": "none", "explanation": "小唐为临时工，周五晚高峰支援果蔬区补货3小时", "source": "system" }
  ],
  "kpis": { "professional_coverage_rate": 1.0, "baseline_achievement_rate": 0.95, "mixed_utilization_rate": 0.28, "peak_gap_count": 2, "intervention_rate": 0.0 },
  "risks": [ { "id": "risk_001", "type": "peak_gap", "level": "warning", "description": "周五17:00-18:00果蔬区补货岗位需求3人，当前仅排2人，缺口1人", "affected_item_ids": [], "suggestion": "可从临时工池推荐小唐或小马支援" } ]
}
```

#### 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | INVALID_REQUEST | week_start 不是周一或日期格式错误 |
| 400 | STORE_NOT_FOUND | store_id 不存在 |
| 422 | VALIDATION_ERROR | 请求体校验失败 |
| 503 | LLM_UNAVAILABLE | LLM 服务不可用，已使用规则兜底（agent_fallback=true） |

---

### 2.2 获取排班版本

获取指定版本的完整排班数据。

```
GET /api/schedule/{version_id}
```

#### 路径参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| version_id | string | 排班版本 ID |

#### 响应

同 `POST /api/schedule/generate` 的响应结构。

#### 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 404 | VERSION_NOT_FOUND | 版本 ID 不存在 |

---

### 2.3 修改排班项

店长手动修改一条排班项，系统会校验风险并记录干预。

```
PATCH /api/schedule/{version_id}/items/{item_id}
```

#### 路径参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| version_id | string | 排班版本 ID |
| item_id | string | 排班项 ID |

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| after | object | 是 | 修改后的排班项内容（仅需传被修改的字段） |
| reason_code | string | 是 | 修改原因编码，见 2.3.1 |
| reason_text | string | 否 | 修改原因说明（reason_code 为 other 时必填） |
| force | boolean | 否 | 是否忽略严重风险强制修改，默认 false |

##### 2.3.1 reason_code 枚举

| 编码 | 说明 | 触发条件 |
| --- | --- | --- |
| employee_unavailable | 员工实际不可用 | 员工请假、无法到岗 |
| employee_not_fit | 员工不适合该区域 | 虽有技能但不熟练 |
| manager_experience | 店长经验调整 | 店长认为需要更强的人 |
| area_leader_request | 区域负责人要求 | 课组负责人要求留守 |
| operation_change | 临时经营变化 | 促销、到货、客流变化 |
| other | 其他 | 手动输入，reason_text 必填 |

#### 请求示例

```json
{ "after": { "employee_id": "emp_013", "employee_name": "小唐", "task_code": "restock", "slot": "18:00-21:00", "area_code": "produce" }, "reason_code": "manager_experience", "reason_text": "小唐补货能力更强，适合周五晚高峰" }
```

> 响应字段类型（`item`[ScheduleItem] / `risks`[RiskItem] / `kpis`[KpiResult] / `intervention_record`[InterventionRecord] / `requires_confirmation`）详见 [SPEC.md §4.3]；表字段见 [数据库表结构设计.md §3.10/§3.11/§3.13/§3.14]。

#### 响应示例

```json
{
  "item": { "id": "si_015", "date": "2026-07-17", "slot": "18:00-21:00", "area_code": "produce", "area_name": "果蔬区", "task_code": "restock", "task_name": "补货", "employee_id": "emp_013", "employee_name": "小唐", "assignment_type": "temporary", "risk_level": "none", "explanation": "店长手动调整", "source": "manual", "is_protected": 0 },
  "risks": [],
  "kpis": { "professional_coverage_rate": 1.0, "baseline_achievement_rate": 0.95, "mixed_utilization_rate": 0.30, "peak_gap_count": 1, "intervention_rate": 0.02 },
  "intervention_record": { "id": "ir_001", "schedule_item_id": "si_015", "before": { "employee_id": "emp_012", "employee_name": "小孙", "area_code": "produce", "task_code": "restock" }, "after": { "employee_id": "emp_013", "employee_name": "小唐", "area_code": "produce", "task_code": "restock" }, "reason_code": "manager_experience", "reason_text": "小唐补货能力更强，适合周五晚高峰", "created_at": "2026-07-12T10:30:00Z" },
  "requires_confirmation": false
}
```

#### 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | INVALID_REASON | 修改原因编码不合法 |
| 404 | VERSION_NOT_FOUND | 版本 ID 不存在 |
| 404 | NOT_FOUND | 排班项 ID 不存在 |
| 409 | SCHEDULE_CONFLICT | 修改导致严重风险（如保底不足），requires_confirmation=true，需用户确认后重试 |
| 422 | VALIDATION_ERROR | 请求体校验失败 |

---

### 2.4 获取员工周意愿

正式工每周可申请变动下周班次类型。数据由外部人力系统同步，排班系统提供只读查询。

```
GET /api/schedule/{version_id}/preferences
```

#### 路径参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| version_id | string | 排班版本 ID（用于确定 week_start） |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| employee_id | string | 否 | 全部 | 按员工 ID 过滤 |

#### 响应

```json
[ { "id": "wp_0001", "employee_id": "emp_030", "employee_name": "小唐", "week_start": "2026-07-13", "preferred_shift_type": "morning", "default_shift_type": "evening", "created_at": "2026-07-10T08:00:00Z" } ]
```

> 响应字段（含 `preferred_shift_type` 取值 morning/evening/split 含义）详见 [数据库表结构设计.md §3.6]。

---

### 2.5 获取员工周休假意愿

正式工每周可申请 1 天休假，自行选择星期几。

```
GET /api/schedule/{version_id}/leave-preferences
```

#### 路径参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| version_id | string | 排班版本 ID（用于确定 week_start） |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| employee_id | string | 否 | 全部 | 按员工 ID 过滤 |

#### 响应

```json
[ { "id": "lv_0001", "employee_id": "emp_001", "employee_name": "老王", "week_start": "2026-07-13", "preferred_day_off": "Wednesday", "created_at": "2026-07-10T08:00:00Z" } ]
```

> 响应字段详见 [数据库表结构设计.md §3.7]。

---

### 2.6 获取休假冲突解决结果

排班生成时，系统自动解决休假冲突后生成的最终结果。

```
GET /api/schedule/{version_id}/leave-resolution
```

#### 路径参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| version_id | string | 排班版本 ID |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| status | string | 否 | 全部 | 过滤：approved / denied |

#### 响应

```json
[ { "id": "lr_0001", "employee_id": "emp_001", "employee_name": "老王", "day_off": "Wednesday", "status": "approved", "reason": null }, { "id": "lr_0002", "employee_id": "emp_003", "employee_name": "小林", "day_off": "Monday", "status": "denied", "reason": "周一休假申请超限（8人申请，最多批准5人），系统已驳回" } ]
```

> 响应字段（含 `status` approved/denied 含义）详见 [数据库表结构设计.md §3.8]。

---

### 2.7 获取 KPI

获取指定排班版本的 KPI 数据。

```
GET /api/schedule/{version_id}/kpis
```

#### 路径参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| version_id | string | 排班版本 ID |

#### 响应

```json
{ "professional_coverage_rate": 1.0, "baseline_achievement_rate": 0.95, "mixed_utilization_rate": 0.28, "peak_gap_count": 2, "intervention_rate": 0.02 }
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| professional_coverage_rate | number (0-1) | 专业岗覆盖率 |
| baseline_achievement_rate | number (0-1) | 部门保底达成率 |
| mixed_utilization_rate | number (0-1) | 临时工利用率 |
| peak_gap_count | number | 高峰缺口数 |
| intervention_rate | number (0-1) | 人工干预率 |

> 各 KPI 计算方式详见 [SPEC.md §4.3 的 KpiResult 类型] / [数据库表结构设计.md §3.9]。

---

### 2.8 获取风险列表

获取指定排班版本的所有风险项。

```
GET /api/schedule/{version_id}/risks
```

#### 路径参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| version_id | string | 排班版本 ID |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| level | string | 否 | 全部 | 风险等级过滤：critical / warning / info |

#### 响应

```json
[ { "id": "risk_001", "type": "peak_gap", "level": "warning", "description": "周五17:00-18:00果蔬区补货岗位需求3人，当前仅排2人，缺口1人", "affected_item_ids": [], "suggestion": "可从临时工池推荐小唐或小马支援", "created_at": "2026-07-12T10:00:00Z" }, { "id": "risk_002", "type": "professional_gap", "level": "critical", "description": "水产区周六08:00-09:00杀鱼岗位无人覆盖", "affected_item_ids": ["si_042"], "suggestion": "当前无可用S/A级杀鱼师傅，请联系水产区域负责人", "created_at": "2026-07-12T10:00:00Z" } ]
```

> 响应字段（`type` / `level` 枚举取值等）详见 [SPEC.md §4.3 的 RiskItem 类型] / [数据库表结构设计.md §3.13]。

---

## 3. Agent 服务 API

### 3.1 Agent 对话

用户通过自然语言与 Agent 交互，支持需求解释、排班解释、候选人推荐、不可调解释等意图。

```
POST /api/agent/chat
```

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| version_id | string | 否 | 当前排班版本 ID（第一次对话可为空） |
| message | string | 是 | 用户输入的自然语言消息 |
| context | object | 否 | 附加上下文，帮助 Agent 理解当前场景 |

##### context 字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| selected_date | string | 否 | 用户当前选中的日期 |
| selected_slot | string | 否 | 用户当前选中的时段 |
| selected_area | string | 否 | 用户当前选中的区域 |
| selected_employee | string | 否 | 用户当前选中的员工 ID |

#### 请求示例

```json
{ "version_id": "sch_a1b2c3d", "message": "周五晚高峰果蔬缺人，谁能支援？", "context": { "selected_date": "2026-07-17", "selected_slot": "17:00-18:00" } }
```

> 响应结构 `AgentResponse`（`conclusion` / `reasons` / `is_fallback` 等契约字段，含 `intent` 枚举、`CandidateInfo`）详见 [SPEC.md §6.4]；候选人评分逻辑见 [SPEC.md §8.2]。

#### 响应示例

```json
{
  "intent": "recommend_support",
  "conclusion": "建议优先安排小唐支援周五17:00-18:00果蔬区，可同时覆盖补货和称重需求",
  "reasons": [
    "小唐具备果蔬A、补货A、打包A技能，可独立完成该时段通用任务",
    "小唐当前周工时16小时，未超过32小时上限，剩余工时充足",
    "该安排不影响水产、肉类保护时段的专业岗保底"
  ],
  "candidates": [
    { "employee_name": "小唐", "skills": ["收银A", "补货A", "果蔬A", "打包A"], "score": 92, "recommended": true, "reason": "技能全面，工时充足，不影响任何区域保底，是当前最优选择", "risks": [] },
    { "employee_name": "小马", "skills": ["称重B", "打包B", "基础补货B"], "score": 68, "recommended": false, "reason": "可做称重和打包，但不建议独立处理高峰补货任务", "risks": ["技能等级B，独立处理高峰能力不足"] },
    { "employee_name": "老王", "skills": ["杀鱼S", "水产处理S", "称重A"], "score": 45, "recommended": false, "reason": "老王为水产区S级杀鱼师傅，当前时段为水产保护时段，不能跨区抽调", "risks": ["保护时段不可抽调", "抽调会导致水产区保底不足"] }
  ],
  "next_actions": [
    "点击\"应用推荐\"安排小唐支援果蔬区",
    "查看小马的详细能力",
    "查看其他候选人的排班情况"
  ],
  "is_fallback": false
}
```

#### 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | INVALID_REQUEST | 消息为空或格式错误 |
| 404 | VERSION_NOT_FOUND | 版本 ID 不存在 |
| 503 | LLM_UNAVAILABLE | LLM 服务不可用，使用规则兜底（is_fallback=true） |

---

### 3.2 推荐支援候选人

针对特定缺口，直接返回候选人列表（跳过 LLM 解释，用于前端快速获取数据）。

```
POST /api/agent/recommend-support
```

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| version_id | string | 是 | 排班版本 ID |
| date | string | 是 | 日期 YYYY-MM-DD |
| slot | string | 是 | 时段，如 `17:00-18:00` |
| area_code | string | 是 | 区域编码 |
| task_code | string | 是 | 任务编码 |
| exclude_employee_ids | array[string] | 否 | 需排除的员工 ID 列表 |

#### 请求示例

```json
{ "version_id": "sch_a1b2c3d", "date": "2026-07-17", "slot": "17:00-18:00", "area_code": "produce", "task_code": "restock", "exclude_employee_ids": ["emp_012"] }
```

#### 响应

> 响应结构（`gap` / `candidates`）详见 [SPEC.md §6.4]；候选人评分见 [SPEC.md §8.2]。

```json
{
  "gap": { "date": "2026-07-17", "slot": "17:00-18:00", "area_code": "produce", "task_code": "restock", "required_count": 3, "current_count": 2, "gap_count": 1 },
  "candidates": [ { "employee_name": "小唐", "skills": ["收银A", "补货A", "果蔬A", "打包A"], "score": 92, "recommended": true, "reason": "技能全面，工时充足", "risks": [] } ]
}
```

---

### 3.3 解释需求计算

针对特定时段和区域，解释需求计算的依据。

```
POST /api/agent/explain-demand
```

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| version_id | string | 是 | 排班版本 ID |
| date | string | 是 | 日期 YYYY-MM-DD |
| slot | string | 是 | 时段 |
| area_code | string | 是 | 区域编码 |
| question | string | 否 | 用户附加问题 |

#### 请求示例

```json
{ "version_id": "sch_a1b2c3d", "date": "2026-07-17", "slot": "17:00-18:00", "area_code": "produce", "question": "说明这个时段果蔬区的人力需求依据" }
```

#### 响应

> 需求计算依据详见 [SPEC.md §7]。

```json
{
  "answer": "周五17:00-18:00是晚高峰时段，该时段历史客流均值比普通工作日高28%，果蔬销售高35%；同时当天预报有降雨，线上订单和打包任务预计增加15%。综合以上因素，果蔬区补货、称重和打包需求上升，建议配置3人。",
  "factors": [ "周五晚高峰：历史客流高于均值28%", "果蔬销售高：历史销售高于均值35%", "降雨：线上订单预计增加15%，到店客流影响可忽略", "周末效应：周五为周末前夜，备货需求增加" ],
  "confidence": "medium",
  "data_summary": { "historical_avg_traffic": 312, "current_forecast_traffic": 399, "historical_avg_sales": 4520.00, "holiday_factor": 1.0, "weather_factor": 1.15, "promotion_factor": 1.0, "base_demand": 2, "final_demand": 3 }
}
```

---

### 3.4 hc_optimize（HC 优化）

Agent 可调用该工具生成门店编制（人员配置）优化建议，与 generate_schedule、explain_demand、recommend_support、resolve_leave 并列。

- 工具名：`hc_optimize`
- 参数：`horizon_weeks`（int，可选，默认 12）—— 优化展望周数
- 行为：调用后端 `POST /api/hc/optimize` 生成编制建议
- 返回：`HcOptimizeResult`，结构见 [SPEC.md §11.4]

> 说明：`hc_optimize` 仅负责生成建议（status=`pending`），是否生效需由店长通过 [POST /api/hc/suggestions/confirm](#) 接口确认。

---

## 4. Demo 管理 API

### 4.1 重置样例数据

清空所有运行时数据（需求结果、排班版本、排班项、风险、干预记录、Agent 记录），重新从 CSV/JSON 加载静态配置数据。

```
POST /api/demo/reset
```

#### 请求参数

无

#### 响应

```json
{
  "status": "ok",
  "message": "样例数据已重置",
  "loaded_tables": ["employees", "areas", "area_tasks", "skill_definitions", "employee_skills", "employee_weekly_preferences", "employee_weekly_leave", "modified_reasons"],
  "cleared_tables": ["demand_results", "schedule_versions", "schedule_items", "candidate_scores", "risk_items", "intervention_records", "agent_messages", "leave_resolution"],
  "timestamp": "2026-07-12T10:00:00Z"
}
```

---

### 4.2 查看历史数据摘要

查看当前加载的样例数据摘要信息。

```
GET /api/demo/source-data
```

#### 查询参数

无

#### 响应

```json
{
  "store": { "store_id": "fresh_store_001", "store_name": "鲜生活超市-望京店", "address": "北京市朝阳区望京街道XX号" },
  "employees_count": 90,
  "employee_types": { "regular": 50, "temporary": 15 },
  "areas": [ {"code": "aquatic", "name": "水产区", "tasks_count": 4}, {"code": "meat", "name": "肉类区", "tasks_count": 4}, {"code": "produce", "name": "果蔬区", "tasks_count": 4}, {"code": "cashier", "name": "收银/前场", "tasks_count": 2}, {"code": "replenishment", "name": "补货区", "tasks_count": 3} ],
  "historical_data_range": { "sales_start": "2026-06-15", "sales_end": "2026-07-12", "total_records": 1627 },
  "holidays_count": 10,
  "promotions_count": 3,
  "promotions": [ {"id": "promo_001", "date": "2026-07-17", "area_code": "produce", "promotion_type": "high", "boost_factor": 1.3}, {"id": "promo_002", "date": "2026-07-18", "area_code": "meat", "promotion_type": "low", "boost_factor": 1.2}, {"id": "promo_003", "date": "2026-07-19", "area_code": "aquatic", "promotion_type": "low", "boost_factor": 1.25} ],
  "last_reset": "2026-07-12T10:00:00Z"
}
```

---

## 5. HC 优化 API

HC 优化（编制优化）能力用于根据历史客流、需求与成本，对门店各区域的正式工 / 临时工编制数量提出建议。建议生成后处于 `pending` 状态，店长确认（confirm）后置为 `approved` 并可生效，驳回（reject）后置为 `rejected`。

### 5.1 生成 HC 优化建议

根据门店当前编制与展望周期内的需求预测，生成编制优化建议。

```
POST /api/hc/optimize
```

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| store_id | string | 是 | — | 门店 ID，当前仅支持 `fresh_store_001` |
| week_start | string | 是 | — | 优化起始周，格式 `YYYY-MM-DD`，必须为周一 |
| horizon_weeks | int | 否 | 12 | 优化展望周数 |

#### 请求示例

```json
{ "store_id": "fresh_store_001", "week_start": "2026-07-13", "horizon_weeks": 12 }
```

> 响应结构 `HcOptimizeResult`（`generated_at` / `horizon_weeks` / `suggestions` / `total_cost_before` / `total_cost_after` / `summary`）与 `HcSuggestion`（`id` / `area_code` / `area_name` / `employee_type` / `current_count` / `suggested_count` / `delta` / `reason` / `est_cost_before` / `est_cost_after` / `status`）字段定义详见 [SPEC.md §11.4] / [数据库表结构设计.md §3.18]；生成算法见 [SPEC.md §11]。

#### 响应示例

```json
{
  "generated_at": "2026-07-13T08:00:00Z",
  "horizon_weeks": 12,
  "suggestions": [
    { "id": "hc_001", "area_code": "aquatic", "area_name": "水产区", "employee_type": "temporary", "current_count": 4, "suggested_count": 7, "delta": 3, "reason": "展望期内水产区晚高峰客流增长 32%，现有临时工无法覆盖称重与打包高峰缺口", "est_cost_before": 19200.0, "est_cost_after": 33600.0, "status": "pending" },
    { "id": "hc_002", "area_code": "replenishment", "area_name": "补货区", "employee_type": "regular", "current_count": 9, "suggested_count": 6, "delta": -3, "reason": "补货区自动化补货设备上线后，基线保底人数可由 9 人下调至 6 人，不影响保底达成率", "est_cost_before": 54000.0, "est_cost_after": 36000.0, "status": "pending" }
  ],
  "total_cost_before": 73200.0,
  "total_cost_after": 69600.0,
  "summary": "建议水产区增配 3 名临时工以覆盖晚高峰缺口，补货区精简 3 名正式工（由自动化补货承接），整体 12 周估算成本下降约 3600 元。"
}
```

#### 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | INVALID_REQUEST | week_start 不是周一或日期格式错误 |
| 400 | STORE_NOT_FOUND | store_id 不存在 |
| 422 | VALIDATION_ERROR | 请求体校验失败 |
| 503 | LLM_UNAVAILABLE | LLM 服务不可用，已使用规则兜底 |

---

### 5.2 获取建议列表

获取已生成的 HC 优化建议列表，支持按状态过滤。

```
GET /api/hc/suggestions
```

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| status | string | 否 | 全部 | 状态过滤：`pending` / `approved` / `rejected` |

#### 响应

返回 `items` 数组，元素为 `HcSuggestion`（含 `status` 字段，字段定义见 [SPEC.md §11.4]）。

```json
{
  "items": [
    { "id": "hc_001", "area_code": "aquatic", "area_name": "水产区", "employee_type": "temporary", "current_count": 4, "suggested_count": 7, "delta": 3, "reason": "展望期内水产区晚高峰客流增长 32%，现有临时工无法覆盖称重与打包高峰缺口", "est_cost_before": 19200.0, "est_cost_after": 33600.0, "status": "pending" },
    { "id": "hc_002", "area_code": "replenishment", "area_name": "补货区", "employee_type": "regular", "current_count": 9, "suggested_count": 6, "delta": -3, "reason": "补货区自动化补货设备上线后，基线保底人数可由 9 人下调至 6 人，不影响保底达成率", "est_cost_before": 54000.0, "est_cost_after": 36000.0, "status": "approved" }
  ]
}
```

#### 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | INVALID_REQUEST | status 取值不合法 |

---

### 5.3 确认生效

对建议进行批量确认或驳回。该接口将 `pending` 的建议按动作更新为 `approved`（确认生效）或 `rejected`（驳回）。

```
POST /api/hc/suggestions/confirm
```

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| suggestion_ids | array[string] | 是 | 待处理建议 ID 列表 |
| action | enum | 是 | 处理动作：`apply`（确认生效）/ `reject`（驳回） |

#### 请求示例

```json
{ "suggestion_ids": ["hc_001", "hc_002"], "action": "apply" }
```

#### 响应参数

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| applied | int | 成功生效（置为 `approved`）的建议数量 |
| rejected | int | 成功驳回（置为 `rejected`）的建议数量 |
| errors | array | 处理失败的建议列表，每项包含错误详情 |

#### 响应示例

```json
{
  "applied": 2,
  "rejected": 0,
  "errors": []
}
```

#### 错误码

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | INVALID_REQUEST | action 取值不合法或 suggestion_ids 为空 |
| 404 | NOT_FOUND | 建议 ID 不存在 |
| 422 | VALIDATION_ERROR | 请求体校验失败 |

---

## 6. 错误处理

### 6.1 统一错误响应格式

所有错误响应使用统一格式：

```json
{
  "error_code": "ERROR_CODE",
  "message": "人类可读的错误描述",
  "details": {
    "errors": [
      {
        "field": "具体错误字段",
        "message": "错误描述",
        "received": "实际收到的值"
      }
    ]
  },
  "request_id": "req_uuid"
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| error_code | string | 是 | 机器可读的错误编码 |
| message | string | 是 | 人类可读的错误描述 |
| details | object | 否 | 错误详情，结构为 `{ errors: [{ field, message, received }] }`，用于前端定位 |
| request_id | string | 否 | 请求追踪 ID |

### 6.2 错误码全集

| HTTP 状态码 | error_code | 说明 | 触发场景 |
| --- | --- | --- | --- |
| 400 | INVALID_REQUEST | 请求参数错误 | 日期格式错误、编码不合法 |
| 400 | STORE_NOT_FOUND | 门店不存在 | store_id 无效 |
| 400 | INVALID_REASON | 修改原因不合法 | reason_code 不存在 |
| 404 | NOT_FOUND | 资源不存在 | 排班项 ID/其他资源无效 |
| 404 | VERSION_NOT_FOUND | 版本 ID 不存在 | Agent 请求中的 version_id 无效 |
| 409 | SCHEDULE_CONFLICT | 排班冲突 | 修改导致保底不足/专业岗缺失 |
| 422 | VALIDATION_ERROR | 请求体验证失败 | Pydantic 校验失败 |
| 500 | INTERNAL_ERROR | 内部错误 | 未预期的异常 |
| 503 | LLM_UNAVAILABLE | LLM 服务不可用 | LLM 调用失败，已降级 |

> 说明：`VERSION_NOT_FOUND` 与 `NOT_FOUND` 分工明确——**版本 ID 不存在**统一使用 `VERSION_NOT_FOUND`（如 2.2、3.1）；**其他资源或记录不存在**（如排班项 ID、门店等）使用 `NOT_FOUND`。两者不合并。

### 6.3 校验错误详情格式

422 VALIDATION_ERROR 的 details 格式：

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "请求参数校验失败",
  "details": {
    "errors": [
      {
        "field": "week_start",
        "message": "week_start 必须为周一 (YYYY-MM-DD)",
        "received": "2026-07-12"
      },
      {
        "field": "store_id",
        "message": "store_id 不能为空",
        "received": ""
      }
    ]
  },
  "request_id": "req_abc123"
}
```

---

---

## 7. 调用限制

| 限制项 | 值 |
| --- | --- |
| 请求体大小上限 | 1MB |
| 响应超时 | 30s (生成排班) / 10s (其他) |

---


