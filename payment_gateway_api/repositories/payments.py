import uuid

from sqlalchemy import select

from payment_gateway_api.dependencies.idempotency import IdempotencyKeyValue
from payment_gateway_api.models.payment import Payment
from payment_gateway_api.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    async def get_by_idempotency_key(
        self, merchant_id: uuid.UUID, key: IdempotencyKeyValue
    ) -> Payment | None:
        return await self._session.scalar(
            select(Payment).where(Payment.merchant_id == merchant_id, Payment.idempotency_key == key)
        )

    async def get_by_id_for_merchant(
        self, payment_id: uuid.UUID, merchant_id: uuid.UUID
    ) -> Payment | None:
        return await self._session.scalar(
            select(Payment).where(
                Payment.id == payment_id,
                Payment.merchant_id == merchant_id,
            )
        )
        