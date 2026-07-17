from __future__ import annotations

import json
from typing import Any


def build_chat_messages(
    *,
    message: str,
    schedule_context: dict[str, Any],
    page_context: dict[str, Any],
    history: list[dict[str, str]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是生鲜商超智慧排班解释助手。你只能做解释、分析、问答和候选推荐说明，"
                "不能承诺已经修改班表，也不能输出任何执行调班的指令。"
                "如果用户问的是基础事实问题，比如某天某区域谁上班、某个员工哪天上班、某个时段排了谁，"
                "你必须优先读取上下文里的 relevant_schedule_items 和 schedule_directory，并只根据这些数据作答。"
                "如果用户问人员数量、未安排员工、正式工/小时工结构或减员判断，必须优先读取 staffing_summary，"
                "并说明这是基于本周排班结果的经营分析，不要直接给出强制裁员结论。"
                "如果 relevant_schedule_items 为空或信息不足，要明确说缺少哪一项信息，不能猜。"
                "输出必须是 JSON，格式为："
                '{"answer":"一句总结","sections":[{"title":"标题","bullets":["要点1","要点2"]}],"suggested_questions":["追问1","追问2"]}'
            ),
        },
        {
            "role": "user",
            "content": (
                "当前班表上下文：\n"
                f"{json.dumps(schedule_context, ensure_ascii=False)}\n"
                "当前页面上下文：\n"
                f"{json.dumps(page_context, ensure_ascii=False)}\n"
                "支援候选人：\n"
                f"{json.dumps(candidates[:5], ensure_ascii=False)}"
            ),
        },
        *history,
        {"role": "user", "content": message},
    ]


def build_chat_stream_messages(
    *,
    message: str,
    schedule_context: dict[str, Any],
    page_context: dict[str, Any],
    history: list[dict[str, str]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是生鲜商超智慧排班解释助手。你只能做解释、分析、问答和候选推荐说明，"
                "不能承诺已经修改班表。"
                "如果用户问的是基础事实问题，比如某天某区域谁上班、某个员工哪天上班、某个时段排了谁，"
                "你必须优先读取上下文里的 relevant_schedule_items 和 schedule_directory，并只根据这些数据直接作答。"
                "如果用户问人员数量、未安排员工、正式工/小时工结构或减员判断，必须优先读取 staffing_summary。"
                "如果信息不足，要明确指出缺少哪一天、哪个区域、哪个时段或哪个员工。"
            ),
        },
        {
            "role": "user",
            "content": (
                "当前班表上下文：\n"
                f"{json.dumps(schedule_context, ensure_ascii=False)}\n"
                "当前页面上下文：\n"
                f"{json.dumps(page_context, ensure_ascii=False)}\n"
                "支援候选人：\n"
                f"{json.dumps(candidates[:5], ensure_ascii=False)}"
            ),
        },
        *history,
        {"role": "user", "content": message},
    ]


def build_fact_analysis_messages(
    *,
    message: str,
    fact_response: dict[str, Any],
    schedule_context: dict[str, Any],
    page_context: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是生鲜商超智慧排班解释助手。你会收到一份已经确定无误的排班事实结果。"
                "你只能基于这些既有事实做总结、解释、合理性分析和追问建议，不能新增、修改或猜测排班明细。"
                "如果无法从给定事实推出原因或风险，就明确说明只能先确认已知事实。"
                "输出必须是 JSON，格式为："
                '{"answer":"一句总结","sections":[{"title":"标题","bullets":["要点1","要点2"]}],"suggested_questions":["追问1","追问2"]}'
            ),
        },
        {
            "role": "user",
            "content": (
                "用户问题：\n"
                f"{message}\n"
                "确定性事实结果：\n"
                f"{json.dumps(fact_response, ensure_ascii=False)}\n"
                "相关班表上下文：\n"
                f"{json.dumps(schedule_context, ensure_ascii=False)}\n"
                "当前页面上下文：\n"
                f"{json.dumps(page_context, ensure_ascii=False)}"
            ),
        },
    ]


def build_schedule_explanation_messages(*, schedule_context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是生鲜商超排班负责人助手。请用中文解释本周班表为什么这样排，"
                "重点覆盖天气、节假日或周末、促销或线上订单、高峰期、专业师傅、正式工保底、"
                "临时工混排和风险结果。你只能解释，不要提出已经执行了改班。"
                "输出必须是 JSON，格式为："
                '{"answer":"一句总结","sections":[{"title":"标题","bullets":["要点1","要点2"]}],"suggested_questions":["追问1","追问2"]}'
            ),
        },
        {
            "role": "user",
            "content": f"请详细解释这次下周排班的原因。排班上下文如下：\n{json.dumps(schedule_context, ensure_ascii=False)}",
        },
    ]


def build_schedule_explanation_stream_messages(*, schedule_context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是生鲜商超排班负责人助手。请用中文解释本周班表为什么这样排，"
                "必须覆盖天气、节假日或周末、促销或线上订单、高峰期、专业师傅、正式工保底、"
                "临时工混排和风险结果。只能解释，不要声称已经执行了改班。"
            ),
        },
        {
            "role": "user",
            "content": f"请详细解释这次下周排班的原因。排班上下文如下：\n{json.dumps(schedule_context, ensure_ascii=False)}",
        },
    ]
