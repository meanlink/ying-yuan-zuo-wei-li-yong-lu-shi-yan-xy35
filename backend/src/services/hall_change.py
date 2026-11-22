from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from ..hall_models import HallAssignment, HallChangeAttempt
from ..models import AuditLog, ExperimentUnit, ScreeningPlan, TicketObservation, now_utc


def audit(db, user, action, entity_type, entity_id, detail=''):
    db.add(AuditLog(actor_id=user.id if user else None, action=action,
                    entity_type=entity_type, entity_id=str(entity_id), detail=detail))


def _naive_utc(value: datetime) -> datetime:
    """数据库列是无时区时间戳，统一转成 UTC naive 再比较。"""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _virtual_segment(unit: ExperimentUnit) -> HallAssignment:
    """未产生任何厅段记录的历史单元：用单元配置合成开场厅段（只读，不落库）。"""
    return HallAssignment(
        id=None, unit_id=unit.id, hall_name=unit.hall_name, seat_zone=unit.seat_zone,
        seat_capacity=unit.seat_count,
        started_at=_naive_utc(unit.started_at or now_utc()), ended_at=None,
        hall_change_id=None,
    )


def ensure_assignments(db, plan: ScreeningPlan) -> None:
    """写路径专用：为历史排片（换厅功能上线前已启动）幂等补齐初始厅段。"""
    units = plan_units(db, plan.id)
    for unit in units:
        exists = db.scalar(
            select(HallAssignment.id).where(HallAssignment.unit_id == unit.id).limit(1)
        )
        if exists:
            continue
        db.add(HallAssignment(
            unit_id=unit.id,
            hall_name=unit.hall_name,
            seat_zone=unit.seat_zone,
            seat_capacity=unit.seat_count,
            started_at=_naive_utc(unit.started_at or now_utc()),
        ))
    db.flush()


def plan_units(db, plan_id: int) -> list[ExperimentUnit]:
    return list(db.scalars(
        select(ExperimentUnit)
        .where(ExperimentUnit.plan_id == plan_id)
        .order_by(ExperimentUnit.hall_name, ExperimentUnit.session_code, ExperimentUnit.seat_zone)
    ).all())


def active_assignment_map(db, units: list[ExperimentUnit]) -> dict[int, HallAssignment]:
    """每个单元当前开放（ended_at 为空）的持久化厅段。调用方需先 ensure_assignments。"""
    ids = [unit.id for unit in units]
    if not ids:
        return {}
    rows = db.scalars(
        select(HallAssignment)
        .where(HallAssignment.unit_id.in_(ids), HallAssignment.ended_at.is_(None))
        .order_by(HallAssignment.started_at)
    ).all()
    return {row.unit_id: row for row in rows}


def current_hall_map(db, units: list[ExperimentUnit]) -> dict[int, HallAssignment]:
    """只读：有持久化段取当前开放段，否则回退到单元配置的虚拟开场段。"""
    persisted = active_assignment_map(db, units)
    result = dict(persisted)
    for unit in units:
        result.setdefault(unit.id, _virtual_segment(unit))
    return result


def _preflight(units, moving, current_map, target_hall: str, target_capacity: int) -> str | None:
    """返回失败原因；None 表示通过。"""
    required = sum(unit.seat_count for unit in moving)
    if required > target_capacity:
        return f'目标厅容量 {target_capacity} 座不足，本组实验单元共需 {required} 座，全场留在原厅'
    target_zones = [unit.seat_zone for unit in moving]
    if len(set(target_zones)) != len(target_zones):
        return '同厅实验单元座区重复，无法整体迁入目标厅，全场留在原厅'
    for unit in units:
        if unit.id in current_map and current_map[unit.id].hall_name == target_hall:
            if unit.seat_zone in target_zones:
                return f'目标厅 {target_hall} 的 {unit.seat_zone} 座区已被占用，全场留在原厅'
    return None


def _record_attempt(db, plan, *, origin, target, capacity, reason, status, failure_reason,
                    retry_count, user, effective_at=None) -> HallChangeAttempt:
    attempt = HallChangeAttempt(
        plan_id=plan.id, origin_hall_name=origin, target_hall_name=target,
        target_capacity=capacity, reason=reason, status=status, failure_reason=failure_reason,
        retry_count=retry_count, requested_by=user.id, requested_at=now_utc(),
        effective_at=effective_at,
    )
    db.add(attempt)
    db.flush()
    return attempt


