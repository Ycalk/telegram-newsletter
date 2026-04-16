from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class ParsingTaskStatus(StrEnum):
    IDLE = "idle"
    SKIP = "skip"
    EXISTS = "exists"
    ERROR = "error"


class Media(BaseModel):
    id: UUID
    mime_type: str
    size_bytes: int
    file_name: str


class MediaWithURL(Media):
    url: str


class Channel(BaseModel):
    id: int
    name: str
    description: str | None
    logo: Media | None


class ChannelMessage(BaseModel):
    id: UUID
    created_at: int
    text: str
    html_text: str
    media: list[Media]


class ParsingTask(BaseModel):
    id: UUID
    url: str
    channel_id: int | None
    status: ParsingTaskStatus
    next_run_at: int | None
    last_parsed_at: int | None
    created_at: int
