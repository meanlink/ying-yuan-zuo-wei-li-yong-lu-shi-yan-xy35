from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from src.database import SessionLocal
from src.hall_models import HallAssignment, HallChangeAttempt
from src.models import ExperimentUnit, ScreeningPlan, TicketObservation, User
from src.security import hash_password

USERS = [
    ("planner@cinema.local", "排片策划", "planner"),
    ("analyst@cinema.local", "实验分析师", "analyst"),
    ("revenue@cinema.local", "收益经理", "revenue"),
    ("boxoffice@cinema.local", "票房专员", "boxoffice"),
]

PLAN_KEY = "SPRING-IMAX-2026-11-21"
# 场次开场与临时换厅的演示时间线（UTC）。
STARTED_AT = datetime(2026, 11, 21, 11, 30, tzinfo=timezone.utc)
FIRST_REJECTED_AT = datetime(2026, 11, 21, 12, 45, tzinfo=timezone.utc)
CHANGED_AT = datetime(2026, 11, 21, 13, 0, tzinfo=timezone.utc)


def seed():
    db: Session = SessionLocal()
    try:
        planner = None
        for email, name, role in USERS:
            user = db.query(User).filter_by(email=email).first()
            if not user:
                user = User(email=email, name=name, role=role, password_hash=hash_password("cinema123"))
                db.add(user)
            if role == "planner":
                planner = user
        db.flush()
        plan = db.query(ScreeningPlan).filter_by(natural_key=PLAN_KEY).first()
        if not plan:
            plan = ScreeningPlan(natural_key=PLAN_KEY, film_title="潮汐边缘", version_name="周末座位策略 v2", show_date=date(2026, 11, 21), show_time="19:30", hall_name="IMAX-1", seat_capacity=120, base_price=58, status="configured")
            db.add(plan); db.flush()
        if not db.query(ExperimentUnit).filter_by(plan_id=plan.id).count():
            units = [
                ("IMAX-1930", "IMAX-1", "前排", "control", 30),
                ("IMAX-1930", "IMAX-1", "中排", "treatment", 30),
                ("IMAX-2030", "IMAX-2", "前排", "control", 24),
                ("IMAX-2030", "IMAX-2", "中排", "treatment", 24),
            ]
            for session, hall, zone, group, count in units:
                db.add(ExperimentUnit(plan_id=plan.id, session_code=session, hall_name=hall, seat_zone=zone, group_name=group, seat_count=count, status="started", started_at=STARTED_AT))
            plan.status = "live"; db.flush()
        units = db.query(ExperimentUnit).filter_by(plan_id=plan.id).all()
        if not db.query(TicketObservation).filter(TicketObservation.ticket_code.like("SEED-CINEMA-%")).count():
            number = 1
            for unit in units:
                for i in range(18):
                    sold = (i % 5 != 0) if unit.group_name == "treatment" else (i % 3 != 0)
                    # IMAX-1930 的观测跨越换厅时刻：前 10 条在原厅，后 8 条迟到入账于新厅。
                    if unit.session_code == "IMAX-1930":
                        observed_at = STARTED_AT + timedelta(minutes=20 + i * 4) if i < 10 else CHANGED_AT + timedelta(minutes=10 + (i - 10) * 5)
                    else:
                        observed_at = STARTED_AT + timedelta(minutes=20 + i * 4)
                    db.add(TicketObservation(unit_id=unit.id, ticket_code=f"SEED-CINEMA-{number:03d}", seat_label=f"{unit.seat_zone}-{i+1:02d}", sold=sold, price_paid=58 if sold else 0, source="seed-box-office", observed_at=observed_at))
                    number += 1
        seed_hall_change(db, plan, units, planner)
        db.commit()
        print("seed ok")
    finally:
        db.close()


def seed_hall_change(db: Session, plan: ScreeningPlan, units: list[ExperimentUnit], planner: User | None):
    """IMAX-1 厅临时改到 IMAX-3：先因容量不足被拒，重试后整体生效。"""
    if db.query(HallChangeAttempt).filter_by(plan_id=plan.id).first():
        return
    moving = [u for u in units if u.hall_name == "IMAX-1"]
    if not moving:
        return
    for unit in units:
        db.add(HallAssignment(unit_id=unit.id, hall_name=unit.hall_name, seat_zone=unit.seat_zone,
                              seat_capacity=unit.seat_count, started_at=STARTED_AT.replace(tzinfo=None)))
    db.flush()
    rejected = HallChangeAttempt(plan_id=plan.id, origin_hall_name="IMAX-1", target_hall_name="IMAX-3",
                                 target_capacity=40, reason="IMAX-1 放映设备故障，申请整体转厅",
                                 status="rejected",
                                 failure_reason="目标厅容量 40 座不足，本组实验单元共需 60 座，全场留在原厅",
                                 retry_count=1, requested_by=planner.id if planner else None,
                                 requested_at=FIRST_REJECTED_AT, effective_at=None)
    db.add(rejected); db.flush()
    effective = HallChangeAttempt(plan_id=plan.id, origin_hall_name="IMAX-1", target_hall_name="IMAX-3",
                                  target_capacity=80, reason="设备故障未排除，扩容目标厅后重试转厅",
                                  status="effective", failure_reason=None, retry_count=1,
                                  requested_by=planner.id if planner else None,
                                  requested_at=CHANGED_AT, effective_at=CHANGED_AT)
    db.add(effective); db.flush()
    naive_changed = CHANGED_AT.replace(tzinfo=None)
    for unit in moving:
        current = db.query(HallAssignment).filter_by(unit_id=unit.id, ended_at=None).one()
        current.ended_at = naive_changed
        db.add(HallAssignment(unit_id=unit.id, hall_name="IMAX-3", seat_zone=unit.seat_zone,
                              seat_capacity=unit.seat_count, started_at=naive_changed,
                              hall_change_id=effective.id))
    db.flush()


if __name__ == "__main__": seed()
