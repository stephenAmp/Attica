from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from datetime import datetime
from uuid import UUID


class OutcomeCreate(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    tenant_id: UUID
    trace_id: str
    name: str = Field(min_length = 1, max_length = 255)
    occured_at: AwareDatetime


class OutcomeRead(OutcomeCreate):
    ingested_at: datetime
