from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..models import now_utc


class PilotSettlement(Base):
    __tablename__ = 'pilot_settlements'
    __table_args__ = (
        UniqueConstraint('pilot_id'),
        UniqueConstraint('pos_reference'),
        CheckConstraint("state IN ('submitted','approved','rejected')"),
        CheckConstraint('tickets_sold >= 0 AND tickets_sold <= seats_offered'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey('scheduling_pilots.id'), nullable=False)
    pos_reference: Mapped[str] = mapped_column(String(80))
    seats_offered: Mapped[int] = mapped_column(Integer)
    tickets_sold: Mapped[int] = mapped_column(Integer)
    gross_tickets_cents: Mapped[int] = mapped_column(BigInteger)
    ticket_commission_cents: Mapped[int] = mapped_column(BigInteger)
    concession_margin_cents: Mapped[int] = mapped_column(BigInteger)
    incremental_cost_cents: Mapped[int] = mapped_column(BigInteger)
    subsidy_cents: Mapped[int] = mapped_column(BigInteger)
    contribution_cents: Mapped[int] = mapped_column(BigInteger)
    breakeven_tickets: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default='submitted')
    submitted_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
