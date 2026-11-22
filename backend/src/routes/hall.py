from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, require_roles
from ..database import get_db
from ..hall_models import HallChangeAttempt
from ..hall_schemas import HallChangeRequest, HallChangeRetry
from ..models import User
from ..services import hall_change
from ..services.operations import plan_by_id

router = APIRouter(prefix='/plans/{plan_id}/hall-changes', tags=['临时换厅'])
planner = require_roles('planner', 'admin')


def attempt_json(row):
    return {
        'id': row.id,
        'plan_id': row.plan_id,
        'origin_hall_name': row.origin_hall_name,
        'target_hall_name': row.target_hall_name,
        'target_capacity': row.target_capacity,
        'reason': row.reason,
        'status': row.status,
        'failure_reason': row.failure_reason,
        'retry_count': row.retry_count,
        'requested_at': row.requested_at.isoformat() if row.requested_at else None,
        'effective_at': row.effective_at.isoformat() if row.effective_at else None,
        'retryable': row.status == 'rejected' and row.retry_count < 1,
    }


@router.get('')
def list_changes(plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan_by_id(db, plan_id)
    rows = db.scalars(
        select(HallChangeAttempt)
        .where(HallChangeAttempt.plan_id == plan_id)
        .order_by(HallChangeAttempt.id.desc())
    ).all()
    return {'items': [attempt_json(row) for row in rows]}


@router.get('/segments')
def segments(plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan = plan_by_id(db, plan_id)
    unit_map, rows = hall_change.segment_board(db, plan)
    return {
        'items': [{
            **row,
            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
            'ended_at': row['ended_at'].isoformat() if row['ended_at'] else None,
        } for row in rows],
    }


@router.post('', status_code=201)
def request_change(plan_id: int, payload: HallChangeRequest, db: Session = Depends(get_db),
                   user: User = Depends(planner)):
    plan = plan_by_id(db, plan_id, lock=True)
    attempt = hall_change.request_hall_change(db, plan, payload, user)
    db.commit()
    return attempt_json(attempt)


@router.post('/{attempt_id}/retry', status_code=201)
def retry_change(plan_id: int, attempt_id: int, payload: HallChangeRetry,
                 db: Session = Depends(get_db), user: User = Depends(planner)):
    plan = plan_by_id(db, plan_id, lock=True)
    attempt = hall_change.retry_hall_change(db, plan, attempt_id, payload, user)
    db.commit()
    return attempt_json(attempt)