def request_hall_change(db, plan: ScreeningPlan, payload, actor) -> HallChangeAttempt:
    if plan.status != 'live':
        raise HTTPException(409, '仅直播中的场次可以临时换厅')
    if payload.target_hall_name == payload.origin_hall_name:
        raise HTTPException(422, '目标厅与原厅相同，无需换厅')
    ensure_assignments(db, plan)
    units = plan_units(db, plan.id)
    current_map = active_assignment_map(db, units)
    moving = [u for u in units if current_map.get(u.id) and
              current_map[u.id].hall_name == payload.origin_hall_name]
    if not moving:
        raise HTTPException(404, f'当前没有实验单元在 {payload.origin_hall_name} 厅，无法发起换厅')
    if any(u.status != 'started' for u in moving):
        raise HTTPException(409, '换厅涉及的实验单元必须全部处于已开始状态')
    failure = _preflight(units, moving, current_map, payload.target_hall_name, payload.target_capacity)
    if failure:
        attempt = _record_attempt(
            db, plan, origin=payload.origin_hall_name, target=payload.target_hall_name,
            capacity=payload.target_capacity, reason=payload.reason, status='rejected',
            failure_reason=failure, retry_count=0, user=actor,
        )
        audit(db, actor, 'hall_change_rejected', 'hall_change_attempt', attempt.id, failure)
        return attempt
    return _apply_change(db, plan, moving, current_map, payload, actor, retry_count=0, attempt=None)


def retry_hall_change(db, plan: ScreeningPlan, attempt_id: int, payload, actor) -> HallChangeAttempt:
    if plan.status != 'live':
        raise HTTPException(409, '仅直播中的场次可以重试换厅')
    attempt = db.get(HallChangeAttempt, attempt_id)
    if not attempt or attempt.plan_id != plan.id:
        raise HTTPException(404, '换厅请求不存在')
    if attempt.status == 'effective':
        raise HTTPException(409, '该换厅请求已生效，不能重复生效')
    ensure_assignments(db, plan)
    units = plan_units(db, plan.id)
    current_map = active_assignment_map(db, units)
    moving = [u for u in units if current_map.get(u.id) and
              current_map[u.id].hall_name == attempt.origin_hall_name]
    if not moving:
        raise HTTPException(409, '原厅已无实验单元，无法重试该换厅请求')
    failure = _preflight(units, moving, current_map, attempt.target_hall_name, attempt.target_capacity)
    if failure:
        # 同一次换厅的重试只计一次：首次重试被拒后，再次重试直接拒绝。
        if attempt.retry_count >= 1:
            raise HTTPException(409, '同一次换厅只可重试一次，且本次重试未生效，请发起新的换厅请求')
        attempt.retry_count = 1
        attempt.failure_reason = failure
        attempt.reason = payload.reason
        attempt.requested_by = actor.id
        attempt.requested_at = now_utc()
        db.flush()
        audit(db, actor, 'hall_change_retry_rejected', 'hall_change_attempt', attempt.id, failure)
        return attempt
    return _apply_change(db, plan, moving, current_map, None, actor,
                         retry_count=attempt.retry_count + 1, attempt=attempt, reason=payload.reason)


