"""Cognito JWT validation: JWKS signature check, issuer, client, expiry.

Cognito access tokens carry `client_id` and `token_use`, not the standard
`aud` claim an ID token would have -- `jwt.decode` is told not to check
`aud` and this module checks `client_id`/`token_use` itself instead.
"""
from __future__ import annotations

from typing import Any

import jwt


class TokenValidationError(Exception):
    """Raised for any invalid, expired, or wrongly-scoped bearer token."""


def validate_token(token: str, jwks_client: Any, issuer: str, client_id: str) -> dict[str, Any]:
    """Validate a Cognito-issued access token and return its claims.

    Args:
        token: The raw bearer token from the Authorization header.
        jwks_client: A jwt.PyJWKClient (or anything with the same
            get_signing_key_from_jwt(token) -> object-with-.key interface).
        issuer: Expected `iss` claim, e.g.
            "https://cognito-idp.<region>.amazonaws.com/<user-pool-id>".
        client_id: Expected `client_id` claim -- the app client this server
            accepts tokens for. Required even though the token's signature
            already proves it came from our user pool: without it, any app
            registered in the same pool could call this server.

    Returns:
        The decoded token claims.

    Raises:
        TokenValidationError: Signature invalid, expired, wrong issuer,
            wrong client, or not an access token.
    """
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"], issuer=issuer,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as e:
        raise TokenValidationError(str(e)) from e

    if claims.get("token_use") != "access":
        raise TokenValidationError("Not an access token")
    if claims.get("client_id") != client_id:
        raise TokenValidationError("Token issued for a different app client")

    return claims
