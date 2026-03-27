import asyncio
from contextlib import asynccontextmanager

from dishka import Provider, Scope, make_async_container, provide
from dishka.dependency_source import CompositeDependencySource
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from newsletter.api_client import APIClientProvider
from newsletter.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from uvicorn import Config, Server

from .router import router
from .settings import MediaProxySettings
from .utils import MediaProxyUtils


class MediaProxyProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> MediaProxySettings:
        return MediaProxySettings()  # type: ignore # pyright: ignore

    media_proxy_utils: CompositeDependencySource = provide(
        MediaProxyUtils,
        provides=MediaProxyUtils,
        scope=Scope.REQUEST,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await app.state.dishka_container.close()


async def build_app() -> FastAPI:
    container = make_async_container(
        MediaProxyProvider(),
        APIClientProvider(),
        LoggingSettingsProvider(),
    )

    app = FastAPI(
        lifespan=lifespan,
    )

    setup_logging(await container.get(LoggingSettings), "media_proxy")

    FastAPIInstrumentor.instrument_app(app)
    setup_dishka(container=container, app=app)
    app.include_router(router)

    return app


async def run_app() -> None:
    app = await build_app()
    settings: MediaProxySettings = await app.state.dishka_container.get(
        MediaProxySettings
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
