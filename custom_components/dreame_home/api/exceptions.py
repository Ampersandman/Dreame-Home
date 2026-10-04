"""Errors deliberately omit account credentials and raw server messages."""


class DreameError(Exception):
    """Base API error."""


class AuthenticationError(DreameError):
    """Credentials or session are invalid; reauthentication is required."""


class TransportError(DreameError):
    """The verified HTTPS request failed."""


class RateLimitError(DreameError):
    def __init__(self, retry_after: str | None = None):
        super().__init__("Dreame cloud rate limit reached")
        self.retry_after = retry_after


class ApiError(DreameError):
    def __init__(self, *, status: int = 200, code=None):
        super().__init__(f"Dreame API failed (HTTP {status}, code {code})")
        self.status = status
        self.code = code


class IncompleteDiscoveryError(DreameError):
    def __init__(self, returned: int, expected: int):
        super().__init__(f"Device list is incomplete: received {returned} of {expected}; pagination needs verification")
        self.returned = returned
        self.expected = expected


class SchemaRequiredError(DreameError):
    """No verified property schema exists for this device model."""
