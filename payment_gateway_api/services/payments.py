import uuid

from payment_gateway_api.exceptions import PaymentNotFoundError
from payment_gateway_api.repositories.payments import PaymentRepository
from payment_gateway_api.schemas.payment_request import PaymentResponse


class PaymentService:
    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def get_payment(
        self, payment_id: uuid.UUID, merchant_id: uuid.UUID
    ) -> PaymentResponse:
        payment = await self._payments.get_by_id_for_merchant(payment_id, merchant_id)
        if payment is None:
            raise PaymentNotFoundError(details={"payment_id": str(payment_id)})
        return PaymentResponse.model_validate(payment)
