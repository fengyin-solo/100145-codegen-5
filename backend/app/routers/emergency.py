"""道路突发事件应急接口：处置概览看板、事件登记、处置经过与状态流转。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.emergency import EmergencyService

router = APIRouter(prefix="/api/emergency", tags=["突发事件应急"])

service = EmergencyService()


@router.get("/board")
def board(
    crew: str | None = Query(default=None, description="按处置班组切换视图"),
    start: str | None = Query(default=None, description="上报时间起，YYYY-MM-DD 或 YYYY-MM-DD HH:MM"),
    end: str | None = Query(default=None, description="上报时间止，YYYY-MM-DD 或 YYYY-MM-DD HH:MM"),
) -> dict[str, Any]:
    """处置概览看板：四状态件数、班组在办量、超期件数与不合规件清单共用同一份筛选口径。"""
    return service.board(crew=crew, start=start, end=end)


@router.get("", response_model=PageResult[dict])
def list_entries(
    crew: str | None = Query(default=None, description="按处置班组过滤"),
    status: str | None = Query(default=None, description="待处置、处置中、已控制、已恢复"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """突发事件列表（含影响范围缺失的不合规件，看板统计时另行剔除）。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(crew=crew, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条突发事件完整处置经过；不存在时给出可读说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"突发事件 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一件突发事件；影响范围可以缺失（标记不合规、不进看板），其余必填项缺失会被拦下。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    message = "突发事件已登记"
    if entry and entry.get("不合规项"):
        message += "；影响范围缺失，该件不进入处置概览统计，请补录后复核"
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """推进处置状态：开始处置、态势控制、恢复通行，并把动作追加到处置经过。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "值班长").strip()
    note = str(payload.values.get("note") or "").strip()
    entry, message = service.run_action(entry_id, action, operator=operator, note=note)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def patch_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """补录影响范围等可后补字段；补齐后不合规标记解除，重新进入看板统计。"""
    entry, messages = service.update_fields(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message="；".join(messages))
    return ActionResult(ok=True, message="资料已补录，该事件重新进入处置概览统计", entry=entry)
