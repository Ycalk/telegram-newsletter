from typing import Annotated, ClassVar, override

from newsletter.dto import ParsingTask

from ._base import BaseMethod, ParamLocation


class AddChannel(BaseMethod[ParsingTask]):
    channel_url: Annotated[str, ParamLocation.BODY]

    endpoint: ClassVar[str] = "/api/v2/parser/schedule"
    method: ClassVar[str] = "POST"
    status_code: ClassVar[int] = 201
    need_auth: ClassVar[bool] = True

    @override
    def load_response(self, json_data: str | bytes | bytearray) -> ParsingTask:
        return ParsingTask.model_validate_json(json_data)
