from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field, StrictInt, ValidationInfo, field_validator

from payment_gateway_api.enums import Currency, PaymentStatus
from payment_gateway_api.schemas.base import SchemaBase

DIGITS_ONLY = r"^[0-9]+$"
MAX_AMOUNT = 999_999_999_999
MAX_EXPIRY_YEAR = 9999


class PaymentRequest(SchemaBase):
    card_number: str = Field(min_length=14, max_length=19, pattern=DIGITS_ONLY, repr=False)
    expiry_month: StrictInt = Field(ge=1, le=12)
    expiry_year: StrictInt = Field(le=MAX_EXPIRY_YEAR)
    currency: Currency
    amount: StrictInt = Field(gt=0, le=MAX_AMOUNT)
    cvv: str = Field(min_length=3, max_length=4, pattern=DIGITS_ONLY, repr=False)

    @field_validator("expiry_year")
    @classmethod
    def card_not_expired(cls, year: int, info: ValidationInfo) -> int:
        month = info.data.get("expiry_month")
        now = datetime.now(UTC)
        if month is not None and (year, month) < (now.year, now.month):
            raise ValueError("Card expiry date must be in the future")
        return year

    @property
    def card_number_last_four(self) -> str:
        return self.card_number[-4:]


class PaymentResponse(SchemaBase):
    id: UUID
    status: PaymentStatus
    card_number_last_four: str = Field(min_length=4, max_length=4, pattern=DIGITS_ONLY)
    expiry_month: int
    expiry_year: int
    currency: Currency
    amount: int = Field(description="Amount in minor currency units, e.g. 1050 = 10.50")
