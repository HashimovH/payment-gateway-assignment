import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import OperationalError
from structlog.testing import capture_logs

from payment_gateway_api.clients.bank import BankPaymentResponse
from payment_gateway_api.clients.exceptions import (
    ExternalServiceBadResponseError,
    ExternalServiceOutcomeUnknownError,
    ExternalServiceUnavailableError,
)
from payment_gateway_api.enums import Currency, PaymentStatus
from payment_gateway_api.exceptions import (
    BankBadResponseError,
    BankUnavailableError,
    IdempotencyKeyReusedError,
    PaymentInProgressError,
)
from payment_gateway_api.models.payment import Payment
from payment_gateway_api.schemas.payment_request import PaymentRequest
from payment_gateway_api.services.payments import PaymentService, request_fingerprint

pytestmark = pytest.mark.anyio

MERCHANT_ID = uuid.uuid4()
KEY = "key-1"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_request(**overrides) -> PaymentRequest:
    payload = {
        "card_number": "2222405343248877",
        "expiry_month": 4,
        "expiry_year": datetime.now(UTC).year + 1,
        "currency": "GBP",
        "amount": 1050,
        "cvv": "123",
    }
    payload.update(overrides)
    return PaymentRequest.model_validate(payload)


def db_error() -> OperationalError:
    return OperationalError("UPDATE payments ...", {}, Exception("connection lost"))


class FakePaymentRepository:
    def __init__(self, set_outcome_failures: int = 0, delete_fails: bool = False) -> None:
        self.rows: dict[tuple[uuid.UUID, str], Payment] = {}
        self.set_outcome_calls = 0
        self.rollbacks = 0
        self._set_outcome_failures = set_outcome_failures
        self._delete_fails = delete_fails

    async def create_pending_if_absent(self, *, merchant_id, idempotency_key, **values):
        if (merchant_id, idempotency_key) in self.rows:
            return None
        payment = Payment(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            status=PaymentStatus.PENDING,
            authorization_code=None,
            **values,
        )
        self.rows[merchant_id, idempotency_key] = payment
        return payment

    async def get_by_idempotency_key(self, merchant_id, key):
        return self.rows.get((merchant_id, key))

    async def get_by_id_for_merchant(self, payment_id, merchant_id):
        return next(
            (p for p in self.rows.values() if p.id == payment_id and p.merchant_id == merchant_id),
            None,
        )

    async def set_outcome(self, payment_id, status, authorization_code):
        self.set_outcome_calls += 1
        if self.set_outcome_calls <= self._set_outcome_failures:
            raise db_error()
        payment = next(p for p in self.rows.values() if p.id == payment_id)
        if payment.status is not PaymentStatus.PENDING:
            return None
        payment.status = status
        payment.authorization_code = authorization_code
        return payment

    async def delete_pending(self, payment_id):
        if self._delete_fails:
            raise db_error()
        self.rows = {
            k: p
            for k, p in self.rows.items()
            if not (p.id == payment_id and p.status is PaymentStatus.PENDING)
        }

    async def rollback(self):
        self.rollbacks += 1


class FakeBank:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.calls = 0
        self._response = response or BankPaymentResponse(
            authorized=True, authorization_code="auth-123"
        )
        self._error = error
        self.references: list[uuid.UUID] = []

    async def authorize_payment(self, _request, *, reference):
        self.calls += 1
        self.references.append(reference)
        if self._error:
            raise self._error
        return self._response


def make_service(repo, bank) -> PaymentService:
    return PaymentService(repo, bank, save_retry_delay_seconds=0)


# --- fingerprint --------------------------------------------------------------------


def test_fingerprint_is_stable_and_excludes_card_secrets():
    request = make_request()

    assert request_fingerprint(request) == request_fingerprint(make_request())
    assert request_fingerprint(request) == request_fingerprint(
        make_request(card_number="4111111111118877", cvv="999")
    )


