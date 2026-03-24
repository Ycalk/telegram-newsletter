from typing import Annotated, ClassVar, Literal, override

from newsletter.dto import ChannelStatistic
from pydantic import RootModel

from ._base import BaseMethod, ParamLocation


class GetChannelStatistics(BaseMethod[RootModel[list[ChannelStatistic]]]):
    channel_id: Annotated[int, ParamLocation.QUERY]
    sorting: Annotated[Literal["newest", "oldest"], ParamLocation.QUERY]
    skip: Annotated[int, ParamLocation.QUERY] = 0
    limit: Annotated[int | None, ParamLocation.QUERY] = None

    endpoint: ClassVar[str] = "/api/public/channel/statistics"
    method: ClassVar[str] = "GET"
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @override
    def load_response(
        self, json_data: str | bytes | bytearray
    ) -> RootModel[list[ChannelStatistic]]:
        return RootModel[list[ChannelStatistic]].model_validate_json(json_data)
