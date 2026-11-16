import asyncio
import contextlib
import hashlib
import json
import uuid

import structlog
from sqlalchemy.exc import DBAPIError

from payment_gateway_api.clients.bank import BankClient, BankPaymentResponse
from payment_gateway_api.clients.exceptions import (
    ExternalServiceBadResponseError,
    ExternalServiceOutcomeUnknownError,
    ExternalServiceUnavailableError,
)
from payment_gateway_api.dependencies.idempotency import IdempotencyKeyValue
from payment_gateway_api.enums import PaymentStatus
from payment_gateway_api.exceptions import (
    BankBadResponseError,
    BankUnavailableError,
    IdempotencyKeyReusedError,
    PaymentInProgressError,
    PaymentNotFoundError,
)
from payment_gateway_api.models.payment import Payment
from payment_gateway_api.repositories.payments import PaymentRepository
from payment_gateway_api.schemas.payment_request import PaymentRequest, PaymentResponse

logger = structlog.get_logger(__name__)


def request_fingerprint(data: PaymentRequest) -> str:
    # No full card number or CVV: their hashes are sensitive data too (PCI DSS).
    canonical = json.dumps(
        {
            "card_number_last_four": data.card_number_last_four,
            "expiry_month": data.expiry_month,
            "expiry_year": data.expiry_year,
            "currency": data.currency,
            "amount": data.amount,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class PaymentService:
    def __init__(
        self,
        payments: PaymentRepository,
        bank_client: BankClient,
        *,
        save_attempts: int = 3,
        save_retry_delay_seconds: float = 0.1,
    ) -> None:
        self._payments = payments
        self._bank_client = bank_client
        self._save_attempts = save_attempts
        self._save_retry_delay_seconds = save_retry_delay_seconds

    async def get_payment(self, payment_id: uuid.UUID, merchant_id: uuid.UUID) -> PaymentResponse:
        payment = await self._payments.get_by_id_for_merchant(payment_id, merchant_id)
        if payment is None:
            raise PaymentNotFoundError(details={"payment_id": str(payment_id)})
        return PaymentResponse.model_validate(payment)

    async def process_payment(
        self,
        data: PaymentRequest,
        merchant_id: uuid.UUID,
        idempotency_key: IdempotencyKeyValue,
    ) -> PaymentResponse:
        fingerprint = request_fingerprint(data)
        payment = await self._payments.create_pending_if_absent(
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            card_number_last_four=data.card_number_last_four,
            expiry_month=data.expiry_month,
            expiry_year=data.expiry_year,
            currency=data.currency,
            amount=data.amount,
        )
        if payment is None:
            return await self._replay(merchant_id, idempotency_key, fingerprint)

        bank_response = await self._authorize(payment, data)
        if bank_response is None:
            return PaymentResponse.model_validate(payment)

        status = PaymentStatus.AUTHORIZED if bank_response.authorized else PaymentStatus.DECLINED
        code = bank_response.authorization_code if bank_response.authorized else None
        saved = await self._save_outcome(payment, status, code)
        logger.info(
            "payment_processed",
            payment_id=saved.id,
            status=saved.status,
            amount=saved.amount,
            currency=saved.currency,
        )
        return PaymentResponse.model_validate(saved)

    async def _replay(
        self, merchant_id: uuid.UUID, idempotency_key: IdempotencyKeyValue, fingerprint: str
    ) -> PaymentResponse:
        existing = await self._payments.get_by_idempotency_key(merchant_id, idempotency_key)
        if existing is None:
            raise PaymentInProgressError()
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyKeyReusedError()
        if existing.status is PaymentStatus.PENDING:
            raise PaymentInProgressError(details={"payment_id": str(existing.id)})
        logger.info("payment_replayed", payment_id=existing.id, status=existing.status)
        return PaymentResponse.model_validate(existing)

    async def _authorize(
        self, payment: Payment, data: PaymentRequest
    ) -> BankPaymentResponse | None:
        try:
            response = await self._bank_client.authorize_payment(data)
        except ExternalServiceUnavailableError as exc:
            logger.warning("bank_unavailable", payment_id=payment.id, error=str(exc))
            await self._release(payment)
            raise BankUnavailableError() from exc
        except ExternalServiceBadResponseError as exc:
            logger.error("bank_bad_response", payment_id=payment.id, error=str(exc))
            await self._release(payment)
            raise BankBadResponseError() from exc
        except ExternalServiceOutcomeUnknownError as exc:
            logger.error("bank_outcome_unknown", payment_id=payment.id, error=str(exc))
            return None

        if response.authorized and not response.authorization_code:
            logger.error("bank_authorized_without_code", payment_id=payment.id)
            return None
        return response

    async def _release(self, payment: Payment) -> None:
        try:
            await self._payments.delete_pending(payment.id)
        except DBAPIError:
            logger.exception("idempotency_key_release_failed", payment_id=payment.id)

    async def _save_outcome(
        self, payment: Payment, status: PaymentStatus, authorization_code: str | None
    ) -> Payment:
        for attempt in range(1, self._save_attempts + 1):
            try:
                saved = await self._payments.set_outcome(payment.id, status, authorization_code)
            except DBAPIError:
                with contextlib.suppress(DBAPIError):
                    await self._payments.rollback()
                if attempt == self._save_attempts:
                    logger.exception(
                        "payment_outcome_not_saved",
                        payment_id=payment.id,
                        status=status,
                        authorization_code=authorization_code,
                    )
                    raise
                logger.warning(
                    "payment_outcome_save_retry",
                    payment_id=payment.id,
                    attempt=attempt,
                    max_attempts=self._save_attempts,
                )
                await asyncio.sleep(self._save_retry_delay_seconds * 2 ** (attempt - 1))
                continue

            if saved is None:
                saved = await self._payments.get_by_id_for_merchant(payment.id, payment.merchant_id)
                assert saved is not None
            return saved

        raise AssertionError("unreachable")
