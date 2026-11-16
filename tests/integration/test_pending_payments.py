"""Payments whose outcome is not known when the request ends.

Real app, real Postgres, and an extra Mountebank imposter that answers slower
than the gateway's bank timeout, so the gateway cannot tell whether the bank
authorized the payment.
"""

import pytest

from api_helpers import auth_headers, create_payment

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

SLOW_BANK_PORT = 8081
GATEWAY_TIMEOUT_SECONDS = 0.5
SLOW_BANK_WAIT_MS = 1500


@pytest.fixture
async def slow_bank(bank_imposter, use_bank):
    bank = await bank_imposter(SLOW_BANK_PORT, wait_ms=SLOW_BANK_WAIT_MS)
    use_bank(bank.url, timeout=GATEWAY_TIMEOUT_SECONDS)
    return bank


async def get_status(client, api_key: str, payment_id: str) -> str:
    response = await client.get(f"/payments/{payment_id}", headers=auth_headers(api_key))
    assert response.status_code == 200
    return response.json()["status"]


async def test_bank_timeout_returns_pending(client, api_key, slow_bank):
    response = await create_payment(client, api_key)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "Pending"
    assert await get_status(client, api_key, body["id"]) == "Pending"
