import asyncio
from datetime import datetime, timedelta, timezone
from typing import ClassVar, Final, override
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

from .base import BaseTask

_tracer: Final[trace.Tracer] = trace.get_tracer(__name__)
_logger: Final[structlog.BoundLogger] = structlog.get_logger()


class NewsletterTask(BaseTask):
    interval: ClassVar[timedelta] = timedelta(minutes=20)

    def __init__(
        self,
        api_client: IAPIClient,
        multiple_dao_factory: MultipleDAOFactory,
        email_sender: IEmailSender,
    ):
        self.api_client: IAPIClient = api_client
        self.multiple_dao_factory: MultipleDAOFactory = multiple_dao_factory
        self.email_sender: IEmailSender = email_sender

    async def _process_subscription(
        self, subscription_id: UUID, semaphore: asyncio.Semaphore
    ) -> None:
        with _tracer.start_as_current_span("process_subscription") as span:
            span.set_attribute("subscription_id", str(subscription_id))
            async with semaphore:
                async with self.multiple_dao_factory() as dao_factory:
                    newsletter_subscription_dao = dao_factory(NewsletterSubscriptionDAO)
                    letter_dao = dao_factory(LetterDAO)
                    channel_dao = dao_factory(ChannelDAO)
                    channel_message_dao = dao_factory(ChannelMessageDAO)

                    newsletter_subscription = (
                        await newsletter_subscription_dao.find_by_id_with_loaded_user(
                            subscription_id
                        )
                    )
                    if newsletter_subscription is None:
                        _logger.error("subscription_not_found")
                        return
                    span.set_attribute("user_id", str(newsletter_subscription.user_id))
                    span.set_attribute(
                        "channel_id", str(newsletter_subscription.channel_id)
                    )

                    newest_letter = (
                        await letter_dao.find_newest_letter_by_subscription_id(
                            subscription_id
                        )
                    )
                    now = datetime.now(timezone.utc)
                    if (
                        newest_letter is not None
                        and newest_letter.created_at.date() == now.date()
                    ):
                        _logger.info("letter_already_sent_today")
                        return

                    _logger.info("generating_and_sending_newsletter")
                    channel = await channel_dao.find_by_id_with_loaded_logo(
                        newsletter_subscription.channel_id
                    )
                    if channel is None:
                        _logger.error("channel_not_found")
                        return

                    messages = (
                        await channel_message_dao.list_by_channel_id_and_created_at(
                            channel.id,
                            now - timedelta(hours=24),
                            now,
                        )
                    )
                    if len(messages) == 0:
                        _logger.info("no_messages")
                        return
                    _logger.info("messages_found", count=len(messages))

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
                    letter_dao = dao_factory(LetterDAO)
                    letter = await letter_dao.create(subscription_id)
                    span.set_attribute("letter_id", str(letter.id))
                    _logger.info("letter_created", letter_id=str(letter.id))
                    html_content = self.email_sender.generate_html_content(
                        channel_dto, messages_dto, letter.id, subscription_id
                    )
                    await self.email_sender(
                        to_emails=[newsletter_subscription.user.email],
                        subject=channel.name,
                        html_content=html_content,
                        subscription_id=subscription_id,
                    )
                    await dao_factory.commit()
                    _logger.info(
                        "newsletter_sent", subscription_id=str(subscription_id)
                    )

    @override
    async def __call__(self) -> None:
        with _tracer.start_as_current_span("newsletter_task") as span:
            async with self.multiple_dao_factory() as dao_factory:
                newsletter_subscription_dao = dao_factory(NewsletterSubscriptionDAO)
                now = datetime.now(timezone.utc)
                moscow_hour = (now.hour + 3) % 24
                span.set_attribute("moscow_hour", moscow_hour)

                _logger.info("getting_subscriptions", moscow_hour=moscow_hour)
                subscriptions = await newsletter_subscription_dao.list_by_send_at(
                    moscow_hour
                )
                span.set_attribute("subscriptions_count", len(subscriptions))

                semaphore = asyncio.Semaphore(10)
                tasks = [
                    self._process_subscription(subscription.id, semaphore)
                    for subscription in subscriptions
                ]

            _logger.info("starting_tasks", tasks_count=len(tasks))
            await asyncio.gather(*tasks)
            _logger.info("tasks_completed")
