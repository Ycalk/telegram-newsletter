from datetime import datetime, timedelta, timezone
from typing import Annotated

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from newsletter.api_client import GetChannel, GetChannelMessages, IAPIClient
from newsletter.channel_id_encryption import IChannelIdEncryption
from newsletter.database import NewsletterDAO
from newsletter.email_sender import IEmailSender

from .service import IAdminPanelService
from .settings import AdminPanelSettings

router = APIRouter(
    prefix="",
    tags=["ui", "admin_panel"],
    route_class=DishkaRoute,
)


@router.get("/")
async def index(
    request: Request,
    templates: FromDishka[Jinja2Templates],
    service: FromDishka[IAdminPanelService],
) -> HTMLResponse:
    channels = await service.get_channels()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "channels": channels,
        },
    )


@router.get("/ui/channels/{channel_id}")
async def get_channel_details(
    request: Request,
    templates: FromDishka[Jinja2Templates],
    service: FromDishka[IAdminPanelService],
    encryption: FromDishka[IChannelIdEncryption],
    settings: FromDishka[AdminPanelSettings],
    newsletter_dao: FromDishka[NewsletterDAO],
    channel_id: int,
) -> Response:
    channel = await service.get_channel(channel_id)
    subscribers = await service.get_channel_subscribers(channel_id)
    channel_stats = await newsletter_dao.get_channel_statistics(channel_id)

    encrypted_id = encryption.encrypt(channel_id)
    invite_link = f"https://t.me/{settings.bot_username}?start={encrypted_id}"

    return templates.TemplateResponse(
        request=request,
        name="partials/channel_details.html",
        context={
            "channel": channel,
            "subscribers": subscribers,
            "invite_link": invite_link,
            "newsletters_stats": channel_stats,
        },
    )


@router.post("/ui/channels/{channel_id}/send")
async def send_newsletter(
    request: Request,
    templates: FromDishka[Jinja2Templates],
    service: FromDishka[IAdminPanelService],
    channel_id: int,
    hours_ago: Annotated[int, Form()],
) -> HTMLResponse:
    await service.send_newsletter(channel_id, hours_ago)
    return templates.TemplateResponse(
        request=request,
        name="partials/send_success.html",
    )


@router.post("/ui/channels/{channel_id}/preview")
async def preview_newsletter(
    request: Request,
    templates: FromDishka[Jinja2Templates],
    email_sender: FromDishka[IEmailSender],
    api_client: FromDishka[IAPIClient],
    channel_id: int,
    hours_ago: Annotated[int, Form()],
) -> HTMLResponse:
    channel = await api_client(GetChannel(channel_id=channel_id))
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(hours=hours_ago)
    messages = await api_client(
        GetChannelMessages(
            channel_id=channel_id,
            created_at_start=int(from_date.timestamp()),
            created_at_end=int(now.timestamp()),
        )
    )
    email_html = email_sender.generate_html_content(channel, messages.root, None)
    return templates.TemplateResponse(
        request=request,
        name="partials/preview_wrapper.html",
        context={"email_html": email_html},
    )
