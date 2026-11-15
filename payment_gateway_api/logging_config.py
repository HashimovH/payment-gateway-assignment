import logging
import sys

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

from payment_gateway_api.config import Settings

SENSITIVE_KEYS = frozenset({"card_number", "cvv", "api_key", "authorization", "password"})
REDACTED = "[REDACTED]"


def redact_sensitive(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    for key in SENSITIVE_KEYS & event_dict.keys():
        event_dict[key] = REDACTED
    return event_dict


def drop_color_message(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    event_dict.pop("color_message", None)  # uvicorn's ANSI-coloured duplicate of "event"
    return event_dict


def configure_logging(settings: Settings) -> None:
    json_output = (settings.log_format or _default_format(settings)) == "json"

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive,
    ]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    renderer: list[Processor] = (
        [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer(default=str)]
        if json_output
        else [structlog.dev.ConsoleRenderer()]
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*shared, structlog.stdlib.ExtraAdder(), drop_color_message],
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _default_format(settings: Settings) -> str:
    return "console" if settings.environment == "local" else "json"
