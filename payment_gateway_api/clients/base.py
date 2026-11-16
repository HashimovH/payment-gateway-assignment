from typing import Any, ClassVar, Self

import httpx

from payment_gateway_api.clients.exceptions import (
    ExternalServiceBadResponseError,
    ExternalServiceOutcomeUnknownError,
    ExternalServiceUnavailableError,
)

# The connection was never established, so the service never saw the request.
_NOT_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class BaseHTTPClient:
    """Shared httpx plumbing for external services.

    Turns httpx/HTTP failures into ExternalService* errors, split by whether the
    request may have been processed. No automatic retries: retrying a payment
    could charge the shopper twice.
    """

    service_name: ClassVar[str] = "external service"

    def __init__(
        self,
        base_url: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _post(
        self, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> Any:
        try:
            response = await self._client.post(path, json=payload, headers=headers)
        except _NOT_SENT_ERRORS as exc:
            raise ExternalServiceUnavailableError(
                self.service_name, str(exc) or "connection failed"
            ) from exc
        except httpx.TransportError as exc:
            raise ExternalServiceOutcomeUnknownError(
                self.service_name, str(exc) or "no response"
            ) from exc

        if response.status_code == httpx.codes.SERVICE_UNAVAILABLE:
            raise ExternalServiceUnavailableError(
                self.service_name, f"returned {response.status_code}", response.status_code
            )
        if response.is_server_error:
            raise ExternalServiceOutcomeUnknownError(
                self.service_name, f"returned {response.status_code}", response.status_code
            )
        if not response.is_success:
            raise ExternalServiceBadResponseError(
                self.service_name, f"returned {response.status_code}", response.status_code
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ExternalServiceOutcomeUnknownError(
                self.service_name, "response is not valid JSON", response.status_code
            ) from exc
