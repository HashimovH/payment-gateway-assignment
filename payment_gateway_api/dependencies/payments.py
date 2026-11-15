from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payment_gateway_api.clients.bank import BankClient
from payment_gateway_api.config import get_settings
from payment_gateway_api.db import get_db_session
from payment_gateway_api.repositories.payments import PaymentRepository
from payment_gateway_api.services.payments import PaymentService


@lru_cache
def get_bank_client() -> BankClient:
    settings = get_settings()
    return BankClient(base_url=settings.bank_url, timeout=settings.bank_timeout_seconds)


async def close_bank_client() -> None:
    if get_bank_client.cache_info().currsize:
        await get_bank_client().aclose()
        get_bank_client.cache_clear()


async def get_payment_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentRepository:
    return PaymentRepository(session)


async def get_payment_service(
    payments: Annotated[PaymentRepository, Depends(get_payment_repository)],
    bank_client: Annotated[BankClient, Depends(get_bank_client)],
) -> PaymentService:
    return PaymentService(payments, bank_client)


PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
