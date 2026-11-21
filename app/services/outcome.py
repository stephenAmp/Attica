from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.schema.outcome import OutcomeCreate
from app.models.general import Outcome
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from fastapi import HTTPException


class OutcomeService:
    def __init__(self, db:AsyncSession):
        self.db = db

    async def createOutcome(self, data: OutcomeCreate, tenant_id: UUID)->Outcome:
        statement = insert(Outcome).values(
            tenant_id = tenant_id,
            event_id = data.event_id,
            name = data.name,
            occurred_at = data.occurred_at,
            trace_id = data.trace_id
        ).on_conflict_do_nothing(
            constraint = "uq_tenant_outcome_event"
        ).returning(Outcome)

        outcome = (await self.db.execute(statement)).scalar_one_or_none()

        if outcome is not None:
            return outcome

        statement = select(Outcome).where(Outcome.event_id == data.event_id, Outcome.tenant_id == tenant_id)
        existing = (await self.db.execute(statement)).scalar_one()

        if(
            existing.occurred_at != data.occurred_at
            or existing.name != data.name 
            or existing.trace_id != data.trace_id
        ):
            raise HTTPException(status_code = 409, detail = "Event ID already exists with different contents")

        return existing
