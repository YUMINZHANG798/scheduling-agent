"""生成 Demo 全部种子数据：静态 JSON 配置 + 历史 CSV"""
import json
import csv
import os
import random
from datetime import date, timedelta, datetime

random.seed(42)

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "backend", "app", "seed")
os.makedirs(OUTDIR, exist_ok=True)

# ============================================================
# 1. 基础配置
# ============================================================
SLOTS = ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-16:00", "16:00-17:00", "17:00-18:00", "18:00-19:00", "19:00-20:00", "20:00-21:00", "21:00-22:00"]
SLOT_INDEX = {s: i for i, s in enumerate(SLOTS)}
REGULAR_SHIFTS = ["08:00-16:00", "14:00-22:00", "08:00-12:00,17:00-21:00"]

AREAS = [
    {"code": "aquatic",      "name": "水产区",     "allow_mixed": True,  "baseline_min": 2, "baseline_max": 4, "sort_order": 1},
    {"code": "meat",         "name": "肉类区",     "allow_mixed": True,  "baseline_min": 2, "baseline_max": 4, "sort_order": 2},
    {"code": "produce",      "name": "果蔬区",     "allow_mixed": True,  "baseline_min": 3, "baseline_max": 5, "sort_order": 3},
    {"code": "cashier",      "name": "收银/前场",  "allow_mixed": True,  "baseline_min": 3, "baseline_max": 6, "sort_order": 4},
    {"code": "replenishment","name": "补货区",     "allow_mixed": True,  "baseline_min": 2, "baseline_max": 4, "sort_order": 5},
]
AREA_CODES = [a["code"] for a in AREAS]

# ============================================================
# 2. 静态 JSON
# ============================================================

# 2a. areas.json
with open(os.path.join(OUTDIR, "areas.json"), "w", encoding="utf-8") as f:
    json.dump(AREAS, f, ensure_ascii=False, indent=2)
print("✅ areas.json")

# 2b. skill_definitions.json
SKILL_DEFS = [
    {"level": "S", "name": "专业师傅",   "description": "可处理高难度专业任务",     "can_independent": 1, "score": 1.0},
    {"level": "A", "name": "熟练员工",   "description": "可独立完成区域常规任务",   "can_independent": 1, "score": 0.9},
    {"level": "B", "name": "可支援员工", "description": "可在监督下承担基础任务",   "can_independent": 0, "score": 0.7},
    {"level": "C", "name": "新手/临时",  "description": "只能做辅助性工作",         "can_independent": 0, "score": 0.0},
]
with open(os.path.join(OUTDIR, "skill_definitions.json"), "w", encoding="utf-8") as f:
    json.dump(SKILL_DEFS, f, ensure_ascii=False, indent=2)
print("✅ skill_definitions.json")

