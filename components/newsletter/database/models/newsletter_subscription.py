from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from ._base import BaseDAO, BaseDAOFactory, BaseModel
from .user import User


class NewsletterSubscription(BaseModel):
    __tablename__: str = "newsletter_subscription"
    __table_args__: tuple[Any, ...] = (
        UniqueConstraint("user_id", "channel_id", name="uq_user_channel"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)

    user: Mapped[User] = relationship(back_populates="subscriptions")


class NewsletterSubscriptionDAO(BaseDAO[NewsletterSubscription, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NewsletterSubscription)

    async def create(
        self,
        user_id: UUID,
        channel_id: int,
    ) -> NewsletterSubscription:
        obj = NewsletterSubscription(
            user_id=user_id,
            channel_id=channel_id,
        )
        await self.save(obj)
        return obj

    async def find_by_user_id_with_loaded_user(
        self, user_id: UUID
    ) -> list[NewsletterSubscription]:
        stmt = (
            select(NewsletterSubscription)
            .where(NewsletterSubscription.user_id == user_id)
            .options(selectinload(NewsletterSubscription.user))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_channel_id(self, channel_id: int) -> int:
        stmt = select(func.count(NewsletterSubscription.id)).where(
            NewsletterSubscription.channel_id == channel_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_for_multiple_channels(
        self, channel_ids: list[int]
    ) -> dict[int, int]:
        stmt = (
            select(
                NewsletterSubscription.channel_id, func.count(NewsletterSubscription.id)
            )
            .where(NewsletterSubscription.channel_id.in_(channel_ids))
            .group_by(NewsletterSubscription.channel_id)
        )

        result = await self._session.execute(stmt)
        return {channel_id: count for channel_id, count in result.tuples().all()}

    async def find_by_channel_id_with_loaded_user(
        self, channel_id: int
    ) -> list[NewsletterSubscription]:
        stmt = (
            select(NewsletterSubscription)
            .where(NewsletterSubscription.channel_id == channel_id)
            .options(
                selectinload(NewsletterSubscription.user).selectinload(
                    User.telegram_user
                )
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NewsletterSubscriptionDAOFactory(BaseDAOFactory[NewsletterSubscriptionDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, NewsletterSubscriptionDAO)
