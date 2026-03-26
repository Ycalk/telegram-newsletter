from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class APIClientSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_base_url: str
    s3_base_url: str
    api_secret_token: str
    timeout_seconds: int = 5
    cache_ttl_seconds: int = 3600
