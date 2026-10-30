from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=100)
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("full_name", "email", mode="before")
    @classmethod
    def normalize_text(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
            if info.field_name == "email":
                value = value.lower()
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    is_active: bool
