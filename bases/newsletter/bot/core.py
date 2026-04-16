import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable
from html import escape
from pathlib import Path
from typing import Any, override

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.aiogram import setup_dishka
from jinja2 import Environment, FileSystemLoader
from newsletter.api_client import APIClientProvider
from newsletter.channel_id_encryption import ChannelIdEncryptionProvider
from newsletter.database import DatabaseProvider
from newsletter.email_sender import EmailSenderProvider
from newsletter.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from opentelemetry import trace
from redis.asyncio import Redis

from .handlers import manage_router, start_router, subscribe_router
from .settings import BotSettings


class BotProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> BotSettings:
        return BotSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def bot(self, settings: BotSettings) -> Bot:
        return Bot(
            token=settings.bot_token, default=DefaultBotProperties(parse_mode="html")
        )

    @provide(scope=Scope.APP)
    async def redis(self, settings: BotSettings) -> AsyncIterable[Redis]:
        redis = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
        )
        yield redis
        await redis.aclose()

    @provide(scope=Scope.APP)
    def dispatcher(self, redis: Redis) -> Dispatcher:
        storage = RedisStorage(redis)
        return Dispatcher(storage=storage)

    @provide(scope=Scope.APP)
    def jinja2_env(self) -> Environment:
        current_dir = Path(__file__).resolve().parent
        templates_dir = current_dir / "templates"
        if not templates_dir.exists():
            raise RuntimeError(f"Templates directory not found: {templates_dir}")
        return Environment(loader=FileSystemLoader(templates_dir))


async def main():
    container = make_async_container(
        BotProvider(),
        APIClientProvider(),
        ChannelIdEncryptionProvider(),
        DatabaseProvider(),
        EmailSenderProvider(),
        LoggingSettingsProvider(),
    )
    logging_settings = await container.get(LoggingSettings)
    setup_logging(logging_settings, "bot")

    dispatcher = await container.get(Dispatcher)
    setup_dishka(container=container, router=dispatcher, auto_inject=True)
    dispatcher.shutdown.register(container.close)
    dispatcher.update.outer_middleware(TracingAndErrorMiddleware())
    dispatcher.include_router(start_router)
    dispatcher.include_router(manage_router)
    dispatcher.include_router(subscribe_router)

    bot = await container.get(Bot)
    await dispatcher.start_polling(bot)


class TracingAndErrorMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.tracer: trace.Tracer = trace.get_tracer("bot.main")

    @override
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_type = type(event).__name__

        with self.tracer.start_as_current_span(f"aiogram.update.{event_type}") as span:
            try:
                return await handler(event, data)

            except Exception as e:
                span.record_exception(e)
                span.set_status(
                    trace.Status(trace.StatusCode.ERROR, description=str(e))
                )

                trace_id = format(span.get_span_context().trace_id, "032x")

                bot: Bot | None = data.get("bot")
                chat_id = None

                if isinstance(event, Update):
                    if event.message:
                        chat_id = event.message.chat.id
                    elif event.callback_query and event.callback_query.message:
                        chat_id = event.callback_query.message.chat.id
                elif isinstance(event, Message):
                    chat_id = event.chat.id
                elif isinstance(event, CallbackQuery) and event.message:
                    chat_id = event.message.chat.id
                if bot and chat_id:
                    error_type = e.__class__.__name__
                    raw_error_msg = str(e)
                    escaped_msg = escape(raw_error_msg)
                    max_length = 300
                    if len(escaped_msg) > max_length:
                        escaped_msg = escaped_msg[:max_length] + "..."
                    error_text = (
                        "⚠️ <b>Произошла непредвиденная ошибка</b>\n\n"
                        f"<b>Trace ID:</b> <code>{trace_id}</code>\n"
                        f"<b>Тип ошибки:</b> <code>{error_type}</code>\n"
                        f"<b>Описание:</b> <code>{escaped_msg}</code>"
                    )
                    await bot.send_message(chat_id=chat_id, text=error_text)
                raise


def run() -> None:
    asyncio.run(main())
