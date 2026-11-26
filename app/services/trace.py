from uuid import UUID
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.queries.trace import build_trace_cohort
from app.models.general import Interaction, Outcome
from app.schema.outcome import OutcomeRead
from app.schema.trace import TraceTotals, TraceCallRead, TraceRead, TraceListResponse, TraceSummary


class TraceService:
    def __init__(self, db: AsyncSession):
        self.db = db


    async def getTrace(self, tenant_id: UUID, trace_id: str)-> TraceRead:
        statement = select(Interaction).where(
            Interaction.tenant_id == tenant_id, 
            Interaction.trace_id == trace_id
            ).order_by(
                Interaction.occurred_at.asc(), 
                Interaction.id.asc()
            )

        result = await self.db.execute(statement)
        interactions = result.scalars().all()

        calls = [TraceCallRead.model_validate(interaction) for interaction in interactions]

        # Added outcome to trace response
        statement = select(Outcome).where(
            Outcome.tenant_id == tenant_id, 
            Outcome.trace_id == trace_id
            ).order_by(
                Outcome.occurred_at.asc(), 
                Outcome.id.asc()
        )

        result = await self.db.execute(statement)
        outcomes = [
            OutcomeRead.model_validate(outcome, from_attributes = True) for outcome in result.scalars().all()
        ]

        totals = TraceTotals(calls = len(calls), failures = sum(call.status == "error" for call in calls), input_tokens = sum(call.input_token for call in calls), output_tokens = sum(call.output_token for call in calls))

        return TraceRead(tenant_id = tenant_id, trace_id = trace_id, calls = calls,totals = totals, outcomes = outcomes)


    async def listTraces(
            self,
            tenant_id: UUID,
            start_time: datetime,
            end_time: datetime,
            release: str | None = None,
            has_error: bool = False,
            limit: int = 20,
            offset: int = 0,
            outcome_name: str | None = None,
            feature: str | None = None,
            environment: str | None = None,
            cohort: str = "activity",
    ) -> TraceListResponse:
        if cohort == "release":
            grouped = build_trace_cohort(tenant_id, [release], feature, environment, start_time, end_time)
            summary_query = select(grouped).where(grouped.c.is_consistent)
            if has_error:
                summary_query = summary_query.where(grouped.c.failure_count > 0)
        else:
            matching = select(Interaction.trace_id).where(
                Interaction.tenant_id == tenant_id,
                Interaction.trace_id.is_not(None),
                Interaction.occurred_at >= start_time,
                Interaction.occurred_at < end_time,
            )
            if release is not None:
                matching = matching.where(Interaction.release == release)
            if feature is not None:
                matching = matching.where(Interaction.feature == feature)
            if environment is not None:
                matching = matching.where(Interaction.environment == environment)
            if has_error:
                matching = matching.where(Interaction.status == "error")

            summary_query = select(
                Interaction.trace_id,
                func.max(Interaction.occurred_at).label("last_activity"),
                func.count().label("call_count"),
                func.count().filter(Interaction.status == "error").label("failure_count"),
                func.sum(Interaction.input_token).label("input_tokens"),
                func.sum(Interaction.output_token).label("output_tokens"),
            ).where(
                Interaction.tenant_id == tenant_id,
                Interaction.trace_id.in_(matching),
            ).group_by(Interaction.trace_id)

        summaries = summary_query.subquery()
        if outcome_name is not None:
            matching_outcome = select(Outcome.id).where(
                Outcome.tenant_id == tenant_id,
                Outcome.trace_id == summaries.c.trace_id,
                Outcome.name == outcome_name,
            ).exists()
            summaries = select(summaries).where(matching_outcome).subquery()

        total = await self.db.scalar(select(func.count()).select_from(summaries))

        statement = select(summaries).order_by(
            summaries.c.last_activity.desc(),
            summaries.c.trace_id.desc(),
        ).limit(limit).offset(offset)


        result = await self.db.execute(statement)

        traces = [
            TraceSummary.model_validate(dict(row))
            for row in result.mappings().all()
        ]

        return TraceListResponse(total = total or 0, limit = limit, offset = offset, traces = traces)
        