@pytest.mark.parametrize(
    "override", [{"amount": 1}, {"currency": "USD"}, {"expiry_month": 5}, {"card_number": "1" * 16}]
)
def test_fingerprint_changes_with_payment_details(override):
    assert request_fingerprint(make_request()) != request_fingerprint(make_request(**override))


# --- outcomes -----------------------------------------------------------------------


async def test_authorized_payment_is_stored_with_code():
    repo = FakePaymentRepository()

    response = await make_service(repo, FakeBank()).process_payment(
        make_request(), MERCHANT_ID, KEY
    )

    assert response.status is PaymentStatus.AUTHORIZED
    assert repo.rows[MERCHANT_ID, KEY].authorization_code == "auth-123"
    assert response.card_number_last_four == "8877"
    assert response.currency is Currency.GBP


async def test_declined_payment_is_stored_without_code():
    repo = FakePaymentRepository()
    bank = FakeBank(BankPaymentResponse(authorized=False, authorization_code=""))

    response = await make_service(repo, bank).process_payment(make_request(), MERCHANT_ID, KEY)

    assert response.status is PaymentStatus.DECLINED
    assert repo.rows[MERCHANT_ID, KEY].authorization_code is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ExternalServiceUnavailableError("bank", "returned 503", 503), BankUnavailableError),
        (ExternalServiceUnavailableError("bank", "connection refused"), BankUnavailableError),
        (ExternalServiceBadResponseError("bank", "returned 400", 400), BankBadResponseError),
    ],
)
async def test_bank_failure_before_processing_releases_the_key(error, expected):
    repo = FakePaymentRepository()

    with pytest.raises(expected):
        await make_service(repo, FakeBank(error=error)).process_payment(
            make_request(), MERCHANT_ID, KEY
        )

    assert repo.rows == {}


@pytest.mark.parametrize(
    "bank",
    [
        FakeBank(error=ExternalServiceOutcomeUnknownError("bank", "timed out")),
        FakeBank(error=ExternalServiceOutcomeUnknownError("bank", "returned 500", 500)),
        FakeBank(error=ExternalServiceOutcomeUnknownError("bank", "not JSON", 200)),
        FakeBank(BankPaymentResponse(authorized=True, authorization_code="")),
    ],
    ids=["timeout", "server-error", "unreadable-body", "authorized-without-code"],
)
async def test_unknown_bank_outcome_keeps_payment_pending(bank):
    repo = FakePaymentRepository()

    response = await make_service(repo, bank).process_payment(make_request(), MERCHANT_ID, KEY)

    assert response.status is PaymentStatus.PENDING
    assert repo.rows[MERCHANT_ID, KEY].status is PaymentStatus.PENDING
    assert repo.set_outcome_calls == 0


async def test_retry_after_unknown_bank_outcome_returns_pending_without_charging_again():
    repo = FakePaymentRepository()
    bank = FakeBank(error=ExternalServiceOutcomeUnknownError("bank", "timed out"))
    service = make_service(repo, bank)
    first = await service.process_payment(make_request(), MERCHANT_ID, KEY)

    retry = await service.process_payment(make_request(), MERCHANT_ID, KEY)

    assert retry == first
    assert retry.status is PaymentStatus.PENDING
    assert bank.calls == 1


@pytest.mark.parametrize(
    "error",
    [
        ExternalServiceUnavailableError("bank", "returned 503", 503),
        ExternalServiceBadResponseError("bank", "returned 400", 400),
    ],
)
async def test_failed_key_release_keeps_payment_pending(error):
    repo = FakePaymentRepository(delete_fails=True)

    with capture_logs() as logs:
        response = await make_service(repo, FakeBank(error=error)).process_payment(
            make_request(), MERCHANT_ID, KEY
        )

    assert response.status is PaymentStatus.PENDING
    assert repo.rows[MERCHANT_ID, KEY].status is PaymentStatus.PENDING
    assert repo.rollbacks == 1
    assert any(e["event"] == "idempotency_key_release_failed" for e in logs)


