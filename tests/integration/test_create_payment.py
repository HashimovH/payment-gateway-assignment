"""POST /payments end to end: real app, real Postgres, bank simulator.

Every test drives the API over HTTP only. The bank simulator decides the
outcome by the card number's last digit:
    odd  -> authorized    even -> declined    0 -> bank unavailable (503)
"""

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import structlog
from structlog.testing import capture_logs

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

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


def assert_matches_request(body: dict, payload: dict) -> None:
    assert body["card_number_last_four"] == payload["card_number"][-4:]
    assert body["expiry_month"] == payload["expiry_month"]
    assert body["expiry_year"] == payload["expiry_year"]
    assert body["currency"] == payload["currency"]
    assert body["amount"] == payload["amount"]
    # The full card number and the CVV are never returned.
    assert "card_number" not in body
    assert "cvv" not in body


# --- success ------------------------------------------------------------------------


async def test_authorized_payment_is_created_and_retrievable(client, api_key):
    payload = payment_payload(card_number=AUTHORIZED_CARD)

    response = await create_payment(client, api_key, payload)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "Authorized"
    uuid.UUID(body["id"])
    assert_matches_request(body, payload)

    fetched = await client.get(f"/payments/{body['id']}", headers=auth_headers(api_key))
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_declined_payment_is_created_and_retrievable(client, api_key):
    payload = payment_payload(card_number=DECLINED_CARD)

    response = await create_payment(client, api_key, payload)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "Declined"
    assert_matches_request(body, payload)

    fetched = await client.get(f"/payments/{body['id']}", headers=auth_headers(api_key))
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "Declined"


@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP"])
async def test_every_supported_currency_is_accepted(client, api_key, currency):
    response = await create_payment(client, api_key, payment_payload(currency=currency))

    assert response.status_code == 201
    assert response.json()["currency"] == currency


async def test_retry_with_same_idempotency_key_returns_original_payment(client, api_key):
    key = str(uuid.uuid4())
    payload = payment_payload()

    first = await create_payment(client, api_key, payload, idempotency_key=key)
    retry = await create_payment(client, api_key, payload, idempotency_key=key)

    assert first.status_code == 201
    assert retry.status_code == 201
    assert retry.json() == first.json()


async def test_same_idempotency_key_is_scoped_per_merchant(client, create_merchant):
    key = str(uuid.uuid4())
    merchant_a = await create_merchant("Merchant A")
    merchant_b = await create_merchant("Merchant B")

    payment_a = await create_payment(client, merchant_a, idempotency_key=key)
    payment_b = await create_payment(client, merchant_b, idempotency_key=key)

    assert payment_a.status_code == 201
    assert payment_b.status_code == 201
    assert payment_a.json()["id"] != payment_b.json()["id"]


async def test_merchant_cannot_read_another_merchants_payment(client, create_merchant):
    owner = await create_merchant("Owner")
    stranger = await create_merchant("Stranger")
    payment_id = (await create_payment(client, owner)).json()["id"]

    response = await client.get(f"/payments/{payment_id}", headers=auth_headers(stranger))

    assert response.status_code == 404
    assert response.json()["code"] == "payment_not_found"


# --- failure ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer sk_unknown_key", "Basic c2tfdGVzdA=="],
    ids=["missing", "unknown-key", "wrong-scheme"],
)
async def test_request_without_valid_api_key_is_unauthorized(client, api_key, authorization):
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    if authorization:
        headers["Authorization"] = authorization

    response = await client.post("/payments", json=payment_payload(), headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"code": "unauthorized", "message": "Invalid or missing API key"}


async def test_missing_idempotency_key_is_rejected(client, api_key):
    response = await client.post(
        "/payments",
        json=payment_payload(),
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "validation_error"
    assert {e["field"] for e in body["details"]["errors"]} == {"Idempotency-Key"}


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"card_number": "2222405343248"}, "card_number"),  # 13 digits
        ({"card_number": "22224053432488771234"}, "card_number"),  # 20 digits
        ({"card_number": "2222-4053-4324-8877"}, "card_number"),
        ({"card_number": 2222405343248877}, "card_number"),  # number, not string
        ({"expiry_month": 0}, "expiry_month"),
        ({"expiry_month": 13}, "expiry_month"),
        ({"expiry_month": 1, "expiry_year": NEXT_YEAR - 2}, "expiry_year"),  # expired
        ({"expiry_year": 99_999}, "expiry_year"),  # too large for the column
        ({"currency": "JPY"}, "currency"),
        ({"amount": 0}, "amount"),
        ({"amount": -100}, "amount"),
        ({"amount": 10**20}, "amount"),  # too large for the column
        ({"amount": "1050"}, "amount"),  # string, not integer
        ({"cvv": "12"}, "cvv"),
        ({"cvv": "12345"}, "cvv"),
        ({"cvv": "12a"}, "cvv"),
    ],
)
async def test_invalid_payment_request_is_rejected(client, api_key, overrides, field):
    payload = payment_payload(**overrides)

    response = await create_payment(client, api_key, payload)

    assert response.status_code == 400
    body = response.json()
    assert "status" not in body
    assert body["code"] == "validation_error"
    assert field in {e["field"] for e in body["details"]["errors"]}
    # Submitted card data is never echoed back in error responses.
    assert str(payload["card_number"]) not in response.text
    assert f'"{payload["cvv"]}"' not in response.text


