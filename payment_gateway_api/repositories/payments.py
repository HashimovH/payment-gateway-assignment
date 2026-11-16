import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from payment_gateway_api.dependencies.idempotency import IdempotencyKeyValue
from payment_gateway_api.enums import Currency, PaymentStatus
from payment_gateway_api.models.payment import Payment
from payment_gateway_api.repositories.base import BaseRepository

IDEMPOTENCY_CONSTRAINT = "uq_payments_merchant_id_idempotency_key"

_FRESH = {"populate_existing": True}


class PaymentRepository(BaseRepository[Payment]):
    async def get_by_idempotency_key(
        self, merchant_id: uuid.UUID, key: IdempotencyKeyValue
    ) -> Payment | None:
        return await self._session.scalar(
            select(Payment).where(
                Payment.merchant_id == merchant_id, Payment.idempotency_key == key
            ),
            execution_options=_FRESH,
        )

    async def get_by_id_for_merchant(
        self, payment_id: uuid.UUID, merchant_id: uuid.UUID
    ) -> Payment | None:
        return await self._session.scalar(
            select(Payment).where(
                Payment.id == payment_id,
                Payment.merchant_id == merchant_id,
            ),
            execution_options=_FRESH,
        )

    async def create_pending_if_absent(
        self,
        *,
        merchant_id: uuid.UUID,
        idempotency_key: IdempotencyKeyValue,
        request_fingerprint: str,
        card_number_last_four: str,
        expiry_month: int,
        expiry_year: int,
        currency: Currency,
        amount: int,
    ) -> Payment | None:
        statement = (
            insert(Payment)
            .values(
                id=uuid.uuid4(),
                status=PaymentStatus.PENDING,
                merchant_id=merchant_id,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                card_number_last_four=card_number_last_four,
                expiry_month=expiry_month,
                expiry_year=expiry_year,
                currency=currency,
                amount=amount,
            )
            .on_conflict_do_nothing(constraint=IDEMPOTENCY_CONSTRAINT)
            .returning(Payment)
        )
        payment = await self._session.scalar(statement)
        await self._session.commit()
        return payment

    async def set_outcome(
        self,
        payment_id: uuid.UUID,
        status: PaymentStatus,
        authorization_code: str | None,
    ) -> Payment | None:
        payment = await self._session.scalar(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
            .values(status=status, authorization_code=authorization_code, updated_at=func.now())
            .returning(Payment)
            .execution_options(populate_existing=True)
        )
        await self._session.commit()
        return payment

    async def delete_pending(self, payment_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(Payment).where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
        )
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
