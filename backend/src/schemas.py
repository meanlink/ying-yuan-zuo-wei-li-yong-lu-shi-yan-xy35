from datetime import date
from pydantic import BaseModel, Field

class LoginIn(BaseModel):
    email: str
    password: str

class PlanCreate(BaseModel):
    natural_key: str = Field(min_length=3, max_length=80)
    film_title: str
    version_name: str
    show_date: date
    show_time: str
    hall_name: str
    seat_capacity: int = Field(gt=0, le=500)
    base_price: float = Field(gt=0, le=1000)

class UnitCreate(BaseModel):
    session_code: str
    hall_name: str
    seat_zone: str
    group_name: str
    seat_count: int = Field(gt=0, le=500)

class ObservationCreate(BaseModel):
    unit_id: int
    ticket_code: str
    seat_label: str
    sold: bool
    price_paid: float = Field(ge=0, le=1000)
    source: str = "box-office"

class ReviewApprove(BaseModel):
    notes: str = ""

class ObservationCreate(BaseModel):
    unit_id: int
    ticket_code: str
    seat_label: str
    sold: bool
    price_paid: float = Field(ge=0, le=1000)
    source: str = "box-office"
