from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel


class ParamLocation(StrEnum):
    QUERY = "query"
    BODY = "body"


class BaseMethod[MethodResponseT: BaseModel](BaseModel, ABC):  # pyright: ignore[reportUnsafeMultipleInheritance]
    endpoint: ClassVar[str]
    method: ClassVar[str]
    status_code: ClassVar[int] = 200
    need_auth: ClassVar[bool] = False

    @abstractmethod
    def load_response(self, json_data: str | bytes | bytearray) -> MethodResponseT: ...

    def extract_by_location(self, target_location: ParamLocation) -> dict[str, Any]:
        result = {}
        dumped_data = self.model_dump()

        for field_name, field_info in self.__class__.model_fields.items():
            location = ParamLocation.BODY

            for meta in field_info.metadata:
                if isinstance(meta, ParamLocation):
                    location = meta
                    break

            if location == target_location and field_name in dumped_data:
                result[field_name] = dumped_data[field_name]

        return result
