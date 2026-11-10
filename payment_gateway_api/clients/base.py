from typing import Any, ClassVar, Self

import httpx

from payment_gateway_api.clients.exceptions import (
    ExternalServiceBadResponseError,
    ExternalServiceUnavailableError,
)


class BaseHTTPClient:
    """Shared httpx plumbing for external services.

    Turns httpx/HTTP failures into ExternalService* errors. No automatic
    retries: retrying a payment could charge the shopper twice.
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

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.TransportError as exc:  # timeouts, connection errors
            raise ExternalServiceUnavailableError(
                self.service_name, str(exc) or "no response"
            ) from exc

        if response.is_server_error:
            raise ExternalServiceUnavailableError(
                self.service_name, f"returned {response.status_code}", response.status_code
            )
        if not response.is_success:
            raise ExternalServiceBadResponseError(
                self.service_name, f"returned {response.status_code}", response.status_code
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ExternalServiceBadResponseError(
                self.service_name, "response is not valid JSON", response.status_code
            ) from exc
