from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Money = Annotated[int, Field(ge=0, le=10_000_000)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=400)]


class SettlementInput(BaseModel):
    pos_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    tickets_sold: int = Field(ge=0, le=10000)
    gross_tickets_cents: Money
    ticket_commission_cents: Money
    concession_margin_cents: Money
    incremental_cost_cents: Money
    subsidy_cents: Money
    notes: Note


class SettlementReview(BaseModel):
    decision: Literal['approved','rejected']
    note: Note
