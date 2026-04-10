from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel as PydanticBase
from sqlalchemy import BigInteger, ForeignKey, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from ._base import BaseDAO, BaseDAOFactory, BaseModel
from .letter import Letter


class Newsletter(BaseModel):
    __tablename__: str = "newsletter"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)

    messages_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    messages_to: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    letters: Mapped[list[Letter]] = relationship(
        back_populates="newsletter", passive_deletes=True
    )
    elements: Mapped[list[NewsletterElement]] = relationship(
        back_populates="newsletter", passive_deletes=True
    )


class NewsletterStatsDTO(PydanticBase):
    id: UUID
    messages_from: datetime
    messages_to: datetime
    total_sent: int
    total_viewed: int


class NewsletterDAO(BaseDAO[Newsletter, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Newsletter)

    async def create(
        self,
        channel_id: int,
        messages_from: datetime,
        messages_to: datetime,
    ) -> Newsletter:
        obj = Newsletter(
            channel_id=channel_id,
            messages_from=messages_from,
            messages_to=messages_to,
        )
        await self.save(obj)
        return obj

    async def get_channel_statistics(self, channel_id: int) -> list[NewsletterStatsDTO]:
        stmt = (
            select(
                Newsletter.id,
                Newsletter.messages_from,
                Newsletter.messages_to,
                func.count(Letter.id),
                func.count(Letter.viewed_at),
            )
            .outerjoin(Letter, Newsletter.id == Letter.newsletter_id)
            .where(Newsletter.channel_id == channel_id)
            .group_by(Newsletter.id, Newsletter.messages_from, Newsletter.messages_to)
            .order_by(Newsletter.messages_from.desc())
        )

        result = await self._session.execute(stmt)

        return [
            NewsletterStatsDTO(
                id=row[0],
                messages_from=row[1],
                messages_to=row[2],
                total_sent=row[3],
                total_viewed=row[4],
            )
            for row in result.tuples().all()
        ]


class NewsletterDAOFactory(BaseDAOFactory[NewsletterDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, NewsletterDAO)


class NewsletterElement(BaseModel):
    __tablename__: str = "newsletter_element"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    newsletter_id: Mapped[UUID] = mapped_column(
        ForeignKey("newsletter.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[UUID] = mapped_column()

    newsletter: Mapped[Newsletter] = relationship(back_populates="elements")


class NewsletterElementDAO(BaseDAO[NewsletterElement, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NewsletterElement)

    async def create(
        self,
        newsletter_id: UUID,
        message_id: UUID,
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
