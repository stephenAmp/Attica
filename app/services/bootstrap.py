from datetime import datetime, timezone
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.general import InstanceSettings
from app.models.general import User, Tenant, Role, UserTenants
from app.core.config import Settings


settings = Settings()

class BootstrapError(Exception):
    pass


class BootstrapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def initialize(
        self,
        full_name: str,
        email: str,
        hashed_password: str,
        workspace_name: str,
        workspace_email: str,
        phone: str,
        location: str,
    ):
        if settings.is_cloud:
            raise BootstrapError("Bootstrap is only available in Community edition")

        async with self.db.begin():
            statement =  select(InstanceSettings).where(InstanceSettings.id == 1).with_for_update()
            instance = (await self.db.execute(statement)).scalar_one()

            if instance.initialized_at is not None:
                raise BootstrapError("Attica has already been initialized")

            # check if atleast one user exists
            has_users = await self.db.scalar(
                select(exists().where(User.id.is_not(None)))
            )

            has_tenants = await self.db.scalar(
                select(exists().where(Tenant.id.is_not(None)))
            )

            if has_users or has_tenants:
                raise BootstrapError("Bootstrap requires a fresh installation")

            admin_role = await self.db.scalar(
                select(Role).where(Role.name == "admin")
            )

            if admin_role is None:
                raise BootstrapError("Admin role required")

            user = User(
                full_name=full_name,
                email=email,
                hashed_password=hashed_password,
                is_active=True,
            )

            tenant = Tenant(
                name=workspace_name,
                email=workspace_email,
                phone=phone,
                location=location,
            )

            self.db.add_all([user, tenant])

            await self.db.flush()

            membership = UserTenants(
                user_id=user.id,
                tenant_id=tenant.id,
                role_id=admin_role.id,
            )

            self.db.add(membership)

            instance.workspace_id = tenant.id
            instance.initialized_at = datetime.now(timezone.utc)

            return tenant.id