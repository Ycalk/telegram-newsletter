from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, override
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, joinedload, mapped_column, relationship

from ._base import BaseDAO, BaseDAOFactory, BaseModel
from .user import User

if TYPE_CHECKING:
    from .channel import Channel
    from .letter import Letter


class NewsletterSubscription(BaseModel):
    __tablename__: str = "newsletter_subscription"
    __table_args__: tuple[Any, ...] = (
        UniqueConstraint("user_id", "channel_id", name="uq_user_channel"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channel.id", ondelete="CASCADE"), index=True
    )
    unsubscribed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None
    )
    send_at: Mapped[int] = mapped_column()

    user: Mapped[User] = relationship(back_populates="subscriptions")
    channel: Mapped[Channel] = relationship(back_populates="subscriptions")
    letters: Mapped[list[Letter]] = relationship(
        back_populates="newsletter_subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class NewsletterSubscriptionDAO(BaseDAO[NewsletterSubscription, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NewsletterSubscription)

    async def create(
        self,
        user_id: UUID,
        channel_id: int,
        send_at: int,
    ) -> NewsletterSubscription:
        obj = NewsletterSubscription(
            user_id=user_id,
            channel_id=channel_id,
            send_at=send_at,
        )
        await self.save(obj)
        return obj

    @override
    async def find_by_id(
        self, id: UUID, skip_unsubscribe: bool = True
    ) -> NewsletterSubscription | None:
        stmt = select(NewsletterSubscription).where(NewsletterSubscription.id == id)
        if skip_unsubscribe:
            stmt = stmt.where(NewsletterSubscription.unsubscribed_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_user_id_with_loaded_user(
        self, user_id: UUID, skip_unsubscribe: bool = True
    ) -> list[NewsletterSubscription]:
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.user_id == user_id
        )
        if skip_unsubscribe:
            stmt = stmt.where(NewsletterSubscription.unsubscribed_at.is_(None))

        stmt = stmt.options(
            joinedload(NewsletterSubscription.user).joinedload(User.telegram_user),
            joinedload(NewsletterSubscription.channel),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_channel_id_with_loaded_user(
        self, channel_id: int, skip_unsubscribe: bool = True
    ) -> list[NewsletterSubscription]:
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.channel_id == channel_id
        )
        if skip_unsubscribe:
            stmt = stmt.where(NewsletterSubscription.unsubscribed_at.is_(None))

        stmt = stmt.options(
            joinedload(NewsletterSubscription.user).joinedload(User.telegram_user)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_id_with_loaded_user(
        self, id: UUID, skip_unsubscribe: bool = True
    ) -> NewsletterSubscription | None:
        stmt = select(NewsletterSubscription).where(NewsletterSubscription.id == id)
        if skip_unsubscribe:
            stmt = stmt.where(NewsletterSubscription.unsubscribed_at.is_(None))

        stmt = stmt.options(
            joinedload(NewsletterSubscription.user).joinedload(User.telegram_user),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_send_at(
        self, send_at: int, skip_unsubscribe: bool = True
    ) -> list[NewsletterSubscription]:
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.send_at == send_at
        )
        if skip_unsubscribe:
            stmt = stmt.where(NewsletterSubscription.unsubscribed_at.is_(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NewsletterSubscriptionDAOFactory(BaseDAOFactory[NewsletterSubscriptionDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, NewsletterSubscriptionDAO)
