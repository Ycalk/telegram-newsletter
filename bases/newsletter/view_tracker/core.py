import asyncio
from contextlib import asynccontextmanager

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from newsletter.database import DatabaseProvider
from newsletter.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from uvicorn import Config, Server

from .router import router
from .settings import ViewTrackerSettings


class ViewTrackerProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> ViewTrackerSettings:
        return ViewTrackerSettings()  # type: ignore # pyright: ignore


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await app.state.dishka_container.close()


async def build_app() -> FastAPI:
    container = make_async_container(
        ViewTrackerProvider(),
        DatabaseProvider(),
        LoggingSettingsProvider(),
    )

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    setup_logging(await container.get(LoggingSettings), "view_tracker")

    FastAPIInstrumentor.instrument_app(app)
    setup_dishka(container=container, app=app)
    app.include_router(router)

    return app


async def run_app() -> None:
    app = await build_app()
    settings: ViewTrackerSettings = await app.state.dishka_container.get(
        ViewTrackerSettings
    )

    config = Config(
        app=app,
        host="0.0.0.0",
        port=settings.port,
        reload=False,
    )
    server = Server(config)
    await server.serve()


def run() -> None:
    asyncio.run(run_app())
