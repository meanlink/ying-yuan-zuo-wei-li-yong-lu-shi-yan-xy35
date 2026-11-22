from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import ExperimentUnit, RevenueReview, ScreeningPlan, TicketObservation, now_utc
from ..operations_models import PosCloseout, SchedulingPilot
from .workflow import audit

CINEMA_TZ = ZoneInfo('Asia/Shanghai')


def plan_by_id(db, plan_id, *, lock=False):
    statement = select(ScreeningPlan).where(ScreeningPlan.id == plan_id)
    if lock:
        statement = statement.with_for_update()
    plan = db.scalar(statement)
    if plan is None:
        raise HTTPException(404, '排片方案不存在')
    return plan


def summarize_closeouts(db, plan_id):
    units = db.scalars(select(ExperimentUnit).where(ExperimentUnit.plan_id == plan_id).order_by(
        ExperimentUnit.hall_name, ExperimentUnit.session_code, ExperimentUnit.seat_zone,
    )).all()
    ids = [unit.id for unit in units]
    snapshots = {unit_id: {'observed': 0, 'sold': 0, 'cents': 0} for unit_id in ids}
    for unit_id, sold, price in db.execute(select(
        TicketObservation.unit_id, TicketObservation.sold, TicketObservation.price_paid,
    ).where(TicketObservation.unit_id.in_(ids))):
        counter = snapshots[unit_id]
        counter['observed'] += 1
        if sold:
            counter['sold'] += 1
            counter['cents'] += int((Decimal(str(price)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    history = db.scalars(select(PosCloseout).where(PosCloseout.unit_id.in_(ids)).order_by(PosCloseout.id.desc())).all()
    reports = {unit_id: [] for unit_id in ids}
    for entry in history:
        reports[entry.unit_id].append(entry)
    return [(unit, snapshots[unit.id], reports[unit.id]) for unit in units]


def closeout_status(snapshot, attempts):
    if not attempts:
        return 'unsubmitted'
    latest = attempts[0]
    if (latest.ledger_count, latest.ledger_sold, latest.ledger_cents) != (snapshot['observed'], snapshot['sold'], snapshot['cents']):
        return 'stale'
    return latest.status


def require_closeouts(db, plan_id, *, review=None):
    rows = summarize_closeouts(db, plan_id)
    # Existing experiments opt into the gate when the first POS batch is entered.
    if any(attempts for _, _, attempts in rows):
        if any(closeout_status(snapshot, attempts) != 'matched' for _, snapshot, attempts in rows):
            raise HTTPException(409, '票房班结尚有未对齐或过期单元，请完成对账后再继续')
        if review and review.sample_size != sum(snapshot['observed'] for _, snapshot, _ in rows):
            raise HTTPException(409, '班结后观测数已变化，请重跑分析后再审批')
    return rows


def submit_closeout(db, plan_id, payload, actor):
    plan = plan_by_id(db, plan_id, lock=True)
    if plan.status not in ('live', 'review'):
        raise HTTPException(409, '仅已开始且未审批的实验可登记班结')
    row = next((row for row in summarize_closeouts(db, plan.id) if row[0].id == payload.unit_id), None)
    if not row:
        raise HTTPException(404, '本排片的实验单元不存在')
    unit, ledger, attempts = row
    if payload.expected_closeout_id != (attempts[0].id if attempts else 0):
        raise HTTPException(409, '已有新的对账回执，请刷新后再登记')
    if ledger['observed'] == 0:
        raise HTTPException(409, '先录入本单元观测，再核对 POS 班结')
    if closeout_status(ledger, attempts) == 'matched':
        raise HTTPException(409, '当前班结已对齐')
    cents = int(payload.revenue * 100)
    status = 'matched' if (payload.observed, payload.sold, cents) == (ledger['observed'], ledger['sold'], ledger['cents']) else 'discrepancy'
    entry = PosCloseout(unit_id=unit.id, batch_ref=payload.batch_ref, report_count=payload.observed,
                        report_sold=payload.sold, report_cents=cents, ledger_count=ledger['observed'],
                        ledger_sold=ledger['sold'], ledger_cents=ledger['cents'], status=status,
                        note=payload.note, submitted_by=actor.id)
    db.add(entry)
    db.flush()
    audit(db, actor, 'pos_closeout_submitted', 'pos_closeout', entry.id, f'{payload.batch_ref} · {status}')
    return entry


def save_pilot(db, plan_id, payload, actor):
    plan = plan_by_id(db, plan_id, lock=True)
    review = db.get(RevenueReview, payload.review_id)
    if review is None or review.plan_id != plan_id:
        raise HTTPException(404, '本排片的收益复盘不存在')
    if plan.status != 'approved' or review.analysis_status != 'approved':
        raise HTTPException(409, '收益复盘审批完成后才能派发试行工单')
    rows = require_closeouts(db, plan_id, review=review)
    if review.sample_size != sum(snapshot['observed'] for _, snapshot, _ in rows):
        raise HTTPException(409, '已审批复盘的观测数已变化，请更新复盘')
    unit = db.get(ExperimentUnit, payload.unit_id)
    if not unit or unit.plan_id != plan.id or unit.group_name != 'treatment':
        raise HTTPException(422, '试行座位区须选择该实验的 treatment 单元')
    if payload.pilot_seats > unit.seat_count:
        raise HTTPException(422, '试行座位数不能超过实验座区容量')
    if payload.show_date <= max(plan.show_date, datetime.now(CINEMA_TZ).date()):
        raise HTTPException(422, '试行日期须晚于原场次和今天')
    pilot = SchedulingPilot(review_id=review.id, unit_id=unit.id, hall_name=unit.hall_name,
                            seat_zone=unit.seat_zone, show_date=payload.show_date, show_time=payload.show_time,
                            pilot_seats=payload.pilot_seats, objective=payload.objective, created_by=actor.id)
    db.add(pilot)
    try:
        db.flush()
    except IntegrityError as exc:
        if getattr(exc.orig.diag, 'constraint_name', None) != 'uq_pilot_timeslot':
            raise
        raise HTTPException(409, '该影厅在指定日期和开场时间已有试行工单') from exc
    audit(db, actor, 'scheduling_pilot_assigned', 'scheduling_pilot', pilot.id, f'approved_review={review.id}')
    return pilot


def resolve_pilot(db, plan_id, pilot_id, payload, actor, *, withdraw=False):
    statement = select(SchedulingPilot).join(RevenueReview).where(SchedulingPilot.id == pilot_id,
        RevenueReview.plan_id == plan_id).with_for_update(of=SchedulingPilot)
    row = db.scalar(statement)
    if row is None:
        raise HTTPException(404, '试行工单不存在')
    if row.status != 'assigned':
        raise HTTPException(409, '仅待排片工单可执行或撤回')
    if not withdraw:
        if payload.actual_seats > row.pilot_seats:
            raise HTTPException(422, '实际座位数不能超过工单计划数')
        row.actual_seats = payload.actual_seats
        row.booking_ref = payload.booking_ref
    row.status = 'withdrawn' if withdraw else 'scheduled'
    row.result_note = payload.result_note
    row.acted_by = actor.id
    row.acted_at = now_utc()
    try:
        db.flush()
    except IntegrityError as exc:
        if getattr(exc.orig.diag, 'constraint_name', None) != 'scheduling_pilots_booking_ref_key':
            raise
        raise HTTPException(409, '排片系统回执编号已被使用') from exc
    audit(db, actor, f'scheduling_pilot_{row.status}', 'scheduling_pilot', row.id, payload.result_note)
    return row
