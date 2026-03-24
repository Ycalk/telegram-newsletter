from typing import ClassVar

from dishka import Provider, Scope, provide
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    trace_exporter_endpoint: str | None = None


class LoggingSettingsProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> LoggingSettings:
        return LoggingSettings()
