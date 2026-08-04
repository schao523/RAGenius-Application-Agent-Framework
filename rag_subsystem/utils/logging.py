"""Simple logging wrapper."""
from __future__ import annotations
import logging


LOGGER_NAME = "rag_subsystem"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(LOGGER_NAME)
