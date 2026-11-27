from pydantic import Field, PostgresDsn
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn
    app_env: str
    access_token_expiry_mins: int = Field(validation_alias="access_token_expiry_mins")
    refresh_token_expiry_days: int
    jwt_secret_key: str
    attica_edition: Literal["community", "cloud"] = "community"

    @property
    def is_community(self) -> bool:
        return self.attica_edition == "community"

    @property
    def is_cloud(self) -> bool:
        return self.attica_edition == "cloud"