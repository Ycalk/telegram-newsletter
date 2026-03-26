import asyncio
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from dishka import Provider, Scope, make_async_container, provide
from dishka.dependency_source import CompositeDependencySource
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from newsletter.api_client import APIClientProvider
from newsletter.channel_id_encryption import ChannelIdEncryptionProvider
from newsletter.database import DatabaseProvider
from newsletter.email_sender import EmailSenderProvider
from newsletter.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from uvicorn import Config, Server

from .router import router
from .service import AdminPanelService, IAdminPanelService
from .settings import AdminPanelSettings


class AdminPanelProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> AdminPanelSettings:
        return AdminPanelSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def templates(self) -> Jinja2Templates:
        current_dir = Path(__file__).resolve().parent
        templates_dir = current_dir / "templates"
        if not templates_dir.exists():
            raise RuntimeError(f"Templates directory not found: {templates_dir}")

        return Jinja2Templates(templates_dir)

    admin_panel_service: CompositeDependencySource = provide(
        AdminPanelService,
        provides=IAdminPanelService,
        scope=Scope.REQUEST,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await app.state.dishka_container.close()


async def build_app() -> FastAPI:
    container = make_async_container(
        AdminPanelProvider(),
        APIClientProvider(),
        ChannelIdEncryptionProvider(),
        DatabaseProvider(),
        LoggingSettingsProvider(),
        EmailSenderProvider(),
    )

    app = FastAPI(
        lifespan=lifespan,
    )

    setup_logging(await container.get(LoggingSettings), "admin_panel")

    templates = await container.get(Jinja2Templates)

    @app.exception_handler(Exception)
    async def all_exception_handler(request: Request, exc: Exception) -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        span = trace.get_current_span()
        span.set_status(trace.Status(trace.StatusCode.ERROR, description=str(exc)))
        span.record_exception(exc)
        stack_trace_str = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        response = templates.TemplateResponse(
            request,
            "error.html",
            {
                "error": exc.__class__.__name__,
                "message": str(exc),
                "trace_id": format(span.get_span_context().trace_id, "032x"),
                "stack_trace": stack_trace_str,
            },
        )
        if request.headers.get("HX-Request"):
            response.headers["HX-Retarget"] = "body"
            response.headers["HX-Reswap"] = "innerHTML"

        return response

    FastAPIInstrumentor.instrument_app(app)
    setup_dishka(container=container, app=app)
    app.include_router(router)

    return app


async def run_app() -> None:
    app = await build_app()
    settings: AdminPanelSettings = await app.state.dishka_container.get(
        AdminPanelSettings
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
