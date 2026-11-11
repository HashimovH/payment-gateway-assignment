from sqlalchemy.ext.asyncio import AsyncSession

from payment_gateway_api.db import Base


class BaseRepository[ModelT: Base]:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, instance: ModelT) -> None:
        self._session.add(instance)
        await self._session.commit()
