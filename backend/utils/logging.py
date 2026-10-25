"""Logging guidance: request handlers log document IDs and safe error classes only."""

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
