from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, joinedload, mapped_column, relationship, selectinload

from ._base import BaseDAO, BaseDAOFactory, BaseModel

if TYPE_CHECKING:
    from .channel_message import ChannelMessage
    from .media import Media
    from .newsletter_subscription import NewsletterSubscription


class Channel(BaseModel):
    __tablename__: str = "channel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    logo_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("media.id", ondelete="SET NULL")
    )

    messages: Mapped[list[ChannelMessage]] = relationship(
        back_populates="channel", cascade="all, delete-orphan", passive_deletes=True
    )
    logo: Mapped[Media | None] = relationship()
    subscriptions: Mapped[list[NewsletterSubscription]] = relationship(
        back_populates="channel", cascade="all, delete-orphan", passive_deletes=True
    )


class ChannelDAO(BaseDAO[Channel, int]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Channel)

    async def create(
        self,
        id: int,
        name: str,
        description: str | None = None,
        logo_id: UUID | None = None,
    ) -> Channel:
        obj = Channel(
            id=id,
            name=name,
            description=description,
            logo_id=logo_id,
        )
        await self.save(obj)
        return obj

    async def list_with_loaded_subscriptions_and_logo(self) -> list[Channel]:
        stmt = select(Channel).options(
            selectinload(Channel.subscriptions),
            joinedload(Channel.logo),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique())

    async def find_by_id_with_loaded_subscriptions_and_logo(
        self, id: int
    ) -> Channel | None:
        stmt = (
            select(Channel)
            .where(Channel.id == id)
            .options(
                selectinload(Channel.subscriptions),
                joinedload(Channel.logo),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_id_with_loaded_logo(self, id: int) -> Channel | None:
        stmt = select(Channel).where(Channel.id == id).options(joinedload(Channel.logo))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class ChannelDAOFactory(BaseDAOFactory[ChannelDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, ChannelDAO)
