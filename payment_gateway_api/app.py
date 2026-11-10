from fastapi import FastAPI

from payment_gateway_api.routers import health, payments

app = FastAPI(title="Payment Gateway API")

app.include_router(health.router)
app.include_router(payments.router)


@app.get("/")
async def ping() -> dict[str, str]:
    return {"app": "payment-gateway-api"}
