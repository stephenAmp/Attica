from pydantic import BaseModel, ConfigDict, AwareDatetime
from uuid import UUID
from datetime import datetime

class TraceCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: AwareDatetime
    model: str
    status: str
    latency_ms: int
    input_token: int
    output_token: int


class TraceTotals(BaseModel):
    calls: int
    failures: int
    input_tokens: int
    output_tokens: int


class TraceRead(BaseModel):
    tenant_id: UUID
    trace_id: str
    totals: TraceTotals
    calls: list[TraceCallRead]

class TraceSummary(BaseModel):
    trace_id: str
    last_activity: datetime
    call_count: int
    failure_count: int
    input_tokens: int
    output_tokens: int


class TraceListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    traces: list[TraceSummary]