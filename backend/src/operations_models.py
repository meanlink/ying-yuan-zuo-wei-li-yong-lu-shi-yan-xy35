from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .models import now_utc


class PosCloseout(Base):
    __tablename__ = 'pos_closeouts'
    __table_args__ = (
        CheckConstraint("status IN ('matched','discrepancy')"),
        CheckConstraint('report_count >= report_sold AND report_sold >= 0 AND report_cents >= 0'),
        CheckConstraint('ledger_count >= ledger_sold AND ledger_sold >= 0 AND ledger_cents >= 0'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('experiment_units.id'), index=True)
    batch_ref: Mapped[str] = mapped_column(String(60))
    report_count: Mapped[int] = mapped_column(Integer)
    report_sold: Mapped[int] = mapped_column(Integer)
    report_cents: Mapped[int] = mapped_column(BigInteger)
    ledger_count: Mapped[int] = mapped_column(Integer)
    ledger_sold: Mapped[int] = mapped_column(Integer)
    ledger_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    submitted_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SchedulingPilot(Base):
    __tablename__ = 'scheduling_pilots'
    __table_args__ = (
        CheckConstraint("status IN ('assigned','scheduled','withdrawn')"),
        CheckConstraint('pilot_seats > 0 AND (actual_seats IS NULL OR actual_seats BETWEEN 1 AND pilot_seats)'),
        CheckConstraint("(status = 'scheduled') = (booking_ref IS NOT NULL AND actual_seats IS NOT NULL)"),
        CheckConstraint("(status <> 'assigned') = (acted_by IS NOT NULL AND acted_at IS NOT NULL AND result_note IS NOT NULL)"),
        Index('uq_pilot_timeslot', 'hall_name', 'show_date', 'show_time', unique=True,
              postgresql_where=text("status IN ('assigned','scheduled')")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('revenue_reviews.id'), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('experiment_units.id'))
    hall_name: Mapped[str] = mapped_column(String(60))
    seat_zone: Mapped[str] = mapped_column(String(30))
    show_date: Mapped[date] = mapped_column(Date)
    show_time: Mapped[str] = mapped_column(String(5))
    pilot_seats: Mapped[int] = mapped_column(Integer)
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default='assigned')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    booking_ref: Mapped[str | None] = mapped_column(String(60), unique=True)
    actual_seats: Mapped[int | None] = mapped_column(Integer)
    result_note: Mapped[str | None] = mapped_column(Text)
    acted_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