# 2c. area_tasks.json
AREA_TASKS = [
    {"id": "task_aquatic_01", "area_code": "aquatic", "task_code": "fish_butcher",    "task_name": "杀鱼",     "is_professional": 1, "min_skill_level": "S", "priority": 100},
    {"id": "task_aquatic_02", "area_code": "aquatic", "task_code": "aquatic_process", "task_name": "水产处理", "is_professional": 1, "min_skill_level": "A", "priority": 90},
    {"id": "task_aquatic_03", "area_code": "aquatic", "task_code": "weighing",        "task_name": "称重",     "is_professional": 0, "min_skill_level": "B", "priority": 50},
    {"id": "task_aquatic_04", "area_code": "aquatic", "task_code": "cleaning",        "task_name": "清洁",     "is_professional": 0, "min_skill_level": "C", "priority": 20},
    {"id": "task_meat_01",    "area_code": "meat",    "task_code": "meat_cut",        "task_name": "切肉",     "is_professional": 1, "min_skill_level": "S", "priority": 100},
    {"id": "task_meat_02",    "area_code": "meat",    "task_code": "meat_divide",     "task_name": "分割",     "is_professional": 1, "min_skill_level": "A", "priority": 90},
    {"id": "task_meat_03",    "area_code": "meat",    "task_code": "weighing",        "task_name": "称重",     "is_professional": 0, "min_skill_level": "B", "priority": 50},
    {"id": "task_meat_04",    "area_code": "meat",    "task_code": "display",         "task_name": "陈列",     "is_professional": 0, "min_skill_level": "B", "priority": 40},
    {"id": "task_produce_01", "area_code": "produce", "task_code": "restock",         "task_name": "补货",     "is_professional": 0, "min_skill_level": "B", "priority": 70},
    {"id": "task_produce_02", "area_code": "produce", "task_code": "display",         "task_name": "陈列",     "is_professional": 0, "min_skill_level": "B", "priority": 50},
    {"id": "task_produce_03", "area_code": "produce", "task_code": "packing",         "task_name": "打包",     "is_professional": 0, "min_skill_level": "B", "priority": 40},
    {"id": "task_produce_04", "area_code": "produce", "task_code": "weighing",        "task_name": "称重",     "is_professional": 0, "min_skill_level": "B", "priority": 50},
    {"id": "task_cashier_01", "area_code": "cashier", "task_code": "cashier",         "task_name": "收银",     "is_professional": 0, "min_skill_level": "A", "priority": 80},
    {"id": "task_cashier_02", "area_code": "cashier", "task_code": "customer_service","task_name": "顾客服务", "is_professional": 0, "min_skill_level": "B", "priority": 40},
    {"id": "task_repl_01",    "area_code": "replenishment","task_code": "restock_unload", "task_name": "到货卸货", "is_professional": 0, "min_skill_level": "B", "priority": 70},
    {"id": "task_repl_02",    "area_code": "replenishment","task_code": "shelf_restock",  "task_name": "上架补货", "is_professional": 0, "min_skill_level": "B", "priority": 70},
    {"id": "task_repl_03",    "area_code": "replenishment","task_code": "inventory",      "task_name": "库存整理", "is_professional": 0, "min_skill_level": "B", "priority": 40},
]
with open(os.path.join(OUTDIR, "area_tasks.json"), "w", encoding="utf-8") as f:
    json.dump(AREA_TASKS, f, ensure_ascii=False, indent=2)
print("✅ area_tasks.json")

# 2d. modified_reasons.json
REASONS = [
    {"code": "employee_unavailable", "label": "员工实际不可用",     "sort_order": 1},
    {"code": "employee_not_fit",     "label": "员工不适合该区域",   "sort_order": 2},
    {"code": "manager_experience",   "label": "店长经验调整",       "sort_order": 3},
    {"code": "area_leader_request",  "label": "区域负责人要求",     "sort_order": 4},
    {"code": "operation_change",     "label": "临时经营变化",       "sort_order": 5},
    {"code": "other",               "label": "其他",               "sort_order": 6},
]
with open(os.path.join(OUTDIR, "modified_reasons.json"), "w", encoding="utf-8") as f:
    json.dump(REASONS, f, ensure_ascii=False, indent=2)
print("✅ modified_reasons.json")

# ============================================================
# 3. 员工数据（复用之前的逻辑）
# ============================================================
SURNAMES = [
    "张","王","李","刘","陈","杨","黄","赵","周","吴",
    "徐","孙","马","朱","胡","郭","何","高","林","罗",
    "郑","梁","谢","宋","唐","韩","曹","许","邓","冯",
    "程","蔡","彭","潘","袁","董","余","苏","叶","吕",
    "魏","蒋","田","杜","丁","沈","姜","范","江","傅",
]
GIVEN_MALE = "伟强磊军勇杰涛明辉鹏飞超波斌锋浩亮健龙华志国建文成海峰".split()
GIVEN_FEMALE = "芳娟敏静丽霞兰萍玲红莲翠凤春花秋梅雪云美慧".split()
GIVEN_MALE_2 = ["建国","志强","伟民","海涛","文彬","俊杰","晓明","建华","国强","永刚","晓东","志远","明辉","大伟","浩宇"]
GIVEN_FEMALE_2 = ["秀英","桂英","玉兰","秀兰","海燕","红梅","丽华","美玲","晓燕","春梅","雪梅","慧敏","小平","秀梅","玉梅"]

