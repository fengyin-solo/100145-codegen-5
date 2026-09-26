"""道路突发事件应急业务规则。

看板统计口径、超期判定、状态流转都收在这里，路由层不做业务判断：

- 影响范围缺失的事件可以登记，但属于「不合规件」，不进入看板统计，
  看板单独列出并指明不合规项；
- 看板件数、班组在办量、超期件数与列表同源于一次筛选，保证看板和
  详情往返后看到的件数一致；
- 状态只能沿 待处置 → 处置中 → 已控制 → 已恢复 单向推进，每次推进
  都往处置经过（timeline）里追加一条。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.store import store

MODULE = "emergency"

# 登记必填：发生位置、处置班组、上报时间默认取当前时间
REQUIRED_FIELDS = ["事件类型", "发生位置", "处置班组"]
# 影响范围是进入看板统计的硬性合规项：允许先登记后补录，缺失期间不进统计
BOARD_FIELDS = ["影响范围"]

STATUS_ORDER = ["待处置", "处置中", "已控制", "已恢复"]
# 在办 = 尚未恢复，即待处置、处置中、已控制三档
ACTIVE_STATUSES = STATUS_ORDER[:-1]
# 不同事件类型的到场处置时限（小时）
SLA_HOURS = {"道路塌陷": 4, "路面油污": 6, "倒伏树木": 2, "积水路面": 4}
DEFAULT_SLA_HOURS = 4

STAGE_NOTES = {
    "处置中": "班组到达现场，设置围挡并开展处置",
    "已控制": "险情已控制，现场转入清理收尾",
    "已恢复": "路面清理验收完毕，道路恢复正常通行",
}
EVENT_KINDS = list(SLA_HOURS)
CREWS = ["应急一队", "应急二队", "应急三队", "市政排水队"]


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def parse_time(value: Any) -> datetime | None:
    """兼容 'YYYY-MM-DD HH:MM'、'YYYY-MM-DDTHH:MM' 与纯日期三种写法。"""
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _sla_hours(row: dict[str, Any]) -> int:
    """优先读登记时落的「处置时限」，读不出来再按事件类型取默认时限。"""
    text = str(row.get("处置时限") or "").strip()
    if text.endswith("小时"):
        try:
            return int(text[:-2])
        except ValueError:
            pass
    return SLA_HOURS.get(str(row.get("事件类型") or ""), DEFAULT_SLA_HOURS)


def is_overdue(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    """超过上报时限仍未恢复即超期；已恢复的件不再算超期。"""
    if row.get("status") == "已恢复":
        return False
    reported = parse_time(row.get("上报时间"))
    if reported is None:
        return False
    moment = now or datetime.now()
    return moment > reported + timedelta(hours=_sla_hours(row))


def board_invalid_reasons(row: dict[str, Any]) -> list[str]:
    """指出该事件不合规、不能进看板统计的具体项；为空表示合规。"""
    return [field for field in BOARD_FIELDS if not str(row.get(field) or "").strip()]


class EmergencyService:
    # ---------- 登记与明细 ----------
    def create_event(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        event = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        kind = str(values["事件类型"]).strip()
        sla_hours = SLA_HOURS.get(kind, DEFAULT_SLA_HOURS)
        reported_at = str(values.get("上报时间") or "").strip() or _now_text()
        crew = str(values["处置班组"]).strip()
        event.update({
            "事件编号": f"EMER-{event['id']:04d}",
            "事件类型": kind,
            "发生位置": str(values["发生位置"]).strip(),
            # 影响范围允许先缺后补：缺失照常登记，但不进看板统计
            "影响范围": str(values.get("影响范围") or "").strip(),
            "处置班组": crew,
            "上报时间": reported_at,
            "上报人员": str(values.get("上报人员") or "值班管理员").strip() or "值班管理员",
            "处置时限": f"{sla_hours}小时",
        })
        event["status"] = "待处置"
        event["pending"] = True
        event["abnormal"] = False
        event["timeline"] = [{
            "stage": "待处置",
            "time": reported_at,
            "crew": "应急中心",
            "note": "应急中心接报登记，等待班组出动",
        }]
        rows.append(event)
        return self._serialize(event), []

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        event = store.find(MODULE, event_id)
        if event is None:
            return None
        return self._serialize(event)

    def list_events(
        self,
        *,
        crew: str | None = None,
        start: str | None = None,
        end: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """明细分页：与看板同一套筛选口径，不合规件同样可以在这里查到。"""
        rows = self._filter_rows(crew=crew, start=start, end=end, status=status)
        total = len(rows)
        left = max(page - 1, 0) * size
        return [self._serialize(row) for row in rows[left:left + size]], total

    # ---------- 看板 ----------
    def board(
        self,
        *,
        crew: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """处置概览看板：状态件数、班组在办量、超期件数与事件列表同源计算。

        班组在办量始终只受时间范围约束，不受当前班组筛选影响，这样值班长
        在班组视图里也能横向对比各队在办量（点击队名即可切换视图）。
        """
        invalid_rows = [row for row in store.rows(MODULE) if board_invalid_reasons(row)]
        valid_rows = [row for row in store.rows(MODULE) if not board_invalid_reasons(row)]

        time_rows = self._within_range(valid_rows, start, end)
        crew_stats = self._crew_stats(time_rows, start, end)

        filtered = self._filter_rows(crew=crew, start=start, end=end, rows=valid_rows)
        now = datetime.now()
        items = [self._serialize(row, now=now) for row in filtered]
        counts = {stage: 0 for stage in STATUS_ORDER}
        for row in filtered:
            counts[str(row.get("status"))] = counts.get(str(row.get("status")), 0) + 1
        overdue = sum(1 for row in filtered if is_overdue(row, now=now))

        cards = [
            {"label": "待处置", "value": counts["待处置"]},
            {"label": "处置中", "value": counts["处置中"]},
            {"label": "已控制", "value": counts["已控制"]},
            {"label": "已恢复", "value": counts["已恢复"]},
            {"label": "在办合计", "value": sum(counts[stage] for stage in ACTIVE_STATUSES)},
            {"label": "超期件", "value": overdue},
        ]
        return {
            "cards": cards,
            "crewStats": crew_stats,
            "items": items,
            "total": len(items),
            "excluded": [self._excluded_item(row) for row in invalid_rows],
            "excludedTotal": len(invalid_rows),
            "filters": {"crew": crew or "", "start": start or "", "end": end or ""},
        }

    def _crew_stats(self, rows: list[dict[str, Any]], start: str | None, end: str | None) -> list[dict[str, Any]]:
        """各处置班组在办量（待处置/处置中/已控制）与其中超期件数。"""
        now = datetime.now()
        names = sorted({str(row.get("处置班组") or "").strip() for row in rows if row.get("处置班组")})
        stats: list[dict[str, Any]] = []
        for name in names:
            crew_rows = [row for row in rows if str(row.get("处置班组") or "").strip() == name]
            active = [row for row in crew_rows if row.get("status") in ACTIVE_STATUSES]
            stats.append({
                "crew": name,
                "active": len(active),
                "overdue": sum(1 for row in active if is_overdue(row, now=now)),
                "recovered": sum(1 for row in crew_rows if row.get("status") == "已恢复"),
            })
        stats.sort(key=lambda item: (-item["active"], item["crew"]))
        return stats

    def _excluded_item(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "事件编号": row.get("事件编号"),
            "事件类型": row.get("事件类型"),
            "发生位置": row.get("发生位置"),
            "处置班组": row.get("处置班组"),
            "上报时间": row.get("上报时间"),
            "reasons": board_invalid_reasons(row),
            "message": f"影响范围缺失（不合规项：{'、'.join(board_invalid_reasons(row))}），暂不进入看板统计",
        }

    # ---------- 状态流转 ----------
    def advance(self, event_id: int, action: str, *, operator: str = "") -> tuple[dict[str, Any] | None, str]:
        event = store.find(MODULE, event_id)
        if event is None:
            return None, f"突发事件 {event_id} 不存在"
        current = str(event.get("status") or "")
        if action != "推进处置":
            return None, f"动作「{action}」不属于突发事件应急可执行范围"
        index = STATUS_ORDER.index(current) if current in STATUS_ORDER else -1
        if index < 0:
            return None, f"当前状态「{current}」不在处置状态序列里"
        if index >= len(STATUS_ORDER) - 1:
            return None, "该事件已恢复，无需继续推进"
        target = STATUS_ORDER[index + 1]
        event["status"] = target
        event["pending"] = target != "已恢复"
        event.setdefault("timeline", []).append({
            "stage": target,
            "time": _now_text(),
            "crew": event.get("处置班组", ""),
            "note": STAGE_NOTES[target],
            "operator": operator or "值班管理员",
        })
        return self._serialize(event), f"处置状态已推进为「{target}」"

    def supplement(
        self,
        event_id: int,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        """补录影响范围：补全后不合规件即纳入看板统计，并在处置经过中留痕。"""
        event = store.find(MODULE, event_id)
        if event is None:
            return None, f"突发事件 {event_id} 不存在"
        impact = str(values.get("影响范围") or "").strip()
        if not impact:
            return None, "影响范围仍为空，补录后才能纳入看板统计"
        event["影响范围"] = impact
        event.setdefault("timeline", []).append({
            "stage": event.get("status", "待处置"),
            "time": _now_text(),
            "crew": event.get("处置班组", ""),
            "note": f"补录影响范围：{impact}",
            "operator": str(values.get("operator") or "值班管理员"),
        })
        return self._serialize(event), "影响范围已补录，该事件纳入看板统计"

    # ---------- 筛选与序列化 ----------
    def _filter_rows(
        self,
        *,
        crew: str | None = None,
        start: str | None = None,
        end: str | None = None,
        status: str | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        result = rows if rows is not None else store.rows(MODULE)
        crew = (crew or "").strip()
        if crew:
            result = [row for row in result if str(row.get("处置班组") or "").strip() == crew]
        if status:
            result = [row for row in result if row.get("status") == status]
        return self._within_range(result, start, end)

    def _within_range(
        self,
        rows: list[dict[str, Any]],
        start: str | None,
        end: str | None,
    ) -> list[dict[str, Any]]:
        """按上报时间过滤；只传开始日期时含当天，结束日期补到当日 23:59。"""
        start_dt = parse_time(start)
        end_dt = parse_time(end)
        if end_dt is not None and len(str(end).strip()) == 10:
            end_dt = end_dt + timedelta(days=1) - timedelta(seconds=1)
        if start_dt is None and end_dt is None:
            return list(rows)

        def kept(row: dict[str, Any]) -> bool:
            reported = parse_time(row.get("上报时间"))
            if reported is None:
                return False
            if start_dt is not None and reported < start_dt:
                return False
            if end_dt is not None and reported > end_dt:
                return False
            return True

        return [row for row in rows if kept(row)]

    def _serialize(self, row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        moment = now or datetime.now()
        invalid = board_invalid_reasons(row)
        data = dict(row)
        data["overdue"] = is_overdue(row, now=moment)
        data["active"] = row.get("status") in ACTIVE_STATUSES
        data["boardEligible"] = not invalid
        data["invalidReasons"] = invalid
        data.setdefault("timeline", [])
        return data
