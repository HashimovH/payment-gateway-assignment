from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payment_gateway_api.config import get_settings
from payment_gateway_api.db import get_engine
from payment_gateway_api.dependencies.payments import close_bank_client
from payment_gateway_api.exception_handlers import register_exception_handlers
from payment_gateway_api.logging_config import configure_logging
from payment_gateway_api.middleware import RequestLoggingMiddleware
from payment_gateway_api.routers import health, payments

configure_logging(get_settings())


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield
    await close_bank_client()
    await get_engine().dispose()  # close pooled DB connections on shutdown


app = FastAPI(title="Payment Gateway API", lifespan=lifespan)
register_exception_handlers(app)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health.router)
app.include_router(payments.router)


@app.get("/")
async def ping() -> dict[str, str]:
    return {"app": "payment-gateway-api"}
