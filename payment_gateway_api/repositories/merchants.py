from sqlalchemy import select

from payment_gateway_api.models.merchant import Merchant
from payment_gateway_api.repositories.base import BaseRepository


class MerchantRepository(BaseRepository[Merchant]):
    async def get_active_by_api_key_hash(self, api_key_hash: str) -> Merchant | None:
        return await self._session.scalar(
            select(Merchant).where(
                Merchant.api_key_hash == api_key_hash,
                Merchant.is_active.is_(True),
            )
        )
