from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminPanelSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    port: int = 8000
    bot_username: str = ""
