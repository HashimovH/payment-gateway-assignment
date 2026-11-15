import uuid

from payment_gateway_api.repositories.payments import PaymentRepository
from payment_gateway_api.schemas.payment_request import PaymentResponse


class PaymentNotFoundError(Exception):
    def __init__(self, payment_id: uuid.UUID) -> None:
        self.payment_id = payment_id
        super().__init__(f"Payment {payment_id} not found")


class PaymentService:
    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def get_payment(
        self, payment_id: uuid.UUID, merchant_id: uuid.UUID
    ) -> PaymentResponse:
        payment = await self._payments.get_by_id_for_merchant(payment_id, merchant_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return PaymentResponse.model_validate(payment)
