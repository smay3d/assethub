# src/assethub/core/utils/logging.py

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger with a basic configuration.

    Later we can wire this to log_root in the config.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

    return logger
