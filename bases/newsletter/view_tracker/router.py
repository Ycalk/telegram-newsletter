from datetime import datetime, timezone
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Response
from newsletter.database import LetterDAO

from .settings import ViewTrackerSettings

router = APIRouter(
    prefix="",
    tags=["view_tracker"],
    route_class=DishkaRoute,
)


@router.get("/track/{letter_id}")
async def get_preview(
    letter_id: UUID,
    letter_dao: FromDishka[LetterDAO],
    settings: FromDishka[ViewTrackerSettings],
):
    letter = await letter_dao.find_by_id(letter_id)
    if letter is not None and letter.viewed_at is None:
        letter.viewed_at = datetime.now(timezone.utc)
        await letter_dao.save(letter)
        await letter_dao.commit()

    return Response(
        content=settings.tracking_pixel,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
