from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import httpx

from app.dependencies import get_agent_service
from app.models.schemas import AgentChatRequest, ExplainDemandRequest, RecommendSupportRequest, ScheduleExplanationRequest
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat")
def chat(request: AgentChatRequest, service: AgentService = Depends(get_agent_service)):
    response = service.chat(request.message, request.version_id, request.context, request.history)
    if response["intent"] == "llm_unavailable":
        raise HTTPException(status_code=503, detail={"error_code": "LLM_UNAVAILABLE", "message": response["message"]})
    return response


@router.post("/chat/stream")
def chat_stream(request: AgentChatRequest, service: AgentService = Depends(get_agent_service)):
    return StreamingResponse(
        _sse(service.stream_chat(request.message, request.version_id, request.context, request.history)),
        media_type="text/event-stream",
    )


@router.post("/schedule-explanation")
def schedule_explanation(request: ScheduleExplanationRequest, service: AgentService = Depends(get_agent_service)):
    response = service.schedule_explanation(request.version_id)
    if response["message"].startswith("没有找到"):
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND", "message": response["message"]})
    if response["intent"] == "schedule_version_incomplete":
        raise HTTPException(status_code=409, detail={"error_code": "SCHEDULE_VERSION_INCOMPLETE", "message": response["message"]})
    if response["message"].startswith("LLM 调用失败"):
        raise HTTPException(status_code=503, detail={"error_code": "LLM_UNAVAILABLE", "message": response["message"]})
    return response


@router.post("/schedule-explanation/stream")
def schedule_explanation_stream(request: ScheduleExplanationRequest, service: AgentService = Depends(get_agent_service)):
    try:
        stream = service.stream_schedule_explanation(request.version_id)
    except ValueError as exc:
        code = str(exc)
        if code == "VERSION_NOT_FOUND":
            raise HTTPException(status_code=404, detail={"error_code": code, "message": "没有找到这版班表，请先生成下周排班。"}) from exc
        if code == "SCHEDULE_VERSION_INCOMPLETE":
            raise HTTPException(status_code=409, detail={"error_code": code, "message": "这版班表缺少需求或排班明细，请重新生成下周排班。"}) from exc
        raise
    return StreamingResponse(_sse(stream), media_type="text/event-stream")


@router.post("/recommend-support")
def recommend_support(request: RecommendSupportRequest, service: AgentService = Depends(get_agent_service)):
    candidates = service.recommend_support(
        request.version_id,
        request.date,
        request.slot,
        request.area_code,
        request.task_code,
    )
    if not candidates:
        return {"candidates": [], "message": "未找到可用候选人，建议放宽时段或检查临时工技能。"}
    return {"candidates": candidates}


@router.post("/explain-demand")
def explain_demand(request: ExplainDemandRequest, service: AgentService = Depends(get_agent_service)):
    response = service.explain_demand(request.version_id, request.date, request.slot, request.area_code)
    if response["message"].startswith("暂未找到"):
        raise HTTPException(status_code=404, detail={"error_code": "DEMAND_NOT_FOUND", "message": response["message"]})
    return response


def _sse(chunks: Iterator[str]) -> Iterator[str]:
    try:
        for chunk in chunks:
            yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
    except (RuntimeError, httpx.HTTPError) as exc:
        yield f"data: {json.dumps({'error': f'LLM 流式调用失败：{str(exc)}'}, ensure_ascii=False)}\n\n"
