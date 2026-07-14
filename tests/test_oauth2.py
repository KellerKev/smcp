"""End-to-end tests for the production (external-IdP) OAuth2 path.

A mock OIDC provider (local aiohttp server) issues RS256 tokens and serves a
JWKS, so the full flow — token fetch, JWKS lookup, signature + aud/iss/exp
verification, and key rotation — is exercised without any external service.
"""
import json
import sys
import time
from pathlib import Path

import jwt
import pytest
from aiohttp import web
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_config import SMCPConfig
from smcp_auth_enhanced import EnhancedSMCPSecurity

AUDIENCE = "smcp-api"
ISSUER = "https://mock-idp.local/"


def _new_key(kid):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return priv, jwk


class MockOIDC:
    """Minimal OIDC provider: /token (client_credentials) and /jwks."""

    def __init__(self):
        self.kid = "key-1"
        self.priv, self.jwk = _new_key(self.kid)
        self.base_url = None
        self._runner = None

    def mint(self, **overrides):
        now = int(time.time())
        payload = {
            "sub": "svc-client", "aud": AUDIENCE, "iss": ISSUER,
            "iat": now, "exp": now + 3600, "scope": "scp:read",
        }
        payload.update(overrides)
        return jwt.encode(payload, self.priv, algorithm="RS256", headers={"kid": self.kid})

    def rotate(self):
        self.kid = "key-2"
        self.priv, self.jwk = _new_key(self.kid)

    async def _token(self, request):
        return web.json_response({"access_token": self.mint(), "expires_in": 3600})

    async def _jwks(self, request):
        return web.json_response({"keys": [self.jwk]})

    async def start(self):
        app = web.Application()
        app.router.add_post("/token", self._token)
        app.router.add_get("/jwks", self._jwks)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        port = list(self._runner.addresses)[0][1]
        self.base_url = f"http://127.0.0.1:{port}"

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()


@pytest.fixture
async def oidc():
    server = MockOIDC()
    await server.start()
    yield server
    await server.stop()


def _config(oidc):
    cfg = SMCPConfig(mode="enterprise")
    cfg.oauth2.enabled = True
    cfg.oauth2.token_url = f"{oidc.base_url}/token"
    cfg.oauth2.jwks_url = f"{oidc.base_url}/jwks"
    cfg.oauth2.client_id = "svc-client"
    cfg.oauth2.client_secret = "shhh"
    cfg.oauth2.audience = AUDIENCE
    cfg.oauth2.issuer = ISSUER
    cfg.oauth2.allow_insecure = True  # loopback http mock IdP
    return cfg


async def _auth(cfg, credentials):
    sec = EnhancedSMCPSecurity(cfg)
    try:
        return await sec.authenticate(credentials)
    finally:
        await sec.close()


# --------------------------------------------------------------------------- #
async def test_valid_token_accepted(oidc):
    r = await _auth(_config(oidc), {"access_token": oidc.mint()})
    assert r.success, r.error


async def test_client_credentials_fetch_then_validate(oidc):
    # No access_token supplied -> fetch from /token, then validate via JWKS.
    r = await _auth(_config(oidc), {})
    assert r.success, r.error


async def test_wrong_audience_rejected(oidc):
    r = await _auth(_config(oidc), {"access_token": oidc.mint(aud="some-other-api")})
    assert not r.success


async def test_wrong_issuer_rejected(oidc):
    r = await _auth(_config(oidc), {"access_token": oidc.mint(iss="https://evil.example/")})
    assert not r.success


async def test_expired_token_rejected(oidc):
    r = await _auth(_config(oidc), {"access_token": oidc.mint(exp=int(time.time()) - 10)})
    assert not r.success


async def test_alg_none_token_rejected(oidc):
    forged = jwt.encode({"sub": "x", "aud": AUDIENCE, "iss": ISSUER,
                         "iat": int(time.time()), "exp": int(time.time()) + 60},
                        key=None, algorithm="none")
    r = await _auth(_config(oidc), {"access_token": forged})
    assert not r.success


async def test_hs256_confusion_rejected(oidc):
    # Attacker signs HS256 using the (public) JWKS material; RS256 pinning rejects it.
    forged = jwt.encode({"sub": "x", "aud": AUDIENCE, "iss": ISSUER,
                         "iat": int(time.time()), "exp": int(time.time()) + 60},
                        key="public-ish-secret", algorithm="HS256")
    r = await _auth(_config(oidc), {"access_token": forged})
    assert not r.success


async def test_key_rotation_refetches_jwks(oidc):
    cfg = _config(oidc)
    sec = EnhancedSMCPSecurity(cfg)
    try:
        # Prime the JWKS cache with key-1.
        assert (await sec.authenticate({"access_token": oidc.mint()})).success
        # IdP rotates its signing key; a token under the new kid must still verify
        # (validator force-refreshes the JWKS on unknown kid).
        oidc.rotate()
        r = await sec.authenticate({"access_token": oidc.mint()})
        assert r.success, r.error
    finally:
        await sec.close()


# --------------------------------------------------------------------------- #
# Config validation for the enterprise OAuth2 path
# --------------------------------------------------------------------------- #
def _base_valid():
    import secrets
    return SMCPConfig(mode="enterprise", api_key=secrets.token_urlsafe(32),
                      secret_key=secrets.token_urlsafe(32),
                      jwt_secret=secrets.token_urlsafe(32),
                      kdf_salt=secrets.token_urlsafe(16))


def test_validate_requires_audience_issuer_jwks():
    cfg = _base_valid()
    cfg.oauth2.enabled = True
    cfg.oauth2.token_url = "https://idp/token"
    issues = cfg.validate()
    assert any("jwks_url" in i for i in issues)
    assert any("audience" in i for i in issues)
    assert any("issuer" in i for i in issues)


def test_validate_rejects_plaintext_idp_to_remote():
    cfg = _base_valid()
    cfg.oauth2.enabled = True
    cfg.oauth2.jwks_url = "http://idp.example.com/jwks"
    cfg.oauth2.token_url = "http://idp.example.com/token"
    cfg.oauth2.audience = AUDIENCE
    cfg.oauth2.issuer = ISSUER
    issues = cfg.validate()
    assert any("jwks_url" in i and "plaintext" in i.lower() for i in issues)


def test_validate_accepts_full_https_oauth2():
    cfg = _base_valid()
    cfg.oauth2.enabled = True
    cfg.oauth2.jwks_url = "https://idp.example.com/jwks"
    cfg.oauth2.token_url = "https://idp.example.com/token"
    cfg.oauth2.audience = AUDIENCE
    cfg.oauth2.issuer = ISSUER
    assert cfg.validate() == []
