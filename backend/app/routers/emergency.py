"""道路突发事件应急接口：处置概览看板、事件登记、处置经过与状态推进。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.emergency import (
    CREWS,
    EVENT_KINDS,
    STATUS_ORDER,
    EmergencyService,
)

router = APIRouter(prefix="/api/emergency", tags=["道路突发事件应急"])

service = EmergencyService()

LIST_FIELDS = ["事件编号", "事件类型", "发生位置", "影响范围", "处置班组", "上报时间", "上报人员", "处置时限"]


@router.get("/board")
def board(
    crew: str | None = Query(default=None, description="按处置班组切换视图"),
    start: str | None = Query(default=None, description="上报时间起，YYYY-MM-DD"),
    end: str | None = Query(default=None, description="上报时间止，YYYY-MM-DD"),
) -> dict:
    """处置概览看板：待处置/处置中/已控制/已恢复件数、各班组在办量与超期件数。

    影响范围缺失的事件不参与统计，在 excluded 里点名是哪一项不合规。
    卡片件数、班组在办量与下方列表同源，保证从详情返回后看到同一份件数。
    """
    return service.board(crew=crew, start=start, end=end)


@router.get("/options")
def options() -> dict:
    """登记与筛选用的固定选项：处置班组、事件类型、处置状态。"""
    return {"crews": CREWS, "kinds": EVENT_KINDS, "statuses": STATUS_ORDER}


@router.get("", response_model=PageResult[dict])
def list_events(
    crew: str | None = Query(default=None, description="按处置班组过滤"),
    status: str | None = Query(default=None, description="待处置、处置中、已控制、已恢复"),
    start: str | None = Query(default=None, description="上报时间起，YYYY-MM-DD"),
    end: str | None = Query(default=None, description="上报时间止，YYYY-MM-DD"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """突发事件明细分页；不合规件也能在这里查到，看板统计才排除它们。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_events(
        crew=crew, status=status, start=start, end=end, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{event_id}", response_model=dict)
def get_event(event_id: int) -> dict:
    """读取单条突发事件明细与完整处置经过；不存在时给出可读说明。"""
    event = service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"突发事件 {event_id} 不存在")
    return event


@router.post("", response_model=ActionResult)
def create_event(payload: EntryPayload) -> ActionResult:
    """登记突发事件（发生位置、处置班组、上报时间等）。

    缺必填字段时说明缺哪几项；影响范围允许先登记后补录，
    缺失期间不进入看板统计，只在看板的不合规清单里点名说明。
    """
    event, missing = service.create_event(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="突发事件已登记", entry=event)


@router.post("/{event_id}/actions", response_model=ActionResult)
def run_action(event_id: int, payload: EntryPayload) -> ActionResult:
    """推进处置状态（待处置→处置中→已控制→已恢复），每次推进追加处置经过。"""
    action = str(payload.values.get("action") or "推进处置").strip()
    operator = str(payload.values.get("operator") or "").strip()
    event, message = service.advance(event_id, action, operator=operator)
    if event is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=event)


@router.post("/{event_id}/supplement", response_model=ActionResult)
def supplement_event(event_id: int, payload: EntryPayload) -> ActionResult:
    """补录影响范围：补全后不合规件重新纳入看板统计，并在处置经过中留痕。"""
    event, message = service.supplement(event_id, payload.values)
    if event is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=event)
