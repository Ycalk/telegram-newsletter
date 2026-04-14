import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from newsletter.database import DatabaseProvider
from newsletter.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from uvicorn import Config, Server

from .router import router
from .settings import UnsubscribeHandlerSettings


class UnsubscribeHandlerProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> UnsubscribeHandlerSettings:
        return UnsubscribeHandlerSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def templates(self) -> Jinja2Templates:
        current_dir = Path(__file__).resolve().parent
        templates_dir = current_dir / "templates"
        if not templates_dir.exists():
            raise RuntimeError(f"Templates directory not found: {templates_dir}")

        return Jinja2Templates(templates_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await app.state.dishka_container.close()


async def build_app() -> FastAPI:
    container = make_async_container(
        UnsubscribeHandlerProvider(),
        DatabaseProvider(),
        LoggingSettingsProvider(),
    )

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    setup_logging(await container.get(LoggingSettings), "unsubscribe_handler")

    FastAPIInstrumentor.instrument_app(app)
    setup_dishka(container=container, app=app)
    app.include_router(router)

    return app


async def run_app() -> None:
    app = await build_app()
    settings: UnsubscribeHandlerSettings = await app.state.dishka_container.get(
        UnsubscribeHandlerSettings
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
