from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.general import Role, Tenant, UserTenants
from app.schema.tenant import TenantCreate, TenantRead


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def createTenant(self, data: TenantCreate, creator_id: UUID) -> TenantRead:
        admin_role_id = await self.db.scalar(
            select(Role.id).where(Role.name == "admin")
        )
        if admin_role_id is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin role is not configured",
            )

        statement = (
            insert(Tenant)
            .values(
                name=data.name,
                email=str(data.email),
                location=data.location,
                phone=data.phone,
            )
            .on_conflict_do_nothing(index_elements=[Tenant.email])
            .returning(Tenant)
        )
        tenant = (await self.db.execute(statement)).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tenant email is already registered",
            )

        self.db.add(
            UserTenants(
                user_id=creator_id, tenant_id=tenant.id, role_id=admin_role_id
            )
        )
        
        response = TenantRead.model_validate(tenant)
        return response


    async def getTenant(self, tenant_id: UUID) -> TenantRead:
        tenant = await self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
            )
        return TenantRead.model_validate(tenant)
