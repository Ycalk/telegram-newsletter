from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from ._base import BaseDAO, BaseDAOFactory, BaseModel

if TYPE_CHECKING:
    from .letter import Letter


class Newsletter(BaseModel):
    __tablename__: str = "newsletter"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_messages_count: Mapped[int] = mapped_column()

    messages_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    messages_to: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    letters: Mapped[list[Letter]] = relationship(
        back_populates="newsletter", passive_deletes=True
    )
    elements: Mapped[list[NewsletterElement]] = relationship(
        back_populates="newsletter", passive_deletes=True
    )


class NewsletterDAO(BaseDAO[Newsletter, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Newsletter)

    async def create(
        self,
        channel_id: int,
        channel_messages_count: int,
        messages_from: datetime,
        messages_to: datetime,
    ) -> Newsletter:
        obj = Newsletter(
            channel_id=channel_id,
            channel_messages_count=channel_messages_count,
            messages_from=messages_from,
            messages_to=messages_to,
        )
        await self.save(obj)
        return obj


class NewsletterDAOFactory(BaseDAOFactory[NewsletterDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, NewsletterDAO)


class NewsletterElement(BaseModel):
    __tablename__: str = "newsletter_element"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    newsletter_id: Mapped[UUID] = mapped_column(
        ForeignKey("newsletter.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int] = mapped_column(BigInteger)

    newsletter: Mapped[Newsletter] = relationship(back_populates="elements")


class NewsletterElementDAO(BaseDAO[NewsletterElement, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NewsletterElement)

    async def create(
        self,
        newsletter_id: UUID,
        message_id: int,
    ) -> NewsletterElement:
        obj = NewsletterElement(
            newsletter_id=newsletter_id,
            message_id=message_id,
        )
        await self.save(obj)
        return obj


class NewsletterElementDAOFactory(BaseDAOFactory[NewsletterElementDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, NewsletterElementDAO)
