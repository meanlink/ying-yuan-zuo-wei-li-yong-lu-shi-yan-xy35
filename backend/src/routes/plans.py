from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import current_user, require_roles
from ..database import get_db
from ..models import ExperimentUnit, RevenueReview, ScreeningPlan, TicketObservation, User
from ..schemas import ObservationCreate, PlanCreate, UnitCreate, ReviewApprove
from ..services import hall_change
from ..services.operations import plan_by_id, require_closeouts
from ..services.workflow import approve_review, audit, run_analysis, start_experiment

router = APIRouter(prefix="/plans", tags=["plans"])

def plan_json(p, db):
    units = db.query(ExperimentUnit).filter_by(plan_id=p.id).all()
    latest = db.query(RevenueReview).filter_by(plan_id=p.id).order_by(RevenueReview.id.desc()).first()
    current = hall_change.current_hall_map(db, units)
    current_halls = sorted({segment.hall_name for segment in current.values()})
    return {"id": p.id, "natural_key": p.natural_key, "film_title": p.film_title, "version_name": p.version_name, "show_date": str(p.show_date), "show_time": p.show_time, "hall_name": p.hall_name, "current_halls": current_halls, "seat_capacity": p.seat_capacity, "base_price": p.base_price, "status": p.status, "unit_count": len(units), "latest_review": review_json(latest) if latest else None}

def unit_json(u, current_hall=None):
    return {"id": u.id, "plan_id": u.plan_id, "session_code": u.session_code, "hall_name": u.hall_name, "current_hall_name": current_hall or u.hall_name, "seat_zone": u.seat_zone, "group_name": u.group_name, "seat_count": u.seat_count, "status": u.status, "started_at": u.started_at.isoformat() if u.started_at else None}

def observation_json(o, unit_map, hall_by_id):
    u = unit_map[o.unit_id]
    return {"id": o.id, "unit_id": o.unit_id, "ticket_code": o.ticket_code, "seat_label": o.seat_label, "sold": o.sold, "price_paid": o.price_paid, "observed_at": o.observed_at.isoformat(), "source": o.source, "group_name": u.group_name, "hall_name": u.hall_name, "effective_hall_name": hall_by_id.get(o.id, u.hall_name), "session_code": u.session_code, "seat_zone": u.seat_zone}

def review_json(r):
    strata = []
    if r is not None and r.result_json:
        strata = json.loads(r.result_json).get("strata", [])
    return {"id": r.id, "plan_id": r.plan_id, "analysis_status": r.analysis_status, "sample_size": r.sample_size, "control_rate": r.control_rate, "treatment_rate": r.treatment_rate, "absolute_diff": r.absolute_diff, "ci_low": r.ci_low, "ci_high": r.ci_high, "stratified_effect": r.stratified_effect, "balance_ratio": r.balance_ratio, "is_stratified": r.is_stratified, "strata": strata, "notes": r.notes, "approved_at": r.approved_at.isoformat() if r.approved_at else None}

@router.get("")
def list_plans(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"items": [plan_json(p, db) for p in db.query(ScreeningPlan).order_by(ScreeningPlan.show_date, ScreeningPlan.show_time).all()]}

@router.post("")
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("planner", "admin"))):
    if db.query(ScreeningPlan).filter_by(natural_key=payload.natural_key).first():
        raise HTTPException(409, "排片版本编码已存在")
    p = ScreeningPlan(**payload.model_dump())
    db.add(p); db.flush(); audit(db, user, "plan_created", "screening_plan", p.id, p.natural_key); db.commit()
    return plan_json(p, db)

@router.get("/{plan_id}/units")
def list_units(plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan_by_id(db, plan_id)
    units = db.query(ExperimentUnit).filter_by(plan_id=plan_id).order_by(ExperimentUnit.hall_name, ExperimentUnit.session_code, ExperimentUnit.seat_zone).all()
    current = hall_change.current_hall_map(db, units)
    return {"items": [unit_json(u, current[u.id].hall_name) for u in units]}

@router.post("/{plan_id}/units")
def create_unit(plan_id: int, payload: UnitCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("planner", "admin"))):
    plan = db.get(ScreeningPlan, plan_id)
    if not plan: raise HTTPException(404, "排片方案不存在")
    if plan.status in {"live", "review", "approved"}: raise HTTPException(409, "场次开始后禁止修改实验组")
    if payload.group_name not in {"control", "treatment"}: raise HTTPException(422, "实验组必须是 control 或 treatment")
    u = ExperimentUnit(plan_id=plan_id, **payload.model_dump()); db.add(u); plan.status = "configured"; db.flush(); audit(db, user, "unit_configured", "experiment_unit", u.id, payload.group_name); db.commit()
    return unit_json(u)

