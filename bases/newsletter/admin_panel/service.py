import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Protocol, override
from uuid import UUID

import structlog
from newsletter.api_client import IAPIClient
from newsletter.database import (
    ChannelDAO,
    ChannelMessageDAO,
    LetterDAO,
    MultipleDAOFactory,
    NewsletterSubscriptionDAO,
)
from newsletter.dto import Channel as ChannelDTO
from newsletter.dto import ChannelMessage as ChannelMessageDTO
from newsletter.dto import Media as MediaDTO
from newsletter.email_sender import IEmailSender
from opentelemetry import trace
from pydantic import BaseModel


class AdminChannelDTO(BaseModel):
    id: int
    name: str
    logo_url: str | None
    subscriptions_count: int


class AdminSubscriberDTO(BaseModel):
    id: str
    email: str
    telegram_id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    unsubscribed_at: int | None = None
    created_at: int


class IAdminPanelService(Protocol):
    async def get_channels(self) -> Sequence[AdminChannelDTO]: ...

    async def get_channel(self, channel_id: int) -> AdminChannelDTO: ...

    async def get_email_html_preview(self, channel_id: int, hours_ago: int) -> str: ...

    async def get_channel_subscribers(
        self, channel_id: int
    ) -> Sequence[AdminSubscriberDTO]: ...

    async def send_newsletter(self, channel_id: int, hours_ago: int) -> None: ...


