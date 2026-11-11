import uuid

from sqlalchemy import select

from payment_gateway_api.models.payment import Payment
from payment_gateway_api.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    async def get_for_merchant(
        self, payment_id: uuid.UUID, merchant_id: uuid.UUID
    ) -> Payment | None:
        return await self._session.scalar(
            select(Payment).where(Payment.id == payment_id, Payment.merchant_id == merchant_id)
        )
