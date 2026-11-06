import logging
import sys
import traceback

import structlog

from app.core.config import Settings


def safe_exception(logger, method_name, event_dict):
    """Retain stack locations without exception messages, source lines or locals."""
    exc_info = event_dict.pop("exc_info", None)
    if exc_info:
        if exc_info is True:
            exc_info = sys.exc_info()
        elif isinstance(exc_info, BaseException):
            exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
        exc_type, _, tb = exc_info
        if exc_type is not None:
            event_dict["exception"] = {
                "type": exc_type.__name__,
                "frames": [
                    {"file": f.filename, "line": f.lineno, "function": f.name}
                    for f in traceback.extract_tb(tb)
                ],
            }
    return event_dict


def configure_logging():
    production = Settings().app_env == "production"
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        safe_exception,
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer()
            if production
            else structlog.dev.ConsoleRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    structlog.configure(
        processors=[
            *processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger():
    return structlog.get_logger()
