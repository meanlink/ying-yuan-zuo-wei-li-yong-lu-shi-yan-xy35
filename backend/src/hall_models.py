from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .models import now_utc


class HallChangeAttempt(Base):
    """场次开场后的临时换厅请求。一次请求覆盖同厅全部实验单元。"""

    __tablename__ = 'hall_change_attempts'
    __table_args__ = (
        CheckConstraint("status IN ('effective','rejected')"),
        CheckConstraint('retry_count >= 0'),
        CheckConstraint('target_capacity > 0'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('screening_plans.id'), index=True)
    origin_hall_name: Mapped[str] = mapped_column(String(60))
    target_hall_name: Mapped[str] = mapped_column(String(60))
    target_capacity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default='rejected')
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HallAssignment(Base):
    """实验单元在一段时间内实际所在的厅与座区，换厅通过闭合旧段、开启新段实现。"""

    __tablename__ = 'hall_assignments'
    __table_args__ = (
        Index('ix_hall_assignment_unit_open', 'unit_id', 'started_at'),
        # 每个实验单元至多保留一个未闭合（当前生效）的厅段；允许反复迁回同一厅。
        # 单开放段不变量同时由 services/hall_change.py 在应用层保证。
        Index('uq_hall_assignment_open', 'unit_id', unique=True,
              postgresql_where=sa_text('ended_at IS NULL')),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('experiment_units.id'), index=True)
    hall_name: Mapped[str] = mapped_column(String(60))
    seat_zone: Mapped[str] = mapped_column(String(30))
    seat_capacity: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hall_change_id: Mapped[int | None] = mapped_column(
        ForeignKey('hall_change_attempts.id'), nullable=True,
    )
