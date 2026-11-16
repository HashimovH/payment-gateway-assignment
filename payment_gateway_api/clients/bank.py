from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from payment_gateway_api.clients.base import BaseHTTPClient
from payment_gateway_api.clients.exceptions import ExternalServiceOutcomeUnknownError
from payment_gateway_api.schemas.payment_request import PaymentRequest


class BankPaymentRequest(BaseModel):
    """Body for the acquiring bank's POST /payments (the bank's format, not ours)."""

    model_config = ConfigDict(frozen=True)

    card_number: str = Field(repr=False)
    expiry_date: str  # "MM/YYYY"
    currency: str
    amount: int
    cvv: str = Field(repr=False)

    @classmethod
    def from_payment_request(cls, request: PaymentRequest) -> Self:
        return cls(
            card_number=request.card_number,
            expiry_date=f"{request.expiry_month:02d}/{request.expiry_year}",
            currency=request.currency,
            amount=request.amount,
            cvv=request.cvv,
        )


class BankPaymentResponse(BaseModel):
    """The bank's answer. Unknown extra fields are ignored (tolerant reader)."""

    model_config = ConfigDict(frozen=True)

    authorized: bool
    authorization_code: str | None = None

    @field_validator("authorization_code")
    @classmethod
    def empty_code_is_none(cls, code: str | None) -> str | None:
        # The bank sends "" for declined payments.
        return code or None


class BankClient(BaseHTTPClient):
    service_name = "acquiring bank"

    async def authorize_payment(self, request: PaymentRequest) -> BankPaymentResponse:
        payload = BankPaymentRequest.from_payment_request(request).model_dump()
        body = await self._post("/payments", payload)

        try:
            return BankPaymentResponse.model_validate(body)
        except ValidationError as exc:
            raise ExternalServiceOutcomeUnknownError(
                self.service_name, "unexpected response body"
            ) from exc
