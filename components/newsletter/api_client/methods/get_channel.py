from typing import Annotated, ClassVar, override

from newsletter.dto import Channel

from ._base import BaseMethod, ParamLocation


class GetChannel(BaseMethod[Channel]):
    channel_id: Annotated[int, ParamLocation.QUERY]

    endpoint: ClassVar[str] = "/api/public/channel"
    method: ClassVar[str] = "GET"
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @override
    def load_response(self, json_data: str | bytes | bytearray) -> Channel:
        return Channel.model_validate_json(json_data)
