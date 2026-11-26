from pydantic import BaseModel, AwareDatetime
from uuid import UUID

class ReleaseMetrics(BaseModel):
    trace_count: int
    call_count: int

    traces_with_failed_calls: int
    failed_call_trace_rate: float | None
    calls_per_trace: float | None

    input_tokens_per_trace: float | None
    output_tokens_per_trace: float | None

    input_tokens_per_call: float | None
    output_tokens_per_call: float | None


class ReleaseMetricsChange(BaseModel):
    trace_count: int
    call_count: int
    traces_with_failed_calls: int

    failed_call_trace_rate_pp: float | None
    calls_per_trace: float | None

    input_tokens_per_trace: float | None
    output_tokens_per_trace: float | None

    input_tokens_per_call: float | None
    output_tokens_per_call: float | None


class TraceDrillDown(BaseModel):
    release: str
    feature: str
    environment: str
    start_time: AwareDatetime
    end_time: AwareDatetime
    has_error: bool = True
    cohort: str = "release"


class ReleaseComparisonRead(BaseModel):
    tenant_id: UUID
    baseline_release: str
    candidate_release: str

    baseline: ReleaseMetrics
    candidate: ReleaseMetrics
    change: ReleaseMetricsChange

    excluded_ambiguous_traces: int

    baseline_drilldown: TraceDrillDown
    candidate_drilldown: TraceDrillDown


#  failure rate will be decimal between 0 and 1