random.shuffle(SURNAMES)

# 排班计划：(area_code, total, regular_ct, temp_ct)
# 正式工固定在部门，临时工跨部门混排
PLAN = [
    ("aquatic",       18, 16, 2),   # 水产：正式工做杀鱼等专业岗，临时工做称重/清洁（16正式/2临时）
    ("meat",          18, 16, 2),   # 肉类：正式工做切肉等专业岗，临时工做称重/陈列
    ("produce",       27, 24, 3),   # 果蔬（24正式/3临时）
    ("cashier",       18, 16, 2),   # 收银（16正式/2临时）
    ("replenishment",  9,  8, 1),   # 补货（8正式/1临时）
]
# 合计：正式工 80 + 临时工 10 = 90 人（真实门店结构：正式远多于临时）

NON_PROF_TASKS = {
    ac: [t for t in AREA_TASKS if t["area_code"] == ac and not t["is_professional"]]
    for ac in AREA_CODES
}
PROF_TASKS = {
    ac: [t for t in AREA_TASKS if t["area_code"] == ac and t["is_professional"]]
    for ac in AREA_CODES
}

def gen_name(seed, style):
    surname = SURNAMES[seed % len(SURNAMES)]
    if style == "lao":
        return f"老{surname}"
    if style == "xiao":
        return f"小{surname}"
    r = (seed * 7 + 13) % 100
    if r < 10:
        return f"老{surname}"
    elif r < 25:
        return f"小{surname}"
    else:
        given = random.choice(GIVEN_MALE + GIVEN_MALE_2 + GIVEN_FEMALE + GIVEN_FEMALE_2)
        return f"{surname}{given}"

def level_order(lv):
    return {"S": 4, "A": 3, "B": 2, "C": 1}.get(lv, 0)

def pick_level(seed, force_high=False):
    if force_high:
        return ["S","S","A","A","A"][seed % 5]
    r = (seed * 3 + 7) % 100
    if r < 5: return "S"
    if r < 20: return "A"
    if r < 80: return "B"
    return "C"

employees = []
employee_skills = []
emp_id = 0
name_seed = 0

REGULAR_SHIFT_TYPES = ["morning", "evening", "split", "rotating"]

# 第一遍：生成员工记录，并按区域收集正式工，用于确定性专业岗覆盖
reg_by_area = {ac: [] for ac in AREA_CODES}
emp_meta = []  # (area_code, is_regular, is_temp, eid, name_seed, emp_id)

for area_code, total, reg_ct, temp_ct in PLAN:
    types = (["regular"] * reg_ct + ["temporary"] * temp_ct)
    random.shuffle(types)
    for i in range(total):
        emp_id += 1
        name_seed += 1
        t = types[i]
        is_regular = t == "regular"
        is_temp = t == "temporary"

        # 正式工固定部门，临时工跨部门（main_area=null）
        main = area_code if is_regular else None
        # 临时工周工时上限统一不超过 32（[24, 28, 32]）
        limit = 48 if is_regular else random.choice([24, 28, 32])

        # 正式工有班次偏好，临时工无
        if is_regular:
            shift_type = random.choice(REGULAR_SHIFT_TYPES)
        else:
            shift_type = None

        name = gen_name(name_seed, "lao" if (is_regular and name_seed % 2 == 0) else ("xiao" if is_temp else "auto"))

        eid = f"emp_{emp_id:03d}"
        emp_record = {
            "id": eid, "name": name, "main_area": main,
            "employee_type": t,
            "regular_shift_type": shift_type,
            "weekly_hours_limit": limit, "is_active": 1,
            "is_protected": 0,
        }
        if is_regular:
            reg_by_area[area_code].append(eid)
        employees.append(emp_record)
        emp_meta.append((area_code, is_regular, is_temp, eid, name_seed, emp_id))

