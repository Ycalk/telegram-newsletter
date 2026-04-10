from typing import Annotated, ClassVar, Literal, override
from uuid import UUID

from newsletter.dto import ChannelMessage

from ._base import BaseMethod, ParamLocation


class GetMessage(BaseMethod[ChannelMessage]):
    message_id: Annotated[UUID, ParamLocation.QUERY]
    with_html_text: Annotated[Literal[True], ParamLocation.QUERY] = True

    endpoint: ClassVar[str] = "/api/public/message"
    method: ClassVar[str] = "GET"
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @override
    def load_response(self, json_data: str | bytes | bytearray) -> ChannelMessage:
        return ChannelMessage.model_validate_json(json_data)
