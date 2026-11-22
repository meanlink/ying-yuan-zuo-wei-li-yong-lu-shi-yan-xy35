from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, require_roles
from ..database import get_db
from ..models import RevenueReview, User
from ..operations_models import SchedulingPilot
from ..operations_schemas import ConfirmPilot, OpenPilot, SubmitCloseout, WithdrawPilot
from ..services.operations import closeout_status, plan_by_id, resolve_pilot, save_pilot, submit_closeout, summarize_closeouts

router = APIRouter(prefix='/plans', tags=['cinema operations'])
boxoffice = require_roles('boxoffice', 'admin')
planner = require_roles('planner', 'admin')
revenue = require_roles('revenue', 'admin')


def closeout_json(row):
    return {
        'id': row.id, 'unit_id': row.unit_id, 'batch_ref': row.batch_ref, 'status': row.status,
        'reported': {'observed': row.report_count, 'sold': row.report_sold, 'cents': row.report_cents},
        'snapshot': {'observed': row.ledger_count, 'sold': row.ledger_sold, 'cents': row.ledger_cents},
        'note': row.note, 'submitted_at': row.submitted_at,
    }


def pilot_json(row):
    return {field: getattr(row, field) for field in (
        'id','review_id','unit_id','hall_name','seat_zone','show_date','show_time','pilot_seats',
        'objective','status','created_at','booking_ref','actual_seats','result_note','acted_at',
    )}


@router.get('/{plan_id}/pos-closeouts')
def closeouts(plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan = plan_by_id(db, plan_id)
    rows = summarize_closeouts(db, plan.id)
    return {'items': [{
        'unit_id': unit.id, 'hall_name': unit.hall_name, 'session_code': unit.session_code,
        'seat_zone': unit.seat_zone, 'group_name': unit.group_name, 'ledger': ledger,
        'status': closeout_status(ledger, history), 'history': [closeout_json(report) for report in history],
    } for unit, ledger, history in rows]}


@router.post('/{plan_id}/pos-closeouts', status_code=201)
def closeout(plan_id: int, payload: SubmitCloseout, db: Session = Depends(get_db), user: User = Depends(boxoffice)):
    row = submit_closeout(db, plan_id, payload, user)
    result = closeout_json(row)
    db.commit()
    return result


@router.get('/{plan_id}/scheduling-pilots')
def pilots(plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan_by_id(db, plan_id)
    rows = db.scalars(select(SchedulingPilot).join(RevenueReview).where(
        RevenueReview.plan_id == plan_id,
    ).order_by(SchedulingPilot.show_date, SchedulingPilot.show_time, SchedulingPilot.id.desc()))
    return {'items': [pilot_json(row) for row in rows]}


@router.post('/{plan_id}/scheduling-pilots', status_code=201)
def create_pilot(plan_id: int, payload: OpenPilot, db: Session = Depends(get_db), user: User = Depends(revenue)):
    row = save_pilot(db, plan_id, payload, user)
    result = pilot_json(row)
    db.commit()
    return result


@router.post('/{plan_id}/scheduling-pilots/{pilot_id}/confirm')
def confirm(plan_id: int, pilot_id: int, payload: ConfirmPilot, db: Session = Depends(get_db), user: User = Depends(planner)):
    row = resolve_pilot(db, plan_id, pilot_id, payload, user)
    result = pilot_json(row)
    db.commit()
    return result


@router.post('/{plan_id}/scheduling-pilots/{pilot_id}/withdraw')
def withdraw(plan_id: int, pilot_id: int, payload: WithdrawPilot, db: Session = Depends(get_db), user: User = Depends(revenue)):
    row = resolve_pilot(db, plan_id, pilot_id, payload, user, withdraw=True)
    result = pilot_json(row)
    db.commit()
    return result
