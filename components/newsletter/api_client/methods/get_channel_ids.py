from typing import ClassVar, override

from pydantic import RootModel

from ._base import BaseMethod


class GetChannelIds(BaseMethod[RootModel[list[int]]]):
    endpoint: ClassVar[str] = "/api/public/channel/ids"
    method: ClassVar[str] = "GET"
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @override
    def load_response(self, json_data: str | bytes | bytearray) -> RootModel[list[int]]:
        return RootModel[list[int]].model_validate_json(json_data)
