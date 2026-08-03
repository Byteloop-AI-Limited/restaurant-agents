"""
Logger configuration using loguru.

  . Configures one readable stdout sink; colours are enabled automatically for
    interactive terminals and omitted for log collectors.
  . Set LOG_FORMAT=json when a structured JSON sink is required.
  . Set LOG_COLORIZE=true to force ANSI colour when a terminal viewer supports it.
  . Set UVICORN_ACCESS_LOG=true to restore successful inbound request lines.
  . Set HTTPX_LOG_LEVEL=INFO to restore successful outbound HTTP request lines.
  . Log level is controlled by the LOG_LEVEL environment variable (default INFO)
  . No file sink: the container filesystem is ephemeral; logs go to stdout so Fly
    (or any log collector) can capture them
  . diagnose/backtrace disabled to avoid leaking variable values into logs
  Functions/Classes:
    . logger
"""

import os
import sys
import logging

from loguru import logger

__all__ = ["logger"]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "pretty").lower()

_PRETTY_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def _is_enabled(name: str, *, default: bool) -> bool:
    """Read a conventional boolean environment variable."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _colorize_setting() -> bool | None:
    """Use terminal detection unless colour output is explicitly requested."""

    if os.getenv("LOG_COLORIZE", "auto").strip().lower() == "auto":
        return None
    return _is_enabled("LOG_COLORIZE", default=False)


def _configure_library_loggers() -> None:
    """Keep routine successful HTTP traffic from obscuring application failures."""

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.disabled = not _is_enabled("UVICORN_ACCESS_LOG", default=False)

    httpx_level = os.getenv("HTTPX_LOG_LEVEL", "WARNING").upper()
    logging.getLogger("httpx").setLevel(httpx_level)
    logging.getLogger("httpcore").setLevel(httpx_level)


_configure_library_loggers()

logger.remove()
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format=_PRETTY_FORMAT if LOG_FORMAT == "pretty" else "{message}",
    serialize=LOG_FORMAT == "json",
    colorize=_colorize_setting(),
    backtrace=False,
    diagnose=False,
    enqueue=False,
)