async def test_bank_receives_the_payment_id_as_reference():
    repo, bank = FakePaymentRepository(), FakeBank()

    response = await make_service(repo, bank).process_payment(make_request(), MERCHANT_ID, KEY)

    assert bank.references == [response.id]


# --- idempotency --------------------------------------------------------------------


async def test_replay_returns_stored_payment_without_calling_bank_again():
    repo, bank = FakePaymentRepository(), FakeBank()
    service = make_service(repo, bank)

    first = await service.process_payment(make_request(), MERCHANT_ID, KEY)
    replay = await service.process_payment(make_request(), MERCHANT_ID, KEY)

    assert replay == first
    assert bank.calls == 1


async def test_reused_key_with_different_request_is_rejected():
    repo, bank = FakePaymentRepository(), FakeBank()
    service = make_service(repo, bank)
    await service.process_payment(make_request(amount=1050), MERCHANT_ID, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await service.process_payment(make_request(amount=9999), MERCHANT_ID, KEY)
    assert bank.calls == 1


async def test_key_of_pending_payment_returns_it_as_pending():
    repo, bank = FakePaymentRepository(), FakeBank()
    request = make_request()
    await repo.create_pending_if_absent(
        merchant_id=MERCHANT_ID,
        idempotency_key=KEY,
        request_fingerprint=request_fingerprint(request),
        card_number_last_four="8877",
        expiry_month=4,
        expiry_year=request.expiry_year,
        currency=Currency.GBP,
        amount=1050,
    )

    response = await make_service(repo, bank).process_payment(request, MERCHANT_ID, KEY)

    assert response.status is PaymentStatus.PENDING
    assert bank.calls == 0


async def test_key_released_between_insert_and_read_is_in_progress():
    class VanishingRowRepository(FakePaymentRepository):
        async def create_pending_if_absent(self, **_values):
            return None

    with pytest.raises(PaymentInProgressError):
        await make_service(VanishingRowRepository(), FakeBank()).process_payment(
            make_request(), MERCHANT_ID, KEY
        )


async def test_get_pending_payment_returns_it_as_pending():
    repo = FakePaymentRepository()
    payment = await repo.create_pending_if_absent(
        merchant_id=MERCHANT_ID,
        idempotency_key=KEY,
        request_fingerprint="x",
        card_number_last_four="8877",
        expiry_month=4,
        expiry_year=2099,
        currency=Currency.GBP,
        amount=1050,
    )

    response = await make_service(repo, FakeBank()).get_payment(payment.id, MERCHANT_ID)

    assert response.id == payment.id
    assert response.status is PaymentStatus.PENDING


# --- saving the bank outcome --------------------------------------------------------


async def test_outcome_save_is_retried_after_transient_db_failure():
    repo, bank = FakePaymentRepository(set_outcome_failures=2), FakeBank()

    response = await make_service(repo, bank).process_payment(make_request(), MERCHANT_ID, KEY)

    assert response.status is PaymentStatus.AUTHORIZED
    assert repo.set_outcome_calls == 3
    assert repo.rollbacks == 2
    assert bank.calls == 1


async def test_outcome_save_gives_up_and_logs_audit_record():
    repo, bank = FakePaymentRepository(set_outcome_failures=99), FakeBank()

    with capture_logs() as logs, pytest.raises(OperationalError):
        await make_service(repo, bank).process_payment(make_request(), MERCHANT_ID, KEY)

    assert repo.set_outcome_calls == 3
    assert bank.calls == 1
    assert repo.rows[MERCHANT_ID, KEY].status is PaymentStatus.PENDING
    audit = [e for e in logs if e["event"] == "payment_outcome_not_saved"]
    assert len(audit) == 1
    assert audit[0]["authorization_code"] == "auth-123"
    assert audit[0]["status"] is PaymentStatus.AUTHORIZED
    assert "2222405343248877" not in str(logs)
