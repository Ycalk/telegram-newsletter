import asyncio

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Response
from newsletter.api_client import IAPIClient

from .settings import MediaProxySettings
from .utils import MediaProxyUtils

router = APIRouter(
    prefix="",
    tags=["media_proxy"],
    route_class=DishkaRoute,
)


@router.get("/media/previews/{file_path:path}")
async def get_preview(
    file_path: str,
    api_client: FromDishka[IAPIClient],
    utils: FromDishka[MediaProxyUtils],
    settings: FromDishka[MediaProxySettings],
):
    media_url = api_client.get_media_url(file_path, preview=False)
    ext = file_path.split(".")[-1].lower()
    cache_headers = {"Cache-Control": f"public, max-age={settings.cache_ttl_seconds}"}

    if ext == "mp4":
        try:
            frame_bytes = await utils.extract_first_frame(media_url)

            final_image = await asyncio.to_thread(utils.add_play_overlay, frame_bytes)

            return Response(
                content=final_image, media_type="image/jpeg", headers=cache_headers
            )
        except Exception:
            doc_bytes = await asyncio.to_thread(utils.generate_dynamic_doc_placeholder)
            return Response(
                content=doc_bytes, media_type="image/jpeg", headers=cache_headers
            )

    else:
        doc_bytes = await asyncio.to_thread(utils.generate_dynamic_doc_placeholder)
        return Response(
            content=doc_bytes, media_type="image/jpeg", headers=cache_headers
        )
