from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime

class APIKeyCreate(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    name: str = Field(min_length = 1, max_length = 100)


class APIKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes = True)

    id: UUID
    tenant_id: UUID
    name: str
    created_at: datetime
    revoked_at: datetime | None
    created_by: UUID


class APIKeyIssued(APIKeyRead):
    api_key: str
