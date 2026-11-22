from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=60)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=600)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SubmitCloseout(Input):
    unit_id: int = Field(gt=0)
    expected_closeout_id: int = Field(ge=0)
    batch_ref: Reference
    observed: int = Field(ge=0, le=20000)
    sold: int = Field(ge=0, le=20000)
    revenue: Decimal = Field(ge=0, max_digits=9, decimal_places=2)
    note: Note

    @model_validator(mode='after')
    def validate_sold(self):
        if self.sold > self.observed or (not self.sold and self.revenue):
            raise ValueError('售出票数不得超过观测数，无售票时实收应为 0')
        return self


class OpenPilot(Input):
    review_id: int = Field(gt=0)
    unit_id: int = Field(gt=0)
    show_date: date
    show_time: Annotated[str, StringConstraints(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')]
    pilot_seats: int = Field(gt=0, le=500)
    objective: Note


class ConfirmPilot(Input):
    booking_ref: Reference
    actual_seats: int = Field(gt=0, le=500)
    result_note: Note


class WithdrawPilot(Input):
    result_note: Note
