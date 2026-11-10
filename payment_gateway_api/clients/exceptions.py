class ExternalServiceError(Exception):
    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service}: {message}")


class ExternalServiceUnavailableError(ExternalServiceError):
    pass


class ExternalServiceBadResponseError(ExternalServiceError):
    pass
