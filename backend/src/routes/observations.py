from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..auth import current_user
from ..database import get_db
from ..models import ExperimentUnit, TicketObservation, User

router = APIRouter(prefix="/observations", tags=["observations"])

@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    units = db.query(ExperimentUnit).all(); unit_map = {u.id: u for u in units}
    rows = db.query(TicketObservation).all()
    total = len(rows); sold = sum(1 for r in rows if r.sold)
    by_group = {}
    for r in rows:
        g = unit_map[r.unit_id].group_name
        by_group.setdefault(g, {"total": 0, "sold": 0})
        by_group[g]["total"] += 1; by_group[g]["sold"] += int(r.sold)
    return {"total": total, "sold": sold, "conversion": sold / total if total else 0, "by_group": by_group}
