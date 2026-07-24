"""Logging configuration for the toy service."""

import logging


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Set up and return the root application logger."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("toyapp")
