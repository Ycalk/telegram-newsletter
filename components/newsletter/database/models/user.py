from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from ._base import BaseDAO, BaseDAOFactory, BaseModel

if TYPE_CHECKING:
    from .letter import Letter


class User(BaseModel):
    __tablename__: str = "user"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(500), unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    telegram_user: Mapped[TelegramUser | None] = relationship(
        back_populates="user", passive_deletes=True
    )
    letters: Mapped[list[Letter]] = relationship(
        back_populates="user", passive_deletes=True
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
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
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


class TelegramUserDAOFactory(BaseDAOFactory[TelegramUserDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, TelegramUserDAO)
