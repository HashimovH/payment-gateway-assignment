import uuid
from datetime import UTC, datetime

import httpx
import pytest

from payment_gateway_api.clients.bank import BankClient
from payment_gateway_api.clients.exceptions import (
    ExternalServiceBadResponseError,
    ExternalServiceOutcomeUnknownError,
    ExternalServiceUnavailableError,
)
from payment_gateway_api.schemas.payment_request import PaymentRequest

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


REQUEST = PaymentRequest.model_validate(
    {
        "card_number": "2222405343248877",
        "expiry_month": 4,
        "expiry_year": datetime.now(UTC).year + 1,
        "currency": "GBP",
        "amount": 1050,
        "cvv": "123",
    }
)


def raising(error: type[httpx.TransportError]):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("boom", request=request)

    return handler


def responding(status_code: int, **kwargs):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, **kwargs)

    return handler


async def authorize(handler) -> None:
    transport = httpx.MockTransport(handler)
    async with BankClient("http://bank", timeout=1, transport=transport) as client:
        await client.authorize_payment(REQUEST, reference=uuid.uuid4())


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (raising(httpx.ConnectError), ExternalServiceUnavailableError),
        (raising(httpx.ConnectTimeout), ExternalServiceUnavailableError),
        (responding(503), ExternalServiceUnavailableError),
        (responding(400, json={}), ExternalServiceBadResponseError),
        (raising(httpx.ReadTimeout), ExternalServiceOutcomeUnknownError),
        (raising(httpx.ReadError), ExternalServiceOutcomeUnknownError),
        (raising(httpx.WriteTimeout), ExternalServiceOutcomeUnknownError),
        (responding(500), ExternalServiceOutcomeUnknownError),
        (responding(504), ExternalServiceOutcomeUnknownError),
        (responding(200, text="not json"), ExternalServiceOutcomeUnknownError),
        (responding(200, json={"unexpected": True}), ExternalServiceOutcomeUnknownError),
    ],
    ids=[
        "connect-error",
        "connect-timeout",
        "503",
        "400",
        "read-timeout",
        "read-error",
        "write-timeout",
        "500",
        "504",
        "invalid-json",
        "unexpected-body",
    ],
)
async def test_failures_are_classified_by_whether_the_bank_may_have_processed(handler, expected):
    with pytest.raises(expected):
        await authorize(handler)


async def test_authorized_response_is_parsed():
    transport = httpx.MockTransport(
        responding(200, json={"authorized": True, "authorization_code": "abc"})
    )
    async with BankClient("http://bank", timeout=1, transport=transport) as client:
        response = await client.authorize_payment(REQUEST, reference=uuid.uuid4())

    assert response.authorized
    assert response.authorization_code == "abc"


async def test_payment_id_is_sent_as_idempotency_key():
    reference = uuid.uuid4()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"authorized": False, "authorization_code": ""})

    async with BankClient("http://bank", timeout=1, transport=httpx.MockTransport(handler)) as c:
        await c.authorize_payment(REQUEST, reference=reference)

    assert seen[0].headers["Idempotency-Key"] == str(reference)
