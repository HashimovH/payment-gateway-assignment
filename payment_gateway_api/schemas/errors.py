from typing import Any

from payment_gateway_api.schemas.base import SchemaBase


class ErrorResponse(SchemaBase):
    code: str
    message: str
    details: dict[str, Any] | None = None
