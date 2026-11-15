from typing import Annotated

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from payment_gateway_api.auth import hash_api_key
from payment_gateway_api.db import get_db_session
from payment_gateway_api.exceptions import UnauthorizedError
from payment_gateway_api.models.merchant import Merchant
from payment_gateway_api.repositories.merchants import MerchantRepository

bearer_scheme = HTTPBearer(auto_error=False, description="Merchant API key")


async def get_merchant_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MerchantRepository:
    return MerchantRepository(session)


async def get_current_merchant(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    merchants: Annotated[MerchantRepository, Depends(get_merchant_repository)],
) -> Merchant:
    merchant = (
        await merchants.get_active_by_api_key_hash(hash_api_key(credentials.credentials))
        if credentials
        else None
    )
    if merchant is None:
        raise UnauthorizedError()
    structlog.contextvars.bind_contextvars(merchant_id=str(merchant.id))
    return merchant


CurrentMerchant = Annotated[Merchant, Depends(get_current_merchant)]
