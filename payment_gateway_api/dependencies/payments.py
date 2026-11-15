from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payment_gateway_api.db import get_db_session
from payment_gateway_api.repositories.payments import PaymentRepository
from payment_gateway_api.services.payments import PaymentService


async def get_payment_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentRepository:
    return PaymentRepository(session)


async def get_payment_service(
    payments: Annotated[PaymentRepository, Depends(get_payment_repository)],
) -> PaymentService:
    return PaymentService(payments)


PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
