import asyncio
from datetime import datetime, timezone

from dishka import Provider, Scope, make_async_container, provide_all
from dishka.dependency_source import CompositeDependencySource
from newsletter.api_client import APIClientProvider
from newsletter.database import DatabaseProvider
from newsletter.logging import LoggingSettings, LoggingSettingsProvider, setup_logging

from .tasks import TASK_CLASSES, BaseTask


class SchedulerProvider(Provider):
    tasks: CompositeDependencySource = provide_all(*TASK_CLASSES, scope=Scope.REQUEST)


async def main() -> None:
    container = make_async_container(
        SchedulerProvider(),
        DatabaseProvider(),
        APIClientProvider(),
        LoggingSettingsProvider(),
    )
    setup_logging(await container.get(LoggingSettings), "scheduler")

    task_latest_run: dict[type[BaseTask], datetime] = {
        task_class: datetime.now(timezone.utc) - task_class.interval
        for task_class in TASK_CLASSES
    }
    background_tasks: set[asyncio.Task[None]] = set()
    try:
        while True:
            for task_class, latest_run in task_latest_run.items():
                if datetime.now(timezone.utc) - latest_run >= task_class.interval:

                    async def execute_task() -> None:
                        async with container() as request_container:
                            task_instance = await request_container.get(task_class)
                            await task_instance()

                    task = asyncio.create_task(execute_task())
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)
                    task_latest_run[task_class] = datetime.now(timezone.utc)

            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    finally:
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        await container.close()


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
