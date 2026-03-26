from collections.abc import Sequence
from typing import Protocol, override

import structlog
from newsletter.api_client import GetAllChannels, GetChannel, IAPIClient
from newsletter.database import NewsletterSubscriptionDAO
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
    ) -> None:
        self.api_client: IAPIClient = api_client
        self.email_sender: IEmailSender = email_sender
        self.subscription_dao: NewsletterSubscriptionDAO = subscription_dao
        self.logger: structlog.BoundLogger = structlog.get_logger("admin_panel_service")
        self.tracer: trace.Tracer = trace.get_tracer("admin_panel_service")

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

    @override
    async def send_newsletter(self, channel_id: int, hours_ago: int) -> None:
        with self.tracer.start_as_current_span("send_newsletter") as span:
            span.set_attribute("channel_id", channel_id)
            span.set_attribute("hours_ago", hours_ago)
            html = await self.email_sender.generate_html_content(channel_id, hours_ago)
            subscribers = (
                await self.subscription_dao.find_by_channel_id_with_loaded_user(
                    channel_id
                )
            )
            channel = await self.api_client(GetChannel(channel_id=channel_id))
            await self.email_sender(
                to_emails=[sub.user.email for sub in subscribers],
                subject=channel.name,
                html_content=html,
            )
