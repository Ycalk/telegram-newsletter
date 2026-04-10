import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Protocol, override
from uuid import UUID

import structlog
from newsletter.api_client import (
    GetAllChannels,
    GetChannel,
    GetChannelMessages,
    IAPIClient,
)
from newsletter.database import (
    LetterDAO,
    MultipleDAOFactory,
    NewsletterDAO,
    NewsletterElementDAO,
    NewsletterSubscriptionDAO,
)
from newsletter.dto import Channel as ChannelDTO
from newsletter.dto import ChannelMessage as ChannelMessageDTO
from newsletter.email_sender import IEmailSender
from opentelemetry import trace
from pydantic import BaseModel


class AdminChannelDTO(BaseModel):
    id: int
    name: str
    logo_url: str | None
    subscribers_count: int
    channel_subscribers_count: int
    statistic_recorded_at: int


class AdminSubscriberDTO(BaseModel):
    id: str
    email: str
    telegram_id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    created_at: int


class IAdminPanelService(Protocol):
    async def get_channels(self) -> Sequence[AdminChannelDTO]: ...

    async def get_channel(self, channel_id: int) -> AdminChannelDTO: ...

    async def get_channel_subscribers(
        self, channel_id: int
    ) -> Sequence[AdminSubscriberDTO]: ...

    async def send_newsletter(self, channel_id: int, hours_ago: int) -> None: ...


class AdminPanelService(IAdminPanelService):
    def __init__(
        self,
        api_client: IAPIClient,
        subscription_dao: NewsletterSubscriptionDAO,
        email_sender: IEmailSender,
        multiple_dao_factory: MultipleDAOFactory,
        newsletter_dao: NewsletterDAO,
        newsletter_element_dao: NewsletterElementDAO,
    ) -> None:
        self.api_client: IAPIClient = api_client
        self.email_sender: IEmailSender = email_sender
        self.subscription_dao: NewsletterSubscriptionDAO = subscription_dao
        self.multiple_dao_factory: MultipleDAOFactory = multiple_dao_factory
        self.newsletter_dao: NewsletterDAO = newsletter_dao
        self.newsletter_element_dao: NewsletterElementDAO = newsletter_element_dao

        self.logger: structlog.BoundLogger = structlog.get_logger("admin_panel.service")
        self.tracer: trace.Tracer = trace.get_tracer("admin_panel.service")

    @override
    async def get_channels(self) -> list[AdminChannelDTO]:
        with self.tracer.start_as_current_span("get_channels") as span:
            channels_response = await self.api_client(GetAllChannels())

            subscribers_counts = (
                await self.subscription_dao.count_for_multiple_channels(
                    [channel.id for channel in channels_response.root]
                )
            )

            result = [
                AdminChannelDTO(
                    id=channel.id,
                    name=channel.name,
                    logo_url=self.api_client.get_media_url(channel.logo.file_name)
                    if channel.logo
                    else None,
                    subscribers_count=subscribers_counts.get(channel.id, 0),
                    channel_subscribers_count=channel.newest_statistic.subscribers_count,
                    statistic_recorded_at=channel.newest_statistic.recorded_at,
                )
                for channel in channels_response.root
            ]
            span.set_attribute("channels.count", len(result))
            result.sort(
                key=lambda x: (x.subscribers_count, x.statistic_recorded_at),
                reverse=True,
            )
            return result

    @override
    async def get_channel(self, channel_id: int) -> AdminChannelDTO:
        with self.tracer.start_as_current_span("get_channel") as span:
            channel = await self.api_client(GetChannel(channel_id=channel_id))
            span.set_attribute("channel_id", channel_id)
            logo_url = (
                self.api_client.get_media_url(channel.logo.file_name)
                if channel.logo is not None
                else None
            )

            subscribers_count = await self.subscription_dao.count_by_channel_id(
                channel_id
            )
            return AdminChannelDTO(
                id=channel.id,
                name=channel.name,
                logo_url=logo_url,
                subscribers_count=subscribers_count,
                channel_subscribers_count=channel.newest_statistic.subscribers_count,
                statistic_recorded_at=channel.newest_statistic.recorded_at,
            )

    @override
    async def get_channel_subscribers(
        self, channel_id: int
    ) -> list[AdminSubscriberDTO]:
        with self.tracer.start_as_current_span("get_channel_subscribers") as span:
            span.set_attribute("channel_id", channel_id)
            subscriptions = (
                await self.subscription_dao.find_by_channel_id_with_loaded_user(
                    channel_id
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
                    created_at=int(subscription.created_at.timestamp()),
                )
                for subscription in subscriptions
            ]

    async def send_letter(
        self,
        email: str,
        newsletter_id: UUID,
        user_id: UUID,
        channel: ChannelDTO,
        messages: list[ChannelMessageDTO],
    ) -> None:
        with self.tracer.start_as_current_span("send_letter") as span:
            span.set_attribute("email", email)
            span.set_attribute("channel.id", channel.id)
            span.set_attribute("messages.count", len(messages))
            async with self.multiple_dao_factory() as dao_factory:
                letter_dao = dao_factory(LetterDAO)
                letter = await letter_dao.create(
                    newsletter_id,
                    user_id,
                )
                html_content = self.email_sender.generate_html_content(
                    channel,
                    messages,
                    letter.id,
                )
                await self.email_sender(
                    to_emails=[email],
                    subject=channel.name,
                    html_content=html_content,
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
            channel = await self.api_client(GetChannel(channel_id=channel_id))
            now = datetime.now(timezone.utc)
            from_date = now - timedelta(hours=hours_ago)
            messages = await self.api_client(
                GetChannelMessages(
                    channel_id=channel_id,
                    created_at_start=int(from_date.timestamp()),
                    created_at_end=int(now.timestamp()),
                )
            )
            if len(messages.root) == 0:
                request_logger.info("no_messages")
                return

            request_logger = request_logger.bind(messages_count=len(messages.root))

            request_logger.info("creating_newsletter")
            newsletter = await self.newsletter_dao.create(
                channel_id=channel_id,
                messages_from=from_date,
                messages_to=now,
            )
            request_logger = request_logger.bind(newsletter_id=str(newsletter.id))
            for message in messages.root:
                await self.newsletter_element_dao.create(
                    newsletter_id=newsletter.id,
                    message_id=message.id,
                )
            request_logger.info("sending_letters")
            subscribers = (
                await self.subscription_dao.find_by_channel_id_with_loaded_user(
                    channel_id
                )
            )
            span.set_attribute("subscribers.count", len(subscribers))
            await self.newsletter_dao.commit()

            semaphore = asyncio.Semaphore(10)

            async def safe_send_letter(subscriber_email: str, subscriber_id: UUID):
                async with semaphore:
                    try:
                        await self.send_letter(
                            subscriber_email,
                            newsletter.id,
                            subscriber_id,
                            channel,
                            messages.root,
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
                    subscriber.user.email,
                    subscriber.user.id,
                )
                for subscriber in subscribers
            ]
            if len(tasks) != 0:
                await asyncio.gather(*tasks)
