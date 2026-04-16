from datetime import timedelta
from typing import ClassVar, Protocol


class BaseTask(Protocol):
    interval: ClassVar[timedelta]

    async def __call__(self) -> None: ...
