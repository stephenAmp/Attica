from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.general import Interaction
from app.schema.trace import TraceTotals, TraceCallRead, TraceRead


class TraceService:
    def __init__(self, db: AsyncSession):
        self.db = db


    async def getTrace(self, tenant_id: UUID, trace_id: str)-> TraceRead:
        statement = select(Interaction).where(Interaction.tenant_id == tenant_id, Interaction.trace_id == trace_id).order_by(Interaction.occurred_at.asc(), Interaction.id.asc())

        result = await self.db.execute(statement)
        interactions = result.scalars().all()

        calls = [TraceCallRead.model_validate(interaction) for interaction in interactions]

        totals = TraceTotals(calls = len(calls), failures = sum(call.status == "error" for call in calls), input_tokens = sum(call.input_token for call in calls), output_tokens = sum(call.output_token for call in calls))

        return TraceRead(tenant_id = tenant_id, trace_id = trace_id, calls = calls,totals = totals)

