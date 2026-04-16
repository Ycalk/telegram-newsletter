from typing import Final

from .base import BaseTask
from .newsletter import NewsletterTask
from .parsing import ParsingTask

TASK_CLASSES: Final[tuple[type[BaseTask], ...]] = (ParsingTask, NewsletterTask)

__all__ = ["BaseTask", "TASK_CLASSES"]
