from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn
    acces_token_expiry_mins: int = Field(validation_alias="access_token_expiry_mins")
    refresh_token_expiry_days: int
    jwt_secret_key: str
