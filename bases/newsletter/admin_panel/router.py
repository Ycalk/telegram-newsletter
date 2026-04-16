from typing import Annotated

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from newsletter.channel_id_encryption import IChannelIdEncryption
from newsletter.database import LetterDAO

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
    letter_dao: FromDishka[LetterDAO],
    channel_id: int,
) -> Response:
    channel = await service.get_channel(channel_id)
    subscribers = await service.get_channel_subscribers(channel_id)
    daily_stats = await letter_dao.get_daily_letter_stats_by_channel(channel_id)

    encrypted_id = encryption.encrypt(channel_id)
    invite_link = f"https://t.me/{settings.bot_username}?start={encrypted_id}"

    return templates.TemplateResponse(
        request=request,
        name="partials/channel_details.html",
        context={
            "channel": channel,
            "subscribers": subscribers,
            "invite_link": invite_link,
            "daily_stats": daily_stats,
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
    service: FromDishka[IAdminPanelService],
    channel_id: int,
    hours_ago: Annotated[int, Form()],
) -> HTMLResponse:
    email_html = await service.get_email_html_preview(channel_id, hours_ago)
    return templates.TemplateResponse(
        request=request,
        name="partials/preview_wrapper.html",
        context={"email_html": email_html},
    )
