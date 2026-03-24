import asyncio
from typing import Protocol, override

import resend
from dishka import Provider, Scope, provide

from .settings import EmailSenderSettings


class IEmailSender(Protocol):
    async def __call__(
        self, to_emails: list[str], subject: str, html_content: str
    ) -> None: ...


class EmailSender(IEmailSender):
    def __init__(self, send_from_email: str) -> None:
        self.send_from_email: str = send_from_email

    @override
    async def __call__(
        self, to_emails: list[str], subject: str, html_content: str
    ) -> None:
        message: resend.Emails.SendParams = {
            "from": self.send_from_email,
            "to": to_emails,
            "subject": subject,
            "html": html_content,
        }
        await asyncio.to_thread(resend.Emails.send, message)


class EmailSenderProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> EmailSenderSettings:
        return EmailSenderSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def email_sender(self, settings: EmailSenderSettings) -> IEmailSender:
        resend.api_key = settings.resend_api_key
        return EmailSender(settings.send_from_email)
