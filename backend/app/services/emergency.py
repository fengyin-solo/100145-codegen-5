"""道路突发事件应急业务规则：登记校验、处置流转、看板统计口径都收在这里。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.store import store

MODULE = "emergency"
REQUIRED_FIELDS = ["突发事件类型", "发生位置", "处置班组", "上报时间"]
# 影响范围允许在登记时缺失，但缺了就不进入看板统计
BOARD_REQUIRED_FIELDS = ["影响范围"]
STATUS_ORDER = ["待处置", "处置中", "已控制", "已恢复"]
ACTION_RULES = {"开始处置": "处置中", "态势控制": "已控制", "恢复通行": "已恢复"}
# 不同突发事件类型的默认处置时限（小时）
SLA_HOURS: dict[str, int] = {
    "道路塌陷": 8,
    "路面油污": 4,
    "倒伏树木": 6,
}
SLA_DEFAULT_HOURS = 8
TIME_FORMAT = "%Y-%m-%d %H:%M"


def _parse_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in (TIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _format_time(value: datetime) -> str:
    return value.strftime(TIME_FORMAT)


def _is_overdue(entry: dict[str, Any], now: datetime | None = None) -> bool:
    """在办件（未恢复）且当前时间已超过处置期限算超期；不合规件不参与统计口径。"""
    if entry.get("status") == "已恢复":
        return False
    if not str(entry.get("影响范围") or "").strip():
        return False
    deadline = _parse_time(str(entry.get("处置期限") or ""))
    if deadline is None:
        return False
    return (now or datetime.now()) > deadline


class EmergencyService:
    # ---------- 列表与详情 ----------
    def list_entries(
        self,
        *,
        crew: str | None = None,
        status: str | None = None,
        include_invalid: bool = True,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(MODULE))
        if crew:
            rows = [row for row in rows if str(row.get("处置班组") or "") == crew]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if not include_invalid:
            rows = [row for row in rows if not row.get("不合规项")]
        rows.sort(key=lambda row: str(row.get("上报时间") or ""), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def crew_options(self) -> list[str]:
        crews = {str(row.get("处置班组") or "").strip() for row in store.rows(MODULE)}
        return sorted(name for name in crews if name)

    # ---------- 登记与流转 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        reported_text = str(values.get("上报时间") or "").strip()
        if reported_text and _parse_time(reported_text) is None:
            missing.append("上报时间格式")
        if missing:
            return None, missing

        event_type = str(values.get("突发事件类型") or "").strip()
        reported = _parse_time(reported_text) or datetime.now()
        sla_hours = int(values.get("处置时限小时") or SLA_HOURS.get(event_type, SLA_DEFAULT_HOURS))
        deadline = reported + timedelta(hours=sla_hours)

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["事件编号"] = str(values.get("事件编号") or f"EMRG-{entry['id']:04d}")
        entry["突发事件类型"] = event_type
        entry["发生位置"] = str(values.get("发生位置") or "").strip()
        entry["影响范围"] = str(values.get("影响范围") or "").strip()
        entry["处置班组"] = str(values.get("处置班组") or "").strip()
        entry["上报时间"] = _format_time(reported.replace(second=0, microsecond=0))
        entry["处置时限小时"] = sla_hours
        entry["处置期限"] = _format_time(deadline)
        entry["上报人员"] = str(values.get("上报人员") or "值班长").strip()
        entry["备注"] = str(values.get("备注") or "").strip()
        entry["timeline"] = [{
            "时间": entry["上报时间"],
            "动作": "事件上报",
            "记录人": entry["上报人员"],
            "说明": "突发事件登记上报",
        }]
        # 影响范围缺失：允许登记，但标记为不合规件，看板统计时剔除
        entry["不合规项"] = [] if entry["影响范围"] else list(BOARD_REQUIRED_FIELDS)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str, operator: str | None = None,
                   note: str | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"突发事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于突发事件可执行范围"
        target = ACTION_RULES[action]
        current_index = STATUS_ORDER.index(entry["status"]) if entry["status"] in STATUS_ORDER else -1
        target_index = STATUS_ORDER.index(target)
        if target_index <= current_index:
            return None, f"事件当前为「{entry['status']}」，不能重复执行「{action}」"
        stamp = _format_time(datetime.now())
        entry.setdefault("timeline", []).append({
            "时间": stamp,
            "动作": action,
            "记录人": (operator or "值班长").strip() or "值班长",
            "说明": (note or f"事件状态更新为{target}").strip(),
        })
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = _is_overdue(entry)
        return entry, f"突发事件已{action}"

    def update_fields(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """补录可后补的字段（目前是影响范围）；补齐后事件重新纳入看板统计。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, [f"突发事件 {entry_id} 不存在或已归档"]
        missing: list[str] = []
        if "影响范围" in values:
            scope = str(values.get("影响范围") or "").strip()
            if not scope:
                missing.append("影响范围")
            else:
                entry["影响范围"] = scope
                if entry.get("不合规项"):
                    entry["不合规项"] = []
                    entry.setdefault("timeline", []).append({
                        "时间": _format_time(datetime.now()),
                        "动作": "补录资料",
                        "记录人": str(values.get("operator") or "值班长").strip() or "值班长",
                        "说明": "补录影响范围，资料合规，重新纳入处置概览统计",
                    })
                entry["abnormal"] = _is_overdue(entry)
        if missing:
            return None, [f"补录内容不能为空：{'、'.join(missing)}"]
        return entry, []

    # ---------- 处置概览看板 ----------
    def board(self, *, crew: str | None = None, start: str | None = None,
              end: str | None = None) -> dict[str, Any]:
        """按班组与上报时间范围出处置概览。

        影响范围缺失的事件不进入任何件数统计，单列在 invalid 里并点名缺失项。
        """
        start_dt = _parse_time(start or "")
        end_dt = _parse_time(end or "")
        # 只给日期不给时分时，结束时间按当天 23:59 收口
        if end_dt is not None and end and len(end.strip()) == 10:
            end_dt = end_dt.replace(hour=23, minute=59)

        scoped: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            if crew and str(row.get("处置班组") or "") != crew:
                continue
            reported = _parse_time(str(row.get("上报时间") or ""))
            if start_dt is not None and (reported is None or reported < start_dt):
                continue
            if end_dt is not None and (reported is None or reported > end_dt):
                continue
            scoped.append(row)

        valid_rows = [row for row in scoped if not row.get("不合规项")]
        invalid_rows = [
            {
                "id": row.get("id"),
                "事件编号": row.get("事件编号"),
                "突发事件类型": row.get("突发事件类型"),
                "发生位置": row.get("发生位置"),
                "处置班组": row.get("处置班组"),
                "上报时间": row.get("上报时间"),
                "不合规项": list(row.get("不合规项") or BOARD_REQUIRED_FIELDS),
                "原因": "、".join(row.get("不合规项") or BOARD_REQUIRED_FIELDS) + "缺失",
            }
            for row in scoped if row.get("不合规项")
        ]

        counts = {status: 0 for status in STATUS_ORDER}
        for row in valid_rows:
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
        overdue_count = sum(1 for row in valid_rows if _is_overdue(row))

        workload_map: dict[str, dict[str, Any]] = {}
        for row in valid_rows:
            name = str(row.get("处置班组") or "未指派班组")
            bucket = workload_map.setdefault(name, {
                "crew": name, "inProgress": 0, "overdue": 0,
                "待处置": 0, "处置中": 0, "已控制": 0, "已恢复": 0,
            })
            status = str(row.get("status") or "")
            if status in ("待处置", "处置中", "已控制"):
                bucket["inProgress"] += 1
            if status in bucket:
                bucket[status] += 1
            if _is_overdue(row):
                bucket["overdue"] += 1

        items = sorted(valid_rows, key=lambda row: str(row.get("上报时间") or ""), reverse=True)
        return {
            "filters": {
                "crew": crew or "",
                "start": start or "",
                "end": end or "",
                "crewOptions": self.crew_options(),
            },
            "counts": counts,
            "overdueCount": overdue_count,
            "total": len(valid_rows),
            "crewWorkload": sorted(workload_map.values(), key=lambda item: item["crew"]),
            "items": items,
            "invalid": invalid_rows,
        }
