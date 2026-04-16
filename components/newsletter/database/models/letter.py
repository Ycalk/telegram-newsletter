from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, cast, func, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from ._base import BaseDAO, BaseDAOFactory, BaseModel
from .newsletter_subscription import NewsletterSubscription

if TYPE_CHECKING:
    from .channel_message import ChannelMessage


class Letter(BaseModel):
    __tablename__: str = "letter"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    newsletter_subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("newsletter_subscription.id", ondelete="CASCADE"), index=True
    )
    viewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None
    )

    elements: Mapped[list[LetterElement]] = relationship(
        back_populates="letter", cascade="all, delete-orphan", passive_deletes=True
    )
    messages: AssociationProxy[list[ChannelMessage]] = association_proxy(
        "elements",
        "message",
        creator=lambda message_obj: ChannelMessage(message=message_obj),
    )
    newsletter_subscription: Mapped[NewsletterSubscription] = relationship(
        back_populates="letters"
    )


class LetterElement(BaseModel):
    __tablename__: str = "letter_element"

    letter_id: Mapped[UUID] = mapped_column(
        ForeignKey("letter.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("channel_message.id", ondelete="CASCADE"), primary_key=True
    )

    letter: Mapped[Letter] = relationship(back_populates="elements")
    message: Mapped[ChannelMessage] = relationship()


class LetterDAO(BaseDAO[Letter, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Letter)

    async def create(
        self,
        newsletter_subscription_id: UUID,
    ) -> Letter:
        obj = Letter(
            newsletter_subscription_id=newsletter_subscription_id,
        )
        await self.save(obj)
        return obj

    async def get_daily_letter_stats_by_channel(
        self, channel_id: int
    ) -> list[tuple[date, int, int]]:
        created_date = cast(Letter.created_at, Date).label("created_date")

        stmt = (
            select(
                created_date,
                func.count(Letter.id).label("total_letters"),
                func.count(Letter.viewed_at).label("viewed_letters"),
            )
            .join(
                NewsletterSubscription,
                Letter.newsletter_subscription_id == NewsletterSubscription.id,
            )
            .where(NewsletterSubscription.channel_id == channel_id)
            .group_by(created_date)
            .order_by(created_date)
        )

        result = await self._session.execute(stmt)
        # дата, всего отправлено, сколько прочитано
        return list(result.tuples().all())


class LetterDAOFactory(BaseDAOFactory[LetterDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, LetterDAO)
