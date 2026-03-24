from collections.abc import AsyncIterable
from typing import NewType

import structlog
from dishka import Provider, Scope, provide, provide_all
from dishka.dependency_source import CompositeDependencySource
from opentelemetry import trace
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import (
    LetterDAO,
    LetterDAOFactory,
    MultipleDAOFactory,
    NewsletterDAO,
    NewsletterDAOFactory,
    NewsletterElementDAO,
    NewsletterElementDAOFactory,
    TelegramUserDAO,
    TelegramUserDAOFactory,
    UserDAO,
    UserDAOFactory,
)
from .settings import DatabaseSettings

DatabaseUrl = NewType("DatabaseUrl", str)


def register_model() -> list[type]:
    from .models import (
        Letter,
        Newsletter,
        NewsletterElement,
        TelegramUser,
        User,
    )

    return [
        Letter,
        Newsletter,
        NewsletterElement,
        TelegramUser,
        User,
    ]


class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> DatabaseSettings:
        return DatabaseSettings()  # type: ignore # pyright: ignore

    @provide(scope=Scope.APP)
    def database_url(
        self,
        database_settings: DatabaseSettings,
    ) -> DatabaseUrl:
        url = (
            f"postgresql+asyncpg://{database_settings.postgres_user}"
            + f":{database_settings.postgres_password}"
            + f"@{database_settings.postgres_host}"
            + f":{database_settings.postgres_port}"
            + f"/{database_settings.postgres_db}"
        )
        return DatabaseUrl(url)

    @provide(scope=Scope.APP)
    async def engine(
        self,
        database_url: DatabaseUrl,
        database_settings: DatabaseSettings,
    ) -> AsyncIterable[AsyncEngine]:
        register_model()
        logger = structlog.get_logger("database")
        engine = create_async_engine(
            database_url,
            echo=False,
            pool_size=database_settings.postgres_pool_size,
            max_overflow=database_settings.postgres_max_overflow,
            pool_pre_ping=True,
            connect_args={
                "server_settings": {
                    "timezone": "UTC",
                }
            },
            isolation_level="READ COMMITTED",
        )
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            tracer_provider=trace.get_tracer_provider(),
            enable_commenter=True,
            commenter_options={"trace_id": True, "span_id": True},
        )
        logger.info("database_engine_created")
        try:
            yield engine
        finally:
            logger.info("disposing_database_engine")
            await engine.dispose()

    @provide(scope=Scope.APP)
    def session_maker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @provide(scope=Scope.REQUEST)
    async def session(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AsyncSession]:
        async with session_maker() as session:
            yield session

    data_access_objects: CompositeDependencySource = provide_all(
        LetterDAO,
        NewsletterDAO,
        NewsletterElementDAO,
        TelegramUserDAO,
        UserDAO,
        scope=Scope.REQUEST,
    )

    data_access_object_factories: CompositeDependencySource = provide_all(
        LetterDAOFactory,
        NewsletterDAOFactory,
        NewsletterElementDAOFactory,
        TelegramUserDAOFactory,
        UserDAOFactory,
        scope=Scope.APP,
    )

    multiple_dao_factory: CompositeDependencySource = provide(
        MultipleDAOFactory, scope=Scope.APP
    )
