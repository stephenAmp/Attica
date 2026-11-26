from uuid import UUID
from datetime import datetime
from app.schema.release import ReleaseComparisonRead, ReleaseMetrics, ReleaseMetricsChange, TraceDrillDown
from app.queries.trace import build_trace_cohort
from sqlalchemy import func, select 
from app.utils.general import safe_divide, difference
from sqlalchemy import true as True_expression

class ReleaseService:
    def __init__(self, db):
        self.db = db


    def calculateChange(self, baseline: ReleaseMetrics, candidate: ReleaseMetrics) -> ReleaseMetricsChange:
        rate_change = difference(candidate.failed_call_trace_rate, baseline.failed_call_trace_rate)

        return ReleaseMetricsChange(
            trace_count = candidate.trace_count - baseline.trace_count,
            call_count = candidate.call_count - baseline.call_count,
            traces_with_failed_calls = candidate.traces_with_failed_calls - baseline.traces_with_failed_calls,
            failed_call_trace_rate_pp = rate_change * 100 if rate_change is not None else None,
            calls_per_trace = difference(candidate.calls_per_trace, baseline.calls_per_trace,),
            input_tokens_per_trace = difference(candidate.input_tokens_per_trace,baseline.input_tokens_per_trace,),
            output_tokens_per_trace = difference(candidate.output_tokens_per_trace,baseline.output_tokens_per_trace,),
            input_tokens_per_call=difference(candidate.input_tokens_per_call, baseline.input_tokens_per_call),
            output_tokens_per_call=difference(candidate.output_tokens_per_call, baseline.output_tokens_per_call)
        )


    async def compareReleases(self, tenant_id: UUID, baseline_release: str, candidate_release: str, feature: str, environment: str, start_time: datetime, end_time: datetime) -> ReleaseComparisonRead:
        cohort = build_trace_cohort(tenant_id = tenant_id, releases = [baseline_release, candidate_release], feature = feature, environment = environment, start_time = start_time, end_time = end_time)

        trace_count = func.count(cohort.c.trace_id)

        call_count = func.coalesce(func.sum(cohort.c.call_count), 0)

        failed_traces = func.count(cohort.c.trace_id).filter(cohort.c.failure_count > 0)

        input_tokens = func.coalesce(func.sum(cohort.c.input_tokens), 0)

        output_tokens = func.coalesce(func.sum(cohort.c.output_tokens), 0)

        statement = select(
            cohort.c.release, 
            trace_count.label("trace_count"), 
            call_count.label("call_count"), 
            failed_traces.label("traces_with_failed_calls"),
            safe_divide(failed_traces, trace_count).label("failed_call_trace_rate"),
            safe_divide(call_count, trace_count).label("calls_per_trace"),
            safe_divide(input_tokens, trace_count).label("input_tokens_per_trace"),
            safe_divide(output_tokens, trace_count).label("output_tokens_per_trace"),
            safe_divide(input_tokens, call_count).label("input_tokens_per_call"),
            safe_divide(output_tokens, call_count).label("output_tokens_per_call"),
        ).where(cohort.c.is_consistent.is_(True)).group_by(cohort.c.release)

        # Count ambiguous traces in the same SQL statement
        metrics_query = statement.cte("release_metrics")

        excluded_query = select(func.count()).select_from(cohort).where(cohort.c.is_consistent.is_(False)).cte("excluded_traces")

        
        statement = select(metrics_query, excluded_query.c[0].label("excluded")).select_from(excluded_query).outerjoin(metrics_query, True_expression())

        result = await self.db.execute(statement)
        rows = result.mappings().all()

        metrics = {
            row["release"]: ReleaseMetrics.model_validate(dict(row))
            for row in rows
            if row["release"] is not None
        }

        excluded = rows[0]["excluded"]

        empty = ReleaseMetrics(
            trace_count=0,
            call_count=0,
            traces_with_failed_calls=0,
            failed_call_trace_rate=None,
            calls_per_trace=None,
            input_tokens_per_trace=None,
            output_tokens_per_trace=None,
            input_tokens_per_call=None,
            output_tokens_per_call=None,
        )

        baseline = metrics.get(baseline_release, empty)
        candidate = metrics.get(candidate_release, empty)

        change = self.calculateChange(baseline = baseline, candidate = candidate)

        drilldown_params = {
            "feature": feature,
            "environment": environment,
            "start_time": start_time,
            "end_time": end_time,
        }

        return ReleaseComparisonRead(
            tenant_id = tenant_id,
            baseline_release = baseline_release,
            candidate_release = candidate_release,
            baseline = baseline,
            candidate = candidate,
            change = change,
            excluded_ambiguous_traces = excluded,
            baseline_drilldown = TraceDrillDown(release = baseline_release, **drilldown_params),
            candidate_drilldown = TraceDrillDown(release = candidate_release, **drilldown_params)
        )
