from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_schedule_service
from app.models.schemas import GenerateScheduleRequest, LeavePreferenceUpdateRequest, ModifyScheduleRequest
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("/generate")
def generate_schedule(
    request: GenerateScheduleRequest,
    service: ScheduleService = Depends(get_schedule_service),
):
    try:
        return service.generate(request)
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "STORE_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"error_code": code}) from exc


@router.get("/leave-options")
def get_leave_options(service: ScheduleService = Depends(get_schedule_service)):
    return service.regular_employees()


@router.get("/versions")
def get_schedule_versions(
    store_id: str | None = Query(default=None),
    week_start: str | None = Query(default=None),
    service: ScheduleService = Depends(get_schedule_service),
):
    return service.versions(store_id, week_start)


@router.post("/leave-preferences")
def update_leave_preference(
    request: LeavePreferenceUpdateRequest,
    service: ScheduleService = Depends(get_schedule_service),
):
    try:
        return service.upsert_leave_preference(request)
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "EMPLOYEE_NOT_FOUND" else 409 if code.startswith("LEAVE_REJECTED") else 400
        if code.startswith("LEAVE_REJECTED:"):
            raise HTTPException(status_code=status, detail={"error_code": "LEAVE_REJECTED", "message": code.split(":", 1)[1]}) from exc
        messages = {
            "EMPLOYEE_NOT_FOUND": "未找到可申请休假的正式工。",
            "INVALID_WEEK_START": "排班周起始日期必须是周一。",
            "LEAVE_TOO_LATE": "请假至少需要提前一天，已过去或当天的班表不能修改。",
        }
        raise HTTPException(status_code=status, detail={"error_code": code, "message": messages.get(code, code)}) from exc


@router.get("/{version_id}")
def get_schedule(version_id: str, service: ScheduleService = Depends(get_schedule_service)):
    response = service.get(version_id)
    if not response:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND"})
    return response


@router.patch("/{version_id}/items/{item_id}")
def modify_schedule_item(
    version_id: str,
    item_id: str,
    request: ModifyScheduleRequest,
    service: ScheduleService = Depends(get_schedule_service),
):
    response = service.modify(version_id, item_id, request)
    if not response:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
    if response.requires_confirmation:
        raise HTTPException(status_code=409, detail=response.model_dump())
    return response


@router.get("/{version_id}/preferences")
def get_preferences(
    version_id: str,
    employee_id: str | None = Query(default=None),
    service: ScheduleService = Depends(get_schedule_service),
):
    rows = service.preferences(version_id, employee_id)
    if rows is None:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND"})
    return rows


@router.get("/{version_id}/leave-preferences")
def get_leave_preferences(
    version_id: str,
    employee_id: str | None = Query(default=None),
    service: ScheduleService = Depends(get_schedule_service),
):
    rows = service.leave_preferences(version_id, employee_id)
    if rows is None:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND"})
    return rows


@router.get("/{version_id}/leave-resolution")
def get_leave_resolution(version_id: str, service: ScheduleService = Depends(get_schedule_service)):
    rows = service.leave_resolution(version_id)
    if rows is None:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND"})
    return rows


@router.get("/{version_id}/kpis")
def get_kpis(version_id: str, service: ScheduleService = Depends(get_schedule_service)):
    rows = service.kpis(version_id)
    if rows is None:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND"})
    return rows


@router.get("/{version_id}/risks")
def get_risks(version_id: str, service: ScheduleService = Depends(get_schedule_service)):
    rows = service.risks(version_id)
    if rows is None:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND"})
    return rows


@router.get("/{version_id}/interventions")
def get_interventions(version_id: str, service: ScheduleService = Depends(get_schedule_service)):
    rows = service.interventions(version_id)
    if rows is None:
        raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND"})
    return rows
