from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from ._base import BaseDAO, BaseDAOFactory, BaseModel

if TYPE_CHECKING:
    from .newsletter_subscription import NewsletterSubscription


class User(BaseModel):
    __tablename__: str = "user"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(500), unique=True, index=True)

    telegram_user: Mapped[TelegramUser | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    subscriptions: Mapped[list[NewsletterSubscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserDAO(BaseDAO[User, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def create(
        self,
        email: str,
    ) -> User:
        obj = User(email=email)
        await self.save(obj)
        return obj


class UserDAOFactory(BaseDAOFactory[UserDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, UserDAO)


class TelegramUser(BaseModel):
    __tablename__: str = "telegram_user"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="telegram_user")


class TelegramUserDAO(BaseDAO[TelegramUser, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TelegramUser)

    async def create(
        self,
        user_id: UUID,
        telegram_id: int,
        first_name: str,
        last_name: str | None = None,
        username: str | None = None,
    ) -> TelegramUser:
        obj = TelegramUser(
            user_id=user_id,
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
        )
        await self.save(obj)
        return obj

    async def find_by_telegram_id_with_loaded_user(
        self, telegram_id: int
    ) -> TelegramUser | None:
        stmt = (
            select(TelegramUser)
            .where(TelegramUser.telegram_id == telegram_id)
            .options(selectinload(TelegramUser.user))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class TelegramUserDAOFactory(BaseDAOFactory[TelegramUserDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, TelegramUserDAO)
