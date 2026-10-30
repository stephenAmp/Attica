from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from typing import Dict, Any, Literal



class InteractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID;
    created_by: UUID;
    tenant_id: UUID;
    status: str;
    scores: Dict[str, Any];
    model: str;
    latency_ms: int;
    occurred_at: AwareDatetime;
    ingested_at: AwareDatetime;
    input_token: int;
    output_token: int;
    input: str ;
    output: str | None;
    schema_version: int



class InteractionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid");

    occurred_at: AwareDatetime;
    status: Literal["success", "error"];
    model: str = Field(min_length=1, max_length=255);
    latency_ms: int = Field(ge=0);
    input_token: int = Field(ge=0);
    output_token: int = Field(ge=0);

    input: str;
    output: str | None = None;
    schema_version: Literal[1] = 1;