"""Tests for the federated auth hardening.

Covers the previously-untested module: audience/issuer binding on client JWTs,
forwarding-proof signing/verification, target-node binding (a proof for node A
must not verify at node B), replay prevention, and tamper detection.
"""
import sys
import time
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_config import SMCPConfig
from smcp_federated_auth import (
    FederatedAuthManager,
    create_test_jwt,
    FEDERATION_ISSUER,
    FEDERATION_AUDIENCE,
)

SECRET = "federation_shared_secret_for_tests_0001"


def _config():
    return SMCPConfig(
        node_id="node",
        jwt_secret=SECRET,
        secret_key="test_secret_key_for_session_negotiation_00",
        kdf_salt="test_kdf_salt_00",
    )


def _mgr(node_id="node_a"):
    return FederatedAuthManager(_config(), node_id)


def _jwt(**over):
    kw = dict(user="alice@corp", permissions=["task:*"],
              forwarding_allowed=["*"], secret=SECRET)
    kw.update(over)
    return create_test_jwt(**kw)


# --------------------------------------------------------------------------- #
# Client JWT validation
# --------------------------------------------------------------------------- #
def test_valid_client_jwt_accepted():
    payload = _mgr().validate_client_jwt(_jwt())
    assert payload["user"] == "alice@corp"


def test_jwt_wrong_audience_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"], "iss": FEDERATION_ISSUER,
         "aud": "some-other-service", "iat": time.time(), "exp": time.time() + 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_jwt_wrong_issuer_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"], "iss": "evil-issuer",
         "aud": FEDERATION_AUDIENCE, "iat": time.time(), "exp": time.time() + 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_jwt_missing_aud_iss_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"],
         "iat": time.time(), "exp": time.time() + 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_jwt_wrong_secret_rejected():
    bad = _jwt(secret="a_different_secret_a_compromised_node_has")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_expired_jwt_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"], "iss": FEDERATION_ISSUER,
         "aud": FEDERATION_AUDIENCE, "iat": time.time() - 120, "exp": time.time() - 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        _mgr().validate_client_jwt(bad)


# --------------------------------------------------------------------------- #
# Forwarding proofs
# --------------------------------------------------------------------------- #
def test_forwarding_proof_roundtrip():
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    # The intended target verifies it.
    receiver = FederatedAuthManager(_config(), "node_b")
    ok, out = receiver.verify_forwarding_proof(signed)
    assert ok and out.forwarded_to == "node_b"


def test_forwarding_proof_target_binding():
    # A proof minted for node_b must NOT verify at node_c (replay to a
    # different node), even though both share the secret.
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    wrong_target = FederatedAuthManager(_config(), "node_c")
    ok, out = wrong_target.verify_forwarding_proof(signed)
    assert not ok


def test_forwarding_proof_tamper_rejected():
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    signed["proof"]["forwarded_by"] = "attacker_node"  # tamper without re-signing
    receiver = FederatedAuthManager(_config(), "node_b")
    ok, _ = receiver.verify_forwarding_proof(signed)
    assert not ok


def test_forwarding_proof_replay_rejected():
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    receiver = FederatedAuthManager(_config(), "node_b")
    ok1, _ = receiver.verify_forwarding_proof(signed)
    ok2, _ = receiver.verify_forwarding_proof(signed)  # same nonce again
    assert ok1 and not ok2


# --------------------------------------------------------------------------- #
# RS256 verify-only posture
# --------------------------------------------------------------------------- #
def test_rs256_requires_public_key():
    cfg = _config()
    cfg.security.jwt_algorithm = "RS256"
    cfg.security.jwt_public_key_path = None
    with pytest.raises(ValueError):
        FederatedAuthManager(cfg, "node_a")
