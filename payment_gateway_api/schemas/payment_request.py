from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, StrictInt, model_validator

from payment_gateway_api.enums import Currency, PaymentStatus
from payment_gateway_api.schemas.base import SchemaBase

DIGITS_ONLY = r"^[0-9]+$"


class PaymentRequest(SchemaBase):
    card_number: str = Field(min_length=14, max_length=19, pattern=DIGITS_ONLY, repr=False)
    expiry_month: StrictInt = Field(ge=1, le=12)
    expiry_year: StrictInt
    currency: Currency
    amount: StrictInt = Field(gt=0)
    cvv: str = Field(min_length=3, max_length=4, pattern=DIGITS_ONLY, repr=False)

    @model_validator(mode="after")
    def card_not_expired(self) -> Self:
        now = datetime.now(UTC)
        if (self.expiry_year, self.expiry_month) < (now.year, now.month):
            raise ValueError("Card expiry date must be in the future")
        return self

    @property
    def card_number_last_four(self) -> str:
        return self.card_number[-4:]


class PaymentResponse(SchemaBase):
    id: UUID
    status: Literal[PaymentStatus.AUTHORIZED, PaymentStatus.DECLINED]
    card_number_last_four: str = Field(min_length=4, max_length=4, pattern=DIGITS_ONLY)
    expiry_month: int
    expiry_year: int
    currency: Currency
    amount: int = Field(description="Amount in minor currency units, e.g. 1050 = 10.50")
