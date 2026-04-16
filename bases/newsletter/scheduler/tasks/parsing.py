import asyncio
from datetime import datetime, timedelta, timezone
from typing import ClassVar, Final, override
from uuid import UUID

import structlog
from newsletter.api_client import GetAllChannels, GetChannelMessages, IAPIClient
from newsletter.database import (
    ChannelDAO,
    ChannelMessageDAO,
    Media,
    MediaDAO,
    MultipleDAOFactory,
)
from newsletter.dto import Channel as ChannelDTO
from opentelemetry import trace

from .base import BaseTask

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger()


class ParsingTask(BaseTask):
    interval: ClassVar[timedelta] = timedelta(minutes=30)

    def __init__(
        self,
        api_client: IAPIClient,
        multiple_dao_factory: MultipleDAOFactory,
    ):
        self.api_client: IAPIClient = api_client
        self.multiple_dao_factory: MultipleDAOFactory = multiple_dao_factory

    async def _update_channel(self, channel_dto: ChannelDTO) -> None:
        with _tracer.start_as_current_span("update_channel") as span:
            span.set_attribute("channel.id", channel_dto.id)

            async with self.multiple_dao_factory() as dao_factory:
                channel_dao = dao_factory(ChannelDAO)
                media_dao = dao_factory(MediaDAO)

                logo_id: UUID | None = None

                if channel_dto.logo is not None:
                    _logger.info("saving_logo")
                    logo = await media_dao.find_by_id(channel_dto.logo.id)
                    if logo is None:
                        _logger.info("logo_not_found")
                        logo = await media_dao.create(
                            id=channel_dto.logo.id,
                            mime_type=channel_dto.logo.mime_type,
                            size_bytes=channel_dto.logo.size_bytes,
                            file_name=channel_dto.logo.file_name,
                        )
                        logo_id = logo.id
                    else:
                        _logger.info("logo_found")
                        logo.mime_type = channel_dto.logo.mime_type
                        logo.size_bytes = channel_dto.logo.size_bytes
                        logo.file_name = channel_dto.logo.file_name
                        await media_dao.save(logo)
                        logo_id = logo.id

                channel = await channel_dao.find_by_id(channel_dto.id)
                _logger.info("got_logo", logo_id=logo_id)
                if channel is None:
                    _logger.info("channel_not_found")
                    await channel_dao.create(
                        id=channel_dto.id,
                        name=channel_dto.name,
                        description=channel_dto.description,
                        logo_id=logo_id,
                    )
                else:
                    _logger.info("channel_found")
                    channel.name = channel_dto.name
                    channel.description = channel_dto.description
                    channel.logo_id = logo_id
                    await channel_dao.save(channel)

                await dao_factory.commit()

    async def _update_messages(self, channel_id: int) -> None:
        with _tracer.start_as_current_span("update_messages") as span:
            span.set_attribute("channel.id", channel_id)
            _logger.info("update_messages", channel_id=channel_id)
            _logger.info("getting_messages")
            now = datetime.now(timezone.utc)
            from_date = now - timedelta(hours=24)
            messages = await self.api_client(
                GetChannelMessages(
                    channel_id=channel_id,
                    created_at_start=int(from_date.timestamp()),
                    created_at_end=int(now.timestamp()),
                )
            )
            span.set_attribute("messages_count", len(messages.root))
            _logger.info("got_messages", messages_count=len(messages.root))
            _logger.info("messages_row", messages=messages.model_dump_json())

            for message in messages.root:
                async with self.multiple_dao_factory() as dao_factory:
                    channel_message_dao = dao_factory(ChannelMessageDAO)
                    media_dao = dao_factory(MediaDAO)
                    media_list: list[Media] = []
                    for message_media in message.media:
                        media = await media_dao.find_by_id(message_media.id)
                        if media is None:
                            media = await media_dao.create(
                                id=message_media.id,
                                mime_type=message_media.mime_type,
                                size_bytes=message_media.size_bytes,
                                file_name=message_media.file_name,
                            )
                        media_list.append(media)

                    channel_message = await channel_message_dao.find_with_loaded_media(
                        message.id
                    )
                    if channel_message is None:
                        _logger.info("message_not_found")
                        channel_message = await channel_message_dao.create(
                            id=message.id,
                            created_at=datetime.fromtimestamp(
                                message.created_at, timezone.utc
                            ),
                            text=message.html_text,
                            channel_id=channel_id,
                        )
                        await channel_message.awaitable_attrs.media_links

                    existing_media_ids = {
                        existing_media.id for existing_media in channel_message.media
                    }
                    for media in media_list:
                        if media.id not in existing_media_ids:
                            channel_message.media.append(media)

                    await channel_message_dao.save(channel_message)
                    await dao_factory.commit()

    async def _process_channel(
        self, channel_dto: ChannelDTO, semaphore: asyncio.Semaphore
    ) -> None:
        with _tracer.start_as_current_span("parse_channel") as span:
            span.set_attribute("channel.id", channel_dto.id)
            _logger.info("channel_row", channel=channel_dto.model_dump_json())
            async with semaphore:
                await self._update_channel(channel_dto)
                await self._update_messages(channel_dto.id)

    @override
    async def __call__(self) -> None:
        with _tracer.start_as_current_span("parsing_task") as span:
            _logger.info("getting_channels_info")
            channels = await self.api_client(GetAllChannels())
            span.set_attribute("channels_count", len(channels.root))
            _logger.info("got_channels_info", channels_count=len(channels.root))

            channel_semaphore = asyncio.Semaphore(10)
            _logger.info("parsing_channels")
            tasks = [
                self._process_channel(channel, channel_semaphore)
                for channel in channels.root
            ]
            await asyncio.gather(*tasks)
            _logger.info("parsed_channels")
