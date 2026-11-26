from datetime import datetime
from uuid import UUID

from sqlalchemy import select, func, and_

from app.models.general import Interaction


def build_trace_cohort(tenant_id: UUID, releases: list[str], feature: str, environment: str, start_time: datetime, end_time: datetime):
    
    call = Interaction

    matches_context = and_(
        call.release.in_(releases),
        call.feature == feature,
        call.environment == environment,
    )

    consistent_attribution = and_(
        func.count(func.distinct(call.release)) == 1,
        func.count(func.distinct(call.feature)) == 1,
        func.count(func.distinct(call.environment)) == 1,

        func.count(call.release) == func.count(),
        func.count(call.feature) == func.count(),
        func.count(call.environment) == func.count(),
    )

    return (
        select(
            call.tenant_id.label("tenant_id"),
            call.trace_id.label("trace_id"),

            func.min(call.occurred_at).label("first_activity"),
            func.max(call.occurred_at).label("last_activity"),

            func.min(call.release).label("release"),

            func.count(call.id).label("call_count"),

            func.count(call.id)
            .filter(call.status == "error")
            .label("failure_count"),

            func.coalesce(func.sum(call.input_token), 0)
            .label("input_tokens"),

            func.coalesce(func.sum(call.output_token), 0)
            .label("output_tokens"),

            consistent_attribution.label("is_consistent"),
        )
        .where(
            call.tenant_id == tenant_id,
            call.trace_id.is_not(None),
        )
        .group_by(
            call.tenant_id,
            call.trace_id,
        )
        .having(
            func.min(call.occurred_at) >= start_time,
            func.min(call.occurred_at) < end_time,

            func.count(call.id)
            .filter(matches_context) > 0,
        )
        .cte("trace_cohort")
    )