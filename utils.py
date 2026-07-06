"""
Utilities Module for the Autonomous Business Document Agent.

This module provides common utilities used across the application:
1. Standard logging configuration with clean console formatting.
2. Custom structured exception classes for clean error handling.
3. An execution timer context manager to record total execution time.

Design Decisions:
- Context-based Timer: Using a context manager for timing ensures that execution
  duration is measured reliably even if exceptions are raised during execution.
- Domain-Specific Exceptions: Defining granular exceptions (e.g., LLMException, DocxException)
  allows the presentation layer (app.py) to catch errors precisely and return readable JSON error responses.
"""

import logging
import time
from contextlib import contextmanager
from typing import Generator, TypedDict

from config import settings


# ==============================================================================
# Custom Exceptions System
# ==============================================================================
class AgentException(Exception):
    """Base exception for all errors within the Autonomous Document Agent."""

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class LLMException(AgentException):
    """Raised when there is an issue calling or parsing Gemini API responses."""


class PlannerException(AgentException):
    """Raised when the planner agent fails to generate a valid structured plan."""


class ExecutorException(AgentException):
    """Raised when the executor fails during task processing or tool invocation."""


class ReflectionException(AgentException):
    """Raised when the reflection agent encounters errors during self-checking."""


class DocxException(AgentException):
    """Raised when there is an issue writing, styling, or saving the .docx document."""


# ==============================================================================
# Logging Configuration
# ==============================================================================
def setup_logging() -> logging.Logger:
    """
    Initializes and returns the application-wide logger.
    Configures log levels and formatting according to the settings module.
    """
    logger = logging.getLogger("document_agent")

    # If logger is already configured, return it to prevent duplicate handler output
    if logger.handlers:
        return logger

    # Resolve log level string from settings to standard logging constant
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # Format: [TIMESTAMP] [LEVEL] [FILENAME:LINE] message
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# Instantiate a singleton logger for direct imports
logger = setup_logging()


# ==============================================================================
# Execution Timer Context Manager
# ==============================================================================
class TimerData(TypedDict):
    duration: float


@contextmanager
def execution_timer() -> Generator[TimerData, None, None]:
    """
    A context manager that measures elapsed wall-clock time in seconds.

    Usage:
        with execution_timer() as timer:
            # perform tasks
        print(f"Elapsed: {timer['duration']}s")
    """
    data: TimerData = {"duration": 0.0}
    start_time = time.perf_counter()
    try:
        yield data
    finally:
        data["duration"] = time.perf_counter() - start_time
