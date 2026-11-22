from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=600)]
HallName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class HallInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


class HallChangeRequest(HallInput):
    origin_hall_name: HallName
    target_hall_name: HallName
    target_capacity: int = Field(gt=0, le=2000)
    reason: Note


class HallChangeRetry(HallInput):
    reason: Note
