from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChannelIdEncryptionSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    channel_id_encryption_key: str
