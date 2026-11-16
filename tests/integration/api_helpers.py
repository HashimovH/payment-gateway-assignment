import uuid
from datetime import UTC, datetime

import httpx

AUTHORIZED_CARD = "2222405343248877"  # ends in 7
DECLINED_CARD = "2222405343248112"  # ends in 2
BANK_UNAVAILABLE_CARD = "2222405343248870"  # ends in 0

NEXT_YEAR = datetime.now(UTC).year + 1


def payment_payload(**overrides) -> dict:
    payload = {
        "card_number": AUTHORIZED_CARD,
        "expiry_month": 4,
        "expiry_year": NEXT_YEAR,
        "currency": "GBP",
        "amount": 1050,
        "cvv": "123",
    }
    payload.update(overrides)
    return payload


def auth_headers(api_key: str, idempotency_key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
    }


async def create_payment(
    client: httpx.AsyncClient,
    api_key: str,
    payload: dict | None = None,
    idempotency_key: str | None = None,
) -> httpx.Response:
    return await client.post(
        "/payments",
        json=payload if payload is not None else payment_payload(),
        headers=auth_headers(api_key, idempotency_key),
    )