# 确定性专业岗覆盖：
# 肉类区(meat) 的 meat_cut/meat_divide、水产区(aquatic) 的 fish_butcher/aquatic_process，
# 每个相关 task 至少分配 4 名满足 min_skill_level 的正式工，
# 且 fish_butcher / meat_cut 至少包含 2 名 S 级员工。
prof_assignment = {}  # (employee_id, task_code) -> skill_level
for ac, prof_tasks in PROF_TASKS.items():
    regs = reg_by_area.get(ac, [])
    if not regs or not prof_tasks:
        continue
    needed = 4
    for tk in prof_tasks:
        min_lv = tk["min_skill_level"]
        for idx, eid in enumerate(regs[:needed]):
            if tk["task_code"] in ("fish_butcher", "meat_cut"):
                lv = "S"
            else:
                lv = "A" if min_lv == "S" else min_lv
            prof_assignment[(eid, tk["task_code"])] = lv

# 第二遍：生成技能
for area_code, is_regular, is_temp, eid, name_seed, emp_id in emp_meta:
    skills = []
    # 正式工：本区域任务（含专业任务）
    if is_regular:
        # 专业任务：确定性保证覆盖（不再随机）
        for tk in PROF_TASKS.get(area_code, []):
            key = (eid, tk["task_code"])
            if key in prof_assignment:
                lv = prof_assignment[key]
                skills.append((eid, area_code, tk["task_code"], lv, round(random.uniform(0.9, 1.0), 2)))
        # 非专业任务：保证至少 1 条本区域技能（保底），其余随机补充
        nonprof = NON_PROF_TASKS.get(area_code, [])
        if nonprof:
            base = random.choice(nonprof)
            lv = pick_level(name_seed + emp_id)
            skills.append((eid, area_code, base["task_code"], lv, round(random.uniform(0.6, 1.0), 2)))
            for tk in nonprof:
                if tk is base:
                    continue
                lv2 = pick_level(name_seed + emp_id + 1)
                if lv2 in ("S", "A", "B") or random.random() < 0.3:
                    skills.append((eid, area_code, tk["task_code"], lv2, round(random.uniform(0.6, 1.0), 2)))
    # 临时工：跨部门非专业任务
    else:
        for ac in AREA_CODES:
            if ac == area_code:
                continue  # 临时工优先去其他部门帮忙，但也可以在本部门
            tasks = NON_PROF_TASKS[ac][:random.randint(1, 2)]
            for tk in tasks:
                lv = pick_level(name_seed + emp_id + hash(tk["task_code"]) % 100)
                if lv in ("S","A","B"):
                    skills.append((eid, ac, tk["task_code"], lv, round(random.uniform(0.5, 0.9), 2)))
        # 临时工也学一点本部门的基础任务
        for tk in NON_PROF_TASKS.get(area_code, [])[:2]:
            lv = pick_level(name_seed + emp_id + 1)
            if lv in ("S","A","B"):
                skills.append((eid, area_code, tk["task_code"], lv, round(random.uniform(0.6, 0.9), 2)))

    # 去重
    seen = {}
    for s in skills:
        k = (s[0], s[1], s[2])
        if k not in seen or level_order(s[3]) > level_order(seen[k][3]):
            seen[k] = s
    for s in seen.values():
        employee_skills.append({
            "id": f"esk_{len(employee_skills)+1:04d}",
            "employee_id": s[0], "area_code": s[1], "task_code": s[2],
            "skill_level": s[3], "area_familiarity": s[4],
        })

# 回填 is_protected：拥有专业岗且技能达 S/A 的员工视为受保护（不可随意调动）
prof_set = {(t["area_code"], t["task_code"]) for t in AREA_TASKS if t.get("is_professional")}
protected_ids = {s["employee_id"] for s in employee_skills
                 if (s["area_code"], s["task_code"]) in prof_set and s["skill_level"] in ("S", "A")}
