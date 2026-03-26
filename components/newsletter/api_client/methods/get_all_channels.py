from typing import ClassVar, override

from newsletter.dto import Channel
from pydantic import RootModel

from ._base import BaseMethod


class GetAllChannels(BaseMethod[RootModel[list[Channel]]]):
    endpoint: ClassVar[str] = "/api/public/channel/all"
    method: ClassVar[str] = "GET"
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @override
    def load_response(
        self, json_data: str | bytes | bytearray
    ) -> RootModel[list[Channel]]:
        return RootModel[list[Channel]].model_validate_json(json_data)
