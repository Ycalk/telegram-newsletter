from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from ._base import BaseDAO, BaseDAOFactory, BaseModel

if TYPE_CHECKING:
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

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

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


class NewsletterSubscriptionDAOFactory(BaseDAOFactory[NewsletterSubscriptionDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, NewsletterSubscriptionDAO)
