"""
Logger configuration using loguru
  . Configures loguru with a single structured (JSON) sink to stdout
  . Log level is controlled by the LOG_LEVEL environment variable (default INFO)
  . No file sink: the container filesystem is ephemeral; logs go to stdout so Fly
    (or any log collector) can capture them
  . diagnose/backtrace disabled to avoid leaking variable values into logs
  Functions/Classes:
    . logger
"""

import os
import sys

from loguru import logger

__all__ = ["logger"]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logger.remove()
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    serialize=True,
    backtrace=False,
    diagnose=False,
    enqueue=False,
)
