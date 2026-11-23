from pydantic import BaseModel, Field, ConfigDict 
from app.schema.interaction import InteractionCreate
from uuid import UUID
from typing import Literal

MAX_BATCH_SIZE = 100

class BatchInteractionItem(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    idempotency_key: str = Field(min_length = 1, max_length = 255)
    interaction: InteractionCreate


class BatchItemResult(BaseModel):
    index: int
    interaction_id: UUID
    status: Literal["created", "duplicate"]


class InteractionBatchCreate(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    items: list[BatchInteractionItem] = Field(min_length = 1, max_length = MAX_BATCH_SIZE )


class InteractionBatchRead(BaseModel):
    result: list[BatchItemResult]