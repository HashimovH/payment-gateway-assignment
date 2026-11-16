"""PaymentRepository against a real Postgres."""

import pytest

from payment_gateway_api.auth import hash_api_key
from payment_gateway_api.db import get_session_factory
from payment_gateway_api.enums import Currency, PaymentStatus
from payment_gateway_api.repositories.merchants import MerchantRepository
from payment_gateway_api.repositories.payments import PaymentRepository

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_reads_return_the_stored_row_not_a_stale_session_copy(client, api_key):
    async with get_session_factory()() as session, get_session_factory()() as other_session:
        merchant = await MerchantRepository(session).get_active_by_api_key_hash(
            hash_api_key(api_key)
        )
        assert merchant is not None
        payments = PaymentRepository(session)
        payment = await payments.create_pending_if_absent(
            merchant_id=merchant.id,
            idempotency_key="key-1",
            request_fingerprint="fingerprint",
            card_number_last_four="8877",
            expiry_month=4,
            expiry_year=2099,
            currency=Currency.GBP,
            amount=1050,
        )
        assert payment is not None
        assert payment.status is PaymentStatus.PENDING

        settled = await PaymentRepository(other_session).set_outcome(
            payment.id, PaymentStatus.DECLINED, None
        )
        assert settled is not None

        assert await payments.set_outcome(payment.id, PaymentStatus.AUTHORIZED, "code") is None
        by_id = await payments.get_by_id_for_merchant(payment.id, merchant.id)
        by_key = await payments.get_by_idempotency_key(merchant.id, "key-1")
        assert by_id is not None
        assert by_id.status is PaymentStatus.DECLINED
        assert by_key is not None
        assert by_key.status is PaymentStatus.DECLINED
