"""Enumerations for the LinkedIn Auto-Apply Bot.

Replaces magic strings with type-safe StrEnum values.
"""

from enum import StrEnum


class ApplicationStatus(StrEnum):
    """Status of a job application attempt."""

    APPLIED = "applied"
    DRY_RUN = "dry_run"
    SKIPPED = "skipped"
    ERROR = "error"


class CircuitState(StrEnum):
    """States for the Circuit Breaker pattern."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"
