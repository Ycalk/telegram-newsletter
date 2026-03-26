from typing import Annotated, ClassVar, Literal, override

from newsletter.dto import ChannelMessage
from pydantic import RootModel

from ._base import BaseMethod, ParamLocation


class GetChannelMessages(BaseMethod[RootModel[list[ChannelMessage]]]):
    channel_id: Annotated[int, ParamLocation.QUERY]
    sorting: Annotated[Literal["newest", "oldest"], ParamLocation.QUERY] = "newest"
    skip: Annotated[int, ParamLocation.QUERY] = 0
    limit: Annotated[int | None, ParamLocation.QUERY] = 1000
    created_at_start: Annotated[int | None, ParamLocation.QUERY] = None
    created_at_end: Annotated[int | None, ParamLocation.QUERY] = None

    endpoint: ClassVar[str] = "/api/public/channel/messages"
    method: ClassVar[str] = "GET"
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @override
    def load_response(
        self, json_data: str | bytes | bytearray
    ) -> RootModel[list[ChannelMessage]]:
        return RootModel[list[ChannelMessage]].model_validate_json(json_data)
