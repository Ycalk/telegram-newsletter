from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from ._base import BaseDAO, BaseDAOFactory, BaseModel

if TYPE_CHECKING:
    from .newsletter import Newsletter
    from .user import User


class Letter(BaseModel):
    __tablename__: str = "letter"
    __table_args__: tuple[Any, ...] = (
        UniqueConstraint("newsletter_id", "user_id", name="uq_letter_newsletter_user"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    newsletter_id: Mapped[UUID] = mapped_column(
        ForeignKey("newsletter.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    viewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    newsletter: Mapped[Newsletter] = relationship(back_populates="letters")
    user: Mapped[User] = relationship(back_populates="letters")


class LetterDAO(BaseDAO[Letter, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Letter)

    async def create(
        self,
        newsletter_id: UUID,
        user_id: UUID,
    ) -> Letter:
        obj = Letter(
            newsletter_id=newsletter_id,
            user_id=user_id,
        )
        await self.save(obj)
        return obj


class LetterDAOFactory(BaseDAOFactory[LetterDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, LetterDAO)
