"""Turns every error into the unified ErrorResponse body.

- GatewayError            -> its own status / code / message
- RequestValidationError  -> 400 validation_error, offending fields listed
- HTTPException           -> fallback for framework errors (404 route, 405, ...)
- anything else           -> 500 internal_error, logged, no internals leaked
"""

from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from payment_gateway_api.exceptions import GatewayError
from payment_gateway_api.schemas.errors import ErrorResponse

logger = structlog.get_logger(__name__)

# Where a value came from; dropped from the field name ("body.amount" -> "amount").
_LOCATIONS = {"body", "query", "path", "header", "cookie"}


def error_response(
    http_status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details)
    return JSONResponse(
        status_code=http_status,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


def _field_name(loc: tuple[int | str, ...]) -> str:
    parts = [str(part) for part in loc]
    if parts and parts[0] in _LOCATIONS:
        parts = parts[1:]
    return ".".join(parts) or "request"


async def handle_gateway_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, GatewayError)
    return error_response(exc.http_status, exc.error_code, exc.message, exc.details, exc.headers)


async def handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Only field + message: pydantic's "input" would echo card numbers / CVVs back.
    errors = [
        {"field": _field_name(error["loc"]), "message": error["msg"]} for error in exc.errors()
    ]
    return error_response(
        status.HTTP_400_BAD_REQUEST,
        "validation_error",
        "Request validation failed",
        {"errors": errors},
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    try:
        phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:  # non-standard status code
        phrase = "Error"
    code = phrase.lower().replace(" ", "_").replace("-", "_")  # "Not Found" -> "not_found"
    message = exc.detail if isinstance(exc.detail, str) else phrase
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error")
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        GatewayError.error_code,
        GatewayError.default_message,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(GatewayError, handle_gateway_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
