from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payment_gateway_api.models.merchant import Merchant


class MerchantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_api_key_hash(self, api_key_hash: str) -> Merchant | None:
        return await self._session.scalar(
            select(Merchant).where(
                Merchant.api_key_hash == api_key_hash,
                Merchant.is_active.is_(True),
            )
        )

    async def add(self, merchant: Merchant) -> None:
        self._session.add(merchant)
        await self._session.commit()
