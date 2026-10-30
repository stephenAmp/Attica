from sqlalchemy.ext.asyncio import AsyncSession
from app.schema.interaction import InteractionCreate
from app.models.general import UserTenants

class InteractionService:
    def __init__(self, db:AsyncSession):
        self.db = db

    async def createInteraction(data:InteractionCreate, tenant_id: str, user_id: str):
        pass