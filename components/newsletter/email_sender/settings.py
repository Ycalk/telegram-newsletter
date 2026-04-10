from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSenderSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    send_from_email: str
    resend_api_key: str
    track_url: str
