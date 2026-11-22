from datetime import datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now_utc():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ScreeningPlan(Base):
    __tablename__ = "screening_plans"
    __table_args__ = (UniqueConstraint("natural_key", name="uq_plan_natural_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    natural_key: Mapped[str] = mapped_column(String(80), index=True)
    film_title: Mapped[str] = mapped_column(String(120))
    version_name: Mapped[str] = mapped_column(String(80))
    show_date: Mapped[datetime] = mapped_column(Date)
    show_time: Mapped[str] = mapped_column(String(10))
    hall_name: Mapped[str] = mapped_column(String(60))
    seat_capacity: Mapped[int] = mapped_column(Integer)
    base_price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    units: Mapped[list["ExperimentUnit"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    reviews: Mapped[list["RevenueReview"]] = relationship(back_populates="plan", cascade="all, delete-orphan")

class ExperimentUnit(Base):
    __tablename__ = "experiment_units"
    __table_args__ = (UniqueConstraint("plan_id", "session_code", "seat_zone", name="uq_unit_stratum"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("screening_plans.id"), index=True)
    session_code: Mapped[str] = mapped_column(String(40))
    hall_name: Mapped[str] = mapped_column(String(60))
    seat_zone: Mapped[str] = mapped_column(String(30))
    group_name: Mapped[str] = mapped_column(String(20))
    seat_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="configured")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan: Mapped[ScreeningPlan] = relationship(back_populates="units")
    observations: Mapped[list["TicketObservation"]] = relationship(back_populates="unit", cascade="all, delete-orphan")

class TicketObservation(Base):
    __tablename__ = "ticket_observations"
    __table_args__ = (UniqueConstraint("ticket_code", name="uq_ticket_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("experiment_units.id"), index=True)
    ticket_code: Mapped[str] = mapped_column(String(60), index=True)
    seat_label: Mapped[str] = mapped_column(String(20))
    sold: Mapped[bool] = mapped_column(Boolean)
    price_paid: Mapped[float] = mapped_column(Float, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    source: Mapped[str] = mapped_column(String(30), default="box-office")
    unit: Mapped[ExperimentUnit] = relationship(back_populates="observations")

class RevenueReview(Base):
    __tablename__ = "revenue_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("screening_plans.id"), index=True)
    analysis_status: Mapped[str] = mapped_column(String(24), default="pending")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    control_rate: Mapped[float] = mapped_column(Float, default=0)
    treatment_rate: Mapped[float] = mapped_column(Float, default=0)
    absolute_diff: Mapped[float] = mapped_column(Float, default=0)
    ci_low: Mapped[float] = mapped_column(Float, default=0)
    ci_high: Mapped[float] = mapped_column(Float, default=0)
    stratified_effect: Mapped[float] = mapped_column(Float, default=0)
    balance_ratio: Mapped[float] = mapped_column(Float, default=1)
    is_stratified: Mapped[bool] = mapped_column(Boolean, default=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    plan: Mapped[ScreeningPlan] = relationship(back_populates="reviews")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