@pytest.mark.parametrize("missing", list(payment_payload()))
async def test_payment_request_with_missing_field_is_rejected(client, api_key, missing):
    payload = payment_payload()
    del payload[missing]

    response = await create_payment(client, api_key, payload)

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert missing in {e["field"] for e in response.json()["details"]["errors"]}


async def test_unknown_field_is_rejected(client, api_key):
    response = await create_payment(client, api_key, payment_payload(merchant_id="someone-else"))

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


async def test_rejected_request_stores_nothing(client, api_key):
    key = str(uuid.uuid4())

    rejected = await create_payment(client, api_key, payment_payload(cvv="1"), key)
    corrected = await create_payment(client, api_key, payment_payload(), key)

    assert rejected.status_code == 400
    assert corrected.status_code == 201
    assert corrected.json()["status"] == "Authorized"


async def test_bank_unavailable_returns_503(client, api_key):
    response = await create_payment(
        client, api_key, payment_payload(card_number=BANK_UNAVAILABLE_CARD)
    )

    assert response.status_code == 503
    assert response.json()["code"] == "bank_unavailable"


async def test_bank_unavailable_releases_idempotency_key(client, api_key):
    key = str(uuid.uuid4())
    payload = payment_payload(card_number=BANK_UNAVAILABLE_CARD)

    first = await create_payment(client, api_key, payload, key)
    retry = await create_payment(client, api_key, payload, key)

    assert first.status_code == 503
    assert retry.status_code == 503
    assert retry.json()["code"] == "bank_unavailable"


async def test_reusing_idempotency_key_with_different_body_is_rejected(client, api_key):
    key = str(uuid.uuid4())
    first = await create_payment(client, api_key, payment_payload(amount=1050), key)

    reused = await create_payment(client, api_key, payment_payload(amount=9999), key)

    assert first.status_code == 201
    # IETF Idempotency-Key draft: same key + different payload -> 422.
    assert reused.status_code == 422
    # The original payment is untouched.
    fetched = await client.get(f"/payments/{first.json()['id']}", headers=auth_headers(api_key))
    assert fetched.json()["amount"] == 1050


# --- race condition -----------------------------------------------------------------


async def test_concurrent_requests_with_same_idempotency_key_create_one_payment(client, api_key):
    """N identical requests race on one Idempotency-Key.

    The unique (merchant_id, idempotency_key) constraint must surface as the same
    payment, either settled (201) or still pending (202), never as a 500 or as a
    second payment.
    """
    concurrency = 10
    key = str(uuid.uuid4())
    payload = payment_payload()

    responses = await asyncio.gather(
        *(create_payment(client, api_key, payload, key) for _ in range(concurrency))
    )

    statuses = [r.status_code for r in responses]
    assert set(statuses) <= {201, 202}, statuses
    assert 201 in statuses, f"no request settled the payment: {statuses}"
    payment_ids = {r.json()["id"] for r in responses}
    assert len(payment_ids) == 1, f"one key created several payments: {payment_ids}"

    # Once the race settles, a retry returns that same single payment.
    (payment_id,) = payment_ids
    retry = await create_payment(client, api_key, payload, key)
    assert retry.status_code == 201
    assert retry.json()["id"] == payment_id
    assert retry.json()["status"] == "Authorized"


# --- logging ------------------------------------------------------------------------


async def test_payment_logs_carry_request_context_without_card_data(client, api_key):
    payload = payment_payload()

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await create_payment(client, api_key, payload)

    processed, completed = (
        next(e for e in logs if e["event"] == name)
        for name in ("payment_processed", "request_completed")
    )
    assert str(processed["payment_id"]) == response.json()["id"]
    assert processed["request_id"] == response.headers["X-Request-ID"]
    assert processed["merchant_id"] == completed["merchant_id"]
    assert completed["status_code"] == 201
    assert payload["card_number"] not in str(logs)
