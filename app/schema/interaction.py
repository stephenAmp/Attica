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
    input: str | None = None
    output: str | None = None
    schema_version: int
    environment: str | None = Field(default=None, max_length=100)
    feature: str | None = Field(default=None, max_length=255)
    trace_id: str | None = Field(default=None, max_length=255)
    release: str | None = Field(default=None, max_length=50)
    prompt_version: int | None = Field(default=None, ge=0, le=2147483647)



class InteractionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid");

    occurred_at: AwareDatetime;
    status: Literal["success", "error"];
    model: str = Field(min_length=1, max_length=255);
    latency_ms: int = Field(ge=0);
    input_token: int = Field(ge=0);
    output_token: int = Field(ge=0);

    input: str | None = None
    output: str | None = None;
    schema_version: Literal[1] = 1;
    environment: str | None = Field(default=None, max_length=100)
    feature: str | None = Field(default=None, max_length=255)
    trace_id: str | None = Field(default=None, max_length=255)
    release: str | None = Field(default=None, max_length=50)
    prompt_version: int | None = Field(default=None, ge=0, le=2147483647)



class InteractionEvent(BaseModel):
    interaction_id: UUID;
    tenant_id: UUID;
    schema_version: Literal[1];
    occurred_at: AwareDatetime;
    ingested_at: AwareDatetime;
    event_id: UUID;
    status: Literal["success", "error"];
    scores: Dict[str, Any];
    model: str;
    latency_ms: int = Field(ge=0);
    input_token: int = Field(ge=0);
    output_token: int = Field(ge=0);
    input: str | None = None
    output: str | None = None
    environment: str | None = Field(default=None, max_length=100)
    feature: str | None = Field(default=None, max_length=255)
    trace_id: str | None = Field(default=None, max_length=255)
    release: str | None = Field(default=None, max_length=50)
    prompt_version: int | None = Field(default=None, ge=0, le=2147483647)