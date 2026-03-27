from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class MediaProxySettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    document_placeholder_width: int = 400
    document_placeholder_height: int = 500

    play_icon_size_percent: int = 20

    port: int = 8000
