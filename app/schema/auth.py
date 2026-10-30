from typing import Literal

from pydantic import BaseModel, EmailStr, SecretStr


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class UserLogin(BaseModel):
    email: EmailStr
    password: SecretStr
