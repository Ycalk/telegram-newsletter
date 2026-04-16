from __future__ import annotations

from uuid import UUID

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from ._base import BaseDAO, BaseDAOFactory, BaseModel


class Media(BaseModel):
    __tablename__: str = "media"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    mime_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column()
    file_name: Mapped[str] = mapped_column(String(255))


class MediaDAO(BaseDAO[Media, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Media)

    async def create(
        self,
        id: UUID,
        mime_type: str,
        size_bytes: int,
        file_name: str,
    ) -> Media:
        obj = Media(
            id=id,
            mime_type=mime_type,
            size_bytes=size_bytes,
            file_name=file_name,
        )
        await self.save(obj)
        return obj


class MediaDAOFactory(BaseDAOFactory[MediaDAO]):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker, MediaDAO)
