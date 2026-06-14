class LlmError(Exception):
    """Raised when the LLM backend cannot answer"""


class InvalidTokenError(Exception):
    """Raised when a user JWT fails verification: missing, malformed, expired,
    bad signature, or wrong issuer/audience."""


class UpstreamError(Exception):
    """Raised when a downstream service (auth or gateway) fails or is
    unreachable. The clients map httpx errors onto this so the domain/service
    layer never sees an httpx exception — same single-adapter rule the LLM and
    JWT clients follow."""