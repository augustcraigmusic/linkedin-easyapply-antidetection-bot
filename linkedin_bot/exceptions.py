"""Custom exception hierarchy for the LinkedIn Auto-Apply Bot.

Provides granular error types for browser, AI, database, and
application-level failures. Replaces generic Exception catches.
"""

from enum import StrEnum


class ErrorSeverity(StrEnum):
    """Severity levels for bot errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BotError(Exception):
    """Base exception for all bot-related errors.

    Args:
        message: Human-readable error description.
        severity: Error severity level.
    """

    def __init__(self, message: str, severity: ErrorSeverity = ErrorSeverity.MEDIUM) -> None:
        self.severity = severity
        super().__init__(message)


class BrowserError(BotError):
    """Errors related to Playwright browser operations."""


class BrowserDeadError(BrowserError):
    """Browser process has unexpectedly closed."""

    def __init__(self, message: str = "Browser process closed") -> None:
        super().__init__(message, severity=ErrorSeverity.CRITICAL)


class NavigationError(BrowserError):
    """Failed to navigate to a URL."""


class StealthError(BrowserError):
    """Failed to inject stealth scripts."""


class AIError(BotError):
    """Errors related to AI engine operations."""


class AICircuitOpenError(AIError):
    """Circuit breaker is open — AI calls are blocked."""

    def __init__(self) -> None:
        super().__init__("Circuit breaker is OPEN, call rejected", ErrorSeverity.HIGH)


class AIResponseParseError(AIError):
    """Failed to parse AI response."""


class AuthError(BotError):
    """Errors related to LinkedIn authentication."""


class LoginFailedError(AuthError):
    """Login attempt failed."""


class SecurityChallengeError(AuthError):
    """CAPTCHA or 2FA challenge detected."""


class FormError(BotError):
    """Errors related to form filling and submission."""


class FormFieldError(FormError):
    """Failed to fill a specific form field."""


class FormNavigationError(FormError):
    """Failed to navigate between form steps."""


class FormSubmissionError(FormError):
    """Failed to submit the application form."""


class DataError(BotError):
    """Errors related to data extraction and validation."""


class JobExtractionError(DataError):
    """Failed to extract job listing data."""


class InvalidJobIdError(DataError):
    """Job ID is missing or invalid."""


class ConfigError(BotError):
    """Errors related to configuration loading and validation."""
