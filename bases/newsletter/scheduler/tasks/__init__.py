from typing import Final

from .base import BaseTask
from .parsing import ParsingTask

TASK_CLASSES: Final[tuple[type[BaseTask], ...]] = (ParsingTask,)

__all__ = ["BaseTask", "TASK_CLASSES"]
