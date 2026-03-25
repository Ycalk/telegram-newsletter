from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    confirmation_code_length: int = 6
    bot_token: str
    redis_host: str
    redis_port: int
    redis_db: int = 1
