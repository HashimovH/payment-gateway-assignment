from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payment_gateway_api.db import get_engine
from payment_gateway_api.routers import health, payments


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield
    await get_engine().dispose()  # close pooled DB connections on shutdown


app = FastAPI(title="Payment Gateway API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(payments.router)


@app.get("/")
async def ping() -> dict[str, str]:
    return {"app": "payment-gateway-api"}
