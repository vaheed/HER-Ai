class ProviderError(Exception):
    """Base provider error type."""


class ProviderTimeoutError(ProviderError):
    """Raised when provider request times out."""


class ProviderRateLimitError(ProviderError):
    """Raised when provider returns rate limit status."""


class ProviderServerError(ProviderError):
    """Raised when provider returns server-side status."""


class ProviderAuthError(ProviderError):
    """Raised when provider credentials are missing or invalid."""
