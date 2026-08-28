"""
SONIC-REDA — Logging Utility
===============================
Provides a structured logger with fallback to standard library logging
if structlog is not yet installed.
"""

from __future__ import annotations

import logging
from typing import Any

try:
    import structlog

    def get_logger(name: str = "sonic"):
        return structlog.get_logger(name)

except ImportError:
    # Standard library logging fallback wrapper with kwarg support
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    class FallbackLogger:
        def __init__(self, name: str):
            self._logger = logging.getLogger(name)

        def _format_msg(self, event: str, kwargs: dict[str, Any]) -> str:
            if kwargs:
                extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
                return f"{event} | {extra}"
            return event

        def info(self, event: str, **kwargs: Any):
            self._logger.info(self._format_msg(event, kwargs))

        def warning(self, event: str, **kwargs: Any):
            self._logger.warning(self._format_msg(event, kwargs))

        def error(self, event: str, **kwargs: Any):
            self._logger.error(self._format_msg(event, kwargs))

        def debug(self, event: str, **kwargs: Any):
            self._logger.debug(self._format_msg(event, kwargs))

    def get_logger(name: str = "sonic"):
        return FallbackLogger(name)
