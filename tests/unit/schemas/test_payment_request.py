from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from payment_gateway_api.enums import Currency, PaymentStatus
from payment_gateway_api.schemas.payment_request import PaymentRequest, PaymentRequestResponse

NOW = datetime.now(UTC)


def valid_payload(**overrides) -> dict:
    payload = {
        "card_number": "2222405343248877",
        "expiry_month": 4,
        "expiry_year": NOW.year + 1,
        "currency": "GBP",
        "amount": 100,
        "cvv": "123",
    }
    payload.update(overrides)
    return payload


def assert_invalid(field: str, **overrides) -> None:
    with pytest.raises(ValidationError) as exc_info:
        PaymentRequest.model_validate(valid_payload(**overrides))
    failed_fields = {err["loc"][0] for err in exc_info.value.errors() if err["loc"]}
    assert field in failed_fields


def test_valid_request_is_accepted():
    request = PaymentRequest.model_validate(valid_payload())

    assert request.card_number == "2222405343248877"
    assert request.currency is Currency.GBP
    assert request.amount == 100


@pytest.mark.parametrize("card_number", ["1" * 14, "1" * 19, "01234567890123"])
def test_card_number_accepts_14_to_19_digits_including_leading_zero(card_number):
    assert PaymentRequest.model_validate(valid_payload(card_number=card_number))


@pytest.mark.parametrize(
    "card_number",
    [
        "1" * 13,                # too short
        "1" * 20,                # too long
        "2222 4053 4324 8877",   # spaces
        "2222-4053-4324-8877",   # dashes
        "22224053432488a7",      # letter
        "١٢٣٤٥٦٧٨٩٠١٢٣٤",        # non-ASCII digits
        2222405343248877,        # int, not string
    ],
)
def test_card_number_rejects_invalid_values(card_number):
    assert_invalid("card_number", card_number=card_number)


@pytest.mark.parametrize("month", [1, 12])
def test_expiry_month_accepts_1_to_12(month):
    assert PaymentRequest.model_validate(valid_payload(expiry_month=month))


@pytest.mark.parametrize("month", [0, 13, -1, "4", 4.0])
def test_expiry_month_rejects_out_of_range_and_non_integers(month):
    assert_invalid("expiry_month", expiry_month=month)


def test_card_expiring_this_month_is_accepted():
    assert PaymentRequest.model_validate(
        valid_payload(expiry_month=NOW.month, expiry_year=NOW.year)
    )


def test_card_that_expired_last_month_is_rejected():
    year, month = (NOW.year, NOW.month - 1) if NOW.month > 1 else (NOW.year - 1, 12)

    with pytest.raises(ValidationError, match="must be in the future"):
        PaymentRequest.model_validate(valid_payload(expiry_month=month, expiry_year=year))


def test_card_that_expired_last_year_is_rejected():
    with pytest.raises(ValidationError, match="must be in the future"):
        PaymentRequest.model_validate(valid_payload(expiry_month=12, expiry_year=NOW.year - 1))


@pytest.mark.parametrize("year", ["2030", 2030.0])
def test_expiry_year_rejects_non_integers(year):
    assert_invalid("expiry_year", expiry_year=year)



@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP"])
def test_supported_currencies_are_accepted(currency):
    assert PaymentRequest.model_validate(valid_payload(currency=currency)).currency == currency


@pytest.mark.parametrize("currency", ["JPY", "gbp", "GB", "GBPP", ""])
def test_unsupported_or_malformed_currency_is_rejected(currency):
    assert_invalid("currency", currency=currency)



@pytest.mark.parametrize("amount", [1, 1050, 10**12])
def test_amount_accepts_positive_integers(amount):
    assert PaymentRequest.model_validate(valid_payload(amount=amount)).amount == amount


@pytest.mark.parametrize("amount", [0, -1, 10.5, 10.0, "1050", True])
def test_amount_rejects_non_positive_and_non_integers(amount):
    assert_invalid("amount", amount=amount)

@pytest.mark.parametrize("cvv", ["123", "1234", "012"])
def test_cvv_accepts_3_or_4_digits_including_leading_zero(cvv):
    assert PaymentRequest.model_validate(valid_payload(cvv=cvv)).cvv == cvv


@pytest.mark.parametrize("cvv", ["12", "12345", "12a", " 123", 123])
def test_cvv_rejects_invalid_values(cvv):
    assert_invalid("cvv", cvv=cvv)


def test_card_number_and_cvv_are_hidden_from_repr():
    request = PaymentRequest.model_validate(valid_payload(cvv="987"))

    assert "2222405343248877" not in repr(request)
    assert "987" not in repr(request)


def test_card_number_last_four():
    request = PaymentRequest.model_validate(valid_payload(card_number="22224053432480123"))

    assert request.card_number_last_four == "0123"


PAYMENT_ID = "0bb07405-6d44-4b50-a14f-7ae0beff13ad"


def valid_response(**overrides) -> dict:
    response = {
        "id": PAYMENT_ID,
        "status": "Authorized",
        "card_number_last_four": "8877",
        "expiry_month": 4,
        "expiry_year": 2030,
        "currency": "GBP",
        "amount": 100,
    }
    response.update(overrides)
    return response


def test_payment_response_serializes_to_api_shape():
    response = PaymentRequestResponse.model_validate(valid_response(card_number_last_four="0123"))

    assert response.model_dump(mode="json") == valid_response(card_number_last_four="0123")


@pytest.mark.parametrize("status", ["Authorized", "Declined"])
def test_payment_response_accepts_bank_outcomes(status):
    assert PaymentRequestResponse.model_validate(valid_response(status=status)).status == status


@pytest.mark.parametrize("status", ["Rejected", "authorized", "Pending"])
def test_payment_response_rejects_other_statuses(status):
    with pytest.raises(ValidationError):
        PaymentRequestResponse.model_validate(valid_response(status=status))


def test_payment_response_has_no_full_card_number_or_cvv_fields():
    assert "card_number" not in PaymentRequestResponse.model_fields
    assert "cvv" not in PaymentRequestResponse.model_fields
