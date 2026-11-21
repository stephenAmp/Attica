from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from datetime import datetime
from uuid import UUID


class OutcomeCreate(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    event_id: UUID
    trace_id: str = Field(min_length = 1, max_length = 255)
    name: str = Field(min_length = 1, max_length = 255)
    occurred_at: AwareDatetime


class OutcomeRead(OutcomeCreate):
    tenant_id: UUID
    ingested_at: datetime
