"""Application errors.

Raise a GatewayError subclass anywhere (service, dependency); the handlers in
exception_handlers.py turn it into the unified ErrorResponse body. Each
`error_code` is part of the public API: keep it stable once released.
"""

from typing import Any, ClassVar

from fastapi import status


class GatewayError(Exception):
    http_status: ClassVar[int] = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: ClassVar[str] = "internal_error"
    default_message: ClassVar[str] = "Internal server error"
    headers: ClassVar[dict[str, str] | None] = None

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class UnauthorizedError(GatewayError):
    http_status = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthorized"
    default_message = "Invalid or missing API key"
    headers = {"WWW-Authenticate": "Bearer"}


class PaymentNotFoundError(GatewayError):
    http_status = status.HTTP_404_NOT_FOUND
    error_code = "payment_not_found"
    default_message = "Payment not found"


class PaymentInProgressError(GatewayError):
    http_status = status.HTTP_409_CONFLICT
    error_code = "payment_in_progress"
    default_message = "A payment with this Idempotency-Key is still being processed, retry later"
    headers = {"Retry-After": "1"}


class IdempotencyKeyReusedError(GatewayError):
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "idempotency_key_reused"
    default_message = "This Idempotency-Key was already used with a different request"


class BankUnavailableError(GatewayError):
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "bank_unavailable"
    default_message = "Bank is temporarily unavailable, retry with the same Idempotency-Key"


class BankBadResponseError(GatewayError):
    http_status = status.HTTP_502_BAD_GATEWAY
    error_code = "bank_bad_response"
    default_message = "Bank returned an unexpected response"
