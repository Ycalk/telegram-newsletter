from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from newsletter.database import NewsletterSubscriptionDAO

router = APIRouter(
    prefix="",
    tags=["unsubscribe_handler"],
    route_class=DishkaRoute,
)


@router.get("/unsubscribe/{subscription_id}")
async def unsubscribe(
    subscription_id: UUID,
    request: Request,
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
    templates: FromDishka[Jinja2Templates],
):
    subscription = await newsletter_subscription_dao.find_by_id(subscription_id)
    if subscription is None:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            status_code=404,
        )
    return templates.TemplateResponse(
        request=request,
        name="unsubscribe.html",
    )


@router.post("/unsubscribe/{subscription_id}")
async def unsubscribe_confirm(
    subscription_id: UUID,
    request: Request,
    newsletter_subscription_dao: FromDishka[NewsletterSubscriptionDAO],
    templates: FromDishka[Jinja2Templates],
):
    subscription = await newsletter_subscription_dao.find_by_id(subscription_id)
    if subscription is not None:
        await newsletter_subscription_dao.delete(subscription_id)
        await newsletter_subscription_dao.commit()
        return templates.TemplateResponse(
            request=request,
            name="confirm.html",
        )
    return templates.TemplateResponse(
        request=request,
        name="404.html",
        status_code=404,
    )