for e in employees:
    e["is_protected"] = 1 if e["id"] in protected_ids else 0

with open(os.path.join(OUTDIR, "employees.json"), "w", encoding="utf-8") as f:
    json.dump(employees, f, ensure_ascii=False, indent=2)
print(f"✅ employees.json ({len(employees)} people)")

with open(os.path.join(OUTDIR, "employee_skills.json"), "w", encoding="utf-8") as f:
    json.dump(employee_skills, f, ensure_ascii=False, indent=2)
print(f"✅ employee_skills.json ({len(employee_skills)} records)")

# ============================================================
# 2e. employee_weekly_preferences.json — 员工周意愿
# ============================================================
# 每个正式工每周一条意愿（约 70% 与默认不同，30% 相同）
weekly_preferences = []
pref_id = 0
demo_week_start = "2026-07-13"

for e in employees:
    if e["employee_type"] != "regular":
        continue
    if e.get("regular_shift_type") not in ("morning", "evening", "split", "rotating"):
        continue
    pref_id += 1
    default = e["regular_shift_type"]
    # 70% 申请不同于默认的班次，30% 维持默认
    if random.random() < 0.7 and default != "rotating":
        others = [s for s in ("morning", "evening", "split") if s != default]
        preferred = random.choice(others)
    elif default == "rotating":
        # rotating 默认没有具体班次，必须选一个具体意愿
        preferred = random.choice(("morning", "evening", "split"))
    else:
        preferred = default
    weekly_preferences.append({
        "id": f"wp_{pref_id:04d}",
        "employee_id": e["id"],
        "week_start": demo_week_start,
        "preferred_shift_type": preferred,
        "created_at": "2026-07-10T08:00:00Z"
    })

with open(os.path.join(OUTDIR, "employee_weekly_preferences.json"), "w", encoding="utf-8") as f:
    json.dump(weekly_preferences, f, ensure_ascii=False, indent=2)
print(f"✅ employee_weekly_preferences.json ({len(weekly_preferences)} records)")

# ============================================================
# 2f. employee_weekly_leave.json — 员工周休假意愿
# ============================================================
# 每个正式工每周 1 天休假，分到七天里（保证每天都有休假的人以触发冲突解决演示）
leave_preferences = []
leave_id = 0
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# 让休假分布不均匀，按区域集中到某些天以触发冲突
# 每个区域都有自己偏好的休假天，造成该区域当天人手不足
area_day_bias = {
    "aquatic":       ["Monday", "Wednesday", "Monday"],   # 水产区偏好周一/周三
    "meat":          ["Wednesday", "Friday", "Wednesday"], # 肉类偏好周三/周五
    "produce":       ["Friday", "Sunday", "Friday"],       # 果蔬偏好周五/周日
    "cashier":       ["Friday", "Saturday", "Friday"],     # 收银偏好周五/周六
    "replenishment": ["Monday", "Friday", "Friday"],       # 补货偏好周一/周五
}

for e in employees:
    if e["employee_type"] != "regular":
        continue
    leave_id += 1
    area = e["main_area"]
    bias_days = area_day_bias.get(area, WEEKDAYS)
    # 80% 概率选偏好天，20% 随机
    if random.random() < 0.8:
        day = random.choice(bias_days)
    else:
        day = random.choice(WEEKDAYS)
    leave_preferences.append({
        "id": f"lv_{leave_id:04d}",
        "employee_id": e["id"],
        "week_start": demo_week_start,
        "preferred_day_off": day,
        "created_at": "2026-07-10T08:00:00Z"
    })

with open(os.path.join(OUTDIR, "employee_weekly_leave.json"), "w", encoding="utf-8") as f:
    json.dump(leave_preferences, f, ensure_ascii=False, indent=2)
print(f"✅ employee_weekly_leave.json ({len(leave_preferences)} records)")