def _apply_change(db, plan, moving, current_map, payload, actor, *, retry_count, attempt, reason=None):
    effective_at = now_utc()
    naive_effective = _naive_utc(effective_at)
    target = attempt.target_hall_name if attempt else payload.target_hall_name
    capacity = attempt.target_capacity if attempt else payload.target_capacity
    change_reason = reason or payload.reason
    if attempt is None:
        origin = current_map[moving[0].id].hall_name
        attempt = _record_attempt(
            db, plan, origin=origin,
            target=target, capacity=capacity, reason=change_reason, status='effective',
            failure_reason=None, retry_count=retry_count, user=actor, effective_at=effective_at,
        )
    else:
        attempt.status = 'effective'
        attempt.failure_reason = None
        attempt.retry_count = retry_count
        attempt.reason = change_reason
        attempt.requested_by = actor.id
        attempt.requested_at = effective_at
        attempt.effective_at = effective_at
    for unit in moving:
        segment = current_map[unit.id]
        segment.ended_at = naive_effective
        db.add(HallAssignment(
            unit_id=unit.id, hall_name=target, seat_zone=unit.seat_zone,
            seat_capacity=unit.seat_count, started_at=naive_effective,
            hall_change_id=attempt.id,
        ))
    db.flush()
    audit(db, actor, 'hall_change_effective', 'hall_change_attempt', attempt.id,
          f'{attempt.origin_hall_name}->{target};units={len(moving)}')
    return attempt


def assignment_timeline(db, units: list[ExperimentUnit]) -> dict[int, list[HallAssignment]]:
    """只读：每单元的厅段时间线；无持久化段时回退到配置厅虚拟段。"""
    ids = [unit.id for unit in units]
    rows = db.scalars(
        select(HallAssignment)
        .where(HallAssignment.unit_id.in_(ids))
        .order_by(HallAssignment.unit_id, HallAssignment.started_at)
    ).all() if ids else []
    timeline: dict[int, list[HallAssignment]] = defaultdict(list)
    for row in rows:
        timeline[row.unit_id].append(row)
    for unit in units:
        if not timeline[unit.id]:
            timeline[unit.id] = [_virtual_segment(unit)]
    return timeline


def resolve_hall(timeline: list[HallAssignment], observed_at: datetime) -> str:
    """按观测发生时间归入当时的厅次（迟到票务记录的归厅依据）。"""
    moment = _naive_utc(observed_at)
    starts = [segment.started_at for segment in timeline]
    index = bisect_right(starts, moment) - 1
    if index < 0:
        index = 0
    return timeline[index].hall_name


def observations_with_halls(db, plan: ScreeningPlan):
    """返回 (units, unit_map, observations, hall_by_observation_id)。只读。"""
    units = plan_units(db, plan.id)
    unit_map = {unit.id: unit for unit in units}
    ids = [unit.id for unit in units]
    observations = db.scalars(
        select(TicketObservation)
        .where(TicketObservation.unit_id.in_(ids))
        .order_by(TicketObservation.id)
    ).all() if ids else []
    timeline = assignment_timeline(db, units)
    hall_by_id = {
        obs.id: resolve_hall(timeline[obs.unit_id], obs.observed_at)
        for obs in observations
    }
    return units, unit_map, observations, hall_by_id


def segment_board(db, plan: ScreeningPlan):
    """只读：每段容量、起止时间和按发生时间归入该段的座位。"""
    units = plan_units(db, plan.id)
    timeline = assignment_timeline(db, units)
    ids = [unit.id for unit in units]
    observations = db.scalars(
        select(TicketObservation).where(TicketObservation.unit_id.in_(ids))
    ).all() if ids else []
    counts: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: {'observed': 0, 'sold': 0})
    for obs in observations:
        moment = _naive_utc(obs.observed_at)
        segments = timeline[obs.unit_id]
        starts = [segment.started_at for segment in segments]
        index = max(bisect_right(starts, moment) - 1, 0)
        bucket = counts[(obs.unit_id, index)]
        bucket['observed'] += 1
        bucket['sold'] += int(obs.sold)
    segments = []
    for unit in units:
        for ordinal, segment in enumerate(timeline[unit.id]):
            bucket = counts.get((unit.id, ordinal), {'observed': 0, 'sold': 0})
            segments.append({
                'assignment_id': segment.id,
                'unit_id': unit.id,
                'session_code': unit.session_code,
                'group_name': unit.group_name,
                'hall_name': segment.hall_name,
                'seat_zone': segment.seat_zone,
                'seat_capacity': segment.seat_capacity,
                'started_at': segment.started_at,
                'ended_at': segment.ended_at,
                'hall_change_id': segment.hall_change_id,
                'observed_seats': bucket['observed'],
                'sold_seats': bucket['sold'],
            })
    segments.sort(key=lambda row: (row['started_at'], row['unit_id']))
    return units, segments
