from typing import ClassVar

from pydantic import model_validator
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
    track_url: str
    resend_api_key: str | None = None
    sendgrid_api_key: str | None = None

    @model_validator(mode="after")
    def check_api_keys(self) -> "EmailSenderSettings":
        if self.resend_api_key is None and self.sendgrid_api_key is None:
            raise ValueError(
                "resend_api_key and sendgrid_api_key cannot be None at the same time"
            )
        return self
