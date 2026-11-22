from app.schema.ingestion_api_key import APIKeyRead, APIKeyCreate, APIKeyIssued
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.models.general import IngestionAPIKey
from app.utils.api_key import generate_api_key
from sqlalchemy import select
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException


class IngestionAPIKeyService:
    def __init__(self, db:AsyncSession):
        self.db = db


    async def listIngestionKeys(self, tenant_id: UUID) -> list[IngestionAPIKey]:
        statement = select(IngestionAPIKey).where(IngestionAPIKey.tenant_id == tenant_id).order_by(IngestionAPIKey.created_at.desc())

        result = await self.db.execute(statement)
        return list(result.scalars())


    async def createIngestionKey(self, data:APIKeyCreate, tenant_id: UUID, user_id: UUID):
        key_id = uuid.uuid4()
        raw_key, secret_hash = generate_api_key(key_id = key_id)

        record = IngestionAPIKey(
            id=key_id, tenant_id=tenant_id, name=data.name,
            secret_hash=secret_hash, created_by=user_id,
        )

        try:
            self.db.add(record)
            await self.db.flush()

            key_read = APIKeyRead.model_validate(record)
            await self.db.commit()
            return APIKeyIssued(**key_read.model_dump(), api_key=raw_key)
        except Exception:
            await self.db.rollback()
            raise
      

    async def revokeIngestionKey(self, key_id: UUID, tenant_id: UUID):
        try:
            statement = select(IngestionAPIKey).where(
                IngestionAPIKey.id == key_id, 
                IngestionAPIKey.tenant_id == tenant_id
                ).with_for_update()

            result = await self.db.execute(statement)
            record = result.scalar_one_or_none()

            if record is None:
                raise HTTPException(status_code = 404, detail = "API key not found")

            if record.revoked_at is not None:
                raise HTTPException(status_code = 409, detail = "key has already been revoked")
            
            record.revoked_at = datetime.now(timezone.utc)
            await self.db.commit()
            
        except Exception:
            await self.db.rollback()
            raise

        

        