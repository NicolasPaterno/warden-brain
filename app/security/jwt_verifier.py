import jwt
from jwt import PyJWKClient

from app.domain.errors import InvalidTokenError

_ALGORITHMS = ["RS256"]


class JwtVerifier:
    """Verifies user JWTs against auth's JWKS.

    This is the ONLY place PyJWT is imported. It maps PyJWT's exceptions onto the
    domain's InvalidTokenError, so the API layer depends on the domain, not on
    the library — the same single-adapter rule the LLM client follows.
    """

    def __init__(self, jwks_url: str, issuer: str, audience: str) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> dict:
        """Validate signature, issuer, audience and expiry; return the claims.

        Blocking: the first call (and cache refreshes) fetch the JWKS over HTTP,
        so callers in async code must run this off the event loop.

        Raises:
            InvalidTokenError: the token is malformed, expired, has a bad
                signature, or the wrong issuer/audience.
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc
