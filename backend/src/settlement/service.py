from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import AuditLog, RevenueReview, now_utc
from ..operations_models import SchedulingPilot
from ..services.operations import plan_by_id
from .economics import calculate
from .models import PilotSettlement

LOCAL = ZoneInfo('Asia/Shanghai')


def eligible(pilot):
    show_start = datetime.combine(pilot.show_date, time.fromisoformat(pilot.show_time), tzinfo=LOCAL)
    return pilot.status == 'scheduled' and show_start < datetime.now(LOCAL)


def pilots(db, plan_id):
    plan_by_id(db, plan_id)
    return select(SchedulingPilot).join(RevenueReview).where(RevenueReview.plan_id == plan_id)


def row_json(row):
    return {col.name: getattr(row, col.name) for col in PilotSettlement.__table__.columns}


def board(db, plan_id):
    data = db.execute(pilots(db, plan_id).add_columns(PilotSettlement).outerjoin(PilotSettlement)
                      .order_by(SchedulingPilot.show_date.desc(), SchedulingPilot.id.desc()))
    return {'items': [{'pilot_id': pilot.id, 'receipt': pilot.booking_ref, 'hall': pilot.hall_name,
                       'show_date': pilot.show_date, 'show_time': pilot.show_time, 'seats': pilot.actual_seats,
                       'can_submit': eligible(pilot) and row is None,
                       'settlement': row_json(row) if row else None} for pilot, row in data if pilot.status == 'scheduled']}


def submit(db, plan_id, pilot_id, payload, user):
    pilot = db.scalar(pilots(db, plan_id).where(SchedulingPilot.id == pilot_id).with_for_update(of=SchedulingPilot))
    if not pilot:
        raise HTTPException(404, '该排片试行不存在')
    if not eligible(pilot):
        raise HTTPException(409, '待排片、已撤销或尚未开场的试行目前无法登记结算')
    if payload.tickets_sold > pilot.actual_seats:
        raise HTTPException(422, '售出数超过该场正式排片的可售座位')
    if db.scalar(select(PilotSettlement.id).where(PilotSettlement.pilot_id == pilot.id)):
        raise HTTPException(409, '该试行场次已登记结算')
    try:
        result = calculate(payload.tickets_sold, payload.gross_tickets_cents, payload.ticket_commission_cents,
                           payload.concession_margin_cents, payload.incremental_cost_cents, payload.subsidy_cents)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    row = PilotSettlement(pilot_id=pilot.id, seats_offered=pilot.actual_seats, **payload.model_dump(),
                          contribution_cents=result.contribution_cents, breakeven_tickets=result.breakeven_tickets,
                          submitted_by=user.id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as error:
        raise HTTPException(409, '场次或 POS 凭证已登记') from error
    db.add(AuditLog(actor_id=user.id, action='pilot_settlement_submitted', entity_type='pilot_settlement',
                    entity_id=str(row.id), detail=payload.pos_reference))
    return row_json(row)


def review(db, plan_id, pilot_id, payload, user):
    pilot = db.scalar(pilots(db, plan_id).where(SchedulingPilot.id == pilot_id))
    if not pilot:
        raise HTTPException(404, '该排片试行不存在')
    row = db.scalar(select(PilotSettlement).where(PilotSettlement.pilot_id == pilot.id).with_for_update())
    if not row or row.state != 'submitted':
        raise HTTPException(409, '只有待复核结算单可以裁定')
    if row.submitted_by == user.id:
        raise HTTPException(409, '票务登记和收益复核须由不同人员完成')
    row.state = payload.decision
    row.review_note = payload.note
    row.reviewed_by = user.id
    row.reviewed_at = now_utc()
    db.add(AuditLog(actor_id=user.id, action='pilot_settlement_reviewed', entity_type='pilot_settlement',
                    entity_id=str(row.id), detail=payload.decision))
    return row_json(row)
