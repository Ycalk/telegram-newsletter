from typing import Annotated, ClassVar, override
from uuid import UUID

from newsletter.dto import MediaWithURL

from ._base import BaseMethod, ParamLocation


class GetMedia(BaseMethod[MediaWithURL]):
    media_id: Annotated[UUID, ParamLocation.QUERY]

    endpoint: ClassVar[str] = "/api/public/media"
    method: ClassVar[str] = "GET"
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @override
    def load_response(self, json_data: str | bytes | bytearray) -> MediaWithURL:
        return MediaWithURL.model_validate_json(json_data)
