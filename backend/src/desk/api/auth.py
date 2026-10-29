"""Clerk session token verification via JWKS (D16, D37).

The frontend sends Clerk's session token as `Authorization: Bearer <jwt>`. It is RS256-signed;
the public keys are at `<issuer>/.well-known/jwks.json` (no secret needed). Checked: signature,
`exp`/`nbf` (5 s leeway), `iss`, `azp` against the allowed origins when present, and
`sts != "pending"`. Roles are not in the token (public metadata is not a default claim); they
live in the `users` table.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import jwt

LEEWAY_SECONDS = 5


class AuthError(Exception):
    """Any verification failure. The message is safe to log; it never contains the token."""


@dataclass(frozen=True)
class Claims:
    sub: str  # Clerk user id
    sid: str | None


class ClerkVerifier:
    def __init__(
        self,
        issuer: str,
        authorized_parties: Iterable[str],
        jwks_client: jwt.PyJWKClient | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.authorized_parties = frozenset(authorized_parties)
        # PyJWKClient caches the key set and refetches when a token names an unknown `kid`.
        self.jwks = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json", cache_keys=True, lifespan=3600, timeout=10
        )

    def verify(self, token: str) -> Claims:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.PyJWKClientError as e:
            raise AuthError(f"signing key unavailable: {type(e).__name__}") from None
        except jwt.InvalidTokenError as e:
            raise AuthError(f"invalid token: {type(e).__name__}") from None
        azp = claims.get("azp")
        if azp and azp not in self.authorized_parties:
            raise AuthError("invalid token: azp")
        if claims.get("sts") == "pending":
            raise AuthError("invalid token: session pending")
        return Claims(sub=str(claims["sub"]), sid=claims.get("sid"))


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("missing bearer token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("missing bearer token")
    return token.strip()
