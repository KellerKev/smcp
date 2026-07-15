"""Tests for the remaining hardening fixes: server calculator divide-by-zero,
simple-auth constant-time key check, and the development-OAuth2 credential gate.
"""
import asyncio
import secrets
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_config import SMCPConfig
from smcp_server import SMCPServer
from smcp_auth_enhanced import EnhancedSMCPSecurity


def strong():
    return secrets.token_urlsafe(32)


def good_config(**over):
    kw = dict(api_key=strong(), secret_key=strong(), jwt_secret=strong(),
              kdf_salt=secrets.token_urlsafe(16))
    kw.update(over)
    return SMCPConfig(**kw)


# --------------------------------------------------------------------------- #
# Server calculator: divide by zero must raise, not silently return 0
# --------------------------------------------------------------------------- #
def test_divide_normal():
    s = SMCPServer(good_config(node_id="s"))
    assert s._calculator_handler("divide", 10, 2) == 5


def test_divide_by_zero_raises():
    s = SMCPServer(good_config(node_id="s"))
    with pytest.raises(ValueError):
        s._calculator_handler("divide", 1, 0)


# --------------------------------------------------------------------------- #
# Simple API-key auth (constant-time comparison still functions correctly)
# --------------------------------------------------------------------------- #
def test_simple_auth_accepts_correct_key():
    api = "cfg_" + strong()
    sec = EnhancedSMCPSecurity(good_config(mode="simple", api_key=api))
    r = asyncio.run(sec.authenticate({"api_key": api, "node_id": "n1"}))
    assert r.success and r.token


def test_simple_auth_rejects_wrong_key():
    api = "cfg_" + strong()
    sec = EnhancedSMCPSecurity(good_config(mode="simple", api_key=api))
    r = asyncio.run(sec.authenticate({"api_key": "wrong-key", "node_id": "n1"}))
    assert not r.success


def test_simple_auth_rejects_missing_key():
    api = "cfg_" + strong()
    sec = EnhancedSMCPSecurity(good_config(mode="simple", api_key=api))
    r = asyncio.run(sec.authenticate({"node_id": "n1"}))
    assert not r.success


# --------------------------------------------------------------------------- #
# Development OAuth2 must not mint a token for an unauthenticated client
# --------------------------------------------------------------------------- #
@pytest.fixture
def dev_sec(tmp_path, monkeypatch):
    # Dev mode generates an RSA keypair under ./dev_keys in the cwd; run in an
    # isolated tmp dir so the repo isn't polluted.
    monkeypatch.chdir(tmp_path)

    def _make(client_id=None, client_secret=None):
        cfg = good_config(mode="development")
        cfg.oauth2.enabled = True
        if client_id:
            cfg.oauth2.client_id = client_id
        if client_secret:
            cfg.oauth2.client_secret = client_secret
        return EnhancedSMCPSecurity(cfg)

    return _make


def test_dev_mint_without_credentials_rejected(dev_sec):
    sec = dev_sec(client_id="svc", client_secret="s3cr3t")
    # No client_id/secret supplied -> must NOT mint a token.
    r = asyncio.run(sec.authenticate({}))
    assert not r.success


def test_dev_mint_wrong_secret_rejected(dev_sec):
    sec = dev_sec(client_id="svc", client_secret="s3cr3t")
    r = asyncio.run(sec.authenticate({"client_id": "svc", "client_secret": "nope"}))
    assert not r.success


def test_dev_mint_with_correct_credentials_succeeds(dev_sec):
    sec = dev_sec(client_id="svc", client_secret="s3cr3t")
    r = asyncio.run(sec.authenticate({"client_id": "svc", "client_secret": "s3cr3t"}))
    assert r.success and r.token


def test_dev_mint_requires_configured_credentials(dev_sec):
    # If no client_id/secret is configured, dev mode must refuse to mint.
    sec = dev_sec()
    r = asyncio.run(sec.authenticate({"client_id": "anyone", "client_secret": "x"}))
    assert not r.success
