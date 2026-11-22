from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import current_user, require_roles
from ..database import get_db
from . import service
from .schemas import SettlementInput, SettlementReview

router = APIRouter(prefix='/plans/{plan_id}/pilot-settlements', tags=['试行场次结算'])


@router.get('')
def settlements(plan_id: int, db: Session = Depends(get_db), _user=Depends(current_user)):
    return service.board(db, plan_id)


@router.post('/{pilot_id}', status_code=201)
def record(plan_id: int, pilot_id: int, payload: SettlementInput, db: Session = Depends(get_db),
           user=Depends(require_roles('boxoffice','admin'))):
    result = service.submit(db, plan_id, pilot_id, payload, user)
    db.commit()
    return result


@router.post('/{pilot_id}/review')
def review(plan_id: int, pilot_id: int, payload: SettlementReview, db: Session = Depends(get_db),
           user=Depends(require_roles('revenue','admin'))):
    result = service.review(db, plan_id, pilot_id, payload, user)
    db.commit()
    return result