# ============================================================
# 4. 历史数据 CSV（4 周历史 + 1 周 Demo 天气/节假日）
# ============================================================

# Demo 目标周：2026-07-13 (Mon) ~ 2026-07-19 (Sun)
DEMO_WEEK_START = date(2026, 7, 13)
# 历史数据：前 4 周 2026-06-15 ~ 2026-07-12
HIST_START = date(2026, 6, 15)
HIST_END = date(2026, 7, 12)

def daterange(start, end):
    for n in range((end - start).days + 1):
        yield start + timedelta(n)

# ---------- 4a. historical_sales.csv ----------
with open(os.path.join(OUTDIR, "historical_sales.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "slot", "area_code", "sales_amount", "transaction_count"])
    for d in daterange(HIST_START, HIST_END):
        wd = d.weekday()
        base_factor = [1.0, 1.0, 1.0, 1.05, 1.2, 1.4, 1.3][wd]  # Mon→Sun factor
        for si, slot in enumerate(SLOTS):
            slot_factor = [0.6, 0.8, 1.0, 1.0, 1.1, 1.0, 0.8, 0.7, 0.6, 0.7, 1.2, 1.3, 1.0, 0.7][si]
            for ac in AREA_CODES:
                area_base = {"aquatic": 900, "meat": 1250, "produce": 750, "cashier": 400, "replenishment": 300}[ac]
                slot_ac_factor = {
                    ("aquatic", 0): 1.5, ("aquatic", 1): 1.3,
                    ("meat", 0): 1.4, ("meat", 1): 1.2,
                    ("produce", 10): 1.4, ("produce", 11): 1.3,
                    ("cashier", 4): 1.3, ("cashier", 5): 1.2,
                    ("cashier", 10): 1.4, ("cashier", 11): 1.3,
                    ("replenishment", 0): 1.3, ("replenishment", 1): 1.2,
                    ("replenishment", 10): 1.2, ("replenishment", 11): 1.1,
                }
                saf = slot_ac_factor.get((ac, si), 1.0)
                noise = random.uniform(0.85, 1.15)
                amount = round(area_base * base_factor * slot_factor * saf * noise, 2)
                txn = max(1, round(amount / random.uniform(50, 90)))
                w.writerow([d.isoformat(), slot, ac, amount, txn])
print(f"✅ historical_sales.csv")

# ---------- 4b. historical_traffic.csv ----------
with open(os.path.join(OUTDIR, "historical_traffic.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "slot", "customer_count"])
    for d in daterange(HIST_START, HIST_END):
        wd = d.weekday()
        base = [200, 200, 210, 220, 260, 350, 320][wd]
        for si, slot in enumerate(SLOTS):
            sf = [0.5, 0.7, 0.9, 1.0, 1.1, 1.0, 0.8, 0.7, 0.6, 0.6, 1.2, 1.3, 0.9, 0.7][si]
            noise = random.uniform(0.85, 1.15)
            w.writerow([d.isoformat(), slot, max(1, round(base * sf * noise))])
print(f"✅ historical_traffic.csv")

# ---------- 4c. online_orders.csv ----------
with open(os.path.join(OUTDIR, "online_orders.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "slot", "order_count", "picking_count"])
    for d in daterange(HIST_START, HIST_END):
        wd = d.weekday()
        base = [25, 25, 28, 30, 40, 55, 50][wd]
        for si, slot in enumerate(SLOTS):
            sf = [0.3, 0.5, 0.7, 0.8, 0.9, 0.9, 0.7, 0.6, 0.5, 0.6, 1.4, 1.6, 1.2, 0.8][si]
            noise = random.uniform(0.85, 1.15)
            orders = max(1, round(base * sf * noise))
            picking = max(1, round(orders * random.uniform(0.7, 0.95)))
            w.writerow([d.isoformat(), slot, orders, picking])
print(f"✅ online_orders.csv")

# ---------- 4d. holidays.csv ----------
HOLIDAYS = [
    # 历史期间的节日
    ("2026-06-20", "周末", "weekend", 1),
    ("2026-06-21", "周末", "weekend", 1),
    ("2026-06-27", "周末", "weekend", 1),
    ("2026-06-28", "周末", "weekend", 1),
    ("2026-07-04", "周末", "weekend", 1),
    ("2026-07-05", "周末", "weekend", 1),
    ("2026-07-11", "周末", "weekend", 1),
    ("2026-07-12", "周末", "weekend", 1),
    # Demo 周的周末
    ("2026-07-18", "周末", "weekend", 1),
    ("2026-07-19", "周末", "weekend", 1),
]
with open(os.path.join(OUTDIR, "holidays.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "holiday_name", "holiday_type", "is_weekend"])
    for h in HOLIDAYS:
        w.writerow(h)
print(f"✅ holidays.csv")

# ---------- 4e. weather.csv ----------
# Demo 周天气：周五降雨，其他晴/多云
DEMO_WEATHER = {
    date(2026, 7, 13): ("cloudy", 28, 0, 2),   # Mon
    date(2026, 7, 14): ("cloudy", 29, 0, 2),   # Tue
    date(2026, 7, 15): ("sunny",  31, 0, 1),   # Wed
    date(2026, 7, 16): ("sunny",  32, 0, 1),   # Thu
    date(2026, 7, 17): ("rainy",  26, 3, 2),   # Fri ← 降雨
    date(2026, 7, 18): ("cloudy", 27, 0, 2),   # Sat
    date(2026, 7, 19): ("sunny",  30, 0, 1),   # Sun
}

with open(os.path.join(OUTDIR, "weather.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "slot", "weather_type", "temperature", "rain_level", "wind_level"])
    for d in daterange(HIST_START, HIST_END):
        # 历史天气按季节规律随机生成（夏季）
        wd = d.weekday()
        wt = random.choices(["sunny", "cloudy", "rainy"], weights=[5, 3, 1])[0]
        temp = random.randint(24, 33)
        rain = random.randint(0, 1) if wt == "rainy" else 0
        if wt == "rainy":
            rain = random.randint(1, 4)
        wind = random.randint(1, 3)
        for slot in SLOTS:
            w.writerow([d.isoformat(), slot, wt, temp, rain, wind])
    # Demo 周
    for d in daterange(DEMO_WEEK_START, date(2026, 7, 19)):
        wt_info = DEMO_WEATHER.get(d, ("sunny", 28, 0, 1))
        wt, temp, rain, wind = wt_info
        for slot in SLOTS:
            w.writerow([d.isoformat(), slot, wt, temp, rain, wind])
print(f"✅ weather.csv")

# ---------- 4f. promotions.csv ----------
PROMOTIONS = [
    ("promo_001", "2026-07-17", "produce", "high", 1.3, "周五果蔬会员日"),
    ("promo_002", "2026-07-18", "meat", "low", 1.2, "周末肉类特惠"),
    ("promo_003", "2026-07-19", "aquatic", "low", 1.25, "周日水产促销"),
]
with open(os.path.join(OUTDIR, "promotions.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "date", "area_code", "promotion_type", "boost_factor", "description"])
    for p in PROMOTIONS:
        w.writerow(p)
print(f"✅ promotions.csv")

# ============================================================
# 统计汇总
# ============================================================
from collections import Counter
tc = Counter(e["employee_type"] for e in employees)
ac = Counter(e["main_area"] for e in employees)
print(f"\n--- Complete ---")
print(f"Employees: {len(employees)} (regular={tc.get('regular',0)}, temporary={tc.get('temporary',0)})")
print(f"By area: {dict(ac)}")
print(f"Skills: {len(employee_skills)}")
print(f"\nAll files in {OUTDIR}:")
for fn in sorted(os.listdir(OUTDIR)):
    sz = os.path.getsize(os.path.join(OUTDIR, fn))
    print(f"  {fn:40s} {sz:>8,} bytes")