@router.post("/{plan_id}/start")
def start(plan_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("planner", "admin"))):
    plan = db.get(ScreeningPlan, plan_id)
    if not plan: raise HTTPException(404, "排片方案不存在")
    start_experiment(db, plan, user); db.commit(); return plan_json(plan, db)

@router.get("/{plan_id}/observations")
def observations(plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan = plan_by_id(db, plan_id)
    units, unit_map, rows, hall_by_id = hall_change.observations_with_halls(db, plan)
    items = sorted(rows, key=lambda row: row.id, reverse=True)
    return {"items": [observation_json(o, unit_map, hall_by_id) for o in items]}

@router.post("/{plan_id}/observations")
def add_observation(plan_id: int, payload: ObservationCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("boxoffice", "admin"))):
    plan = plan_by_id(db, plan_id, lock=True)
    hall_change.ensure_assignments(db, plan)
    unit = db.get(ExperimentUnit, payload.unit_id)
    if not unit or unit.plan_id != plan_id: raise HTTPException(404, "实验单元不存在")
    if unit.status != "started": raise HTTPException(409, "只能向已开始的场次录入观测")
    if db.query(TicketObservation).filter_by(ticket_code=payload.ticket_code).first(): raise HTTPException(409, "票务观测编码重复")
    data = payload.model_dump()
    observed_at = data.pop("observed_at", None)
    if observed_at is None:
        observed_at = datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    observed_naive = observed_at.astimezone(timezone.utc).replace(tzinfo=None)
    if unit.started_at:
        started = unit.started_at
        if started.tzinfo is not None:
            started = started.astimezone(timezone.utc).replace(tzinfo=None)
        if observed_naive < started:
            raise HTTPException(422, "票务发生时间早于场次开始时间，不能归入该实验单元")
    if observed_naive > now_naive:
        raise HTTPException(422, "票务发生时间不能晚于当前时间")
    timeline = hall_change.assignment_timeline(db, [unit]).get(unit.id, [])
    effective_hall = hall_change.resolve_hall(timeline, observed_at) if timeline else unit.hall_name
    o = TicketObservation(**data, observed_at=observed_at)
    db.add(o); db.flush()
    audit(db, user, "ticket_observed", "ticket_observation", payload.ticket_code,
          f"sold={payload.sold};hall={effective_hall};at={observed_at.isoformat()}")
    db.commit()
    return {"ok": True, "id": o.id, "effective_hall_name": effective_hall}

@router.post("/{plan_id}/analysis")
def analysis(plan_id: int, stratified: bool = False, db: Session = Depends(get_db), user: User = Depends(require_roles("analyst", "admin"))):
    plan = plan_by_id(db, plan_id, lock=True)
    require_closeouts(db, plan_id)
    try: review = run_analysis(db, plan, user, force_stratified=stratified)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    db.commit(); return review_json(review)

@router.get("/{plan_id}/reviews")
def reviews(plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"items": [review_json(r) for r in db.query(RevenueReview).filter_by(plan_id=plan_id).order_by(RevenueReview.id.desc()).all()]}

@router.post("/{plan_id}/reviews/{review_id}/approve")
def approve(plan_id: int, review_id: int, payload: ReviewApprove, db: Session = Depends(get_db), user: User = Depends(require_roles("revenue", "admin"))):
    plan_by_id(db, plan_id, lock=True)
    review = db.get(RevenueReview, review_id)
    if not review or review.plan_id != plan_id: raise HTTPException(404, "复盘不存在")
    require_closeouts(db, plan_id, review=review)
    approve_review(db, review, user, payload.notes); db.commit(); return review_json(review)
