"""Logging utilities for the bot.

This module centralizes logging configuration so every component shares
consistent formatting and log levels. Use :func:`get_logger` instead of
creating ad-hoc loggers to avoid duplicate configuration in tests and
runtime.
"""

from __future__ import annotations

import logging
import os
from typing import Optional


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s]: %(message)s"


def configure_logging(level: Optional[str] = None) -> None:
    """Initialize root logger configuration.

    Parameters
    ----------
    level: Optional[str]
        Explicit log level. When omitted, the ``LOG_LEVEL`` environment
        variable is used, defaulting to ``INFO``.
    """

    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(level=resolved_level, format=LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger with the shared configuration."""

    return logging.getLogger(name)
