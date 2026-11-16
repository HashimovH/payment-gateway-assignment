"""Payments whose outcome is not known when the request ends.

Real app, real Postgres, and an extra Mountebank imposter that answers slower
than the gateway's bank timeout, so the gateway cannot tell whether the bank
authorized the payment. The payment must stay Pending, and retries must never
call the bank again.
"""

import asyncio
import uuid

import pytest

from payment_gateway_api.db import get_session_factory
from payment_gateway_api.enums import PaymentStatus
from payment_gateway_api.models.payment import Payment
from payment_gateway_api.repositories.payments import PaymentRepository

from api_helpers import auth_headers, create_payment

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

SLOW_BANK_PORT = 8081
COUNTING_BANK_PORT = 8082
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


async def test_bank_timeout_returns_pending_with_location(client, api_key, slow_bank):
    response = await create_payment(client, api_key)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "Pending"
    assert response.headers["Location"] == f"/payments/{body['id']}"
    assert await get_status(client, api_key, body["id"]) == "Pending"


async def test_retry_of_pending_payment_returns_it_without_calling_the_bank(
    client, api_key, slow_bank
):
    key = str(uuid.uuid4())
    first = await create_payment(client, api_key, idempotency_key=key)

    retries = [await create_payment(client, api_key, idempotency_key=key) for _ in range(3)]

    assert first.status_code == 202
    assert [r.status_code for r in retries] == [202, 202, 202]
    assert all(r.json() == first.json() for r in retries)
    assert "Retry-After" not in retries[0].headers
    assert await slow_bank.request_count() == 1


async def test_concurrent_requests_with_same_key_call_the_bank_once(
    client, api_key, bank_imposter, use_bank
):
    bank = await bank_imposter(COUNTING_BANK_PORT, wait_ms=300)
    use_bank(bank.url, timeout=5)
    key = str(uuid.uuid4())

    responses = await asyncio.gather(
        *(create_payment(client, api_key, idempotency_key=key) for _ in range(10))
    )

    statuses = [r.status_code for r in responses]
    assert set(statuses) <= {201, 202}, statuses
    assert len({r.json()["id"] for r in responses}) == 1
    assert await bank.request_count() == 1
    settled = await create_payment(client, api_key, idempotency_key=key)
    assert settled.status_code == 201
    assert settled.json()["status"] == "Authorized"


async def test_reads_return_the_stored_row_not_a_stale_session_copy(client, api_key, slow_bank):
    payment_id = uuid.UUID((await create_payment(client, api_key)).json()["id"])

    async with get_session_factory()() as request_session, get_session_factory()() as other:
        request_repo = PaymentRepository(request_session)
        loaded = await request_session.get(Payment, payment_id)
        assert loaded is not None
        assert loaded.status is PaymentStatus.PENDING

        settled = await PaymentRepository(other).set_outcome(
            payment_id, PaymentStatus.DECLINED, None
        )
        assert settled is not None

        assert await request_repo.set_outcome(payment_id, PaymentStatus.AUTHORIZED, "x") is None
        fresh = await request_repo.get_by_id_for_merchant(payment_id, loaded.merchant_id)
        assert fresh is not None
        assert fresh.status is PaymentStatus.DECLINED
