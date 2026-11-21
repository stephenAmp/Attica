from uuid import UUID
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.models.general import Interaction, Outcome
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
            TraceRead.model_validate(outcome, from_attributes = True) for outcome in result.scalars().all()
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
    ) -> TraceListResponse:
        matching_query = select(Interaction.trace_id).where(Interaction.tenant_id == tenant_id, Interaction.trace_id.is_not(None), Interaction.occurred_at >= start_time, Interaction.occurred_at < end_time)

        if release is not None:
            matching_query = matching_query.where(Interaction.release == release)
        if has_error:
            matching_query = matching_query.where(Interaction.status == "error")

        matching_traces = matching_query.distinct().subquery()

        calls = aliased(Interaction)
       
        summary_query = select(
            calls.trace_id.label("trace_id"), 
            func.max(calls.occurred_at).label("last_activity"),
            func.count(calls.id).label("call_count"),
            func.count(calls.id).filter(calls.status == "error").label("failure_count"),
            func.coalesce(func.sum(calls.input_token), 0).label("input_tokens"),
            func.coalesce(func.sum(calls.output_token), 0).label("output_tokens")
            ).join(
                matching_traces, calls.trace_id == matching_traces.c.trace_id
            ).where(
                calls.tenant_id == tenant_id
            ). group_by(
                calls.trace_id
            )
        

        summaries = summary_query.subquery()

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
        