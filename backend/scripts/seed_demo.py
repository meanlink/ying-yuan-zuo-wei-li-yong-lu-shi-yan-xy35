from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from src.database import SessionLocal
from src.models import ExperimentUnit, ScreeningPlan, TicketObservation, User
from src.security import hash_password

USERS = [
    ("planner@cinema.local", "排片策划", "planner"),
    ("analyst@cinema.local", "实验分析师", "analyst"),
    ("revenue@cinema.local", "收益经理", "revenue"),
    ("boxoffice@cinema.local", "票房专员", "boxoffice"),
]

def seed():
    db: Session = SessionLocal()
    try:
        for email, name, role in USERS:
            if not db.query(User).filter_by(email=email).first():
                db.add(User(email=email, name=name, role=role, password_hash=hash_password("cinema123")))
        db.flush()
        plan = db.query(ScreeningPlan).filter_by(natural_key="SPRING-IMAX-2026-11-21").first()
        if not plan:
            plan = ScreeningPlan(natural_key="SPRING-IMAX-2026-11-21", film_title="潮汐边缘", version_name="周末座位策略 v2", show_date=date(2026, 11, 21), show_time="19:30", hall_name="IMAX-1", seat_capacity=120, base_price=58, status="configured")
            db.add(plan); db.flush()
        if not db.query(ExperimentUnit).filter_by(plan_id=plan.id).count():
            units = [
                ("IMAX-1930", "IMAX-1", "前排", "control", 30),
                ("IMAX-1930", "IMAX-1", "中排", "treatment", 30),
                ("IMAX-2030", "IMAX-2", "前排", "control", 24),
                ("IMAX-2030", "IMAX-2", "中排", "treatment", 24),
            ]
            for session, hall, zone, group, count in units:
                db.add(ExperimentUnit(plan_id=plan.id, session_code=session, hall_name=hall, seat_zone=zone, group_name=group, seat_count=count, status="started", started_at=datetime.now(timezone.utc)))
            plan.status = "live"; db.flush()
        units = db.query(ExperimentUnit).filter_by(plan_id=plan.id).all()
        if not db.query(TicketObservation).filter(TicketObservation.ticket_code.like("SEED-CINEMA-%")).count():
            number = 1
            for unit in units:
                for i in range(18):
                    sold = (i % 5 != 0) if unit.group_name == "treatment" else (i % 3 != 0)
                    db.add(TicketObservation(unit_id=unit.id, ticket_code=f"SEED-CINEMA-{number:03d}", seat_label=f"{unit.seat_zone}-{i+1:02d}", sold=sold, price_paid=58 if sold else 0, source="seed-box-office"))
                    number += 1
        db.commit()
        print("seed ok")
    finally:
        db.close()

if __name__ == "__main__": seed()