class AdminPanelService(IAdminPanelService):
    def __init__(
        self,
        email_sender: IEmailSender,
        multiple_dao_factory: MultipleDAOFactory,
        api_client: IAPIClient,
    ) -> None:
        self.email_sender: IEmailSender = email_sender
        self.multiple_dao_factory: MultipleDAOFactory = multiple_dao_factory
        self.api_client: IAPIClient = api_client

        self.logger: structlog.BoundLogger = structlog.get_logger("admin_panel.service")
        self.tracer: trace.Tracer = trace.get_tracer("admin_panel.service")

    @override
    async def get_channels(self) -> list[AdminChannelDTO]:
        with self.tracer.start_as_current_span("get_channels") as span:
            async with self.multiple_dao_factory() as dao_factory:
                channel_dao = dao_factory(ChannelDAO)

                channels = await channel_dao.list_with_loaded_subscriptions_and_logo()

                result = [
                    AdminChannelDTO(
                        id=channel.id,
                        name=channel.name,
                        logo_url=self.api_client.get_media_url(channel.logo.file_name)
                        if channel.logo
                        else None,
                        subscriptions_count=len(
                            [
                                sub
                                for sub in channel.subscriptions
                                if sub.unsubscribed_at is None
                            ]
                        ),
                    )
                    for channel in channels
                ]
                span.set_attribute("channels.count", len(result))
                result.sort(key=lambda x: x.subscriptions_count, reverse=True)
                return result

    @override
    async def get_channel(self, channel_id: int) -> AdminChannelDTO:
        with self.tracer.start_as_current_span("get_channel") as span:
            async with self.multiple_dao_factory() as dao_factory:
                channel_dao = dao_factory(ChannelDAO)
                channel = (
                    await channel_dao.find_by_id_with_loaded_subscriptions_and_logo(
                        channel_id
                    )
                )
                if channel is None:
                    raise ValueError(f"Channel with id {channel_id} not found")
                span.set_attribute("channel_id", channel_id)
                logo_url = (
                    self.api_client.get_media_url(channel.logo.file_name)
                    if channel.logo is not None
                    else None
                )

                return AdminChannelDTO(
                    id=channel.id,
                    name=channel.name,
                    logo_url=logo_url,
                    subscriptions_count=len(
                        [
                            sub
                            for sub in channel.subscriptions
                            if sub.unsubscribed_at is None
                        ]
                    ),
                )

    @override
    async def get_email_html_preview(self, channel_id: int, hours_ago: int) -> str:
        with self.tracer.start_as_current_span("get_email_html_preview") as span:
            async with self.multiple_dao_factory() as dao_factory:
                channel_dao = dao_factory(ChannelDAO)
                channel = await channel_dao.find_by_id_with_loaded_logo(channel_id)
                if channel is None:
                    raise ValueError(f"Channel with id {channel_id} not found")
                span.set_attribute("channel_id", channel_id)

                channel_dto = ChannelDTO(
                    id=channel.id,
                    name=channel.name,
                    description=channel.description,
                    logo=MediaDTO(
                        id=channel.logo.id,
                        mime_type=channel.logo.mime_type,
                        size_bytes=channel.logo.size_bytes,
                        file_name=channel.logo.file_name,
                    )
                    if channel.logo is not None
                    else None,
                )

                now = datetime.now(timezone.utc)
                from_date = now - timedelta(hours=hours_ago)

                channel_message_dao = dao_factory(ChannelMessageDAO)
                messages = await channel_message_dao.list_by_channel_id_and_created_at(
                    channel_id=channel_id,
                    created_at_start=from_date,
                    created_at_end=now,
                )

                messages_dto = [
                    ChannelMessageDTO(
                        id=message.id,
                        text=message.text,
                        html_text=message.text,
                        created_at=int(message.created_at.timestamp()),
                        media=[
                            MediaDTO(
                                id=media.id,
                                mime_type=media.mime_type,
                                size_bytes=media.size_bytes,
                                file_name=media.file_name,
                            )
                            for media in message.media
                        ],
                    )
                    for message in messages
                ]

                return self.email_sender.generate_html_content(
                    channel_dto, messages_dto, None, None
                )

    @override
    async def get_channel_subscribers(
        self, channel_id: int
    ) -> list[AdminSubscriberDTO]:
        with self.tracer.start_as_current_span("get_channel_subscribers") as span:
            async with self.multiple_dao_factory() as dao_factory:
                subscription_dao = dao_factory(NewsletterSubscriptionDAO)
                span.set_attribute("channel_id", channel_id)
                subscriptions = (
                    await subscription_dao.find_by_channel_id_with_loaded_user(
                        channel_id, skip_unsubscribe=False
                    )
                )
                return [
                    AdminSubscriberDTO(
                        id=str(subscription.user.id),
                        email=subscription.user.email,
                        telegram_id=subscription.user.telegram_user.telegram_id
                        if subscription.user.telegram_user
                        else None,
                        first_name=subscription.user.telegram_user.first_name
                        if subscription.user.telegram_user
                        else None,
                        last_name=subscription.user.telegram_user.last_name
                        if subscription.user.telegram_user
                        else None,
                        username=subscription.user.telegram_user.username
                        if subscription.user.telegram_user
                        else None,
                        unsubscribed_at=int(subscription.unsubscribed_at.timestamp())
                        if subscription.unsubscribed_at
                        else None,
                        created_at=int(subscription.created_at.timestamp()),
                    )
                    for subscription in subscriptions
                ]

    async def send_letter(
        self,
        email: str,
        subscription_id: UUID,
        channel: ChannelDTO,
        messages: list[ChannelMessageDTO],
    ) -> None:
        with self.tracer.start_as_current_span("send_letter") as span:
            span.set_attribute("email", email)
            span.set_attribute("channel.id", channel.id)
            span.set_attribute("messages.count", len(messages))
            async with self.multiple_dao_factory() as dao_factory:
                letter_dao = dao_factory(LetterDAO)
                letter = await letter_dao.create(subscription_id)
                html_content = self.email_sender.generate_html_content(
                    channel, messages, letter.id, subscription_id
                )
                await self.email_sender(
                    to_emails=[email],
                    subject=channel.name,
                    html_content=html_content,
                    subscription_id=subscription_id,
                )
                await dao_factory.commit()

    @override
    async def send_newsletter(self, channel_id: int, hours_ago: int) -> None:
        with self.tracer.start_as_current_span("send_newsletter") as span:
            span.set_attribute("channel_id", channel_id)
            span.set_attribute("hours_ago", hours_ago)
            request_logger = self.logger.bind(
                channel_id=channel_id, hours_ago=hours_ago
            )

            request_logger.info("getting_newsletter_messages")
            now = datetime.now(timezone.utc)
            from_date = now - timedelta(hours=hours_ago)
            async with self.multiple_dao_factory() as dao_factory:
                channel_message_dao = dao_factory(ChannelMessageDAO)
                subscription_dao = dao_factory(NewsletterSubscriptionDAO)
                channel_dao = dao_factory(ChannelDAO)

                channel = await channel_dao.find_by_id_with_loaded_logo(channel_id)
                if channel is None:
                    raise ValueError(f"Channel with id {channel_id} not found")

                messages = await channel_message_dao.list_by_channel_id_and_created_at(
                    channel_id=channel_id,
                    created_at_start=from_date,
                    created_at_end=now,
                )
                if len(messages) == 0:
                    request_logger.info("no_messages")
                    return
                subscriptions = (
                    await subscription_dao.find_by_channel_id_with_loaded_user(
                        channel_id
                    )
                )

                request_logger = request_logger.bind(
                    messages_count=len(messages),
                    subscribers_count=len(subscriptions),
                )

                channel_dto = ChannelDTO(
                    id=channel.id,
                    name=channel.name,
                    description=channel.description,
                    logo=MediaDTO(
                        id=channel.logo.id,
                        mime_type=channel.logo.mime_type,
                        size_bytes=channel.logo.size_bytes,
                        file_name=channel.logo.file_name,
                    )
                    if channel.logo is not None
                    else None,
                )
                messages_dto = [
                    ChannelMessageDTO(
                        id=message.id,
                        text=message.text,
                        html_text=message.text,
                        created_at=int(message.created_at.timestamp()),
                        media=[
                            MediaDTO(
                                id=media.id,
                                mime_type=media.mime_type,
                                size_bytes=media.size_bytes,
                                file_name=media.file_name,
                            )
                            for media in message.media
                        ],
                    )
                    for message in messages
                ]
                semaphore = asyncio.Semaphore(10)

                async def safe_send_letter(
                    subscriber_email: str, subscription_id: UUID
                ):
                    async with semaphore:
                        try:
                            await self.send_letter(
                                subscriber_email,
                                subscription_id,
                                channel_dto,
                                messages_dto,
                            )
                        except Exception as e:
                            self.logger.error(
                                "failed_to_send_letter",
                                email=subscriber_email,
                                error=str(e),
                                exc_info=True,
                            )

                tasks = [
                    safe_send_letter(
                        subscription.user.email,
                        subscription.id,
                    )
                    for subscription in subscriptions
                ]
            if len(tasks) != 0:
                await asyncio.gather(*tasks)
