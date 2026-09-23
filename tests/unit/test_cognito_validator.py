"""TDD: Cognito JWT validation -- signature (JWKS), issuer, client, expiry.

CLAUDE.md Phase 3 query flow: "Fetches JWKS from Cognito endpoint. Validates
signature, expiry, and scope. Rejects if invalid." Cognito access tokens
carry `client_id` and `token_use`, not the standard `aud` claim an ID token
would have -- this is Cognito-specific and worth pinning down explicitly.
"""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server.auth.cognito_validator import TokenValidationError, validate_token

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TestPool"
CLIENT_ID = "test-client-id-123"


@pytest.fixture
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _make_token(private_key, **claim_overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "scope": "finrag/invoke",
        "iat": now,
        "exp": now + 3600,
        **claim_overrides,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-kid"})


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


def _fake_jwks_client(public_key):
    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _FakeSigningKey(public_key)

    return _Client()


def test_valid_token_returns_claims(keypair):
    private_key, public_key = keypair
    token = _make_token(private_key)

    claims = validate_token(
        token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER, client_id=CLIENT_ID
    )

    assert claims["client_id"] == CLIENT_ID


def test_expired_token_rejected(keypair):
    private_key, public_key = keypair
    now = int(time.time())
    token = _make_token(private_key, iat=now - 7200, exp=now - 3600)

    with pytest.raises(TokenValidationError):
        validate_token(
            token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER, client_id=CLIENT_ID
        )


def test_wrong_issuer_rejected(keypair):
    private_key, public_key = keypair
    token = _make_token(private_key, iss="https://evil.example.com/fake-pool")

    with pytest.raises(TokenValidationError):
        validate_token(
            token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER, client_id=CLIENT_ID
        )


def test_wrong_client_id_rejected(keypair):
    """A token legitimately issued by OUR Cognito pool but for a DIFFERENT
    app client must not be accepted -- otherwise any app registered in the
    same user pool could call this server."""
    private_key, public_key = keypair
    token = _make_token(private_key, client_id="some-other-app-client")

    with pytest.raises(TokenValidationError):
        validate_token(
            token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER, client_id=CLIENT_ID
        )


def test_non_access_token_rejected(keypair):
    """An ID token (identity claims, meant for the client app to read) must
    not be usable as an API bearer token -- only an access token authorizes
    calling this server."""
    private_key, public_key = keypair
    token = _make_token(private_key, token_use="id")

    with pytest.raises(TokenValidationError):
        validate_token(
            token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER, client_id=CLIENT_ID
        )


def test_missing_required_scope_rejected(keypair):
    private_key, public_key = keypair
    token = _make_token(private_key, scope="some/other-scope")

    with pytest.raises(TokenValidationError):
        validate_token(
            token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER,
            client_id=CLIENT_ID, required_scope="finrag/invoke",
        )


def test_required_scope_present_among_several_is_accepted(keypair):
    private_key, public_key = keypair
    token = _make_token(private_key, scope="openid finrag/invoke profile")

    claims = validate_token(
        token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER,
        client_id=CLIENT_ID, required_scope="finrag/invoke",
    )

    assert claims["client_id"] == CLIENT_ID


def test_tampered_signature_rejected(keypair):
    _, public_key = keypair
    wrong_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _make_token(wrong_private_key)  # signed with the WRONG key

    with pytest.raises(TokenValidationError):
        validate_token(
            token, jwks_client=_fake_jwks_client(public_key), issuer=ISSUER, client_id=CLIENT_ID
        )
