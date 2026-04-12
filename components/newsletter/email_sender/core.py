import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import NewType, Protocol, override
from uuid import UUID
from zoneinfo import ZoneInfo

import resend
from dishka import Provider, Scope, provide
from jinja2 import Environment, FileSystemLoader
from newsletter.api_client import IAPIClient
from newsletter.dto import Channel, ChannelMessage
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .settings import EmailSenderSettings

_EmailSenderEnv = NewType("_EmailSenderEnv", Environment)


class IEmailSender(Protocol):
    async def __call__(
        self, to_emails: list[str], subject: str, html_content: str
    ) -> None: ...

    def generate_html_content(
        self, channel: Channel, messages: list[ChannelMessage], letter_id: UUID | None
    ) -> str: ...


class EmailSender(IEmailSender):
    def __init__(
        self,
        send_from_email: str,
        env: _EmailSenderEnv,
        api_client: IAPIClient,
        track_url: str,
        sendgrid_client: SendGridAPIClient | None,
    ) -> None:
        self.send_from_email: str = send_from_email
        self.env: Environment = env
        self.api_client: IAPIClient = api_client
        self.track_url: str = track_url
        self.sendgrid_client: SendGridAPIClient | None = sendgrid_client

    @override
    async def __call__(
        self, to_emails: list[str], subject: str, html_content: str
    ) -> None:
        if self.sendgrid_client is None:
            message: resend.Emails.SendParams = {
                "from": self.send_from_email,
                "to": to_emails,
                "subject": subject,
                "html": html_content,
            }
            await asyncio.to_thread(resend.Emails.send, message)
        else:
            mail = Mail(
                from_email=self.send_from_email,
                to_emails=to_emails,
                subject=subject,
                html_content=html_content,
            )
            await asyncio.to_thread(self.sendgrid_client.send, mail)

    def _format_ru_date(self, dt: datetime) -> str:
        msk_tz = ZoneInfo("Europe/Moscow")
        ru_months = {
            1: "Янв",
            2: "Фев",
            3: "Мар",
            4: "Апр",
            5: "Мая",
            6: "Июн",
            7: "Июл",
            8: "Авг",
            9: "Сен",
            10: "Окт",
            11: "Ноя",
            12: "Дек",
        }
        msk_dt = dt.astimezone(msk_tz)
        month_str = ru_months[msk_dt.month]
        return f"{msk_dt.day} {month_str} {msk_dt.strftime('%H:%M')} (МСК)"

    @override
    def generate_html_content(
        self, channel: Channel, messages: list[ChannelMessage], letter_id: UUID | None
    ) -> str:
        template = self.env.get_template("newsletter-new-color.html")
        return template.render(
            channel_name=channel.name,
            channel_avatar=self.api_client.get_media_url(channel.logo.file_name)
            if channel.logo
            else None,
            tracking_url=f"{self.track_url}/{letter_id}" if letter_id else None,
            messages=[
                {
                    "text": re.sub(
                        r"<tg-emoji[^>]*>(.*?)</tg-emoji>", r"\1", msg.html_text
                    ).replace("\n", "<br>"),
                    "media": [
                        {
                            "url": self.api_client.get_media_url(media.file_name),
                            "preview": self.api_client.get_media_url(
                                media.file_name, preview=True
                            )
                            if not media.mime_type.startswith("image")
                            else None,
                        }
                        for media in msg.media
                    ]
                    if msg.media
                    else None,
                    "created_at": self._format_ru_date(
                        datetime.fromtimestamp(msg.created_at, tz=timezone.utc)
                    ),
                }
                for msg in messages
            ],
        )


class EmailSenderProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> EmailSenderSettings:
        return EmailSenderSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def jinja_env(self) -> _EmailSenderEnv:
        current_dir = Path(__file__).resolve().parent
        templates_dir = current_dir / "templates"
        if not templates_dir.exists():
            raise RuntimeError(f"Templates directory not found: {templates_dir}")
        return _EmailSenderEnv(Environment(loader=FileSystemLoader(templates_dir)))

    @provide(scope=Scope.REQUEST)
    def email_sender(
        self,
        settings: EmailSenderSettings,
        env: _EmailSenderEnv,
        api_client: IAPIClient,
    ) -> IEmailSender:
        sendgrid_client: SendGridAPIClient | None = None
        if settings.resend_api_key is not None:
            resend.api_key = settings.resend_api_key
        else:
            sendgrid_client = SendGridAPIClient(settings.sendgrid_api_key)
        return EmailSender(
            settings.send_from_email,
            env,
            api_client,
            settings.track_url,
            sendgrid_client,
        )
