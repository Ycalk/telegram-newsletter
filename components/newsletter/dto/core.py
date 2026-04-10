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
    recorded_at: int


class MediaWithURL(Media):
    url: str


class ChannelStatistic(BaseModel):
    subscribers_count: int
    views: int
    posts_count: int
    views_24h: int
    views_48h: int
    views_72h: int
    views_96h: int
    views_120h: int
    views_144h: int
    views_168h: int
    posts_count_24h: int
    posts_count_48h: int
    posts_count_72h: int
    posts_count_96h: int
    posts_count_120h: int
    posts_count_144h: int
    posts_count_168h: int
    recorded_at: int


class Channel(BaseModel):
    id: int
    name: str
    description: str | None
    logo: Media | None
    newest_statistic: ChannelStatistic
    recorded_at: int
    updated_at: int


class ChannelMessageStatistic(BaseModel):
    views: int
    recorded_at: int


class ChannelMessage(BaseModel):
    id: UUID
    channel_message_id: int
    created_at: int
    text: str
    html_text: str
    media: list[Media]
    statistics: list[ChannelMessageStatistic]
    recorded_at: int
    updated_at: int


class ParsingTask(BaseModel):
    id: UUID
    url: str
    channel_id: int | None
    status: ParsingTaskStatus
    next_run_at: int | None
    last_parsed_at: int | None
    created_at: int
