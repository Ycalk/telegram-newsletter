from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import TIMESTAMP, ForeignKey, Text, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, joinedload, mapped_column, relationship, selectinload

from ._base import BaseDAO, BaseDAOFactory, BaseModel
from .media import Media

if TYPE_CHECKING:
    from .channel import Channel


class ChannelMessage(BaseModel):
    __tablename__: str = "channel_message"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    text: Mapped[str] = mapped_column(Text)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channel.id", ondelete="CASCADE"), index=True
    )

    channel: Mapped[Channel] = relationship(back_populates="messages")
    media_links: Mapped[list[MessageMediaLink]] = relationship(
        back_populates="message", cascade="all, delete-orphan", passive_deletes=True
    )
    media: AssociationProxy[list[Media]] = association_proxy(
        "media_links",
        "media",
        creator=lambda media_obj: MessageMediaLink(media=media_obj),
    )


class MessageMediaLink(BaseModel):
    __tablename__: str = "message_media_link"

    media_id: Mapped[UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("channel_message.id", ondelete="CASCADE"), index=True
    )

    message: Mapped[ChannelMessage] = relationship(back_populates="media_links")
    media: Mapped[Media] = relationship()


class ChannelMessageDAO(BaseDAO[ChannelMessage, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ChannelMessage)

    async def create(
        self,
        id: UUID,
        created_at: datetime,
        text: str,
        channel_id: int,
    ) -> ChannelMessage:
        obj = ChannelMessage(
            id=id,
            created_at=created_at,
            text=text,
            channel_id=channel_id,
        )
        await self.save(obj)
        return obj

    async def find_with_loaded_media(self, message_id: UUID):
        stmt = (
            select(ChannelMessage)
            .where(ChannelMessage.id == message_id)
            .options(
                selectinload(ChannelMessage.media_links).joinedload(
                    MessageMediaLink.media
                ),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_by_channel_id_and_created_at(
        self,
        channel_id: int,
        created_at_start: datetime,
        created_at_end: datetime,
    ) -> list[ChannelMessage]:
        stmt = (
            select(ChannelMessage)
            .where(ChannelMessage.channel_id == channel_id)
            .where(ChannelMessage.created_at >= created_at_start)
            .where(ChannelMessage.created_at <= created_at_end)
            .order_by(ChannelMessage.created_at.desc())
            .options(
                selectinload(ChannelMessage.media_links).joinedload(
                    MessageMediaLink.media
                ),
                joinedload(ChannelMessage.channel),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique())


class ChannelMessageDAOFactory(BaseDAOFactory[ChannelMessageDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, ChannelMessageDAO)
