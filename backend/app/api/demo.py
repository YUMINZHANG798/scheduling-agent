from fastapi import APIRouter, Depends

from app.dependencies import get_demand_service, get_schedule_service
from app.services.demand_service import DemandService
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset_demo(service: ScheduleService = Depends(get_schedule_service)):
    service.reset_demo()
    return {"ok": True, "message": "Demo 数据已重置，已生成合理波动的历史排班样本"}


@router.get("/source-data")
def source_data(service: DemandService = Depends(get_demand_service)):
    return service.source_summary()
