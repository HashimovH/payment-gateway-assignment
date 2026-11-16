class ExternalServiceError(Exception):
    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service}: {message}")


class ExternalServiceUnavailableError(ExternalServiceError):
    """The service did not process the request, so it is safe to send again."""


class ExternalServiceBadResponseError(ExternalServiceError):
    """The service rejected the request."""


class ExternalServiceOutcomeUnknownError(ExternalServiceError):
    """The request may have been processed: sending it again could repeat it."""
