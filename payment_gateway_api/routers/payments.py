import uuid

from fastapi import APIRouter, Depends, status

from payment_gateway_api.dependencies.idempotency import IdempotencyKey
from payment_gateway_api.dependencies.merchants import CurrentMerchant, get_current_merchant
from payment_gateway_api.dependencies.payments import PaymentServiceDep
from payment_gateway_api.schemas.payment_request import PaymentRequest, PaymentResponse

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(get_current_merchant)],
)


@router.post("", status_code=status.HTTP_201_CREATED)
async def process_payment(
    data: PaymentRequest,
    idempotency_key: IdempotencyKey,
    merchant: CurrentMerchant,
    service: PaymentServiceDep,
) -> PaymentResponse:
    return await service.process_payment(data, merchant.id, idempotency_key)


@router.get("/{payment_id}")
async def get_payment(
    payment_id: uuid.UUID,
    merchant: CurrentMerchant,
    service: PaymentServiceDep,
) -> PaymentResponse:
    return await service.get_payment(payment_id, merchant.id)
